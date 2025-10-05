"""Serializers supporting messaging API endpoints."""
from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import serializers


UserModel = get_user_model()


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value: str) -> str:
        try:
            user = UserModel.objects.get(email__iexact=value.strip())
        except UserModel.DoesNotExist:
            self.user = None
            return value
        if not user.is_active:
            self.user = None
            return value
        self.user = user
        return value


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        uid = attrs["uid"]
        token = attrs["token"]
        password = attrs["new_password"]

        try:
            uid_int = force_str(urlsafe_base64_decode(uid))
            user = UserModel.objects.get(pk=uid_int)
        except (ValueError, UserModel.DoesNotExist):
            raise serializers.ValidationError({"uid": "Utilisateur introuvable"})

        if not default_token_generator.check_token(user, token):
            raise serializers.ValidationError({"token": "Token invalide ou expiré"})

        validate_password(password, user=user)

        attrs["user"] = user
        return attrs
