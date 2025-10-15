# apps/atelier/compose/response.py
from __future__ import annotations
from typing import Dict, Any
import logging

from django.conf import settings
from django.template.loader import get_template
from django.template import TemplateDoesNotExist
from django.template.response import TemplateResponse
from django.templatetags.static import static

from apps.atelier.compose.pages import page_meta
from apps.atelier.config.loader import FALLBACK_NAMESPACE

log = logging.getLogger("atelier.compose.response")


class NamespaceTemplateMissing(TemplateDoesNotExist):
    """Aucun template d'écran trouvé pour le namespace indiqué ni le fallback."""


def _alias_to_ctx_key(alias: str) -> str:
    """
    Convertit un alias de composant en clé de contexte “safe”.
    Ex: 'header/struct' -> 'header_struct', 'proofbar/videos' -> 'proofbar_videos'
    """
    return (alias or "").replace("/", "_").replace("-", "_").strip()


def _merge_slots_context(page_ctx: Dict[str, Any], fragments: Dict[str, str]) -> Dict[str, str]:
    """
    Construit un dict 'slots_html' qui contient :
      - les fragments par ID de slot (ex: 'hero', 'footer', ...)
      - les fragments mappés par alias "safe" (ex: 'header_struct', 'footer_main', ...)
    Ainsi, les templates d'écran existants (screens/*.html) peuvent utiliser indifféremment
    l'une ou l'autre clé.
    """
    by_slot = dict(fragments or {})
    by_alias: Dict[str, str] = {}

    for sid, s in (page_ctx.get("slots") or {}).items():
        alias = s.get("alias") or sid
        html = by_slot.get(sid, "")  # si pas trouvé, chaîne vide
        by_alias[_alias_to_ctx_key(alias)] = html

    # Fusion non-destructive : les clés par alias n'écrasent pas les clés par slot
    merged = {}
    merged.update(by_slot)
    merged.update(by_alias)
    return merged


def _choose_template(page_ctx: Dict[str, Any]) -> str:
    """
    Sélectionne un template d'écran si disponible (screens/<page_id>.html),
    sinon retombe sur la base 'base.html'.
    """
    page_id = (page_ctx.get("id") or "").strip()
    namespace = (page_ctx.get("site_version") or FALLBACK_NAMESPACE).strip() or FALLBACK_NAMESPACE

    if not page_id:
        return "base.html"

    candidates = [f"screens/{namespace}/{page_id}.html"]
    if namespace != FALLBACK_NAMESPACE:
        candidates.append(f"screens/{FALLBACK_NAMESPACE}/{page_id}.html")
    candidates.append(f"screens/{page_id}.html")

    for candidate in candidates:
        try:
            get_template(candidate)
            return candidate
        except TemplateDoesNotExist:
            continue

    raise NamespaceTemplateMissing(
        f"Template introuvable pour page '{page_id}' namespace '{namespace}' (fallback '{FALLBACK_NAMESPACE}')."
    )


def render_base(page_ctx: dict, fragments: dict, assets: dict, request):
    """
    Fabrique une TemplateResponse prête à renvoyer depuis la vue.
    - page_ctx: construit par pipeline.build_page_spec(...)
    - fragments: dict {slot_id: html} rendu par pipeline (HIT/MISS déjà géré côté pipeline)
    - assets: dict {'css': [...], 'js': [...], 'head': [...]} (collectés via components.assets)
    """
    page_ctx = page_ctx or {}
    fragments = fragments or {}
    assets = assets or {"css": [], "js": [], "head": []}

    segments = getattr(request, "_segments", None)
    configured_default_lang = getattr(settings, "LANGUAGE_CODE", "fr")
    lang_code = getattr(segments, "lang", None) or getattr(request, "LANGUAGE_CODE", configured_default_lang)
    lang_code = (lang_code or configured_default_lang).lower()
    primary_lang = lang_code.split("-")[0]
    rtl_languages = {code.split("-")[0] for code in getattr(settings, "RTL_LANGUAGES", {"ar"})}
    is_rtl = primary_lang in rtl_languages
    lang_dir = "rtl" if is_rtl else "ltr"

    css_assets = list(dict.fromkeys(assets.get("css", []) or []))
    if is_rtl:
        css_assets.append(static("css/rtl.css"))
    css_assets = list(dict.fromkeys(css_assets))

    page_id = page_ctx.get("id") or ""
    namespace = page_ctx.get("site_version")
    ctx = {
        "page_id": page_id,
        "page_meta": page_meta(page_id, namespace=namespace) if page_id else {},
        "slots_html": _merge_slots_context(page_ctx, fragments),
        "page_assets": {
            "css": css_assets,
            "js": list(dict.fromkeys(assets.get("js", []) or [])),
            "head": list(dict.fromkeys(assets.get("head", []) or [])),
        },
        "qa_preview": bool(page_ctx.get("qa_preview")),
        "content_rev": page_ctx.get("content_rev"),
        "site_version": namespace,
        "lang_code": lang_code,
        "lang_dir": lang_dir,
        "is_rtl": is_rtl,
    }

    template_name = _choose_template(page_ctx)
    return TemplateResponse(request, template_name, ctx)
