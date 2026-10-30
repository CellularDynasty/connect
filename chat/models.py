from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
import os

User = settings.AUTH_USER_MODEL


class Conversation(models.Model):
    class Type(models.TextChoices):
        PRIVATE = "private", "Private"
        GROUP = "group", "Group"
    type = models.CharField(max_length=10, choices=Type.choices, db_index=True)
    title = models.CharField(max_length=200, blank=True)                 # group name; empty for private
    description = models.TextField(blank=True)                            # group description
    avatar = models.ImageField(upload_to="groups/", blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="created_conversations")
    members = models.ManyToManyField(User, through="ConversationMember", related_name="conversations")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.title or f"{self.type} conversation #{self.pk}"


class ConversationMember(models.Model):
    """Through model: carries role + per-user state (last_read, muted) for a conversation."""
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        MEMBER = "member", "Member"
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)
    joined_at = models.DateTimeField(auto_now_add=True)
    is_muted = models.BooleanField(default=False)
    cleared_at = models.DateTimeField(null=True, blank=True)  # per-user "clear chat": hide messages at/before this time for this user only

    class Meta:
        unique_together = ("conversation", "user")
        indexes = [models.Index(fields=["user", "conversation"])]


class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sent_messages")
    body = models.TextField(blank=True)
    reply_to = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="replies")
    is_edited = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)   # soft-delete so replies/receipts keep context
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["conversation", "created_at"])]

    def __str__(self):
        return f"Msg {self.pk} by {self.sender_id}: {self.body[:30]}"


def validate_attachment(file):
    from django.conf import settings as s
    ext = os.path.splitext(file.name)[1].lower()
    if ext not in s.ALLOWED_UPLOAD_EXTENSIONS:
        raise ValidationError(f"File type {ext} not allowed.")
    if file.size > s.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise ValidationError(f"File exceeds {s.MAX_UPLOAD_SIZE_MB} MB limit.")


class Attachment(models.Model):
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="attachments", null=True, blank=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to="attachments/%Y/%m/", validators=[validate_attachment])
    original_name = models.CharField(max_length=255, blank=True)
    size_bytes = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def is_image(self):
        return os.path.splitext(self.file.name)[1].lower() in {".jpg", ".jpeg", ".png", ".gif", ".webp"}


class MessageRead(models.Model):
    """One row per (message, user): gives delivered/read receipts without a JSON blob on Message."""
    class Status(models.TextChoices):
        DELIVERED = "delivered", "Delivered"
        READ = "read", "Read"
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="receipts")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="message_receipts")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DELIVERED)
    timestamp = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("message", "user")
        indexes = [models.Index(fields=["user", "status"])]


class MessageReaction(models.Model):
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="reactions")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="reactions")
    emoji = models.CharField(max_length=16)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("message", "user", "emoji")
