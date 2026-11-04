from django.db.models import Q, Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.views import APIView
from accounts.models import BlockedUser
from notifications.models import Notification
from .models import Conversation, ConversationMember, Message, Attachment, MessageRead, MessageReaction
from .serializers import ConversationSerializer, MessageSerializer, AttachmentSerializer

def is_member(conv, user):
    return conv.memberships.filter(user=user).exists()

def has_block_between(user_a, user_b):
    """Privacy: a block in EITHER direction stops new chats/messages."""
    return BlockedUser.objects.filter(
        Q(blocker=user_a, blocked=user_b) | Q(blocker=user_b, blocked=user_a)).exists()

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
            for mid in member_ids:
                if int(mid) != request.user.id and has_block_between(request.user.id, int(mid)):
                    return Response({"detail": "Cannot add a user where a block exists."}, status=403)
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
        if has_block_between(request.user.id, int(request.data.get("user_id"))):
            return Response({"detail": "Cannot add a user where a block exists."}, status=403)
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
    def mute(self, request, pk=None):
        """Toggle/set mute for the requesting user's OWN membership only.
        Muted members are already excluded from notifications in
        MessageViewSet.perform_create."""
        conv = self.get_object()
        membership = conv.memberships.filter(user=request.user).first()
        if membership is None:
            return Response({"detail": "Not a member."}, status=403)
        if "muted" in request.data:
            membership.is_muted = bool(request.data.get("muted"))
        else:
            membership.is_muted = not membership.is_muted
        membership.save(update_fields=["is_muted"])
        return Response({"is_muted": membership.is_muted})

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
    # Live location durations the client may request (minutes)
    LIVE_MINUTES = (15, 60, 480)

    def _parse_location(self):
        """Validate location fields from the request. Returns a dict of
        Message kwargs, {} for a normal message, or raises ValidationError."""
        from rest_framework.exceptions import ValidationError
        lat, lng = self.request.data.get("latitude"), self.request.data.get("longitude")
        if lat is None and lng is None:
            return {}
        try:
            lat, lng = float(lat), float(lng)
        except (TypeError, ValueError):
            raise ValidationError("latitude/longitude must be numbers.")
        if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
            raise ValidationError("latitude must be -90..90 and longitude -180..180.")
        live_until = None
        minutes = self.request.data.get("live_minutes")
        if minutes:
            if int(minutes) not in self.LIVE_MINUTES:
                raise ValidationError(f"live_minutes must be one of {self.LIVE_MINUTES}.")
            live_until = timezone.now() + timezone.timedelta(minutes=int(minutes))
        return {"kind": "location", "latitude": lat, "longitude": lng,
                "location_live_until": live_until}

    def perform_create(self, serializer):
        conv = serializer.validated_data["conversation"]
        if not is_member(conv, self.request.user):
            from rest_framework.exceptions import PermissionDenied; raise PermissionDenied("Not a member")
        # Privacy: in a private chat, a block in either direction stops new
        # messages too - blocking after a chat exists must still protect you.
        if conv.type == "private":
            other = conv.members.exclude(id=self.request.user.id).first()
            if other is not None and has_block_between(self.request.user.id, other.id):
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied("You can't message this user.")
        msg = serializer.save(sender=self.request.user, **self._parse_location())
        # Link a previously-uploaded attachment, if one was passed
        attachment_id = self.request.data.get("attachment_id")
        if attachment_id:
            Attachment.objects.filter(id=attachment_id, uploaded_by=self.request.user).update(message=msg)
        # Delivered receipts + notifications for everyone else
        others = conv.members.exclude(id=self.request.user.id)
        MessageRead.objects.bulk_create([MessageRead(message=msg, user=u) for u in others], ignore_conflicts=True)
        note_text = msg.body[:120] or ("📍 Shared a location" if msg.kind == "location" else "")
        Notification.objects.bulk_create([Notification(recipient=u, actor=self.request.user,
            conversation_id_ref=conv.id, message_id_ref=msg.id, text=note_text) for u in others if not conv.memberships.filter(user=u, is_muted=True).exists()])

    @action(detail=True, methods=["post"])
    def location(self, request, pk=None):
        """POST /api/chat/messages/<id>/location/ {latitude, longitude} or {stop: true}
        Updates a LIVE location message in place (REST twin of the WebSocket
        location_update event). Only the sender, and only until it expires."""
        msg = self.get_object()
        if msg.sender != request.user or msg.kind != "location":
            return Response({"detail": "Only the sender can update their location message."}, status=403)
        if request.data.get("stop"):
            msg.location_live_until = timezone.now()
            msg.save(update_fields=["location_live_until"])
            return Response(self.get_serializer(msg).data)
        if not msg.is_live_location:
            return Response({"detail": "This live location has ended."}, status=400)
        try:
            lat, lng = float(request.data.get("latitude")), float(request.data.get("longitude"))
        except (TypeError, ValueError):
            return Response({"detail": "latitude/longitude must be numbers."}, status=400)
        if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
            return Response({"detail": "latitude/longitude out of range."}, status=400)
        msg.latitude, msg.longitude = lat, lng
        msg.save(update_fields=["latitude", "longitude"])
        return Response(self.get_serializer(msg).data)
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
        try:
            att.full_clean()  # runs validate_attachment: type + size
        except Exception as exc:
            # A rejected file (bad type / too big) is a client error, not a
            # server crash - without this catch the upload died with a 500
            # HTML page and the browser showed a broken/blank failure.
            messages = getattr(exc, "messages", None) or [str(exc)]
            return Response({"detail": " ".join(messages)}, status=400)
        att.save()
        if request.data.get("message_id"):
            att.message_id = request.data["message_id"]; att.save()
        return Response(AttachmentSerializer(att).data, status=201)


class AttachmentDownloadView(APIView):
    """Authenticated file download: GET /api/chat/attachments/<id>/download/

    Files are served by the app itself instead of a public /media/ URL:
    1) it works in production, where DEBUG=False means Django does not
       serve /media/ at all (the old setup uploaded fine but every
       download/preview was a 404 on Render), and
    2) it is private - only the uploader, or a member of the conversation
       the file was sent in, can download it.
    The browser loads these URLs in <img>/<a> tags, which cannot send an
    Authorization header, so a JWT may also be passed as ?token=<access>,
    the same pattern the WebSocket uses."""
    permission_classes = [permissions.AllowAny]  # auth is checked manually (header OR ?token=)

    def _user_from_token(self, request):
        from django.contrib.auth import get_user_model
        from rest_framework_simplejwt.tokens import AccessToken
        from rest_framework_simplejwt.exceptions import TokenError
        token = request.query_params.get("token")
        if not token:
            return None
        try:
            return get_user_model().objects.get(id=AccessToken(token)["user_id"])
        except Exception:
            return None

    def get(self, request, pk=None):
        from django.http import FileResponse, Http404
        user = request.user if getattr(request, "user", None) and request.user.is_authenticated \
            else self._user_from_token(request)
        if user is None:
            return Response({"detail": "Authentication required."}, status=401)
        att = Attachment.objects.filter(id=pk).select_related("message__conversation").first()
        if att is None:
            raise Http404
        allowed = att.uploaded_by_id == user.id or (
            att.message_id and att.message.conversation.memberships.filter(user=user).exists())
        if not allowed:
            return Response({"detail": "You do not have access to this file."}, status=403)
        try:
            handle = att.file.open("rb")
        except FileNotFoundError:
            raise Http404
        response = FileResponse(handle, as_attachment=not att.is_image,
                                filename=att.original_name or att.file.name.split("/")[-1])
        return response
