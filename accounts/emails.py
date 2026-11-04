"""Email verification mail.

Uses Django's built-in token generator (the same one password reset uses):
the token is signed from the user's id, password hash, email and a timestamp,
so it expires automatically (PASSWORD_RESET_TIMEOUT, 3 days by default) and
becomes invalid as soon as it is used or the password/email changes.
No verification-token table is needed.
"""
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode


def build_verification_link(request, user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    path = reverse("verify-email", kwargs={"uidb64": uid, "token": token})
    if request is not None:
        return request.build_absolute_uri(path)
    base = getattr(settings, "SITE_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    return base + path


def build_password_reset_link(request, user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    path = reverse("password-reset-page", kwargs={"uidb64": uid, "token": token})
    if request is not None:
        return request.build_absolute_uri(path)
    base = getattr(settings, "SITE_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    return base + path


def send_password_reset_email(request, user):
    """Same token generator as verification: the reset token is signed from
    the password hash, so it dies automatically once the password changes."""
    link = build_password_reset_link(request, user)
    send_mail(
        subject="Reset your password - Real-Time Chat",
        message=(
            f"Hi {user.username},\n\n"
            "Someone asked to reset the password for this account. Open this "
            f"link to choose a new password:\n\n{link}\n\n"
            "The link expires in 3 days and stops working as soon as the "
            "password is changed. If you did not ask for this, you can "
            "ignore this email - your password stays the same.\n"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )
    return link


def send_verification_email(request, user):
    link = build_verification_link(request, user)
    send_mail(
        subject="Verify your email - Real-Time Chat",
        message=(
            f"Hi {user.username},\n\n"
            "Thanks for registering. Please verify your email address by "
            f"opening this link:\n\n{link}\n\n"
            "The link expires in 3 days. If you did not create this account, "
            "you can ignore this email.\n"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )
    return link
