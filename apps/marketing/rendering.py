# apps/marketing/rendering.py
from typing import Optional, Dict, Any
from django.shortcuts import render
from django.http import HttpRequest, HttpResponse
from meta.views import Meta

from .helpers import get_global_config

def render_with_meta(
    request: HttpRequest,
    template_name: str,
    context: Optional[Dict[str, Any]] = None,
    *,
    title: str = "",
    description: str = "",
    image: str = "",
    object_type: str = "website",
    noindex: bool = False,
    jsonld: Any = None,  # dict or list
) -> HttpResponse:
    """
    Rendu pour FBV avec support django-meta + robots noindex optionnel.
    Injecte:
      - context["meta"] : objet Meta utilisé par _seo_head.html
      - request._meta_override : {"noindex": bool} lu par le context processor pour robots
      - context["seo_jsonld"] : JSON-LD optionnel
    """
    cfg = get_global_config()
    meta = Meta(
        title=title or None,
        description=description or None,
        image=image or (cfg.get("default_image") or None),
        object_type=object_type or "website",
        twitter_site=cfg.get("twitter_site") or None,
        twitter_creator=cfg.get("twitter_creator") or None,
        og_app_id=cfg.get("facebook_app_id") or None,
    )
    seo_override = dict(getattr(request, "_seo_override", {}) or {})
    for key, value in (
        ("title", title),
        ("description", description),
        ("image", image),
        ("og_type", object_type),
    ):
        if value:
            seo_override[key] = value
    if seo_override:
        request._seo_override = seo_override
    request._meta_override = {"noindex": bool(noindex)}
    ctx = dict(context or {})
    ctx["meta"] = meta
    if jsonld:
        ctx["seo_jsonld"] = jsonld
    return render(request, template_name, ctx)
