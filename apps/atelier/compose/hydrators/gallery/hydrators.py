from typing import Dict, Any, List
from urllib.parse import quote_plus

from django.db import models
from django.templatetags.static import static
from django.utils.translation import gettext as _

from apps.catalog.models.models_catalog import Gallery, GalleryItem


PLACEHOLDER_IMG = "https://placehold.co/600x600?text=Galerie"


def _resolve_asset(
    path: str | None,
    *,
    fallback: str | None = None,
    allow_placeholder: bool = True,
) -> str:
    """Return a usable URL for an asset, handling missing static files gracefully."""

    candidates: List[str] = []
    for candidate in (path, fallback):
        candidate = (candidate or "").strip()
        if candidate:
            candidates.append(candidate)

    if allow_placeholder:
        candidates.append(PLACEHOLDER_IMG)

    for candidate in candidates:
        if candidate.startswith(("http://", "https://", "//")):
            return candidate
        if candidate.startswith("/"):
            return candidate
        try:
            return static(candidate)
        except Exception:
            continue

    return ""

def _item_to_ctx(item: GalleryItem) -> Dict[str, Any]:
    """Normalize a gallery item coming from the DB."""
    name = (item.name or "").strip() or _("Participante")
    meta = (item.meta or "").strip()
    caption = (item.caption or "").strip() or (f"{name} — {meta}" if meta else name)

    src = _resolve_asset(item.image)
    placeholder_with_name = PLACEHOLDER_IMG
    if src == PLACEHOLDER_IMG:
        placeholder_with_name = f"https://placehold.co/600x600?text={quote_plus(name)}"
        src = placeholder_with_name

    href = _resolve_asset(item.effective_href, fallback=src)
    if href == PLACEHOLDER_IMG:
        href = placeholder_with_name
    webp = (item.webp or "").strip()
    webp_url = _resolve_asset(webp, allow_placeholder=False) if webp else ""

    return {
        "href": href,
        "src": src,
        "webp": webp_url,
        "name": name,
        "badge": (item.badge or "").strip() or _("Participante"),
        "meta": meta,
        "alt": (item.alt or "").strip() or name,
        "caption": caption,
        "aria_label": _("Ouvrir la photo de %(name)s") % {"name": name},
    }

def participants(request, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Construit la galerie 'participants' en DB-first, avec fallback placeholder si vide.
    Params (via manifest/pages.yml) :
      - gallery_slug (str): slug de la galerie (def: 'participants')
      - initial_visible (int): nb d'items visibles au chargement (def: 8)
      - reveal_step (int): nb d'items révélés par clic (def: 4)
      - lightbox (bool): forcer l'état (sinon hérité de la galerie)
      - cta_label (str): override du label bouton
      - product_code (str): filtre additionnel par code produit
      - use_placeholder_when_empty (bool): rendre un HTML de secours si pas de données (def: true)
      - placeholder_template (str): chemin du template partiel (_placeholder.html)
      - anchor_id (str): id de la section (def: 'galerie')
    """
    p = params or {}
    slug = (p.get("gallery_slug") or "participants").strip()
    initial_visible = int(p.get("initial_visible") or 8)
    reveal_step = int(p.get("reveal_step") or 4)
    product_code = (p.get("product_code") or "pack-cosmetique-naturel").strip()
    use_placeholder = bool(p.get("use_placeholder_when_empty", True))
    placeholder_tpl = p.get("placeholder_template") or "components/core/gallery/participants/_placeholder.html"
    anchor_id = (p.get("anchor_id") or "galerie").strip()

    # Galerie
    try:
        gal = Gallery.objects.get(slug=slug, is_active=True)
    except Gallery.DoesNotExist:
        gal = None

    # Items publiés
    items_qs = GalleryItem.objects.none()
    if gal:
        items_qs = gal.items.filter(is_published=True)
        # Filtre produit optionnel : param > galerie > item
        pc = product_code or gal.product_code
        if pc:
            items_qs = items_qs.filter(models.Q(product_code=pc) | models.Q(product_code=""))
        items_qs = items_qs.order_by("sort_order", "id")

    print('-'*30)
    print('-'*30)
    print('gal.pk : %s' % gal.id)
    items: List[Dict[str, Any]] = [_item_to_ctx(it) for it in items_qs]

    # En-têtes & preuves (db-first → override par params au besoin)
    title = (p.get("title") or (gal.title if gal else "") or _("Leurs créations & sourires")).strip()
    subtitle = p.get("subtitle") or (gal.subtitle if gal else "")

    proofs = p.get("proofs") or (gal.proofs if gal and gal.proofs else [
        {"icon": "fas fa-user-check", "text": _("1 200+ participantes formées")},
        {"icon": "fas fa-star", "text": _("Note moyenne 4,9/5")},
        {"icon": "fas fa-shield-alt", "text": _("Formations certifiantes")},
    ])

    cta_label = (p.get("cta_label") or (gal.cta_label if gal else "") or _("Voir plus de réalisations")).strip()
    lightbox_enabled = p.get("lightbox")
    if lightbox_enabled is None:
        lightbox_enabled = bool(gal.lightbox_enabled) if gal else True

    has_more = len(items) > max(0, initial_visible)

    context = {
        "anchor_id": p.get("anchor_id") or (gal.anchor_id if gal else anchor_id),
        "title": title,
        "subtitle_gallery": subtitle,
        "proofs_gallery": proofs,
        "items": items,
        "initial_visible": max(0, initial_visible),
        "reveal_step": max(1, reveal_step),
        "cta_label": cta_label,
        "has_more": has_more,
        "lightbox": lightbox_enabled,
        "use_placeholder": use_placeholder and not items,
        "placeholder_tpl": placeholder_tpl,
        "aria": {
            "proofs": _("Preuves sociales"),
            "dialog": _("Agrandissement image"),
            "prev": _("Précédente"),
            "next": _("Suivante"),
            "close": _("Fermer"),
        }
    }
    print(context)
    return context
