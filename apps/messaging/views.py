"""Public endpoints for messaging flows."""
from __future__ import annotations

import logging
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.shortcuts import redirect
from django.urls import reverse
from django.views import View
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .constants import (
    DEFAULT_SITE_NAME,
    EMAIL_VERIFICATION_TTL_SECONDS,
    PASSWORD_RESET_TTL_SECONDS,
    TOKEN_NAMESPACE_ACCOUNTS,
    TOKEN_PURPOSE_UNSUBSCRIBE,
    TOKEN_PURPOSE_VERIFY_EMAIL,
    UNSUBSCRIBE_TTL_SECONDS,
)
from .exceptions import TokenExpiredError, TokenInvalidError
from .serializers import PasswordResetConfirmSerializer, PasswordResetRequestSerializer
from .services import EmailService
from .throttling import MessagingEmailThrottle, MessagingIPThrottle
from .tokens import TokenService
from .utils import secure_base_url

log = logging.getLogger("messaging.views")
UserModel = get_user_model()


VERIFICATION_ERROR_SESSION_KEY = "accounts:verification_error"


def healthcheck(_request: HttpRequest) -> JsonResponse:
    """Simple readiness endpoint used by smoke tests."""
    return JsonResponse({"status": "ok", "app": "messaging"})


class MessagingBaseView(View):
    http_method_names = ["get"]

    def _missing_token(self) -> JsonResponse:
        return JsonResponse({"status": "error", "code": "missing_token"}, status=400)

    def _expired(self, message: str) -> JsonResponse:
        return JsonResponse({"status": "error", "code": "expired", "detail": message}, status=410)

    def _invalid(self, message: str) -> JsonResponse:
        return JsonResponse({"status": "error", "code": "invalid", "detail": message}, status=400)


