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


class FileTransferTests(TestCase):
    """The full file flow the way the browser does it:
    upload -> send in a message -> the other side sees it -> downloads it."""

    def setUp(self):
        self.a = User.objects.create_user(username="sender", email="s@test.com", password="testpass123")
        self.b = User.objects.create_user(username="receiver", email="r@test.com", password="testpass123")
        self.outsider = User.objects.create_user(username="outsider", email="o@test.com", password="testpass123")
        self.client = APIClient(); self.client.force_authenticate(self.a)
        conv = Conversation.objects.create(type="private", created_by=self.a)
        ConversationMember.objects.bulk_create([
            ConversationMember(conversation=conv, user=self.a),
            ConversationMember(conversation=conv, user=self.b)])
        self.conv = conv

    def _upload(self, client, name="notes.pdf", content=b"%PDF-1.4 hello"):
        return client.post("/api/chat/attachments/",
                           {"file": SimpleUploadedFile(name, content)}, format="multipart")

    def test_upload_send_receive_download(self):
        r = self._upload(self.client)
        self.assertEqual(r.status_code, 201, r.data)
        att_id = r.data["id"]
        # the API hands out an app download URL, never a public /media/ URL
        self.assertEqual(r.data["file"], f"/api/chat/attachments/{att_id}/download/")
        # send it (REST path - the browser's fallback when the socket is down)
        r = self.client.post("/api/chat/messages/",
                             {"conversation": self.conv.id, "body": "", "attachment_id": att_id},
                             format="json")
        self.assertEqual(r.status_code, 201, r.data)
        # the RECEIVER sees the attachment in the message list
        other = APIClient(); other.force_authenticate(self.b)
        r = other.get(f"/api/chat/messages/?conversation={self.conv.id}")
        msgs = r.data.get("results", r.data)
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["attachments"][0]["original_name"], "notes.pdf")
        # receiver can download the exact bytes, using the ?token= form the
        # browser uses in <a>/<img> tags
        from rest_framework_simplejwt.tokens import RefreshToken
        token = str(RefreshToken.for_user(self.b).access_token)
        r = other.get(f"/api/chat/attachments/{att_id}/download/?token={token}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(b"".join(r.streaming_content), b"%PDF-1.4 hello")
        # uploader can download via the normal Authorization header too
        r = self.client.get(f"/api/chat/attachments/{att_id}/download/")
        self.assertEqual(r.status_code, 200)

    def test_outsider_cannot_download(self):
        r = self._upload(self.client)
        att_id = r.data["id"]
        self.client.post("/api/chat/messages/",
                         {"conversation": self.conv.id, "body": "", "attachment_id": att_id},
                         format="json")
        outsider = APIClient(); outsider.force_authenticate(self.outsider)
        r = outsider.get(f"/api/chat/attachments/{att_id}/download/")
        self.assertEqual(r.status_code, 403)
        anon = APIClient()
        r = anon.get(f"/api/chat/attachments/{att_id}/download/")
        self.assertEqual(r.status_code, 401)

    def test_bad_file_type_is_a_clean_400_not_a_500(self):
        r = self._upload(self.client, name="virus.exe", content=b"MZ fake")
        self.assertEqual(r.status_code, 400)
        self.assertIn("not allowed", str(r.data["detail"]))
        self.assertEqual(Attachment.objects.count(), 0)

    def test_oversize_file_is_a_clean_400(self):
        big = b"x" * (10 * 1024 * 1024 + 1)
        r = self._upload(self.client, name="big.pdf", content=big)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Attachment.objects.count(), 0)

    def test_ws_broadcast_points_at_download_endpoint(self):
        att = Attachment.objects.create(uploaded_by=self.a,
            file=SimpleUploadedFile("pic.pdf", b"data"), original_name="pic.pdf", size_bytes=4)
        consumer = ChatConsumer(); consumer.user = self.a; consumer.conversation_id = self.conv.id
        payload = async_to_sync(consumer._create_message)("", None, att.id)
        self.assertEqual(payload["attachments"][0]["file"],
                         f"/api/chat/attachments/{att.id}/download/")


