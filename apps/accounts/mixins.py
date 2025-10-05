# accounts/mixins.py
from django.contrib import messages
from django.shortcuts import redirect
from django.utils.translation import gettext as _

class VerifiedEmailRequiredMixin:
    require_verified_email = True

    def dispatch(self, request, *args, **kwargs):
        if self.require_verified_email and request.user.is_authenticated:
            profile = getattr(request.user, "profile", None)
            if not profile or not profile.email_verified:
                messages.warning(request, _("Veuillez vérifier votre email avant d’accéder à cette page."))
                return redirect("pages:check_email")
        return super().dispatch(request, *args, **kwargs)
