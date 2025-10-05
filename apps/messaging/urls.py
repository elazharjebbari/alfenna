"""Messaging endpoints (to be filled in Step 6)."""
from __future__ import annotations

from django.urls import path

from . import views

app_name = "messaging"

urlpatterns = [
    path("health/", views.healthcheck, name="healthcheck"),
    path("verify/", views.VerifyEmailView.as_view(), name="verify-email"),
    path("unsubscribe/", views.UnsubscribeView.as_view(), name="unsubscribe"),
    path("reset/request/", views.PasswordResetRequestView.as_view(), name="password-reset-request"),
    path("reset/confirm/", views.PasswordResetConfirmView.as_view(), name="password-reset-confirm"),
]
