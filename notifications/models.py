from django.db import models
from django.conf import settings

class Notification(models.Model):
    class Type(models.TextChoices):
        MESSAGE = "message", "New message"
        MENTION = "mention", "Mention"
        GROUP_ADDED = "group_added", "Added to group"
        SYSTEM = "system", "System"
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="triggered_notifications")
    type = models.CharField(max_length=20, choices=Type.choices, default=Type.MESSAGE)
    conversation_id_ref = models.IntegerField(null=True, blank=True)
    message_id_ref = models.IntegerField(null=True, blank=True)
    text = models.CharField(max_length=300, blank=True)
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["recipient", "is_read", "-created_at"])]
