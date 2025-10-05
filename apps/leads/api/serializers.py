from rest_framework import serializers
from django.utils.translation import gettext_lazy as _

class LeadCheckoutIntentSerializer(BaseLeadSerializer):
    # AVANT: accept_terms = serializers.CharField(...)
    accept_terms = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        # Si l’acceptation est obligatoire pour le checkout, on impose True
        # (si tu as déjà un système de "required flags" dynamiques, branche-le ici)
        if not attrs.get("accept_terms", False):
            raise serializers.ValidationError({"accept_terms": _("Vous devez accepter les conditions.")})
        return attrs