class VerifyEmailView(MessagingBaseView):
    def get(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        redirect_mode = request.GET.get("redirect", "1") != "0"
        token = request.GET.get("t")
        if not token:
            if redirect_mode:
                request.session[VERIFICATION_ERROR_SESSION_KEY] = "Token manquant."
                return redirect(reverse("pages:verification_error"))
            return self._missing_token()
        try:
            payload = TokenService.read_signed(
                token,
                namespace=TOKEN_NAMESPACE_ACCOUNTS,
                purpose=TOKEN_PURPOSE_VERIFY_EMAIL,
                ttl_seconds=EMAIL_VERIFICATION_TTL_SECONDS,
            )
        except TokenExpiredError:
            if redirect_mode:
                request.session[VERIFICATION_ERROR_SESSION_KEY] = "Token expiré. Merci de demander un nouveau lien."
                return redirect(reverse("pages:verification_error"))
            return self._expired("Token expiré. Merci de demander un nouveau lien.")
        except TokenInvalidError:
            if redirect_mode:
                request.session[VERIFICATION_ERROR_SESSION_KEY] = "Token invalide."
                return redirect(reverse("pages:verification_error"))
            return self._invalid("Token invalide.")

        user_id = payload.claims.get("user_id")
        if not user_id:
            if redirect_mode:
                request.session[VERIFICATION_ERROR_SESSION_KEY] = "Requête incomplète."
                return redirect(reverse("pages:verification_error"))
            return self._invalid("Requête incomplète.")

        try:
            user = UserModel.objects.select_related("profile").get(pk=user_id)
        except UserModel.DoesNotExist:
            if redirect_mode:
                request.session[VERIFICATION_ERROR_SESSION_KEY] = "Utilisateur introuvable."
                return redirect(reverse("pages:verification_error"))
            return self._invalid("Utilisateur introuvable.")

        profile = getattr(user, "profile", None)
        if not profile:
            if redirect_mode:
                request.session[VERIFICATION_ERROR_SESSION_KEY] = "Profil utilisateur indisponible."
                return redirect(reverse("pages:verification_error"))
            return self._invalid("Profil utilisateur indisponible.")

        now = timezone.now()
        update_fields = ["email_verified", "email_verified_at"]
        if hasattr(profile, "updated_at"):
            update_fields.append("updated_at")
        if not profile.email_verified:
            profile.email_verified = True
            profile.email_verified_at = now
            profile.save(update_fields=update_fields)
            log.info("email_verified", extra={"user_id": user.id})

        if redirect_mode:
            request.session.pop(VERIFICATION_ERROR_SESSION_KEY, None)
            return redirect(reverse("pages:verification_success"))

        return JsonResponse(
            {
                "status": "verified",
                "user_id": user.id,
                "email": user.email,
                "verified_at": profile.email_verified_at.isoformat() if profile.email_verified_at else None,
            }
        )


class UnsubscribeView(MessagingBaseView):
    def get(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        token = request.GET.get("t")
        if not token:
            return self._missing_token()
        try:
            payload = TokenService.read_signed(
                token,
                namespace=TOKEN_NAMESPACE_ACCOUNTS,
                purpose=TOKEN_PURPOSE_UNSUBSCRIBE,
                ttl_seconds=UNSUBSCRIBE_TTL_SECONDS,
            )
        except TokenExpiredError:
            return self._expired("Lien expiré. Merci de te désinscrire via ton espace.")
        except TokenInvalidError:
            return self._invalid("Token invalide.")

        user_id = payload.claims.get("user_id")
        if not user_id:
            return self._invalid("Requête incomplète.")

        try:
            user = UserModel.objects.select_related("profile").get(pk=user_id)
        except UserModel.DoesNotExist:
            return self._invalid("Utilisateur introuvable.")

        profile = getattr(user, "profile", None)
        if not profile:
            return self._invalid("Profil utilisateur indisponible.")

        now = timezone.now()
        update_fields = ["marketing_opt_in", "marketing_opt_out_at"]
        if hasattr(profile, "updated_at"):
            update_fields.append("updated_at")
        if profile.marketing_opt_in or profile.marketing_opt_out_at is None:
            profile.marketing_opt_in = False
            profile.marketing_opt_out_at = now
            profile.save(update_fields=update_fields)
            log.info("marketing_unsubscribe", extra={"user_id": user.id})

        return JsonResponse(
            {
                "status": "unsubscribed",
                "user_id": user.id,
                "email": user.email,
                "unsubscribed_at": profile.marketing_opt_out_at.isoformat() if profile.marketing_opt_out_at else None,
            }
        )


class PasswordResetRequestView(APIView):
    throttle_classes = [MessagingIPThrottle, MessagingEmailThrottle]
    throttle_purpose = "password-reset-request"

    def post(self, request: HttpRequest, *args, **kwargs) -> Response:
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = getattr(serializer, "user", None)
        if user:
            self._enqueue_reset_email(request, user)
        return Response({"status": "accepted"}, status=status.HTTP_202_ACCEPTED)

    def _enqueue_reset_email(self, request: HttpRequest, user) -> None:
        base_url = secure_base_url()
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        path = reverse(
            "accounts:password_reset_confirm",
            kwargs={"uidb64": uid, "token": token},
        )
        reset_url = f"{base_url}{path}"

        site_name = getattr(settings, "SITE_NAME", settings.SEO_DEFAULTS.get("site_name", DEFAULT_SITE_NAME))
        support_email = getattr(settings, "SUPPORT_EMAIL", settings.DEFAULT_FROM_EMAIL)
        first_name = user.first_name or user.username or user.email

        EmailService.compose_and_enqueue(
            namespace="accounts",
            purpose="password_reset",
            template_slug="accounts/reset",
            to=[user.email],
            context={
                "user_first_name": first_name,
                "reset_url": reset_url,
                "reset_ttl_minutes": PASSWORD_RESET_TTL_SECONDS // 60,
                "site_name": site_name,
                "support_email": support_email,
            },
            metadata={
                "uid": uid,
                "token": "***",
            },
        )
        log.info("password_reset_enqueued", extra={"user_id": user.id})


class PasswordResetConfirmView(APIView):
    throttle_classes = [MessagingIPThrottle]
    throttle_purpose = "password-reset-confirm"

    def post(self, request: HttpRequest, *args, **kwargs) -> Response:
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        new_password = serializer.validated_data["new_password"]
        user.set_password(new_password)
        user.save(update_fields=["password"])
        log.info("password_reset_confirmed", extra={"user_id": user.id})
        return Response({"status": "password_reset"}, status=status.HTTP_200_OK)
