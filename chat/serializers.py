from rest_framework import serializers
from .models import Conversation, ConversationMember, Message, Attachment, MessageRead, MessageReaction

class AttachmentSerializer(serializers.ModelSerializer):
    is_image = serializers.ReadOnlyField()
    class Meta:
        model = Attachment
        fields = ["id", "file", "original_name", "size_bytes", "is_image", "created_at"]

class ReactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = MessageReaction
        fields = ["id", "user", "emoji", "created_at"]

class MessageSerializer(serializers.ModelSerializer):
    attachments = AttachmentSerializer(many=True, read_only=True)
    reactions = ReactionSerializer(many=True, read_only=True)
    sender_username = serializers.CharField(source="sender.username", read_only=True)
    class Meta:
        model = Message
        fields = ["id", "conversation", "sender", "sender_username", "body", "reply_to",
                  "is_edited", "is_deleted", "attachments", "reactions", "created_at", "updated_at"]
        read_only_fields = ["sender", "is_edited", "is_deleted", "created_at", "updated_at"]

class MemberSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    class Meta:
        model = ConversationMember
        fields = ["id", "user", "username", "role", "joined_at", "is_muted"]

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
