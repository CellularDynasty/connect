"""
ChatConsumer - one WebSocket per conversation.
Client -> server events (JSON):
  {"type":"send_message","body":"hi","reply_to": 12|null,"attachment_id": 3|null}
  {"type":"send_message","location":{"latitude": 28.6,"longitude": 77.2,"live_minutes": 15|null}}
  {"type":"location_update","message_id": 12,"latitude": 28.7,"longitude": 77.3}
  {"type":"location_update","message_id": 12,"stop": true}
  {"type":"typing","is_typing": true}
  {"type":"mark_read","message_id": 12}
  {"type":"edit_message","message_id": 12,"body":"..."}
  {"type":"delete_message","message_id": 12}
Server -> client events: chat_message, typing, presence, read_receipt,
message_edited, message_deleted, location_updated, error.
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
        # Privacy: users with show_online_status off always appear offline.
        visible_online = await self._show_online()
        await self.channel_layer.group_send(self.group, {"type": "presence.event",
            "user_id": self.user.id, "username": self.user.username, "is_online": visible_online})

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
            "location_update": self._handle_location_update,
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
        location = data.get("location")
        if not body and not attachment_id and not location:
            return await self._error("Empty message")
        msg = await self._create_message(body, data.get("reply_to"), attachment_id, location)
        if msg == "blocked":
            return await self._error("You can't message this user.")
        if msg == "bad_location":
            return await self._error("Invalid location")
        if msg is None:
            return await self._error("Attachment not found")
        await self.channel_layer.group_send(self.group, {"type": "chat.message", **msg})

    async def _handle_location_update(self, data):
        result = await self._update_location(data.get("message_id"), data.get("latitude"),
                                             data.get("longitude"), bool(data.get("stop")))
        if result is None:
            return await self._error("Live location update not allowed (not yours, or it has ended).")
        await self.channel_layer.group_send(self.group, {"type": "location.event", **result})

    async def _handle_typing(self, data):
        await self.channel_layer.group_send(self.group, {"type": "typing.event",
            "user_id": self.user.id, "username": self.user.username,
            "is_typing": bool(data.get("is_typing")), "sender_channel": self.channel_name})

    async def _handle_read(self, data):
        if data.get("message_id"):
            await self._mark_read(int(data["message_id"]))
            # Privacy: reads are still recorded (your own unread counts clear),
            # but no read receipt is broadcast if you turned receipts off.
            if await self._receipts_enabled():
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
    async def chat_message(self, event): await self.send(text_data=json.dumps({**event, "type": "chat_message"}))
    async def typing_event(self, event):
        if event.get("sender_channel") != self.channel_name:
            await self.send(text_data=json.dumps({**event, "type": "typing"}))
    async def presence_event(self, event): await self.send(text_data=json.dumps({**event, "type": "presence"}))
    async def receipt_event(self, event): await self.send(text_data=json.dumps({**event, "type": "read_receipt"}))
    async def location_event(self, event): await self.send(text_data=json.dumps({**event, "type": "location_updated"}))
    async def edited_event(self, event): await self.send(text_data=json.dumps({**event, "type": "message_edited"}))
    async def deleted_event(self, event): await self.send(text_data=json.dumps({**event, "type": "message_deleted"}))
    async def _error(self, msg): await self.send(text_data=json.dumps({"type": "error", "detail": msg}))

    # ---- DB (sync, wrapped) ----
    @database_sync_to_async
    def _is_member(self):
        from .models import Conversation
        return Conversation.objects.filter(id=self.conversation_id, memberships__user=self.user).exists()

    @database_sync_to_async
    def _set_presence(self, online):
        from accounts.models import UserProfile
        profile = UserProfile.objects.filter(user=self.user).first()
        if profile is None:
            return
        # Privacy: if the user hides their online status, the stored state
        # also stays offline, so the REST API never leaks it either.
        stored = online and profile.show_online_status
        UserProfile.objects.filter(user=self.user).update(is_online=stored, last_seen=timezone.now())

    @database_sync_to_async
    def _show_online(self):
        from accounts.models import UserProfile
        profile = UserProfile.objects.filter(user=self.user).first()
        return bool(profile and profile.show_online_status)

    @database_sync_to_async
    def _receipts_enabled(self):
        from accounts.models import UserProfile
        profile = UserProfile.objects.filter(user=self.user).first()
        return bool(profile is None or profile.send_read_receipts)

    @database_sync_to_async
    def _create_message(self, body, reply_to, attachment_id=None, location=None):
        from .models import Message, MessageRead, Attachment, Conversation
        from accounts.models import BlockedUser
        from django.db.models import Q
        from notifications.models import Notification
        # Location messages: validate coordinates (and live duration) here so
        # both transports enforce exactly the same rules.
        loc_kwargs = {}
        if location is not None:
            try:
                lat, lng = float(location.get("latitude")), float(location.get("longitude"))
            except (TypeError, ValueError, AttributeError):
                return "bad_location"
            if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
                return "bad_location"
            live_until = None
            minutes = location.get("live_minutes")
            if minutes:
                if int(minutes) not in (15, 60, 480):
                    return "bad_location"
                live_until = timezone.now() + timezone.timedelta(minutes=int(minutes))
            loc_kwargs = {"kind": "location", "latitude": lat, "longitude": lng,
                          "location_live_until": live_until}
        # Privacy: a block in either direction stops messages in a private
        # chat, even if the conversation was created before the block.
        conv = Conversation.objects.filter(id=self.conversation_id).first()
        if conv is not None and conv.type == "private":
            other = conv.members.exclude(id=self.user.id).first()
            if other is not None and BlockedUser.objects.filter(
                    Q(blocker=self.user, blocked=other) | Q(blocker=other, blocked=self.user)).exists():
                return "blocked"
        attachment = None
        if attachment_id:
            # Only the uploader can attach their own upload to a message
            attachment = Attachment.objects.filter(id=attachment_id, uploaded_by=self.user).first()
            if attachment is None:
                return None
        msg = Message.objects.create(conversation_id=self.conversation_id, sender=self.user,
                                     body=body, reply_to_id=reply_to, **loc_kwargs)
        attachments = []
        if attachment is not None:
            attachment.message = msg
            attachment.save(update_fields=["message"])
            attachments = [{"id": attachment.id, "file": f"/api/chat/attachments/{attachment.id}/download/",
                            "original_name": attachment.original_name or attachment.file.name.split("/")[-1],
                            "size_bytes": attachment.size_bytes, "is_image": attachment.is_image,
                            "is_audio": attachment.is_audio}]
        others = msg.conversation.members.exclude(id=self.user.id)
        MessageRead.objects.bulk_create([MessageRead(message=msg, user=u) for u in others], ignore_conflicts=True)
        note_text = body[:120] if body else (
            "📍 Shared a location" if loc_kwargs else
            (f"Shared a file: {attachments[0]['original_name']}" if attachments else ""))
        Notification.objects.bulk_create([Notification(recipient=u, actor=self.user,
            conversation_id_ref=self.conversation_id, message_id_ref=msg.id, text=note_text) for u in others])
        return {"message_id": msg.id, "conversation_id": self.conversation_id,
                "sender_id": self.user.id, "sender_username": self.user.username,
                "body": msg.body, "reply_to": reply_to, "attachments": attachments,
                "kind": msg.kind, "latitude": msg.latitude, "longitude": msg.longitude,
                "location_live_until": msg.location_live_until.isoformat() if msg.location_live_until else None,
                "created_at": msg.created_at.isoformat()}

    @database_sync_to_async
    def _update_location(self, message_id, lat, lng, stop=False):
        from .models import Message
        msg = Message.objects.filter(id=message_id, conversation_id=self.conversation_id,
                                     sender=self.user, kind="location").first()
        if msg is None:
            return None
        if stop:
            msg.location_live_until = timezone.now()
            msg.save(update_fields=["location_live_until"])
            return {"message_id": msg.id, "latitude": msg.latitude, "longitude": msg.longitude,
                    "location_live_until": msg.location_live_until.isoformat(), "stopped": True}
        if not msg.is_live_location:
            return None
        try:
            lat, lng = float(lat), float(lng)
        except (TypeError, ValueError):
            return None
        if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
            return None
        msg.latitude, msg.longitude = lat, lng
        msg.save(update_fields=["latitude", "longitude"])
        return {"message_id": msg.id, "latitude": lat, "longitude": lng,
                "location_live_until": msg.location_live_until.isoformat(), "stopped": False}

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
