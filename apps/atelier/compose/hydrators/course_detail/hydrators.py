from __future__ import annotations
from typing import Any, Dict, List, Mapping
from urllib.parse import urlencode, urlparse, parse_qsl, urlunparse

from django.conf import settings
from django.db.utils import OperationalError, ProgrammingError
from django.urls import NoReverseMatch, reverse

from apps.catalog.models.models import Course
from apps.pages.services import compute_promotion_price
from apps.catalog.models import (
    CourseTrainingContent,
    TrainingCurriculumSection,
    CourseSidebarSettings,
    SidebarLink,
    LinkKind,
)
from apps.marketing.models.models_pricing import PricePlan

HERO_PLACEHOLDER = "https://placehold.co/960x540"
AVATAR_PLACEHOLDER = "https://placehold.co/100x100"
DEFAULT_REFERENCE_PRICE = 169
DEFAULT_DISCOUNT_PCT = 30


def _default_plan_slug() -> str:
    try:
        plan = PricePlan.objects.filter(is_active=True).order_by("display_order", "id").first()
    except (ProgrammingError, OperationalError):
        return ""
    return plan.slug if plan else ""


def _clean_str(value: Any, default: str = "") -> str:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned if cleaned else default
    return default


def _clean_url(value: Any, default: str = "") -> str:
    url = _clean_str(value, default)
    return url or default


def _clean_int(value: Any, default: int = 0) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if number >= 0 else default


def _clean_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number


def _list_of_strings(value: Any) -> List[str]:
    if isinstance(value, (list, tuple)):
        items: List[str] = []
        for entry in value:
            if isinstance(entry, str):
                cleaned = entry.strip()
                if cleaned:
                    items.append(cleaned)
        return items
    return []


def _normalize_curriculum(sections: Any) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    if isinstance(sections, (list, tuple)):
        for raw in sections:
            if not isinstance(raw, Mapping):
                continue
            title = _clean_str(raw.get("title"))
            items = _list_of_strings(raw.get("items"))
            if title or items:
                normalized.append({"title": title, "items": items})
    return normalized


def _normalize_people(people: Any) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    if isinstance(people, (list, tuple)):
        for raw in people:
            if not isinstance(raw, Mapping):
                continue
            normalized.append(
                {
                    "name": _clean_str(raw.get("name")),
                    "role": _clean_str(raw.get("role")),
                    "profile_url": _clean_url(raw.get("profile_url")),
                    "avatar_url": _clean_url(raw.get("avatar_url"), AVATAR_PLACEHOLDER),
                    "bio": _clean_str(raw.get("bio")),
                }
            )
    return normalized


def _normalize_reviews(reviews: Any) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    if isinstance(reviews, (list, tuple)):
        for raw in reviews:
            if not isinstance(raw, Mapping):
                continue
            normalized.append(
                {
                    "author": _clean_str(raw.get("author")),
                    "location": _clean_str(raw.get("location")),
                    "content": _clean_str(raw.get("content")),
                    "avatar_url": _clean_url(raw.get("avatar_url"), AVATAR_PLACEHOLDER),
                }
            )
    return normalized


def _normalize_info_items(items: Any) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    if isinstance(items, (list, tuple)):
        for raw in items:
            if not isinstance(raw, Mapping):
                continue
            normalized.append(
                {
                    "icon": _clean_str(raw.get("icon")),
                    "label": _clean_str(raw.get("label")),
                    "value": _clean_str(raw.get("value")),
                }
            )
    return normalized


def _clamp_percentage(value: Any, fallback: int = 0) -> int:
    pct = _clean_int(value, fallback)
    return max(0, min(100, pct))


