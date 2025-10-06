from rest_framework import serializers
from .conf import get_form_policy
from .validators import is_valid_email, is_valid_phone, is_valid_postal

_VALIDATOR_MAP = {
    "email": is_valid_email,
    "phone": is_valid_phone,
    "postal": is_valid_postal,
}

class BooleanLikeField(serializers.BooleanField):
    TRUE_SET = {"true", "1", "on", "yes", "y", "t"}
    FALSE_SET = {"false", "0", "off", "no", "n", "f"}

    def to_internal_value(self, data):
        # Accepte bool natif
        if isinstance(data, bool):
            return data
        # Accepte None -> laisse DRF gérer required/blank
        if data is None:
            return super().to_internal_value(data)

        # Normalise chaînes
        if isinstance(data, str):
            s = data.strip().lower()
            if s in self.TRUE_SET:
                return True
            if s in self.FALSE_SET:
                return False

        # Fallback DRF (lèvera ValidationError si inacceptable)
        return super().to_internal_value(data)

class DynamicLeadSerializer(serializers.Serializer):
    # socle commun minimal
    form_kind = serializers.CharField()
    client_ts = serializers.DateTimeField(required=False, allow_null=True)
    campaign = serializers.CharField(required=False, allow_blank=True)
    source = serializers.CharField(required=False, allow_blank=True)
    utm_source = serializers.CharField(required=False, allow_blank=True)
    utm_medium = serializers.CharField(required=False, allow_blank=True)
    utm_campaign = serializers.CharField(required=False, allow_blank=True)
    context = serializers.JSONField(required=False)
    signed_token = serializers.CharField(required=False, allow_blank=True)
    honeypot = serializers.CharField(required=False, allow_blank=True)
    consent = serializers.BooleanField(required=False)

    # on acceptera n'importe quel champ dynamique sans lever d'erreur
    def to_internal_value(self, data):
        kind = (data.get("form_kind") or "").strip()
        campaign = (data.get("campaign") or "").strip() or None
        policy = get_form_policy(kind, campaign)
        fields_pol = policy.get("fields") or {}

        for fname, spec in fields_pol.items():
            if fname in self.fields:
                continue
            req = bool(spec.get("required", False))
            allow_blank = not req
            max_length = spec.get("max_length")
            ftype = (spec.get("type") or "string").lower()

            if ftype in ("bool", "boolean"):
                field = BooleanLikeField(required=req)
            elif ftype in ("json", "object", "dict"):
                field = serializers.JSONField(required=req)
            else:
                field = serializers.CharField(required=req, allow_blank=allow_blank,
                                              max_length=max_length, allow_null=False)

            self.fields[fname] = field

        return super().to_internal_value(data)

    def validate(self, attrs):
        kind = attrs.get("form_kind", "")
        campaign = attrs.get("campaign")
        policy = get_form_policy(kind, campaign)
        fields_pol = policy.get("fields") or {}

        # validators personnalisés
        for fname, spec in fields_pol.items():
            val = attrs.get(fname, "")
            for vname in spec.get("validators", []):
                fn = _VALIDATOR_MAP.get(vname)
                if fn and val and not fn(val):
                    raise serializers.ValidationError({fname: f"Format invalide ({vname})."})

        return attrs