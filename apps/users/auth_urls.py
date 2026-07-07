from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    LoginView,
    LogoutView,
    MeView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    RegisterView,
    ResendVerificationView,
    VerifyEmailView,
)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="auth-register"),
    path("login/", LoginView.as_view(), name="auth-login"),
    path("refresh/", TokenRefreshView.as_view(), name="auth-refresh"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    path("me/", MeView.as_view(), name="auth-me"),
    path("verify-email/", VerifyEmailView.as_view(), name="auth-verify-email"),
    path("resend-verification/", ResendVerificationView.as_view(), name="auth-resend-verification"),
    path("password-reset/", PasswordResetRequestView.as_view(), name="auth-password-reset"),
    path(
        "password-reset/confirm/",
        PasswordResetConfirmView.as_view(),
        name="auth-password-reset-confirm",
    ),
]
