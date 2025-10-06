# apps/atelier/templatetags/atelier_images.py
from __future__ import annotations
import logging
import os
from pathlib import PurePosixPath
from typing import Dict, Iterable, List, Optional, Tuple, Set
import base64
from html import escape

from django import template
from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage
from django.forms.utils import flatatt
from django.templatetags.static import static
from django.utils.html import format_html, format_html_join

register = template.Library()

# Ordre de compatibilité : AVIF → WEBP → PNG
_FORMATS_ORDER: Tuple[str, ...] = ("avif", "webp", "png", "jpg", "jpeg")


_log = logging.getLogger("atelier.images.responsive_picture")
_DEBUG_FLAG = os.getenv("ATELIER_IMAGES_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}


def _debug(msg: str, *args) -> None:
    if _DEBUG_FLAG:
        if args:
            _log.info(msg, *args)
        else:
            _log.info(msg)


def _exists(relpath: str) -> bool:
    try:
        return staticfiles_storage.exists(relpath)
    except Exception:
        return False


def _split_base(src: str) -> Tuple[str, str, Optional[str]]:
    """
    Retourne (parent, stem, original_relpath_or_none).
    - src peut être 'images/logo' OU 'images/logo.webp'.
    """
    p = PurePosixPath(src)
    parent = str(p.parent) if str(p.parent) != "." else ""
    stem = p.stem
    # Si on a donné une extension, garde le chemin original pour fallback ultime
    orig = f"{parent}/{p.name}" if parent else p.name
    # Mais si aucune extension, pas d'original “fort”
    if not p.suffix:
        orig = None
    return parent, stem, orig


def _candidates_for_format(parent: str, stem: str, ext: str) -> List[str]:
    """
    Deux schémas de recherche :
    1) sous-dossier : images/logo/logo.avif
    2) plat        : images/logo.avif
    """
    nested = f"{parent}/{stem}/{stem}.{ext}" if parent else f"{stem}/{stem}.{ext}"
    flat = f"{parent}/{stem}.{ext}" if parent else f"{stem}.{ext}"
    # Évite les // si parent vide
    nested = nested.lstrip("/")
    flat = flat.lstrip("/")
    return [nested, flat]


def _first_existing(paths: Iterable[str]) -> Optional[str]:
    for p in paths:
        if _exists(p):
            return p
    return None


def _build_variants(parent: str, stem: str, original_rel: Optional[str]) -> Tuple[Dict[str, str], Set[str]]:
    """
    1) Essaie le manifest enrichi (_variants) exposé par staticfiles_storage
    2) Sinon, fallback legacy: scan plat/nested (dev sans collectstatic)
    """
    try:
        variants_index = getattr(staticfiles_storage, "variants_index", {}) or {}
    except Exception:
        variants_index = {}

    manifest_candidates: List[str] = []

    def _push(candidate: Optional[str]) -> None:
        if not candidate:
            return
        normalized = candidate.lstrip("/")
        if normalized and normalized not in manifest_candidates:
            manifest_candidates.append(normalized)

    if original_rel:
        _push(original_rel)

    base = f"{parent}/{stem}" if parent else stem
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        _push(f"{base}{ext}")
        for candidate in _candidates_for_format(parent, stem, ext.lstrip(".")):
            _push(candidate)

    _debug(
        "responsive_picture manifest candidates for %s/%s: %s",
        parent,
        stem,
        manifest_candidates,
    )

    seen: Set[str] = set()
    for key in manifest_candidates:
        if key in seen:
            continue
        seen.add(key)
        mapping = variants_index.get(key)
        if mapping:
            hashed_formats = {fmt for fmt, rel in mapping.items() if rel}
            _debug(
                "responsive_picture hit manifest for %s - formats=%s",
                key,
                sorted(hashed_formats),
            )
            return {fmt: rel for fmt, rel in mapping.items() if rel}, hashed_formats

    _debug("responsive_picture falling back to legacy search for %s/%s", parent, stem)
    return _legacy_variants(parent, stem), set()


def _legacy_variants(parent: str, stem: str) -> Dict[str, str]:
    """
    Retourne les variantes détectées via le schéma legacy (scan plat/nested).
    """
    found: Dict[str, str] = {}
    for ext in _FORMATS_ORDER:
        cand = _candidates_for_format(parent, stem, ext)
        hit = _first_existing(cand)
        if hit:
            found[ext] = hit
    return found


def _filter_existing(variants: Dict[str, str]) -> Dict[str, str]:
    """Filtre les variantes selon leur présence réelle côté storage."""
    filtered: Dict[str, str] = {}
    for ext, rel in variants.items():
        normalized = rel.lstrip("/")
        try:
            if staticfiles_storage.exists(normalized):
                filtered[ext] = normalized
        except Exception:
            continue
    return filtered


def _static_url(relpath: str) -> str:
    base = settings.STATIC_URL or ""
    suffix = relpath.lstrip("/")
    if not base:
        return f"/{suffix}"
    prefix = base[:-1] if base.endswith("/") else base
    return f"{prefix}/{suffix}" if suffix else prefix


def _url_for(relpath: str, *, force_hashed: Optional[bool] = None) -> str:
    normalized = relpath.lstrip("/")
    hashed_files = getattr(staticfiles_storage, "hashed_files", {}) or {}
    hashed_values = set(hashed_files.values())
    hashed = force_hashed if force_hashed is not None else normalized in hashed_values
    return _static_url(normalized) if hashed else static(normalized)


def _choose_fallback(
    variants: Dict[str, str],
    hashed_formats: Set[str],
    original_rel: Optional[str],
) -> str:
    """Fallback <img>: préférer PNG, puis JPG/JPEG, puis WEBP, puis AVIF, sinon l'original."""
    for ext in ("png", "jpg", "jpeg", "webp", "avif"):
        rel = variants.get(ext)
        if rel:
            try:
                return _url_for(rel, force_hashed=ext in hashed_formats)
            except Exception:
                continue

    if original_rel:
        normalized = original_rel.lstrip("/")
        if _exists(normalized):
            try:
                return _url_for(normalized)
            except Exception:
                return "#"

    return "#"


def _safe_source(rel: str, ext: str, hashed_formats: Set[str]) -> Optional[str]:
    try:
        return _url_for(rel, force_hashed=ext in hashed_formats)
    except Exception:
        return None


def _normalize_attrs(alt: str, cls: str, width, height, loading, decoding, fetchpriority, sizes, **kwargs) -> Dict[str, str]:
    # Conversion data_* / aria_* en data-* / aria-*
    attrs: Dict[str, str] = {}
    if alt is not None:
        attrs["alt"] = alt
    if cls:
        attrs["class"] = cls
    if width:
        attrs["width"] = str(width)
    if height:
        attrs["height"] = str(height)
    if loading:
        attrs["loading"] = loading
    if decoding:
        attrs["decoding"] = decoding
    if fetchpriority:
        attrs["fetchpriority"] = fetchpriority
    if sizes:
        attrs["sizes"] = sizes

    for k, v in kwargs.items():
        if v is None:
            continue
        key = k.replace("_", "-") if (k.startswith("data_") or k.startswith("aria_")) else k
        attrs[key] = str(v)
    return attrs


def _auto_placeholder(width: Optional[int], height: Optional[int], text: str) -> str:
    w = width or 48
    h = height or 36
    label = escape((text or "").strip() or "Img")
    svg = (
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{w}' height='{h}' viewBox='0 0 {w} {h}'>"
        f"<rect width='100%' height='100%' fill='#f1f5f9'/>"
        f"<text x='50%' y='50%' fill='#94a3b8' font-family='sans-serif' font-size='{max(12, min(w, h)//4)}'"
        f" text-anchor='middle' dominant-baseline='central'>{label}</text>"
        "</svg>"
    )
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")


def _render_picture(source_rows, img_src: str, attrs: Dict[str, str]):
    sources_html = format_html_join(
        "",
        '<source type="{}" srcset="{}" />',
        ((mime, url) for mime, url in source_rows),
    )
    return format_html(
        "<picture>{sources}<img src=\"{img_src}\"{img_attrs} /></picture>",
        sources=sources_html,
        img_src=img_src,
        img_attrs=flatatt(attrs),
    )


@register.simple_tag
def responsive_picture(
    src: str,
    *,
    alt: str = "",
    cls: str = "",
    width: Optional[int] = None,
    height: Optional[int] = None,
    loading: str = "auto",        # 'lazy' si tu préfères
    decoding: str = "async",
    fetchpriority: Optional[str] = None,  # 'high'|'low'
    sizes: Optional[str] = None,
    placeholder: Optional[str] = None,
    **kwargs,
):
    """
    Rend un <picture> avec <source> AVIF → WEBP et <img> fallback (PNG→JPG→WEBP→AVIF→original).
    Utilisation :
        {% responsive_picture 'images/logo' alt='logo' cls='img-fluid' %}
        {% responsive_picture 'images/logo.webp' alt='logo' cls='img-fluid' %}
    """
    placeholder_data: Optional[str] = None
    if placeholder == "auto":
        placeholder_data = _auto_placeholder(width, height, alt)
        if placeholder_data:
            kwargs.setdefault("data_placeholder", placeholder_data)

    is_remote = src.startswith(("http://", "https://", "data:"))
    if is_remote:
        if placeholder_data and src.startswith("https://placehold.co/"):
            kwargs.setdefault("data_src", src)
            img_src_remote = placeholder_data
        else:
            img_src_remote = src

        attrs = _normalize_attrs(alt, cls, width, height, loading, decoding, fetchpriority, sizes, **kwargs)
        return _render_picture([], img_src_remote, attrs)

    parent, stem, original_rel = _split_base(src)
    variants_raw, manifest_formats = _build_variants(parent, stem, original_rel)
    variants = _filter_existing(variants_raw)

    if not variants:
        legacy_variants = _legacy_variants(parent, stem)
        variants = _filter_existing(legacy_variants)
        manifest_formats = set()

    img_src = _choose_fallback(variants, manifest_formats, original_rel)

    if img_src == "#" and original_rel:
        normalized = original_rel.lstrip("/")
        if _exists(normalized):
            try:
                img_src = _url_for(original_rel)
            except Exception:
                img_src = "#"

    if img_src == "#" and not placeholder_data:
        placeholder_data = _auto_placeholder(width, height, alt)
        if placeholder_data:
            kwargs.setdefault("data_placeholder", placeholder_data)

    if placeholder_data and img_src == "#":
        img_src = placeholder_data

    source_rows = []
    if "avif" in variants:
        src_avif = _safe_source(variants["avif"], "avif", manifest_formats)
        if src_avif:
            source_rows.append(("image/avif", src_avif))
    if "webp" in variants:
        src_webp = _safe_source(variants["webp"], "webp", manifest_formats)
        if src_webp:
            source_rows.append(("image/webp", src_webp))

    attrs = _normalize_attrs(alt, cls, width, height, loading, decoding, fetchpriority, sizes, **kwargs)

    return _render_picture(source_rows, img_src, attrs)
