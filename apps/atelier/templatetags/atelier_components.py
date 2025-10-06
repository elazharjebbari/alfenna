"""
Templatetag de rendu de composant (placeholder).
Étape 1: aucun rendu spécial, juste structure.
"""

from django import template

register = template.Library()

@register.simple_tag
def render_component(alias: str, **context):
    """À l'étape 1: ne renvoie rien (implémentation ultérieure)."""
    return ""