from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings


class User(AbstractUser):
    """Custom user: email is unique, password is hashed by Django (PBKDF2 by default)."""
    email = models.EmailField(unique=True, db_index=True)
    # Set to True only when the user clicks the verification link sent to their
    # email. Users who registered before verification existed were marked
    # verified by the migration, so only new registrations start unverified.
    email_verified = models.BooleanField(default=False)

    class Meta:
        indexes = [models.Index(fields=["username"]), models.Index(fields=["email"])]


class UserProfile(models.Model):
    """1-to-1 extension of User: avatar, bio, presence. Kept separate so auth stays lean."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    display_name = models.CharField(max_length=100, blank=True)
    bio = models.TextField(max_length=500, blank=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    # --- Appearance (v4): chat wallpaper choice + optional uploaded image.
    # chat_wallpaper encodes the choice as "preset:<key>", "color:<#hex>" or
    # "image" (use the uploaded wallpaper image). Theme (dark/light) is a
    # per-device display preference and lives in the browser, not here.
    chat_wallpaper = models.CharField(max_length=60, blank=True, default="")
    wallpaper = models.ImageField(upload_to="wallpapers/", blank=True, null=True)
    is_online = models.BooleanField(default=False, db_index=True)
    last_seen = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    # --- Privacy settings (user-controlled, enforced by the API/consumers) ---
    show_online_status = models.BooleanField(default=True)   # False = always appear offline
    show_last_seen = models.BooleanField(default=True)       # False = last_seen hidden from others
    send_read_receipts = models.BooleanField(default=True)   # False = no blue-tick/read events sent
    discoverable = models.BooleanField(default=True)         # False = hidden from user search
    show_email = models.BooleanField(default=False)          # False = email visible only to yourself

    def __str__(self):
        return f"Profile({self.user.username})"


class BlockedUser(models.Model):
    blocker = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="blocking")
    blocked = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="blocked_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("blocker", "blocked")
        indexes = [models.Index(fields=["blocker", "blocked"])]
