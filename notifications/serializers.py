from rest_framework import serializers
from .models import Notification
class NotificationSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(source="actor.username", read_only=True, default=None)
    class Meta:
        model = Notification
        fields = ["id", "type", "actor", "actor_username", "conversation_id_ref", "message_id_ref", "text", "is_read", "created_at"]