def _ensure_next(url: str, next_url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if next_url:
        query.setdefault("next", next_url)
    new_query = urlencode(query, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def _replace_tokens_in_kwargs(kwargs: dict, course) -> dict:
    out = {}
    for k, v in (kwargs or {}).items():
        if isinstance(v, str) and v.startswith("<") and v.endswith(">"):
            token = v[1:-1]  # ex: course.slug
            if token == "course.slug" and course:
                out[k] = getattr(course, "slug", "")
            else:
                out[k] = ""
        else:
            out[k] = v
    return out


def _reverse_link(name: str, kwargs: dict | None) -> str:
    if not name:
        return "#"
    try:
        return reverse(name, kwargs=kwargs or None)
    except NoReverseMatch:
        try:
            return reverse(name)
        except NoReverseMatch:
            return "#"


def _resolve_link_from_spec(spec: dict | None, course, next_url: str | None = None) -> str:
    if not spec:
        return "#"
    kind = (spec.get("kind") or "reverse").lower()
    if kind == "external":
        url = (spec.get("external_url") or "#").strip() or "#"
    else:
        name = (spec.get("url_name") or spec.get("name") or "").strip()
        kwargs = _replace_tokens_in_kwargs(spec.get("url_kwargs") or {}, course)
        url = _reverse_link(name, kwargs)
    if spec.get("append_next") and next_url:
        url = _ensure_next(url, next_url)
    return url


def _link_to_spec(link: SidebarLink | None) -> dict | None:
    if not link:
        return None
    if link.kind == LinkKind.EXTERNAL:
        return {"kind": "external", "external_url": link.external_url}
    return {
        "kind": "reverse",
        "url_name": link.url_name,
        "url_kwargs": link.url_kwargs or {},
        "append_next": link.append_next,
    }


def _slug_from_request(request, data):
    slug = _clean_str(data.get("course_slug")) or _clean_str(data.get("slug"))
    if not slug:
        rm = getattr(request, "resolver_match", None)
        if rm:
            slug = _clean_str((rm.kwargs or {}).get("course_slug"))
    return slug


def training(request, params):
    data = dict(params or {})
    slug = _slug_from_request(request, data)
    course_obj = Course.objects.filter(slug=slug).first()
    if not course_obj:
        return {}  # <- pas de contenu par défaut si cours introuvable

    tc = CourseTrainingContent.objects.filter(course=course_obj).first()
    if not tc:
        return {}  # idem

    rating_value = tc.rating_value or 0.0
    rating_pct = tc.rating_percentage or (
        int(round(min(max(rating_value, 0.0), 5.0) / 5.0 * 100)) if rating_value else 0)

    return {
        "hero_image_url": _clean_url(tc.hero_image_url, HERO_PLACEHOLDER),
        "hero_tag": _clean_str(tc.hero_tag),
        "video_url": _clean_url(tc.video_url),
        "video_label": _clean_str(tc.video_label),
        "title": _clean_str(tc.title or course_obj.title),
        "subtitle": _clean_str(tc.subtitle),
        "enrollment_label": _clean_str(tc.enrollment_label),
        "rating_value": rating_value,
        "rating_percentage": rating_pct,
        "rating_count": tc.rating_count or 0,
        "description_title": _clean_str(tc.description_title),
        "bundle_title": _clean_str(tc.bundle_title),
        "curriculum_title": _clean_str(tc.curriculum_title),
        "instructors_title": _clean_str(tc.instructors_title),
        "reviews_title": _clean_str(tc.reviews_title),
        "description_blocks": [b.content for b in tc.description_blocks.all().order_by("order", "id")],
        "bundle_items": [b.text for b in tc.bundle_items.all().order_by("order", "id")],
        "curriculum_sections": [
            {"title": s.title, "items": [it.text for it in s.items.all().order_by("order", "id")]}
            for s in tc.curriculum_sections.all().order_by("order", "id")
        ],
        "instructors": [
            {"name": ins.name, "role": ins.role, "profile_url": ins.profile_url,
             "avatar_url": ins.avatar_url or AVATAR_PLACEHOLDER, "bio": ins.bio}
            for ins in tc.instructors.all().order_by("order", "id")
        ],
        "reviews": [
            {"author": rv.author, "location": rv.location, "content": rv.content,
             "avatar_url": rv.avatar_url or AVATAR_PLACEHOLDER}
            for rv in tc.reviews.all().order_by("order", "id")
        ],
        # overrides éventuels venant du manifest (gardé)
        "reviews_cta_label": _clean_str(data.get("reviews_cta_label")),
        "reviews_cta_url": _clean_url(data.get("reviews_cta_url")),
    }


# def sidebar(request, params):
#     data = dict(params or {})
#     slug = _slug_from_request(request, data)
#     course_obj = Course.objects.filter(slug=slug).first()
#
#     # ⬇️ Si aucun cours → pas de valeurs “magiques”
#     if not course_obj:
#         return {
#             "course_slug": slug, "currency": "", "promo_badge": "",
#             "info_items": [], "bundle_title": "", "bundle_items": [],
#             "cta_guest_label": "", "cta_guest_url": "", "cta_member_label": "",
#             "cta_member_url": "", "cta_note": "", "price": 0, "promotion": 0,
#             "course": {"slug": slug, "title": ""},
#         }
#
#     ss = CourseSidebarSettings.objects.filter(course=course_obj).first()
#     base_price = ss.price_override if (ss and ss.price_override is not None) else None
#     discount_pct = ss.discount_pct_override if (ss and ss.discount_pct_override is not None) else None
#
#     # Si aucun prix override, on ne fabrique pas de prix par défaut
#     price = int(base_price or 0)
#     promotion = 0
#     if price:
#         promotion = compute_promotion_price(
#             course_obj,
#             default_reference=price,
#             discount_pct=int(discount_pct or 0),
#         )
#
#     # Liens (config > DB > fallback)
#     cfg_guest = data.get("cta_guest_link")
#     cfg_member = data.get("cta_member_link")
#
#     db_guest = db_member = None
#     if ss:
#         links = {ln.role: ln for ln in ss.links.all()}
#         db_guest = links.get(SidebarLink.Role.GUEST)
#         db_member = links.get(SidebarLink.Role.MEMBER)
#
#     def _default_guest():
#         try:
#             return reverse("billing:checkout", kwargs={"slug": course_obj.slug})
#         except NoReverseMatch:
#             return f"/billing/checkout/{course_obj.slug}/"
#
#     guest_url = (
#         _resolve_link_from_spec(cfg_guest, course_obj, None) if cfg_guest else
#         _resolve_link_from_spec(_link_to_spec(db_guest), course_obj, None) if db_guest else
#         _default_guest()
#     )
#
#     def _default_member():
#         login_url = getattr(settings, "LOGIN_URL", "") or "#"
#         return _ensure_next(login_url, guest_url)
#
#     member_url = (
#         _resolve_link_from_spec(cfg_member, course_obj, guest_url) if cfg_member else
#         _resolve_link_from_spec(_link_to_spec(db_member), course_obj, guest_url) if db_member else
#         _default_member()
#     )
#
#     return {
#         "course_slug": course_obj.slug,
#         "currency": (ss.currency if ss else ""),
#         "promo_badge": (ss.promo_badge if ss else ""),
#         "info_items": (
#             [{"icon": i.icon, "label": i.label, "value": i.value}
#              for i in ss.info_items.all().order_by("order", "id")] if ss else []
#         ),
#         "bundle_title": (ss.bundle_title if ss else ""),
#         "bundle_items": (
#             [it.text for it in ss.bundle_items.all().order_by("order", "id")] if ss else []
#         ),
#         "cta_guest_label": (ss.cta_guest_label if ss else ""),
#         "cta_guest_url": guest_url,
#         "cta_member_label": (ss.cta_member_label if ss else ""),
#         "cta_member_url": member_url,
#         "cta_note": (ss.cta_note if ss else ""),
#         "price": price,
#         "promotion": promotion,
#         "course": {"slug": course_obj.slug, "title": course_obj.title},
#     }

# ... (toutes tes imports et helpers existants) ...

def sidebar(request, params):
    data = dict(params or {})

    # ↓↓↓ récupération du slug et des extras calculés par la view
    slug = _clean_str(data.get("course_slug"))
    access = data.get("access") or {}              # <- ajouté
    access_state = (access.get("state") or "").lower()

    course_obj = None
    if slug:
        try:
            course_obj = Course.objects.get(slug=slug)
        except Exception:
            course_obj = None

    # === defaults + DB overrides (inchangés) ===
    base_price = _clean_int(data.get("price"), DEFAULT_REFERENCE_PRICE)
    discount_pct = _clean_int(data.get("discount_pct"), DEFAULT_DISCOUNT_PCT)

    ss = CourseSidebarSettings.objects.filter(course=course_obj).first() if course_obj else None
    if ss:
        if ss.price_override is not None:
            base_price = ss.price_override
        if ss.discount_pct_override is not None:
            discount_pct = ss.discount_pct_override

    price = base_price or 0
    course_payload = {"slug": slug, "title": _clean_str(data.get("course_title"))}
    if course_obj:
        course_payload = {"slug": course_obj.slug, "title": course_obj.title}

    promotion = compute_promotion_price(
        course_obj,
        default_reference=base_price or DEFAULT_REFERENCE_PRICE,
        discount_pct=discount_pct or DEFAULT_DISCOUNT_PCT,
    ) if price else 0

    # --- Résolution des liens existants (config/DB/fallback) ---
    cfg_guest = data.get("cta_guest_link")
    cfg_member = data.get("cta_member_link")

    db_guest = db_member = None
    if ss:
        links = {ln.role: ln for ln in ss.links.all()}
        db_guest = links.get(SidebarLink.Role.GUEST)
        db_member = links.get(SidebarLink.Role.MEMBER)

    def _default_guest():
        plan_slug = _clean_str(data.get("plan_slug")) or _default_plan_slug()
        if plan_slug:
            try:
                return reverse("pages:checkout", kwargs={"plan_slug": plan_slug})
            except NoReverseMatch:
                return f"/billing/checkout/plan/{plan_slug}/"
        if slug:
            try:
                return reverse("billing:checkout", kwargs={"slug": slug})
            except NoReverseMatch:
                return f"/billing/checkout/{slug}/"
        return "#"

    guest_url = (
        _resolve_link_from_spec(cfg_guest, course_obj, None) if cfg_guest else
        _resolve_link_from_spec(_link_to_spec(db_guest), course_obj, None) if db_guest else
        _default_guest()
    )

    def _default_member():
        from django.conf import settings as dj_settings
        login_url = getattr(dj_settings, "LOGIN_URL", "") or "#"
        return _ensure_next(login_url, guest_url)

    member_url = (
        _resolve_link_from_spec(cfg_member, course_obj, guest_url) if cfg_member else
        _resolve_link_from_spec(_link_to_spec(db_member), course_obj, guest_url) if db_member else
        _default_member()
    )

    # =========================
    # RESOLVER D'ACCÈS (Approche A)
    # =========================
    #  - guest   : CTA paiement + CTA connexion + note invité
    #  - member  : (connecté sans droit) -> CTA paiement
    #  - owner   : droit d’accès -> “Voir le cours” (redir lecture)
    #  NB: pas de casse : on ne modifie que les 3 champs CTA + (optionnel) on masque price/promo
    if access_state == "owner":
        first_url = _clean_url(access.get("first_url")) or (
            reverse("pages:lecture", kwargs={"course_slug": slug}) if slug else "#"
        )
        cta_guest_label = "Voir le cours"
        cta_guest_url = first_url
        cta_member_label = ""
        cta_member_url = ""
        cta_note = ""
        # Option UX: masquer prix/promo
        price = 0
        promotion = 0

    elif access_state == "member":
        cta_guest_label = "Accéder au paiement"
        cta_guest_url = guest_url
        cta_member_label = ""    # déjà connecté
        cta_member_url = ""
        cta_note = _clean_str(access.get("note"))

    else:  # guest (anonyme)
        cta_guest_label = ss.cta_guest_label if ss else _clean_str(data.get("cta_guest_label")) or "Accéder au paiement"
        cta_guest_url = guest_url
        cta_member_label = ss.cta_member_label if ss else _clean_str(data.get("cta_member_label")) or "Connexion"
        cta_member_url = member_url
        cta_note = ss.cta_note if ss else (_clean_str(data.get("cta_note")) or _clean_str(access.get("note")))

    ctx = {
        "course_slug": slug,
        "currency": ss.currency if ss else _clean_str(data.get("currency"), "MAD"),
        "promo_badge": ss.promo_badge if ss else _clean_str(data.get("promo_badge")),
        "info_items": (
            [{"icon": i.icon, "label": i.label, "value": i.value}
             for i in ss.info_items.all().order_by("order", "id")] if ss
            else _normalize_info_items(data.get("info_items"))
        ),
        "bundle_title": ss.bundle_title if ss else _clean_str(data.get("bundle_title")),
        "bundle_items": (
            [it.text for it in ss.bundle_items.all().order_by("order", "id")] if ss
            else _list_of_strings(data.get("bundle_items"))
        ),
        # ↙️ CTA final après résolution
        "cta_guest_label": cta_guest_label,
        "cta_guest_url": cta_guest_url,
        "cta_member_label": cta_member_label,
        "cta_member_url": cta_member_url,
        "cta_note": cta_note,
        "price": price,
        "promotion": promotion if price else 0,
        "course": course_payload,
    }
    return ctx