class LocationAndVoiceNoteTests(TestCase):
    def setUp(self):
        self.a = User.objects.create_user(username="loca", email="la@test.com", password="testpass123")
        self.b = User.objects.create_user(username="locb", email="lb@test.com", password="testpass123")
        self.client = APIClient(); self.client.force_authenticate(self.a)
        conv = Conversation.objects.create(type="private", created_by=self.a)
        ConversationMember.objects.bulk_create([
            ConversationMember(conversation=conv, user=self.a),
            ConversationMember(conversation=conv, user=self.b)])
        self.conv = conv

    def test_send_one_time_location_rest(self):
        r = self.client.post("/api/chat/messages/",
                             {"conversation": self.conv.id, "body": "",
                              "latitude": 28.6139, "longitude": 77.2090}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["kind"], "location")
        self.assertAlmostEqual(r.data["latitude"], 28.6139)
        self.assertIsNone(r.data["location_live_until"])
        self.assertFalse(r.data["is_live_location"])

    def test_invalid_coordinates_rejected(self):
        r = self.client.post("/api/chat/messages/",
                             {"conversation": self.conv.id, "body": "",
                              "latitude": 123.0, "longitude": 77.0}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Message.objects.filter(conversation=self.conv).count(), 0)

    def test_live_location_lifecycle_rest(self):
        r = self.client.post("/api/chat/messages/",
                             {"conversation": self.conv.id, "body": "",
                              "latitude": 28.6, "longitude": 77.2, "live_minutes": 15}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertTrue(r.data["is_live_location"])
        msg_id = r.data["id"]
        # sender moves -> updates in place
        r = self.client.post(f"/api/chat/messages/{msg_id}/location/",
                             {"latitude": 28.7, "longitude": 77.3}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertAlmostEqual(r.data["latitude"], 28.7)
        # the other member cannot move MY pin
        other = APIClient(); other.force_authenticate(self.b)
        r = other.post(f"/api/chat/messages/{msg_id}/location/",
                       {"latitude": 0.0, "longitude": 0.0}, format="json")
        self.assertEqual(r.status_code, 403)
        # stop sharing -> no longer live, further updates rejected
        r = self.client.post(f"/api/chat/messages/{msg_id}/location/", {"stop": True}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.data["is_live_location"])
        r = self.client.post(f"/api/chat/messages/{msg_id}/location/",
                             {"latitude": 28.8, "longitude": 77.4}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_live_location_via_websocket_consumer(self):
        consumer = ChatConsumer(); consumer.user = self.a; consumer.conversation_id = self.conv.id
        payload = async_to_sync(consumer._create_message)("", None, None,
                                                          {"latitude": 28.6, "longitude": 77.2, "live_minutes": 60})
        self.assertEqual(payload["kind"], "location")
        self.assertIsNotNone(payload["location_live_until"])
        updated = async_to_sync(consumer._update_location)(payload["message_id"], 28.9, 77.9, False)
        self.assertAlmostEqual(updated["latitude"], 28.9)
        bad = async_to_sync(consumer._create_message)("", None, None, {"latitude": 999, "longitude": 0})
        self.assertEqual(bad, "bad_location")

    def test_voice_note_upload_send_download(self):
        audio = b"fake-webm-audio-bytes"
        r = self.client.post("/api/chat/attachments/",
                             {"file": SimpleUploadedFile("voice-note.webm", audio, content_type="audio/webm")},
                             format="multipart")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertTrue(r.data["is_audio"])
        att_id = r.data["id"]
        r = self.client.post("/api/chat/messages/",
                             {"conversation": self.conv.id, "body": "", "attachment_id": att_id},
                             format="json")
        self.assertEqual(r.status_code, 201, r.data)
        other = APIClient(); other.force_authenticate(self.b)
        r = other.get(f"/api/chat/messages/?conversation={self.conv.id}")
        msgs = r.data.get("results", r.data)
        self.assertTrue(msgs[0]["attachments"][0]["is_audio"])
        from rest_framework_simplejwt.tokens import RefreshToken
        token = str(RefreshToken.for_user(self.b).access_token)
        r = other.get(f"/api/chat/attachments/{att_id}/download/?token={token}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(b"".join(r.streaming_content), audio)


class MuteAndMemberPrivacyTests(TestCase):
    """v6: mute action + privacy-respecting MemberSerializer.is_online."""
    def setUp(self):
        self.a = User.objects.create_user(username="muter", email="m@test.com", password="testpass123")
        self.b = User.objects.create_user(username="peer", email="peer@test.com", password="testpass123")
        self.client = APIClient(); self.client.force_authenticate(self.a)
        self.conv = Conversation.objects.create(type="private", created_by=self.a)
        ConversationMember.objects.bulk_create([
            ConversationMember(conversation=self.conv, user=self.a),
            ConversationMember(conversation=self.conv, user=self.b)])

    def _memberships(self):
        r = self.client.get(f"/api/chat/conversations/{self.conv.id}/")
        self.assertEqual(r.status_code, 200, r.data)
        return {m["user"]: m for m in r.data["memberships"]}

    def test_mute_sets_and_unsets_own_membership(self):
        r = self.client.post(f"/api/chat/conversations/{self.conv.id}/mute/", {"muted": True}, format="json")
        self.assertEqual(r.status_code, 200); self.assertTrue(r.data["is_muted"])
        self.assertTrue(ConversationMember.objects.get(conversation=self.conv, user=self.a).is_muted)
        # peer's membership untouched
        self.assertFalse(ConversationMember.objects.get(conversation=self.conv, user=self.b).is_muted)
        r = self.client.post(f"/api/chat/conversations/{self.conv.id}/mute/", {"muted": False}, format="json")
        self.assertFalse(r.data["is_muted"])
        self.assertFalse(ConversationMember.objects.get(conversation=self.conv, user=self.a).is_muted)

    def test_mute_toggles_when_muted_absent(self):
        r = self.client.post(f"/api/chat/conversations/{self.conv.id}/mute/", {}, format="json")
        self.assertTrue(r.data["is_muted"])
        r = self.client.post(f"/api/chat/conversations/{self.conv.id}/mute/", {}, format="json")
        self.assertFalse(r.data["is_muted"])

    def test_member_is_online_hidden_when_privacy_off(self):
        self.b.profile.is_online = True
        self.b.profile.show_online_status = False
        self.b.profile.save()
        members = self._memberships()
        self.assertFalse(members[self.b.id]["is_online"])

    def test_member_is_online_visible_when_privacy_on(self):
        self.b.profile.is_online = True
        self.b.profile.show_online_status = True
        self.b.profile.save()
        members = self._memberships()
        self.assertTrue(members[self.b.id]["is_online"])

    def test_member_is_online_false_when_offline(self):
        self.b.profile.is_online = False
        self.b.profile.show_online_status = True
        self.b.profile.save()
        members = self._memberships()
        self.assertFalse(members[self.b.id]["is_online"])
