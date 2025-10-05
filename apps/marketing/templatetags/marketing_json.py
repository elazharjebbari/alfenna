import json
from django import template

register = template.Library()

@register.filter
def tojson(value):
    """
    Sérialise value (dict/list) en JSON. Retourne "" si échec.
    """
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return ""
