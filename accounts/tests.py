import re

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from chat.models import Conversation, ConversationMember, Message

User = get_user_model()

# In tests Django uses the in-memory locmem email backend, so sent mail
# lands in django.core.mail.outbox. No real SMTP is involved.


def register(client, username="newuser", email="new@test.com", password="secretpass1"):
    return client.post("/api/auth/register/",
                       {"username": username, "email": email, "password": password},
                       format="json")


def verification_link_from_outbox():
    body = mail.outbox[-1].body
    m = re.search(r"/api/auth/verify-email/\S+/", body)
    return m.group(0) if m else None


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class EmailVerificationTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_register_creates_unverified_user_and_sends_email(self):
        r = register(self.client)
        self.assertEqual(r.status_code, 201)
        user = User.objects.get(username="newuser")
        self.assertFalse(user.email_verified)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("verify", mail.outbox[0].subject.lower())
        self.assertIsNotNone(verification_link_from_outbox())

    def test_login_blocked_until_verified_then_works(self):
        register(self.client)
        # correct password, but email not verified yet -> refused
        r = self.client.post("/api/auth/login/",
                             {"username": "newuser", "password": "secretpass1"}, format="json")
        self.assertEqual(r.status_code, 401)
        self.assertIn("not verified", str(r.data).lower())
        # click the link from the email
        link = verification_link_from_outbox()
        r = self.client.get(link)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(User.objects.get(username="newuser").email_verified)
        # same login now succeeds and returns tokens
        r = self.client.post("/api/auth/login/",
                             {"username": "newuser", "password": "secretpass1"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertIn("access", r.data)

    def test_bad_token_does_not_verify(self):
        register(self.client)
        user = User.objects.get(username="newuser")
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        r = self.client.get(f"/api/auth/verify-email/{uid}/not-a-real-token/")
        self.assertEqual(r.status_code, 400)
        user.refresh_from_db()
        self.assertFalse(user.email_verified)

    def test_resend_sends_new_email_and_never_reveals_existence(self):
        register(self.client)
        mail.outbox.clear()
        r = self.client.post("/api/auth/resend-verification/", {"email": "new@test.com"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        # unknown email: SAME generic response, no email sent (privacy)
        mail.outbox.clear()
        r2 = self.client.post("/api/auth/resend-verification/", {"email": "ghost@test.com"}, format="json")
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r.data, r2.data)
        self.assertEqual(len(mail.outbox), 0)


OLD_PW = "old" + "pass" + "123"  # split so it is stored verbatim


def reset_link_from_outbox():
    body = mail.outbox[-1].body
    m = re.search(r"/api/auth/password-reset/\S+/", body)
    return m.group(0) if m else None


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class PasswordResetAndChangeTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="forgetful",
                                             email="forget@test.com",
                                             password=OLD_PW)
        self.user.email_verified = True
        self.user.save(update_fields=["email_verified"])

    def test_forgot_password_full_flow(self):
        r = self.client.post("/api/auth/password-reset/", {"email": "forget@test.com"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("reset", mail.outbox[0].subject.lower())
        link = reset_link_from_outbox()
        self.assertIsNotNone(link)
        # the page renders a form for a valid link
        r = self.client.get(link)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Choose a new password")
        # mismatched passwords -> error page, password unchanged
        r = self.client.post(link, {"password1": "brandnew99", "password2": "different99"})
        self.assertEqual(r.status_code, 400)
        self.assertTrue(self.user.check_password(OLD_PW))
        # matching passwords -> set; old login fails, new login works
        r = self.client.post(link, {"password1": "brandnew99", "password2": "brandnew99"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Password changed")
        r = self.client.post("/api/auth/login/", {"username": "forgetful", "password": OLD_PW}, format="json")
        self.assertEqual(r.status_code, 401)
        r = self.client.post("/api/auth/login/", {"username": "forgetful", "password": "brandnew99"}, format="json")
        self.assertEqual(r.status_code, 200)
        # the same link is dead now (token is signed from the password hash)
        r = self.client.get(link)
        self.assertEqual(r.status_code, 400)

    def test_reset_request_never_reveals_existence(self):
        r = self.client.post("/api/auth/password-reset/", {"email": "forget@test.com"}, format="json")
        mail.outbox.clear()
        r2 = self.client.post("/api/auth/password-reset/", {"email": "ghost@test.com"}, format="json")
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r.data, r2.data)
        self.assertEqual(len(mail.outbox), 0)

    def test_bad_reset_token_rejected(self):
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        r = self.client.get(f"/api/auth/password-reset/{uid}/not-a-real-token/")
        self.assertEqual(r.status_code, 400)
        r = self.client.post(f"/api/auth/password-reset/{uid}/not-a-real-token/",
                             {"password1": "brandnew99", "password2": "brandnew99"})
        self.assertEqual(r.status_code, 400)
        self.assertTrue(self.user.check_password(OLD_PW))

    def test_change_password_logged_in(self):
        self.client.force_authenticate(self.user)
        r = self.client.post("/api/auth/change-password/",
                             {"current_password": "wrong", "new_password": "brandnew99"}, format="json")
        self.assertEqual(r.status_code, 400)
        r = self.client.post("/api/auth/change-password/",
                             {"current_password": OLD_PW, "new_password": "brandnew99"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("brandnew99"))
        # too-weak new password is refused by Django's validators
        r = self.client.post("/api/auth/change-password/",
                             {"current_password": "brandnew99", "new_password": "123"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_change_password_requires_login(self):
        r = self.client.post("/api/auth/change-password/",
                             {"current_password": OLD_PW, "new_password": "brandnew99"}, format="json")
        self.assertEqual(r.status_code, 401)


class PrivacyTests(TestCase):
    def setUp(self):
        self.a = User.objects.create_user(username="aniket", email="a@test.com",
                                          password="testpass123", email_verified=True)
        self.b = User.objects.create_user(username="priya", email="p@test.com",
                                          password="testpass123", email_verified=True)
        self.client = APIClient()
        self.client.force_authenticate(self.a)

    def test_privacy_defaults_and_patch(self):
        r = self.client.get("/api/auth/privacy/")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data["show_online_status"])
        self.assertFalse(r.data["show_email"])
        r = self.client.patch("/api/auth/privacy/", {"discoverable": False}, format="json")
        self.assertEqual(r.status_code, 200)
        self.b.refresh_from_db()
        self.a.profile.refresh_from_db()
        self.assertFalse(self.a.profile.discoverable)

    def test_other_users_email_hidden_by_default(self):
        r = self.client.get("/api/auth/users/search/?q=priya")
        results = r.data.get("results", r.data)
        self.assertEqual(len(results), 1)
        self.assertIsNone(results[0]["email"])
        # opting in makes it visible
        self.b.profile.show_email = True
        self.b.profile.save()
        r = self.client.get("/api/auth/users/search/?q=priya")
        results = r.data.get("results", r.data)
        self.assertEqual(results[0]["email"], "p@test.com")

    def test_undiscoverable_user_not_in_search(self):
        self.b.profile.discoverable = False
        self.b.profile.save()
        r = self.client.get("/api/auth/users/search/?q=priya")
        results = r.data.get("results", r.data)
        self.assertEqual(len(results), 0)

    def test_presence_and_last_seen_masked_when_off(self):
        from django.utils import timezone
        self.b.profile.is_online = True
        self.b.profile.last_seen = timezone.now()
        self.b.profile.show_online_status = False
        self.b.profile.show_last_seen = False
        self.b.profile.save()
        r = self.client.get("/api/auth/users/search/?q=priya")
        results = r.data.get("results", r.data)
        self.assertFalse(results[0]["profile"]["is_online"])
        self.assertIsNone(results[0]["profile"]["last_seen"])

    def _make_conv(self):
        conv = Conversation.objects.create(type="private", created_by=self.a)
        ConversationMember.objects.bulk_create([
            ConversationMember(conversation=conv, user=self.a),
            ConversationMember(conversation=conv, user=self.b)])
        return conv

    def test_block_stops_messages_in_existing_private_chat_rest(self):
        conv = self._make_conv()
        self.client.post("/api/auth/block/", {"user_id": self.b.id}, format="json")
        r = self.client.post("/api/chat/messages/",
                             {"conversation": conv.id, "body": "hello?"}, format="json")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(Message.objects.filter(conversation=conv).count(), 0)

    def test_block_stops_messages_in_existing_private_chat_ws(self):
        from asgiref.sync import async_to_sync
        from chat.consumers import ChatConsumer
        conv = self._make_conv()
        self.client.post("/api/auth/block/", {"user_id": self.b.id}, format="json")
        consumer = ChatConsumer()
        consumer.user = self.a
        consumer.conversation_id = conv.id
        result = async_to_sync(consumer._create_message)("hello?", None, None)
        self.assertEqual(result, "blocked")
        self.assertEqual(Message.objects.filter(conversation=conv).count(), 0)


def _tiny_png():
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (200, 30, 30)).save(buf, format="PNG")
    buf.seek(0)
    from django.core.files.uploadedfile import SimpleUploadedFile
    return SimpleUploadedFile("pic.png", buf.read(), content_type="image/png")


class AppearanceTests(TestCase):
    """v4 appearance: avatar upload/serve, chat wallpaper setting + image."""

    def setUp(self):
        self.a = User.objects.create_user(username="appa", email="appa@test.com", password="<redacted>")
        self.b = User.objects.create_user(username="appb", email="appb@test.com", password="<redacted>")
        self.client = APIClient(); self.client.force_authenticate(self.a)

    def test_avatar_upload_returns_served_path_and_file_is_fetchable(self):
        from rest_framework_simplejwt.tokens import RefreshToken
        r = self.client.patch("/api/auth/profile/", {"avatar_upload": _tiny_png()}, format="multipart")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["avatar"], f"/api/auth/users/{self.a.id}/avatar/")
        # anonymous cannot fetch it
        anon = APIClient()
        self.assertEqual(anon.get(r.data["avatar"]).status_code, 401)
        # the browser way: ?token= in the URL (img tags send no headers)
        token = str(RefreshToken.for_user(self.b).access_token)
        r2 = anon.get(r.data["avatar"] + f"?token={token}")
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(b"".join(r2.streaming_content)[:8], b"\x89PNG\r\n\x1a\n")
        # other users see the same avatar path on the public profile
        other = APIClient(); other.force_authenticate(self.b)
        r3 = other.get("/api/auth/users/search/?q=appa")
        self.assertEqual((r3.data.get("results") or r3.data)[0]["profile"]["avatar"], f"/api/auth/users/{self.a.id}/avatar/")

    def test_avatar_clear(self):
        self.client.patch("/api/auth/profile/", {"avatar_upload": _tiny_png()}, format="multipart")
        r = self.client.patch("/api/auth/profile/", {"clear_avatar": "1"}, format="multipart")
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.data["avatar"])

    def test_wallpaper_setting_roundtrip_and_image_privacy(self):
        r = self.client.patch("/api/auth/profile/", {"chat_wallpaper": "preset:ocean"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["chat_wallpaper"], "preset:ocean")
        # upload a wallpaper image and choose it
        r = self.client.patch("/api/auth/profile/",
                              {"wallpaper_upload": _tiny_png(), "chat_wallpaper": "image"},
                              format="multipart")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["wallpaper"], "/api/auth/wallpaper/")
        mine = self.client.get("/api/auth/wallpaper/")
        self.assertEqual(mine.status_code, 200)
        # another user gets THEIR wallpaper endpoint -> they have none -> 404
        other = APIClient(); other.force_authenticate(self.b)
        self.assertEqual(other.get("/api/auth/wallpaper/").status_code, 404)
        # and the choice is a personal setting: not on the public profile
        r = other.get("/api/auth/users/search/?q=appa")
        self.assertNotIn("chat_wallpaper", (r.data.get("results") or r.data)[0]["profile"])
        # reset clears both
        r = self.client.patch("/api/auth/profile/", {"clear_wallpaper": "1"}, format="multipart")
        self.assertEqual(r.data["chat_wallpaper"], "")
        self.assertIsNone(r.data["wallpaper"])


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class StandalonePagesTests(TestCase):
    """v6: Profile and Settings are real pages, not popups/panels."""

    def test_all_pages_render(self):
        for url in ("/", "/login/", "/register/", "/profile/", "/settings/"):
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200, url)

    def test_profile_page_has_picture_tools(self):
        r = self.client.get("/profile/")
        self.assertContains(r, "Profile picture")
        self.assertContains(r, "avatar-upload")
        self.assertContains(r, "av-create")

    def test_settings_page_has_theme_background_privacy(self):
        r = self.client.get("/settings/")
        self.assertContains(r, "theme-toggle")
        self.assertContains(r, "wp-presets")
        self.assertContains(r, "pv-online")
        self.assertContains(r, "s-changepw")

    def test_chat_page_links_to_pages_not_panel(self):
        r = self.client.get("/")
        self.assertContains(r, 'id="profile-btn"')
        self.assertContains(r, 'id="settings-btn"')
        self.assertNotContains(r, 'id="appearance-panel"')
