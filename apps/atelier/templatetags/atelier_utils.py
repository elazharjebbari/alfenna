from __future__ import annotations
from django import template
from django.template import Template, Context
from django.utils.safestring import mark_safe

register = template.Library()

@register.simple_tag(takes_context=True)
def render_string(context, tpl_string: str = "") -> str:
    """
    Évalue une chaîne comme un template Django avec le contexte courant.
    Usage : {% render_string item.html %}
    Sécurisé car nos manifests sont internes (pas de contenu utilisateur).
    """
    if not isinstance(tpl_string, str) or not tpl_string:
        return ""
    try:
        tpl = Template(tpl_string)
        data = context.flatten()  # RequestContext -> dict
        return mark_safe(tpl.render(Context(data)))
    except Exception:
        # Fallback: on renvoie la chaîne brute si un souci survient
        return tpl_string
