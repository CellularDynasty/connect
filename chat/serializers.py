from rest_framework import serializers
from .models import Conversation, ConversationMember, Message, Attachment, MessageRead, MessageReaction

def attachment_download_path(att):
    """App-served download URL for an attachment (see AttachmentDownloadView).
    Used everywhere a file link is produced, so no public /media/ URL is
    ever handed out."""
    return f"/api/chat/attachments/{att.id}/download/"


class AttachmentSerializer(serializers.ModelSerializer):
    is_image = serializers.ReadOnlyField()
    is_audio = serializers.ReadOnlyField()
    file = serializers.SerializerMethodField()
    class Meta:
        model = Attachment
        fields = ["id", "file", "original_name", "size_bytes", "is_image", "is_audio", "created_at"]
    def get_file(self, obj):
        return attachment_download_path(obj)

class ReactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = MessageReaction
        fields = ["id", "user", "emoji", "created_at"]

class MessageSerializer(serializers.ModelSerializer):
    attachments = AttachmentSerializer(many=True, read_only=True)
    reactions = ReactionSerializer(many=True, read_only=True)
    sender_username = serializers.CharField(source="sender.username", read_only=True)
    is_live_location = serializers.ReadOnlyField()
    class Meta:
        model = Message
        fields = ["id", "conversation", "sender", "sender_username", "body", "reply_to",
                  "kind", "latitude", "longitude", "location_live_until", "is_live_location",
                  "is_edited", "is_deleted", "attachments", "reactions", "created_at", "updated_at"]
        read_only_fields = ["sender", "is_edited", "is_deleted", "created_at", "updated_at",
                            "kind", "location_live_until"]

class MemberSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    avatar = serializers.SerializerMethodField()
    is_online = serializers.SerializerMethodField()
    class Meta:
        model = ConversationMember
        fields = ["id", "user", "username", "avatar", "role", "joined_at", "is_muted", "is_online"]
    def get_is_online(self, obj):
        profile = getattr(obj.user, "profile", None)
        if profile is None:
            return False
        request = self.context.get("request")
        viewer = getattr(request, "user", None) if request is not None else None
        if viewer == obj.user or profile.show_online_status:
            return bool(profile.is_online)
        return False
    def get_avatar(self, obj):
        profile = getattr(obj.user, "profile", None)
        if profile is not None and profile.avatar:
            return f"/api/auth/users/{obj.user_id}/avatar/"
        return None

class ConversationSerializer(serializers.ModelSerializer):
    memberships = MemberSerializer(many=True, read_only=True)
    unread_count = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    class Meta:
        model = Conversation
        fields = ["id", "type", "title", "description", "avatar", "created_by",
                  "memberships", "unread_count", "last_message", "created_at", "updated_at"]
    def _visible_messages(self, obj):
        """Messages visible to the requesting user (respects their per-user clear)."""
        user = self.context["request"].user
        qs = obj.messages.all()
        membership = obj.memberships.filter(user=user).first()
        if membership and membership.cleared_at:
            qs = qs.filter(created_at__gt=membership.cleared_at)
        return qs
    def get_unread_count(self, obj):
        user = self.context["request"].user
        read_ids = MessageRead.objects.filter(user=user, status="read", message__conversation=obj).values_list("message_id", flat=True)
        return self._visible_messages(obj).exclude(sender=user).exclude(id__in=read_ids).count()
    def get_last_message(self, obj):
        m = self._visible_messages(obj).order_by("-created_at").first()
        return MessageSerializer(m).data if m else None

class ReceiptSerializer(serializers.ModelSerializer):
    class Meta:
        model = MessageRead
        fields = ["id", "message", "user", "status", "timestamp"]
