from __future__ import annotations

from typing import Any

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from apps.accounts.models import StudentProfile

User = get_user_model()


class SignupForm(forms.Form):
    full_name = forms.CharField(label=_("Nom complet"), max_length=150)
    email = forms.EmailField(label=_("Adresse e-mail"))
    password1 = forms.CharField(label=_("Mot de passe"), widget=forms.PasswordInput)
    password2 = forms.CharField(label=_("Confirmez le mot de passe"), widget=forms.PasswordInput)
    marketing_opt_in = forms.BooleanField(label=_("Recevoir les offres et actualités"), required=False, initial=True)

    def __init__(self, request=None, *args: Any, **kwargs: Any) -> None:
        self.request = kwargs.pop("request", request)
        super().__init__(*args, **kwargs)

    def clean_full_name(self) -> str:
        return " ".join(self.cleaned_data.get("full_name", "").split()).strip()

    def clean_email(self) -> str:
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(_("Un compte existe déjà avec cette adresse e-mail."))
        return email

    def clean(self) -> dict:
        cleaned = super().clean()
        password1 = cleaned.get("password1")
        password2 = cleaned.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", _("Les mots de passe ne correspondent pas."))
        if password1:
            validate_password(password1)
        return cleaned

    def _generate_username(self, email: str) -> str:
        base = slugify(self.cleaned_data.get("full_name") or "")
        if not base:
            base = slugify(email.split("@", 1)[0]) or "user"
        base = base[:20] or "user"
        candidate = base
        suffix = 1
        while User.objects.filter(username=candidate).exists():
            candidate = f"{base}{suffix}"
            suffix += 1
            if len(candidate) > 150:
                candidate = candidate[:150]
        return candidate

    def save(self) -> User:
        email = self.cleaned_data["email"]
        password = self.cleaned_data["password1"]
        full_name = self.cleaned_data.get("full_name") or ""
        marketing_opt_in = bool(self.cleaned_data.get("marketing_opt_in", False))
        username = self._generate_username(email)

        first_name = ""
        last_name = ""
        if full_name:
            parts = full_name.split()
            if parts:
                first_name = parts[0]
                last_name = " ".join(parts[1:])

        with transaction.atomic():
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
            )

            profile, _ = StudentProfile.objects.get_or_create(user=user)
            profile.marketing_opt_in = marketing_opt_in
            profile.marketing_opt_out_at = None if marketing_opt_in else timezone.now()
            profile.save(update_fields=["marketing_opt_in", "marketing_opt_out_at"])

        return user
