# accounts/views.py
import logging
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.views import (
    LoginView,
    PasswordResetView,
    PasswordResetDoneView,
    PasswordResetConfirmView,
    PasswordResetCompleteView,
)
from django.core.cache import cache
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.http import (
    HttpResponseNotAllowed,
    HttpResponse,
    HttpResponseBadRequest,
    JsonResponse,
)
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlencode, urlsafe_base64_encode
from django.utils.translation import gettext as _
from django.views import View
from django.views.generic import TemplateView, FormView

from .forms import LoginForm
from .forms_signup import SignupForm
from .forms_password_reset import OutboxPasswordResetForm
from .services import enqueue_email_verification
from .utils import resolve_safe_next_url
from .mixins import VerifiedEmailRequiredMixin
from apps.atelier.compose import pipeline, response
from apps.messaging.constants import (
    ACTIVATION_TTL_SECONDS,
    TOKEN_NAMESPACE_ACCOUNTS,
    TOKEN_PURPOSE_ACTIVATION,
)
from apps.messaging.exceptions import TokenExpiredError, TokenInvalidError
from apps.messaging.tokens import TokenService
from apps.messaging.models import OutboxEmail

log = logging.getLogger("accounts")
UserModel = get_user_model()

# Throttle simple: 5 tentatives/10 minutes par IP + identifiant
THROTTLE_ATTEMPTS = 5
THROTTLE_WINDOW = 10 * 60  # seconds
LOCK_SECONDS = 10 * 60

CHECK_EMAIL_SESSION_KEY = "accounts:pending_email"
CHECK_EMAIL_NEXT_SESSION_KEY = "accounts:pending_next"
PASSWORD_RESET_FLOWS_SESSION_KEY = "accounts:password_reset_flows"
PASSWORD_RESET_LAST_FLOW_KEY = "accounts:last_reset_flow_id"
VERIFICATION_ERROR_SESSION_KEY = "accounts:verification_error"
VERIFICATION_JUST_SENT_SESSION_KEY = "accounts:verification_just_sent"
VERIFICATION_LAST_SENT_SESSION_KEY = "accounts:verification_last_sent_ts"
VERIFICATION_RESEND_COOLDOWN_SECONDS = 60

DEFAULT_MAX_ATTEMPTS = getattr(settings, "PASSWORD_RESET_MAX_ATTEMPTS", 5)


def _mask_email_address(email: str | None) -> str:
    if not email:
        return "—"
    parts = str(email).split("@", 1)
    local = parts[0] if parts else ""
    prefix = (local[:1] or "*")
    return f"{prefix}***@***"


def _mark_verification_sent(request) -> None:
    request.session[VERIFICATION_JUST_SENT_SESSION_KEY] = True
    request.session[VERIFICATION_LAST_SENT_SESSION_KEY] = timezone.now().timestamp()
    request.session.modified = True


def redirect_reset_qs_to_confirm(request):
    uid = request.GET.get("uid")
    token = request.GET.get("token")
    if not uid or not token:
        return HttpResponseBadRequest("Missing uid or token.")

    url = reverse("accounts:password_reset_confirm", kwargs={"uidb64": uid, "token": token})
    next_value = request.GET.get("next")
    if next_value:
        url = f"{url}?{urlencode({'next': next_value})}"
    return redirect(url)


def _key(ip, ident):
    return f"login-attempts:{ip}:{ident or ''}"

