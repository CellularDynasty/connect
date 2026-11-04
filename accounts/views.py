from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.db.models import Q
from django.shortcuts import render
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.views import View
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from .emails import send_verification_email, send_password_reset_email
from .models import UserProfile, BlockedUser
from .serializers import (RegisterSerializer, UserSerializer, ProfileSerializer,
                          BlockSerializer, EmailVerifiedTokenObtainPairSerializer,
                          PrivacySerializer)

User = get_user_model()

class RegisterView(generics.CreateAPIView):
    """Register -> account is created UNVERIFIED and a verification email is
    sent. Login stays blocked until the link in that email is clicked."""
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    queryset = User.objects.all()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        send_verification_email(request, user)
        data = dict(serializer.data)
        data["detail"] = ("Account created. A verification link has been sent to "
                          "your email - open it to verify your account, then log in.")
        return Response(data, status=status.HTTP_201_CREATED)


class LoginView(TokenObtainPairView):
    """JWT login, but only for email-verified accounts."""
    serializer_class = EmailVerifiedTokenObtainPairSerializer


class VerifyEmailView(View):
    """The link people click in the verification email. Renders a small HTML
    page (it is opened in a browser, not called by the app)."""
    def get(self, request, uidb64, token):
        try:
            user = User.objects.get(pk=force_str(urlsafe_base64_decode(uidb64)))
        except Exception:
            user = None
        if user is not None and user.email_verified:
            return render(request, "verify_email.html",
                          {"ok": True, "already": True, "username": user.username})
        if user is not None and default_token_generator.check_token(user, token):
            user.email_verified = True
            user.save(update_fields=["email_verified"])
            return render(request, "verify_email.html",
                          {"ok": True, "already": False, "username": user.username})
        return render(request, "verify_email.html", {"ok": False}, status=400)


class ResendVerificationView(APIView):
    """POST {email} -> sends a fresh verification link if needed.
    Privacy: the response is ALWAYS the same generic message, whether or
    not that email exists, so this endpoint cannot be used to check which
    emails are registered."""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = (request.data.get("email") or "").strip()
        user = User.objects.filter(email__iexact=email).first() if email else None
        if user is not None and not user.email_verified:
            send_verification_email(request, user)
        return Response({"detail": "If that email is registered and not yet verified, "
                                   "a new verification link has been sent."})


class PasswordResetRequestView(APIView):
    """POST {email} -> emails a set-new-password link.
    Privacy: ALWAYS the same generic response, whether or not the email is
    registered, so nobody can probe which emails have accounts."""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = (request.data.get("email") or "").strip()
        user = User.objects.filter(email__iexact=email).first() if email else None
        if user is not None:
            send_password_reset_email(request, user)
        return Response({"detail": "If that email is registered, a password reset "
                                   "link has been sent."})


def _user_from_uidb64(uidb64):
    try:
        return User.objects.get(pk=force_str(urlsafe_base64_decode(uidb64)))
    except Exception:
        return None


class PasswordResetPageView(View):
    """The link people click in the reset email: a small standalone HTML page
    with a set-new-password form (opened in a browser, not called by the app).
    GET shows the form if the token is valid; POST sets the password. The
    token is signed from the password hash, so the link self-destructs the
    moment the password changes and cannot be reused."""

    def get(self, request, uidb64, token):
        user = _user_from_uidb64(uidb64)
        ok = user is not None and default_token_generator.check_token(user, token)
        return render(request, "reset_password.html",
                      {"valid": ok, "done": False, "errors": []},
                      status=200 if ok else 400)

    def post(self, request, uidb64, token):
        user = _user_from_uidb64(uidb64)
        if user is None or not default_token_generator.check_token(user, token):
            return render(request, "reset_password.html",
                          {"valid": False, "done": False, "errors": []}, status=400)
        pw1 = request.POST.get("password1") or ""
        pw2 = request.POST.get("password2") or ""
        errors = []
        if pw1 != pw2:
            errors.append("The two passwords do not match.")
        else:
            from django.contrib.auth.password_validation import validate_password
            from django.core.exceptions import ValidationError as DjangoValidationError
            try:
                validate_password(pw1, user)
            except DjangoValidationError as exc:
                errors.extend(exc.messages)
        if errors:
            return render(request, "reset_password.html",
                          {"valid": True, "done": False, "errors": errors}, status=400)
        user.set_password(pw1)
        user.save(update_fields=["password"])
        return render(request, "reset_password.html",
                      {"valid": True, "done": True, "errors": [],
                       "username": user.username})


class ChangePasswordView(APIView):
    """POST {current_password, new_password} — for a signed-in user who
    KNOWS their current password (the forgot-password flow above is for
    when they don't)."""
    def post(self, request):
        current = request.data.get("current_password") or ""
        new = request.data.get("new_password") or ""
        if not request.user.check_password(current):
            return Response({"detail": "Current password is incorrect."}, status=400)
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError as DjangoValidationError
        try:
            validate_password(new, request.user)
        except DjangoValidationError as exc:
            return Response({"detail": " ".join(exc.messages)}, status=400)
        request.user.set_password(new)
        request.user.save(update_fields=["password"])
        return Response({"detail": "Password changed. Log in again on your other devices."})


