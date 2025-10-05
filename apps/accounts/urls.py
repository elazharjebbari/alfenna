# accounts/urls.py
from django.urls import path
from django.views.generic.base import RedirectView
from .views import (
    LogoutViewPostOnly,
    ProfileView,
    ResendVerificationView,
    SignupView,
    PasswordResetRequestView,
    PasswordResetDoneViewCustom,
    PasswordResetConfirmViewCustom,
    PasswordResetCompleteViewCustom,
    PasswordResetStatusView,
    redirect_reset_qs_to_confirm,
    CheckEmailView,
    ActivateAccountView,
    VerificationSuccessView,
    VerificationErrorView,
)

app_name = "accounts"

urlpatterns = [
    path(
        "login/",
        RedirectView.as_view(pattern_name="pages:login", permanent=False),
        name="login",
    ),
    path("logout/", LogoutViewPostOnly.as_view(), name="logout"),
    path("inscription/", SignupView.as_view(), name="register"),
    path("register/", SignupView.as_view(), name="register_legacy"),
    path("inscription/check-email/", CheckEmailView.as_view(), name="check_email"),
    path("activate/", ActivateAccountView.as_view(), name="activate"),
    path("me/",     ProfileView.as_view(), name="profile"),
    path("resend-verification/", ResendVerificationView.as_view(), name="resend_verification"),
    path("verification/succes/", VerificationSuccessView.as_view(), name="verification_success"),
    path("verification/erreur/", VerificationErrorView.as_view(), name="verification_error"),
    path("password-reset/request/", PasswordResetRequestView.as_view(), name="password_reset_request"),
    path("password-reset/", PasswordResetRequestView.as_view(), name="password_reset"),
    path("password-reset/done/", PasswordResetDoneViewCustom.as_view(), name="password_reset_done"),
    path(
        "password-reset/status/<str:flow_id>/",
        PasswordResetStatusView.as_view(),
        name="password_reset_status",
    ),
    path("password-reset/confirm/<uidb64>/<token>/", PasswordResetConfirmViewCustom.as_view(), name="password_reset_confirm"),
    path("reset/confirm/", redirect_reset_qs_to_confirm, name="password_reset_confirm_qs"),
    path("password-reset/complete/", PasswordResetCompleteViewCustom.as_view(), name="password_reset_complete"),
]
