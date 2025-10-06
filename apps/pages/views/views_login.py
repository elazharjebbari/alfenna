# apps/pages/views/views_login.py
from django.contrib.auth import login
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect
from django.contrib import messages
from django.utils.translation import gettext as _
from django.http import HttpResponse
from django.core.cache import cache
from django.conf import settings
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from apps.accounts.forms import LoginForm
from apps.accounts.services import enqueue_email_verification
from apps.atelier.compose import pipeline, response

THROTTLE_WINDOW = 60       # secondes
THROTTLE_ATTEMPTS = 5
LOCK_SECONDS = 600

def _key(ip, ident):
    return f"login:{ip}:{ident}"

VERIFICATION_JUST_SENT_SESSION_KEY = "accounts:verification_just_sent"
VERIFICATION_LAST_SENT_SESSION_KEY = "accounts:verification_last_sent_ts"


def _mark_verification_sent(request) -> None:
    request.session[VERIFICATION_JUST_SENT_SESSION_KEY] = True
    request.session[VERIFICATION_LAST_SENT_SESSION_KEY] = timezone.now().timestamp()
    request.session.modified = True


class LoginViewSafe(LoginView):
    # on rend via pipeline, ce template_name n'est pas utilisé
    template_name = "screens/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    # ----- rendu screen via pipeline -----
    def _render_screen(self, request, form=None, *, status=200):
        page_ctx = pipeline.build_page_spec("login", request, extra={"form": form})
        fragments = {}
        for slot_id, slot_ctx in (page_ctx.get("slots") or {}).items():
            rendered = pipeline.render_slot_fragment(page_ctx, slot_ctx, request)
            fragments[slot_id] = rendered.get("html", "")
        assets = pipeline.collect_page_assets(page_ctx)
        resp = response.render_base(page_ctx, fragments, assets, request)
        resp.status_code = status
        return resp

    # ----- GET -----
    def get(self, request, *args, **kwargs):
        if self.redirect_authenticated_user and request.user.is_authenticated:
            return redirect(self.get_success_url())
        form = self.get_form()
        return self._render_screen(request, form=form)

    # ----- POST invalide -----
    def form_invalid(self, form):
        ip = self.request.META.get("REMOTE_ADDR", "0.0.0.0")
        ident = self.request.POST.get("username", "").strip().lower()
        key = _key(ip, ident)
        count = cache.get(key, 0) + 1
        cache.set(key, count, THROTTLE_WINDOW)
        if count >= THROTTLE_ATTEMPTS:
            cache.set(key + ":lock", True, LOCK_SECONDS)
            messages.error(self.request, _("Trop de tentatives. Réessayez plus tard."))
            return self._render_screen(self.request, form=form, status=429)

        messages.error(self.request, _("Identifiants invalides."))
        return self._render_screen(self.request, form=form, status=400)

    # ----- POST valide -----
    def form_valid(self, form):
        ip = self.request.META.get("REMOTE_ADDR", "0.0.0.0")
        ident = self.request.POST.get("username", "").strip().lower()
        if cache.get(_key(ip, ident) + ":lock"):
            messages.error(self.request, _("Trop de tentatives. Réessayez plus tard."))
            return self._render_screen(self.request, form=form, status=429)

        user = form.get_user()
        login(self.request, user)

        remember = form.cleaned_data.get("remember_me")
        self.request.session.set_expiry(getattr(settings, "SESSION_COOKIE_AGE", 1209600) if remember else 0)

        messages.success(self.request, _("Connexion réussie."))

        profile = getattr(user, "profile", None)
        if not profile or not getattr(profile, "email_verified", False):
            enqueue_email_verification(user)
            _mark_verification_sent(self.request)
            messages.warning(self.request, _("Vérifie ton email pour accéder à tout le contenu."))
            return redirect("pages:check_email")

        # ✅ Priorité au `next` s’il est sûr
        nxt = self.request.POST.get("next") or self.request.GET.get("next")
        if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={self.request.get_host()}):
            return redirect(nxt)

        # ✅ Sinon, on retombe sur LOGIN_REDIRECT_URL (pages:home)
        return redirect(self.get_success_url())