class MeView(generics.RetrieveUpdateAPIView):
    """GET/PATCH /api/auth/me/ and /api/auth/profile/"""
    serializer_class = UserSerializer
    def get_object(self):
        return self.request.user

class ProfileView(APIView):
    def get(self, request):
        return Response(ProfileSerializer(request.user.profile).data)
    def patch(self, request):
        profile = request.user.profile
        # Explicit clears (an empty file field cannot express "remove it")
        if str(request.data.get("clear_avatar", "")).lower() in ("1", "true"):
            if profile.avatar:
                profile.avatar.delete(save=False)
            profile.avatar = None
            profile.save(update_fields=["avatar"])
        if str(request.data.get("clear_wallpaper", "")).lower() in ("1", "true"):
            if profile.wallpaper:
                profile.wallpaper.delete(save=False)
            profile.wallpaper = None
            profile.chat_wallpaper = ""
            profile.save(update_fields=["wallpaper", "chat_wallpaper"])
        ser = ProfileSerializer(profile, data=request.data, partial=True)
        ser.is_valid(raise_exception=True); ser.save()
        return Response(ser.data)


def _user_from_token(request):
    """Resolve the user from the Authorization header OR a ?token=<JWT>
    query parameter (for <img> tags, which cannot send headers - the same
    pattern as the attachment download endpoint)."""
    if getattr(request, "user", None) is not None and request.user.is_authenticated:
        return request.user
    token = request.query_params.get("token")
    if not token:
        return None
    try:
        from rest_framework_simplejwt.tokens import AccessToken
        return User.objects.get(id=AccessToken(token)["user_id"])
    except Exception:
        return None


class AvatarFileView(APIView):
    """GET /api/auth/users/<user_id>/avatar/ — serves a user's profile
    picture to any signed-in user (avatars are public profile data inside
    the app). App-served like attachment downloads, because /media/ is not
    served in production."""
    permission_classes = [permissions.AllowAny]  # auth checked manually (header OR ?token=)

    def get(self, request, user_id):
        from django.http import FileResponse, Http404
        if _user_from_token(request) is None:
            return Response({"detail": "Authentication required."}, status=401)
        profile = UserProfile.objects.filter(user_id=user_id).first()
        if profile is None or not profile.avatar:
            raise Http404("No avatar")
        import mimetypes
        return FileResponse(profile.avatar.open("rb"),
                            content_type=mimetypes.guess_type(profile.avatar.name)[0] or "application/octet-stream")


class OwnWallpaperView(APIView):
    """GET /api/auth/wallpaper/ — the signed-in user's OWN chat wallpaper
    image. Nobody else can fetch it: your wallpaper is your setting."""
    permission_classes = [permissions.AllowAny]  # auth checked manually (header OR ?token=)

    def get(self, request):
        from django.http import FileResponse, Http404
        user = _user_from_token(request)
        if user is None:
            return Response({"detail": "Authentication required."}, status=401)
        profile = user.profile
        if not profile.wallpaper:
            raise Http404("No wallpaper")
        import mimetypes
        return FileResponse(profile.wallpaper.open("rb"),
                            content_type=mimetypes.guess_type(profile.wallpaper.name)[0] or "application/octet-stream")

class PrivacyView(APIView):
    """GET/PATCH the signed-in user's own privacy toggles."""
    def get(self, request):
        return Response(PrivacySerializer(request.user.profile).data)
    def patch(self, request):
        ser = PrivacySerializer(request.user.profile, data=request.data, partial=True)
        ser.is_valid(raise_exception=True); ser.save()
        return Response(ser.data)

class UserSearchView(generics.ListAPIView):
    serializer_class = UserSerializer
    def get_queryset(self):
        q = self.request.query_params.get("q", "").strip()
        # Privacy: users who turned off discoverability never appear in search.
        qs = (User.objects.exclude(id=self.request.user.id)
              .filter(profile__discoverable=True).select_related("profile"))
        if q:
            qs = qs.filter(Q(username__icontains=q) | Q(email__icontains=q) |
                           Q(first_name__icontains=q) | Q(last_name__icontains=q))
        return qs.order_by("username")[:50]

class BlockView(APIView):
    def get(self, request):
        return Response(BlockSerializer(BlockedUser.objects.filter(blocker=request.user), many=True).data)
    def post(self, request):
        blocked_id = request.data.get("user_id")
        if not blocked_id or int(blocked_id) == request.user.id:
            return Response({"detail": "Invalid user_id"}, status=400)
        obj, _ = BlockedUser.objects.get_or_create(blocker=request.user, blocked_id=blocked_id)
        return Response(BlockSerializer(obj).data, status=status.HTTP_201_CREATED)
    def delete(self, request):
        BlockedUser.objects.filter(blocker=request.user, blocked_id=request.data.get("user_id")).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
