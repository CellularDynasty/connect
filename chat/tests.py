from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient
from asgiref.sync import async_to_sync
from .models import Conversation, ConversationMember, Message, Attachment
from .consumers import ChatConsumer

User = get_user_model()

class ChatFlowTests(TestCase):
    def setUp(self):
        self.a = User.objects.create_user(username="aniket", email="a@test.com", password="testpass123")
        self.b = User.objects.create_user(username="priya", email="p@test.com", password="testpass123")
        self.client = APIClient()
        self.client.force_authenticate(self.a)

    def test_profile_auto_created(self):
        self.assertTrue(hasattr(self.a, "profile"))

    def test_private_conversation_dedup(self):
        r1 = self.client.post("/api/chat/conversations/", {"type": "private", "member_ids": [self.b.id]}, format="json")
        r2 = self.client.post("/api/chat/conversations/", {"type": "private", "member_ids": [self.b.id]}, format="json")
        self.assertEqual(r1.data["id"], r2.data["id"])
        self.assertEqual(Conversation.objects.count(), 1)

    def test_message_and_search(self):
        conv = Conversation.objects.create(type="private", created_by=self.a)
        ConversationMember.objects.bulk_create([
            ConversationMember(conversation=conv, user=self.a),
            ConversationMember(conversation=conv, user=self.b)])
        Message.objects.create(conversation=conv, sender=self.a, body="hello websocket")
        r = self.client.get(f"/api/chat/messages/?conversation={conv.id}&q=websocket")
        results = r.data.get("results", r.data)
        self.assertEqual(len(results), 1)

    def _make_conv(self):
        conv = Conversation.objects.create(type="private", created_by=self.a)
        ConversationMember.objects.bulk_create([
            ConversationMember(conversation=conv, user=self.a),
            ConversationMember(conversation=conv, user=self.b)])
        return conv

    def test_clear_chat_hides_history_for_that_user_only(self):
        conv = self._make_conv()
        Message.objects.create(conversation=conv, sender=self.b, body="old message")
        r = self.client.post(f"/api/chat/conversations/{conv.id}/clear/")
        self.assertEqual(r.status_code, 200)
        mine = self.client.get(f"/api/chat/messages/?conversation={conv.id}")
        self.assertEqual(len(mine.data.get("results", mine.data)), 0)
        other = APIClient(); other.force_authenticate(self.b)
        theirs = other.get(f"/api/chat/messages/?conversation={conv.id}")
        self.assertEqual(len(theirs.data.get("results", theirs.data)), 1)

    def test_ws_message_links_attachment(self):
        conv = self._make_conv()
        att = Attachment.objects.create(uploaded_by=self.a,
            file=SimpleUploadedFile("hello.pdf", b"%PDF-1.4 test", content_type="application/pdf"),
            original_name="hello.pdf", size_bytes=13)
        consumer = ChatConsumer(); consumer.user = self.a; consumer.conversation_id = conv.id
        payload = async_to_sync(consumer._create_message)("", None, att.id)
        self.assertIsNotNone(payload)
        att.refresh_from_db()
        self.assertIsNotNone(att.message)
        self.assertEqual(payload["attachments"][0]["original_name"], "hello.pdf")

    def test_cannot_attach_someone_elses_upload(self):
        conv = self._make_conv()
        att = Attachment.objects.create(uploaded_by=self.b,
            file=SimpleUploadedFile("x.pdf", b"data"), original_name="x.pdf", size_bytes=4)
        consumer = ChatConsumer(); consumer.user = self.a; consumer.conversation_id = conv.id
        self.assertIsNone(async_to_sync(consumer._create_message)("", None, att.id))

    def test_react_edit_delete(self):
        conv = self._make_conv()
        msg = Message.objects.create(conversation=conv, sender=self.a, body="hi 👍")
        r = self.client.post(f"/api/chat/messages/{msg.id}/react/", {"emoji": "❤️"}, format="json")
        self.assertTrue(r.data["reacted"])
        r = self.client.patch(f"/api/chat/messages/{msg.id}/", {"body": "edited"}, format="json")
        self.assertEqual(r.data["body"], "edited"); self.assertTrue(r.data["is_edited"])
        r = self.client.delete(f"/api/chat/messages/{msg.id}/")
        self.assertTrue(r.data["is_deleted"])

    def test_register_hashes_password(self):
        r = APIClient().post("/api/auth/register/", {"username": "new", "email": "n@test.com", "password": "secretpass1"}, format="json")
        self.assertEqual(r.status_code, 201)
        u = User.objects.get(username="new")
        self.assertNotEqual(u.password, "secretpass1")
        self.assertTrue(u.check_password("secretpass1"))
