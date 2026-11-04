from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import UserProfile, BlockedUser

User = get_user_model()

PRIVACY_FIELDS = ["show_online_status", "show_last_seen", "send_read_receipts",
                  "discoverable", "show_email"]


def avatar_path(profile):
    """App-served avatar URL (never a public /media/ URL - media is only
    served in DEBUG, and files stay behind login this way)."""
    if profile is not None and profile.avatar:
        return f"/api/auth/users/{profile.user_id}/avatar/"
    return None


def wallpaper_path(profile):
    if profile is not None and profile.wallpaper:
        return "/api/auth/wallpaper/"
    return None


class ProfileSerializer(serializers.ModelSerializer):
    """Full profile - used only for the owner's own profile endpoints,
    so it includes their privacy settings."""
    avatar = serializers.SerializerMethodField()
    wallpaper = serializers.SerializerMethodField()
    # Write-only upload fields; reads come back as the served paths above.
    avatar_upload = serializers.ImageField(write_only=True, required=False)
    wallpaper_upload = serializers.ImageField(write_only=True, required=False)

    class Meta:
        model = UserProfile
        fields = ["display_name", "bio", "avatar", "avatar_upload", "chat_wallpaper",
                  "wallpaper", "wallpaper_upload",
                  "is_online", "last_seen", "updated_at"] + PRIVACY_FIELDS
        read_only_fields = ["is_online", "last_seen", "updated_at"]

    def get_avatar(self, obj):
        return avatar_path(obj)

    def get_wallpaper(self, obj):
        return wallpaper_path(obj)

    def update(self, instance, validated_data):
        avatar_file = validated_data.pop("avatar_upload", None)
        wallpaper_file = validated_data.pop("wallpaper_upload", None)
        if avatar_file is not None:
            instance.avatar = avatar_file
        if wallpaper_file is not None:
            instance.wallpaper = wallpaper_file
        return super().update(instance, validated_data)


class PrivacySerializer(serializers.ModelSerializer):
    """Just the privacy toggles: GET/PATCH /api/auth/privacy/"""
    class Meta:
        model = UserProfile
        fields = PRIVACY_FIELDS


class PublicProfileSerializer(serializers.ModelSerializer):
    """Profile as OTHER users are allowed to see it: presence and last seen
    are masked when the owner has turned those privacy settings off."""
    is_online = serializers.SerializerMethodField()
    last_seen = serializers.SerializerMethodField()
    avatar = serializers.SerializerMethodField()

    class Meta:
        model = UserProfile
        fields = ["display_name", "bio", "avatar", "is_online", "last_seen", "updated_at"]

    def get_avatar(self, obj):
        return avatar_path(obj)

    def _is_self(self, obj):
        request = self.context.get("request")
        return request is not None and getattr(request, "user", None) == obj.user

    def get_is_online(self, obj):
        if self._is_self(obj) or obj.show_online_status:
            return obj.is_online
        return False

    def get_last_seen(self, obj):
        if self._is_self(obj) or obj.show_last_seen:
            return obj.last_seen
        return None


class UserSerializer(serializers.ModelSerializer):
    profile = PublicProfileSerializer(read_only=True)
    email = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "email", "email_verified", "first_name", "last_name", "profile", "date_joined"]
        read_only_fields = ["id", "date_joined", "email_verified"]

    def get_email(self, obj):
        """Privacy: your email is shown to another user only if you opted in
        (profile.show_email). You and staff always see it."""
        request = self.context.get("request")
        viewer = getattr(request, "user", None) if request is not None else None
        if viewer is not None and (viewer == obj or viewer.is_staff):
            return obj.email
        profile = getattr(obj, "profile", None)
        if profile is not None and profile.show_email:
            return obj.email
        return None


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    class Meta:
        model = User
        fields = ["id", "username", "email", "password", "first_name", "last_name"]
    def create(self, validated_data):
        # create_user hashes the password securely - never store plaintext.
        # New registrations always start unverified; the verification email
        # is sent by RegisterView after creation.
        return User.objects.create_user(**validated_data, email_verified=False)


class EmailVerifiedTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Login that refuses unverified accounts. The password is checked by
    the parent class first, so this never reveals verification status to
    someone who does not know the password."""
    def validate(self, attrs):
        data = super().validate(attrs)
        if not self.user.email_verified:
            raise AuthenticationFailed(
                "Email not verified. Please click the verification link in "
                "your email, or request a new one.",
                code="email_not_verified",
            )
        return data


class BlockSerializer(serializers.ModelSerializer):
    class Meta:
        model = BlockedUser
        fields = ["id", "blocked", "created_at"]
