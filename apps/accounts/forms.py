# accounts/forms.py
from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _

class LoginForm(AuthenticationForm):
    # On garde le champ *username*, mais on l'étiquette proprement
    username = forms.CharField(label=_("Email ou nom d’utilisateur"))
    remember_me = forms.BooleanField(required=False, initial=False, label=_("Rester connecté"))

    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request, *args, **kwargs)
        self.fields["username"].widget.attrs.update({"autofocus": True})

    # Autoriser l'email: si on tape un email, on le convertit en username attendu par le backend
    def clean_username(self):
        ident = self.cleaned_data.get("username")
        if not ident:
            return ident
        try:
            user = User.objects.get(email__iexact=ident)
            return user.username
        except User.DoesNotExist:
            return ident
