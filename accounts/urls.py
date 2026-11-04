from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView, TokenBlacklistView
from .views import (RegisterView, LoginView, VerifyEmailView, ResendVerificationView,
                    PasswordResetRequestView, PasswordResetPageView, ChangePasswordView,
                    MeView, ProfileView, PrivacyView, UserSearchView, BlockView,
                    AvatarFileView, OwnWallpaperView)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("verify-email/<uidb64>/<token>/", VerifyEmailView.as_view(), name="verify-email"),
    path("resend-verification/", ResendVerificationView.as_view(), name="resend-verification"),
    path("password-reset/", PasswordResetRequestView.as_view(), name="password-reset-request"),
    path("password-reset/<uidb64>/<token>/", PasswordResetPageView.as_view(), name="password-reset-page"),
    path("change-password/", ChangePasswordView.as_view(), name="change-password"),
    path("login/", LoginView.as_view(), name="token-obtain"),       # JWT, verified emails only
    path("refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("logout/", TokenBlacklistView.as_view(), name="token-blacklist"),
    path("me/", MeView.as_view(), name="me"),
    path("profile/", ProfileView.as_view(), name="profile"),
    path("privacy/", PrivacyView.as_view(), name="privacy"),
    path("users/search/", UserSearchView.as_view(), name="user-search"),
    path("users/<int:user_id>/avatar/", AvatarFileView.as_view(), name="user-avatar"),
    path("wallpaper/", OwnWallpaperView.as_view(), name="own-wallpaper"),
    path("block/", BlockView.as_view(), name="block"),
]