class LoginViewSafe(LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["next_value"] = resolve_safe_next_url(self.request)
        return context

    def form_invalid(self, form):
        ip = self.request.META.get("REMOTE_ADDR", "0.0.0.0")
        ident = self.request.POST.get("username", "").strip().lower()
        key = _key(ip, ident)
        count = cache.get(key, 0) + 1
        cache.set(key, count, THROTTLE_WINDOW)
        if count >= THROTTLE_ATTEMPTS:
            cache.set(key + ":lock", True, LOCK_SECONDS)
            log.warning("Login lockout for ip=%s ident=%s", ip, ident)
            messages.error(self.request, _("Trop de tentatives. Réessayez plus tard."))
            return HttpResponse(status=429)
        messages.error(self.request, _("Identifiants invalides."))
        return super().form_invalid(form)

    def form_valid(self, form):
        ip = self.request.META.get("REMOTE_ADDR", "0.0.0.0")
        ident = self.request.POST.get("username", "").strip().lower()
        if cache.get(_key(ip, ident) + ":lock"):
            messages.error(self.request, _("Trop de tentatives. Réessayez plus tard."))
            return HttpResponse(status=429)

        user = form.get_user()
        login(self.request, user)

        remember = form.cleaned_data.get("remember_me")
        if remember:
            self.request.session.set_expiry(getattr(settings, "SESSION_COOKIE_AGE", 1209600))
        else:
            self.request.session.set_expiry(0)

        messages.success(self.request, _("Connexion réussie."))

        profile = getattr(user, "profile", None)
        if not profile or not getattr(profile, "email_verified", False):
            enqueue_email_verification(user)
            _mark_verification_sent(self.request)
            messages.warning(self.request, _("Vérifie ton email pour accéder à tout le contenu."))
            return redirect("pages:check_email")

        return redirect(self.get_success_url())

    def get_success_url(self):
        return super().get_success_url()

class LogoutViewPostOnly(View):
    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("pages:login")
        logout(request)
        messages.success(request, _("Vous êtes déconnecté."))
        return redirect("pages:login")

    def get(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(["POST"])

class ProfileView(LoginRequiredMixin, VerifiedEmailRequiredMixin, TemplateView):
    template_name = "accounts/profile.html"
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        self.meta_title = "Mon compte"
        self.meta_description = "Espace privé."
        self.meta_noindex = True
        return ctx

class ResendVerificationView(LoginRequiredMixin, TemplateView):
    template_name = "accounts/resend_verification.html"

    def dispatch(self, request, *args, **kwargs):
        profile = getattr(request.user, "profile", None)
        if profile and getattr(profile, "email_verified", False):
            messages.info(request, _("Ton email est déjà vérifié."))
            return redirect("accounts:profile")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session = self.request.session
        just_sent = bool(session.pop(VERIFICATION_JUST_SENT_SESSION_KEY, False))
        if just_sent:
            session.modified = True
        cooldown_remaining = self._cooldown_remaining()
        context.update(
            {
                "masked_email": _mask_email_address(getattr(self.request.user, "email", "")),
                "verification_just_sent": just_sent,
                "cooldown_remaining": cooldown_remaining,
                "can_resend": cooldown_remaining == 0,
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        remaining = self._cooldown_remaining()
        if remaining > 0:
            messages.info(
                request,
                _( "Merci de patienter %(seconds)s secondes avant de renvoyer un nouvel email." )
                % {"seconds": remaining},
            )
            return redirect("accounts:resend_verification")

        enqueue_email_verification(request.user)
        _mark_verification_sent(request)
        messages.success(request, _("Un lien de vérification vient d’être envoyé."))
        return redirect("accounts:resend_verification")

    def _cooldown_remaining(self) -> int:
        last_sent_ts = self.request.session.get(VERIFICATION_LAST_SENT_SESSION_KEY)
        if not last_sent_ts:
            return 0
        try:
            elapsed = timezone.now().timestamp() - float(last_sent_ts)
        except (TypeError, ValueError):
            return 0
        if elapsed < 0:
            return VERIFICATION_RESEND_COOLDOWN_SECONDS
        remaining = VERIFICATION_RESEND_COOLDOWN_SECONDS - int(elapsed)
        return max(0, remaining)


class AtelierPageMixin:
    page_id: str

    def get_page_extra(self) -> dict:
        return {}

    def render_page(self, extra=None, *, status: int = 200):
        payload = dict(extra or {})
        page_ctx = pipeline.build_page_spec(self.page_id, self.request, extra=payload)
        fragments = {}
        for slot_id, slot_ctx in (page_ctx.get("slots") or {}).items():
            rendered = pipeline.render_slot_fragment(page_ctx, slot_ctx, self.request)
            fragments[slot_id] = rendered.get("html", "")
        assets = pipeline.collect_page_assets(page_ctx)
        resp = response.render_base(page_ctx, fragments, assets, self.request)
        resp.status_code = status
        return resp

    def get(self, request, *args, **kwargs):
        return self.render_page(self.get_page_extra())


class AtelierFormPageMixin(AtelierPageMixin):
    pipeline_context_keys: tuple[str, ...] = ()

    def get_form_page_extra(self, form=None) -> dict:
        return {}

    def render_form_page(
        self,
        form,
        *,
        status: int = 200,
        extra=None,
        include_default_extra: bool = True,
    ):
        payload: dict = {"form": form}
        if include_default_extra:
            default_extra = self.get_form_page_extra(form=form)
            if default_extra:
                payload.update(default_extra)
        if extra:
            payload.update(extra)
        return self.render_page(payload, status=status)

    def render_to_response(self, context, **response_kwargs):
        form = context.get("form")
        default_extra = self.get_form_page_extra(form=form)
        pipeline_extra = {
            key: context.get(key)
            for key in self.pipeline_context_keys
            if key in context
        }
        combined_extra: dict = {}
        if default_extra:
            combined_extra.update(default_extra)
        if pipeline_extra:
            combined_extra.update(pipeline_extra)
        status = response_kwargs.pop("status", 200)
        return self.render_form_page(
            form,
            status=status,
            extra=combined_extra,
            include_default_extra=False,
        )

    def form_invalid(self, form):
        return self.render_form_page(form, status=400)


class SignupView(AtelierFormPageMixin, FormView):
    page_id = "register"
    template_name = "accounts/register.html"
    form_class = SignupForm
    success_url = reverse_lazy("pages:check_email")

    _pending_next: str | None = None

    def get_form_page_extra(self, form=None) -> dict:
        return {"next_value": resolve_safe_next_url(self.request)}

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("accounts:profile")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        return kwargs

    def get(self, request, *args, **kwargs):
        form = self.get_form()
        return self.render_form_page(form)

    def form_valid(self, form):
        try:
            user = form.save()
        except IntegrityError:
            form.add_error("email", _("Un compte existe déjà avec cette adresse e-mail."))
            return self.render_form_page(form, status=400)
        self._pending_next = resolve_safe_next_url(self.request) or None
        self.request.session[CHECK_EMAIL_SESSION_KEY] = user.email
        if self._pending_next:
            self.request.session[CHECK_EMAIL_NEXT_SESSION_KEY] = self._pending_next
        self._enqueue_email_verification(user)
        return redirect(self.get_success_url())

    def form_invalid(self, form):
        if form.non_field_errors():
            for error in form.non_field_errors():
                messages.error(self.request, error)
        return super().form_invalid(form)

    def get_success_url(self):
        base = super().get_success_url()
        next_url = getattr(self, "_pending_next", None) or resolve_safe_next_url(self.request)
        if next_url:
            return f"{base}?{urlencode({'next': next_url})}"
        return base

    def _enqueue_email_verification(self, user):
        enqueue_email_verification(user)


class CheckEmailView(AtelierPageMixin, TemplateView):
    page_id = "check_email"
    template_name = "accounts/check_email.html"

    def get_page_extra(self) -> dict:
        email = self.request.session.pop(CHECK_EMAIL_SESSION_KEY, None) or self.request.GET.get("email")
        next_hint = self.request.session.pop(CHECK_EMAIL_NEXT_SESSION_KEY, None)
        next_value = resolve_safe_next_url(self.request, next_hint)
        extra: dict = {}
        if email:
            extra["email"] = email
        login_url = reverse("pages:login")
        if next_value:
            extra["next_value"] = next_value
            login_url = f"{login_url}?{urlencode({'next': next_value})}"
        extra["login_url"] = login_url
        return extra


class ActivateAccountView(View):
    """Handle activation links coming from transactional e-mails."""

    def get(self, request, *args, **kwargs):
        token = request.GET.get("t")
        if not token:
            return HttpResponseBadRequest("Missing activation token.")

        try:
            payload = TokenService.read_signed(
                token,
                namespace=TOKEN_NAMESPACE_ACCOUNTS,
                purpose=TOKEN_PURPOSE_ACTIVATION,
                ttl_seconds=ACTIVATION_TTL_SECONDS,
            )
        except TokenExpiredError:
            return HttpResponseBadRequest("Activation link expired.")
        except TokenInvalidError:
            return HttpResponseBadRequest("Activation link invalid.")

        user_id = payload.claims.get("user_id")
        if not user_id:
            return HttpResponseBadRequest("Activation payload incomplete.")

        try:
            user = UserModel.objects.get(pk=user_id)
        except UserModel.DoesNotExist:
            return HttpResponseBadRequest("User not found.")

        updated = False
        if not user.is_active:
            user.is_active = True
            updated = True
        if updated:
            user.save(update_fields=["is_active"])

        if not user.has_usable_password():
            uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
            reset_token = default_token_generator.make_token(user)
            return redirect(
                "accounts:password_reset_confirm",
                uidb64=uidb64,
                token=reset_token,
            )

        messages.info(request, _("Ton compte est déjà activé. Tu peux te connecter."))
        return redirect("pages:login")


class PasswordResetRequestView(AtelierFormPageMixin, PasswordResetView):
    page_id = "password_reset"
    form_class = OutboxPasswordResetForm
    template_name = "accounts/password_reset_form.html"
    success_url = reverse_lazy("accounts:password_reset_done")
    _reset_next: str | None = None

    def get_form_page_extra(self, form=None) -> dict:
        return {"next_value": resolve_safe_next_url(self.request)}

    def get(self, request, *args, **kwargs):
        form = self.get_form()
        return self.render_form_page(form)

    def form_valid(self, form):
        self._reset_next = resolve_safe_next_url(self.request) or None
        form.save(request=self.request, next_url=self._reset_next)
        flow = getattr(form, "primary_flow", {"flow_id": "", "state": "noop"})
        flows = self.request.session.get(PASSWORD_RESET_FLOWS_SESSION_KEY, {})
        if flow.get("flow_id"):
            flows[flow["flow_id"]] = flow
            self.request.session[PASSWORD_RESET_LAST_FLOW_KEY] = flow["flow_id"]
        else:
            # Même si aucun flow-id n'est connu, conserver une trace "noop" pour l’UX minuteur.
            generated = flow.get("flow_id") or ""
            if generated:
                flows[generated] = flow
                self.request.session[PASSWORD_RESET_LAST_FLOW_KEY] = generated
        self.request.session[PASSWORD_RESET_FLOWS_SESSION_KEY] = flows
        self.request.session.modified = True
        messages.info(self.request, _("Si l'adresse existe, un e-mail vient d'être envoyé."))
        return redirect(self.get_success_url())

    def form_invalid(self, form):
        return super().form_invalid(form)

    def get_success_url(self):
        base = super().get_success_url()
        next_url = self._reset_next or resolve_safe_next_url(self.request)
        if next_url:
            return f"{base}?{urlencode({'next': next_url})}"
        return base


class PasswordResetDoneViewCustom(AtelierPageMixin, PasswordResetDoneView):
    page_id = "password_reset_done"
    template_name = "accounts/password_reset_done.html"

    def get_page_extra(self) -> dict:
        next_value = resolve_safe_next_url(self.request)
        login_url = reverse("pages:login")
        if next_value:
            login_url = f"{login_url}?{urlencode({'next': next_value})}"
        flows = self.request.session.get(PASSWORD_RESET_FLOWS_SESSION_KEY, {})
        last_flow_id = self.request.session.get(PASSWORD_RESET_LAST_FLOW_KEY)
        flow_data = flows.get(last_flow_id) if last_flow_id else None
        status_url = (
            reverse("accounts:password_reset_status", kwargs={"flow_id": last_flow_id})
            if last_flow_id
            else ""
        )
        initial_state = flow_data or {"state": "noop"}
        return {
            "next_value": next_value,
            "login_url": login_url,
            "reset_flow": {
                "flow_id": last_flow_id or "",
                **initial_state,
            },
            "status_url": status_url,
        }


class PasswordResetStatusView(View):
    http_method_names = ["get"]

    def get(self, request, flow_id: str, *args, **kwargs) -> JsonResponse:
        flows = request.session.get(PASSWORD_RESET_FLOWS_SESSION_KEY, {})
        flow = flows.get(flow_id)
        payload: dict[str, object] = {"flow_id": flow_id}

        max_attempts = getattr(settings, "PASSWORD_RESET_MAX_ATTEMPTS", DEFAULT_MAX_ATTEMPTS)

        if not flow:
            payload.update({"state": "noop", "attempt_count": 0, "max_attempts": max_attempts})
            return JsonResponse(payload)

        outbox = OutboxEmail.objects.filter(flow_id=flow_id).first()
        if not outbox:
            payload.update(
                {
                    "state": flow.get("state", "noop"),
                    "attempt_count": flow.get("attempt_count", 0),
                    "max_attempts": max_attempts,
                    "next_attempt_eta": flow.get("next_attempt_eta"),
                }
            )
            return JsonResponse(payload)

        if outbox.status == OutboxEmail.Status.SENT:
            state = "sent"
        elif outbox.status == OutboxEmail.Status.SUPPRESSED:
            state = "suppressed"
        else:
            state = "retrying" if outbox.status == OutboxEmail.Status.RETRYING else "queued"

        next_eta = outbox.next_attempt_at or outbox.scheduled_at
        if state == "queued" and outbox.attempt_count > 0 and next_eta and next_eta > timezone.now():
            state = "retrying"

        payload.update(
            {
                "state": state,
                "attempt_count": outbox.attempt_count,
                "max_attempts": max_attempts,
                "next_attempt_eta": next_eta.isoformat() if next_eta else None,
                "issue_code": outbox.last_error_code,
            }
        )

        flows[flow_id] = {
            "flow_id": flow_id,
            "state": state,
            "attempt_count": outbox.attempt_count,
            "next_attempt_eta": payload["next_attempt_eta"],
            "created_at": flow.get("created_at"),
        }

        if state in {"sent", "suppressed"}:
            flows.pop(flow_id, None)
            if request.session.get(PASSWORD_RESET_LAST_FLOW_KEY) == flow_id:
                request.session.pop(PASSWORD_RESET_LAST_FLOW_KEY, None)
        request.session[PASSWORD_RESET_FLOWS_SESSION_KEY] = flows
        request.session.modified = True

        return JsonResponse(payload)


class PasswordResetConfirmViewCustom(AtelierFormPageMixin, PasswordResetConfirmView):
    page_id = "password_reset_confirm"
    template_name = "accounts/password_reset_confirm.html"
    success_url = reverse_lazy("accounts:password_reset_complete")
    pipeline_context_keys = ("validlink",)

    def get_form_page_extra(self, form=None) -> dict:
        return {"next_value": resolve_safe_next_url(self.request)}

    def get_success_url(self):
        base = super().get_success_url()
        next_url = resolve_safe_next_url(self.request)
        if next_url:
            return f"{base}?{urlencode({'next': next_url})}"
        return base


class PasswordResetCompleteViewCustom(AtelierPageMixin, PasswordResetCompleteView):
    page_id = "password_reset_complete"
    template_name = "accounts/password_reset_complete.html"

    def get_page_extra(self) -> dict:
        next_value = resolve_safe_next_url(self.request)
        login_url = reverse("pages:login")
        if next_value:
            login_url = f"{login_url}?{urlencode({'next': next_value})}"
        return {"next_value": next_value, "login_url": login_url}



class VerificationSuccessView(AtelierPageMixin, TemplateView):
    page_id = "verification_success"
    template_name = "accounts/verification_success.html"

    def get_page_extra(self) -> dict:
        next_value = resolve_safe_next_url(self.request)
        login_url = reverse("pages:login")
        if next_value:
            login_url = f"{login_url}?{urlencode({'next': next_value})}"
        return {"next_value": next_value, "login_url": login_url}


class VerificationErrorView(AtelierPageMixin, TemplateView):
    page_id = "verification_error"
    template_name = "accounts/verification_error.html"

    def get_page_extra(self) -> dict:
        message = self.request.session.pop(VERIFICATION_ERROR_SESSION_KEY, None)
        return {"message": message}
