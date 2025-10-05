from django import template
from django.urls import reverse, NoReverseMatch

register = template.Library()

@register.simple_tag
def safe_url(name, default="#", *args, **kwargs):
    """
    Usage : {% safe_url 'register' as reg_url %} <a href="{{ reg_url }}">...</a>
    Retourne `default` si la résolution échoue.
    """
    try:
        return reverse(name, args=args, kwargs=kwargs)
    except NoReverseMatch:
        return default