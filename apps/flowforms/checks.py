from __future__ import annotations
from django.core.checks import register, Error
from django.urls import reverse, NoReverseMatch
from django.conf import settings

@register()
def check_flowforms_endpoints(app_configs, **kwargs):
    errors = []
    # collect
    try:
        reverse(getattr(settings, "FLOWFORMS_ENDPOINT_COLLECT_URLNAME", "leads:collect"))
    except NoReverseMatch:
        errors.append(Error(
            "FLOWFORMS: URL 'leads:collect' introuvable",
            hint="Déclare 'name=\"collect\"' dans apps.leads.urls (namespace 'leads').",
            id="flowforms.E001",
        ))
    # sign (optionnel)
    if getattr(settings, "FLOWFORMS_REQUIRE_SIGNED", False):
        try:
            reverse(getattr(settings, "FLOWFORMS_SIGN_URLNAME", "leads:sign"))
        except NoReverseMatch:
            errors.append(Error(
                "FLOWFORMS: URL 'leads:sign' introuvable alors que REQUIRE_SIGNED=True",
                hint="Déclare 'name=\"sign\"' dans apps.leads.urls (namespace 'leads') ou désactive la signature.",
                id="flowforms.E002",
            ))
    return errors
