from django.db.models import Q, Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from accounts.models import BlockedUser
from notifications.models import Notification
from .models import Conversation, ConversationMember, Message, Attachment, MessageRead, MessageReaction
from .serializers import ConversationSerializer, MessageSerializer, AttachmentSerializer

def is_member(conv, user):
    return conv.memberships.filter(user=user).exists()

def is_admin(conv, user):
    return conv.memberships.filter(user=user, role="admin").exists()

class ConversationViewSet(viewsets.ModelViewSet):
    serializer_class = ConversationSerializer
    def get_queryset(self):
        return Conversation.objects.filter(memberships__user=self.request.user).distinct().prefetch_related("memberships__user", "messages")
    def create(self, request, *args, **kwargs):
        ctype = request.data.get("type", "private")
        member_ids = request.data.get("member_ids", [])
        if ctype == "private":
            if len(member_ids) != 1:
                return Response({"detail": "Private chat needs exactly one other user."}, status=400)
            other_id = member_ids[0]
            if BlockedUser.objects.filter(Q(blocker=request.user, blocked_id=other_id) | Q(blocker_id=other_id, blocked=request.user)).exists():
                return Response({"detail": "Cannot chat with a blocked user."}, status=403)
            # De-duplicate: reuse an existing private conversation between exactly this pair
            existing = None
            for conv in Conversation.objects.filter(type="private", memberships__user=request.user).prefetch_related("memberships"):
                if {m.user_id for m in conv.memberships.all()} == {request.user.id, int(other_id)}:
                    existing = conv; break
            if existing:
                return Response(self.get_serializer(existing).data)
            conv = Conversation.objects.create(type="private", created_by=request.user)
            ConversationMember.objects.bulk_create([
                ConversationMember(conversation=conv, user=request.user),
                ConversationMember(conversation=conv, user_id=other_id)])
        else:
            if not request.data.get("title"):
                return Response({"detail": "Group needs a title."}, status=400)
            conv = Conversation.objects.create(type="group", title=request.data["title"],
                description=request.data.get("description", ""), created_by=request.user)
            members = [ConversationMember(conversation=conv, user=request.user, role="admin")]
            members += [ConversationMember(conversation=conv, user_id=mid) for mid in member_ids if int(mid) != request.user.id]
            ConversationMember.objects.bulk_create(members)
        return Response(self.get_serializer(conv).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def add_member(self, request, pk=None):
        conv = self.get_object()
        if conv.type != "group" or not is_admin(conv, request.user):
            return Response({"detail": "Only group admins can add members."}, status=403)
        obj, created = ConversationMember.objects.get_or_create(conversation=conv, user_id=request.data.get("user_id"))
        return Response({"added": created})

    @action(detail=True, methods=["post"])
    def remove_member(self, request, pk=None):
        conv = self.get_object()
        if conv.type != "group" or not is_admin(conv, request.user):
            return Response({"detail": "Only group admins can remove members."}, status=403)
        ConversationMember.objects.filter(conversation=conv, user_id=request.data.get("user_id")).exclude(user=request.user).delete()
        return Response({"removed": True})

    @action(detail=True, methods=["post"])
    def leave(self, request, pk=None):
        ConversationMember.objects.filter(conversation=self.get_object(), user=request.user).delete()
        return Response(status=204)

    @action(detail=True, methods=["post"])
    def clear(self, request, pk=None):
        """Clear chat for the requesting user only (like WhatsApp's Clear Chat):
        older messages are hidden for them, the other members keep their history."""
        conv = self.get_object()
        ConversationMember.objects.filter(conversation=conv, user=request.user).update(cleared_at=timezone.now())
        return Response({"cleared": True})

class MessageViewSet(viewsets.ModelViewSet):
    serializer_class = MessageSerializer
    def get_queryset(self):
        conv_id = self.request.query_params.get("conversation")
        qs = Message.objects.filter(conversation__memberships__user=self.request.user).select_related("sender").prefetch_related("attachments", "reactions")
        if conv_id:
            qs = qs.filter(conversation_id=conv_id)
            membership = ConversationMember.objects.filter(conversation_id=conv_id, user=self.request.user).first()
            if membership and membership.cleared_at:
                qs = qs.filter(created_at__gt=membership.cleared_at)
        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(body__icontains=q)  # message search
        return qs.distinct()
    def perform_create(self, serializer):
        conv = serializer.validated_data["conversation"]
        if not is_member(conv, self.request.user):
            from rest_framework.exceptions import PermissionDenied; raise PermissionDenied("Not a member")
        msg = serializer.save(sender=self.request.user)
        # Link a previously-uploaded attachment, if one was passed
        attachment_id = self.request.data.get("attachment_id")
        if attachment_id:
            Attachment.objects.filter(id=attachment_id, uploaded_by=self.request.user).update(message=msg)
        # Delivered receipts + notifications for everyone else
        others = conv.members.exclude(id=self.request.user.id)
        MessageRead.objects.bulk_create([MessageRead(message=msg, user=u) for u in others], ignore_conflicts=True)
        Notification.objects.bulk_create([Notification(recipient=u, actor=self.request.user,
            conversation_id_ref=conv.id, message_id_ref=msg.id, text=msg.body[:120]) for u in others if not conv.memberships.filter(user=u, is_muted=True).exists()])
    def update(self, request, *args, **kwargs):
        msg = self.get_object()
        if msg.sender != request.user:
            return Response({"detail": "You can only edit your own messages."}, status=403)
        msg.body = request.data.get("body", msg.body); msg.is_edited = True; msg.save()
        return Response(self.get_serializer(msg).data)
    def destroy(self, request, *args, **kwargs):
        msg = self.get_object()
        if msg.sender != request.user:
            return Response({"detail": "You can only delete your own messages."}, status=403)
        msg.body = ""; msg.is_deleted = True; msg.save()  # soft delete
        return Response(self.get_serializer(msg).data)

    @action(detail=True, methods=["post"])
    def mark_read(self, request, pk=None):
        msg = self.get_object()
        MessageRead.objects.update_or_create(message=msg, user=request.user, defaults={"status": "read"})
        return Response({"status": "read"})

    @action(detail=False, methods=["post"])
    def mark_conversation_read(self, request):
        conv = get_object_or_404(Conversation, pk=request.data.get("conversation"))
        if not is_member(conv, request.user):
            return Response(status=403)
        for m in conv.messages.exclude(sender=request.user):
            MessageRead.objects.update_or_create(message=m, user=request.user, defaults={"status": "read"})
        return Response({"status": "all read"})

    @action(detail=True, methods=["post"])
    def react(self, request, pk=None):
        msg = self.get_object(); emoji = request.data.get("emoji", "👍")
        obj, created = MessageReaction.objects.get_or_create(message=msg, user=request.user, emoji=emoji)
        if not created:
            obj.delete(); return Response({"reacted": False})
        return Response({"reacted": True})

class AttachmentUploadView(viewsets.ViewSet):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [permissions.IsAuthenticated]
    def create(self, request):
        f = request.FILES.get("file")
        if not f:
            return Response({"detail": "No file"}, status=400)
        att = Attachment(uploaded_by=request.user, file=f, original_name=f.name, size_bytes=f.size)
        att.full_clean()  # runs validate_attachment: type + size
        att.save()
        if request.data.get("message_id"):
            att.message_id = request.data["message_id"]; att.save()
        return Response(AttachmentSerializer(att).data, status=201)
