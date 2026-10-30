"""
ChatConsumer - one WebSocket per conversation.
Client -> server events (JSON):
  {"type":"send_message","body":"hi","reply_to": 12|null,"attachment_id": 3|null}
  {"type":"typing","is_typing": true}
  {"type":"mark_read","message_id": 12}
  {"type":"edit_message","message_id": 12,"body":"..."}
  {"type":"delete_message","message_id": 12}
Server -> client events: chat_message, typing, presence, read_receipt,
message_edited, message_deleted, error.
"""
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        self.conversation_id = int(self.scope["url_route"]["kwargs"]["conversation_id"])
        self.group = f"chat_{self.conversation_id}"
        if not getattr(self.user, "is_authenticated", False) or not await self._is_member():
            await self.close(code=4003); return
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()
        await self._set_presence(True)
        await self.channel_layer.group_send(self.group, {"type": "presence.event",
            "user_id": self.user.id, "username": self.user.username, "is_online": True})

    async def disconnect(self, code):
        if getattr(self, "group", None):
            await self._set_presence(False)
            await self.channel_layer.group_send(self.group, {"type": "presence.event",
                "user_id": self.user.id, "username": getattr(self.user, "username", ""),
                "is_online": False})
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        try:
            data = json.loads(text_data or "{}")
        except json.JSONDecodeError:
            return await self._error("Invalid JSON")
        handler = {
            "send_message": self._handle_send,
            "typing": self._handle_typing,
            "mark_read": self._handle_read,
            "edit_message": self._handle_edit,
            "delete_message": self._handle_delete,
        }.get(data.get("type"))
        if handler:
            await handler(data)
        else:
            await self._error(f"Unknown event: {data.get('type')}")

    # ---- handlers ----
    async def _handle_send(self, data):
        body = (data.get("body") or "").strip()
        attachment_id = data.get("attachment_id")
        if not body and not attachment_id:
            return await self._error("Empty message")
        msg = await self._create_message(body, data.get("reply_to"), attachment_id)
        if msg is None:
            return await self._error("Attachment not found")
        await self.channel_layer.group_send(self.group, {"type": "chat.message", **msg})

    async def _handle_typing(self, data):
        await self.channel_layer.group_send(self.group, {"type": "typing.event",
            "user_id": self.user.id, "username": self.user.username,
            "is_typing": bool(data.get("is_typing")), "sender_channel": self.channel_name})

    async def _handle_read(self, data):
        if data.get("message_id"):
            await self._mark_read(int(data["message_id"]))
            await self.channel_layer.group_send(self.group, {"type": "receipt.event",
                "message_id": data["message_id"], "user_id": self.user.id, "status": "read"})

    async def _handle_edit(self, data):
        ok = await self._edit_message(int(data["message_id"]), data.get("body", ""))
        if ok:
            await self.channel_layer.group_send(self.group, {"type": "edited.event",
                "message_id": data["message_id"], "body": data.get("body", "")})

    async def _handle_delete(self, data):
        ok = await self._delete_message(int(data["message_id"]))
        if ok:
            await self.channel_layer.group_send(self.group, {"type": "deleted.event",
                "message_id": data["message_id"]})

    # ---- group dispatch (type dots become underscores) ----
    async def chat_message(self, event): await self.send(text_data=json.dumps({"type": "chat_message", **event}))
    async def typing_event(self, event):
        if event.get("sender_channel") != self.channel_name:
            await self.send(text_data=json.dumps({"type": "typing", **event}))
    async def presence_event(self, event): await self.send(text_data=json.dumps({"type": "presence", **event}))
    async def receipt_event(self, event): await self.send(text_data=json.dumps({"type": "read_receipt", **event}))
    async def edited_event(self, event): await self.send(text_data=json.dumps({"type": "message_edited", **event}))
    async def deleted_event(self, event): await self.send(text_data=json.dumps({"type": "message_deleted", **event}))
    async def _error(self, msg): await self.send(text_data=json.dumps({"type": "error", "detail": msg}))

    # ---- DB (sync, wrapped) ----
    @database_sync_to_async
    def _is_member(self):
        from .models import Conversation
        return Conversation.objects.filter(id=self.conversation_id, memberships__user=self.user).exists()

    @database_sync_to_async
    def _set_presence(self, online):
        from accounts.models import UserProfile
        UserProfile.objects.filter(user=self.user).update(is_online=online, last_seen=timezone.now())

    @database_sync_to_async
    def _create_message(self, body, reply_to, attachment_id=None):
        from .models import Message, MessageRead, Attachment
        from notifications.models import Notification
        attachment = None
        if attachment_id:
            # Only the uploader can attach their own upload to a message
            attachment = Attachment.objects.filter(id=attachment_id, uploaded_by=self.user).first()
            if attachment is None:
                return None
        msg = Message.objects.create(conversation_id=self.conversation_id, sender=self.user,
                                     body=body, reply_to_id=reply_to)
        attachments = []
        if attachment is not None:
            attachment.message = msg
            attachment.save(update_fields=["message"])
            attachments = [{"id": attachment.id, "file": attachment.file.url,
                            "original_name": attachment.original_name or attachment.file.name.split("/")[-1],
                            "size_bytes": attachment.size_bytes, "is_image": attachment.is_image}]
        others = msg.conversation.members.exclude(id=self.user.id)
        MessageRead.objects.bulk_create([MessageRead(message=msg, user=u) for u in others], ignore_conflicts=True)
        note_text = body[:120] if body else (f"Shared a file: {attachments[0]['original_name']}" if attachments else "")
        Notification.objects.bulk_create([Notification(recipient=u, actor=self.user,
            conversation_id_ref=self.conversation_id, message_id_ref=msg.id, text=note_text) for u in others])
        return {"message_id": msg.id, "conversation_id": self.conversation_id,
                "sender_id": self.user.id, "sender_username": self.user.username,
                "body": msg.body, "reply_to": reply_to, "attachments": attachments,
                "created_at": msg.created_at.isoformat()}

    @database_sync_to_async
    def _mark_read(self, message_id):
        from .models import MessageRead
        MessageRead.objects.filter(message_id=message_id).exclude(user=self.user).update(status="delivered")
        MessageRead.objects.update_or_create(message_id=message_id, user=self.user, defaults={"status": "read"})

    @database_sync_to_async
    def _edit_message(self, message_id, body):
        from .models import Message
        return Message.objects.filter(id=message_id, sender=self.user).update(body=body, is_edited=True) == 1

    @database_sync_to_async
    def _delete_message(self, message_id):
        from .models import Message
        return Message.objects.filter(id=message_id, sender=self.user).update(body="", is_deleted=True) == 1
