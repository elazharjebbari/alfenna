from __future__ import annotations
from typing import Any, Dict, List, Mapping, Optional
import logging
import os

from django.conf import settings
from django.core.files.storage import default_storage
from django.db import OperationalError, ProgrammingError
from django.db.models import Prefetch, prefetch_related_objects
from django.http import Http404
from django.urls import reverse, NoReverseMatch
from django.utils.text import slugify

from apps.billing.models import Entitlement
from apps.catalog.models.models import Course
from apps.content.models import Section, Lecture, LanguageCode
from apps.marketing.models.models_pricing import PricePlan

logger = logging.getLogger("atelier.learning.debug")

PLACEHOLDER_POSTER = "https://placehold.co/960x540?text=Preview"
PLACEHOLDER_AVATAR = "https://placehold.co/100x100?text=Author"

# ---------- helpers ----------
def _as_dict(x: Any) -> Dict[str, Any]:
    return x if isinstance(x, dict) else {}

def _as_list_of_dicts(x: Any) -> List[Dict[str, Any]]:
    if not isinstance(x, list):
        return []
    return [it for it in x if isinstance(it, dict)]

def _s(x: Any, default: str = "") -> str:
    return (x or default) if isinstance(x, str) else default

def _i(x: Any, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return default

def _brief(val: Any, maxlen: int = 240) -> str:
    try:
        s = repr(val)
    except Exception:
        s = f"<unrepr {type(val).__name__}>"
    return s if len(s) <= maxlen else s[:maxlen] + "…"

def _log(phase: str, payload: Dict[str, Any], anomalies: List[str], keys: List[str]):
    logger.warning("LEARNING %s :: payload=%s anomalies=%s keys=%s",
                   phase, _brief(payload), _brief(anomalies), keys)

def _norm_text_items(lst: Any, anomalies: List[str], field: str) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for i, it in enumerate(_as_list_of_dicts(lst)):
        html = _s(it.get("text_html")).strip()
        icon = _s(it.get("icon")).strip() or "fa fa-circle"
        if not html:
            anomalies.append(f"[{field}[{i}]] vide → ignoré")
            continue
        out.append({"text_html": html, "icon": icon})
    return out

def _norm_trainers(lst: Any) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for it in lst or []:
        if isinstance(it, dict):
            name = _s(it.get("name")).strip()
            if name:
                out.append({"name": name})
        elif isinstance(it, str) and it.strip():
            out.append({"name": it.strip()})
    return out

def _resolve_cta(cta_raw: Dict[str, Any], default_label: str, default_icon: str) -> Dict[str, str] | None:
    if not isinstance(cta_raw, dict):
        return None
    label = _s(cta_raw.get("label"), default_label)
    icon = _s(cta_raw.get("icon"), default_icon)
    url = _s(cta_raw.get("url"))
    if not url:
        name = _s(cta_raw.get("url_name"))
        kwargs = _as_dict(cta_raw.get("url_kwargs"))
        if name:
            try:
                url = reverse(name, kwargs=kwargs) if kwargs else reverse(name)
            except NoReverseMatch:
                url = "#"
        else:
            url = "#"
    return {"label": label, "icon": icon, "url": url}


def _field_file_url(field: Any) -> Optional[str]:
    if not field:
        return None
    try:
        url = field.url
    except Exception:
        return None
    return url or None


def _path_to_url(path: str) -> Optional[str]:
    raw = (path or "").strip()
    if not raw:
        return None
    rel = raw
    if os.path.isabs(raw):
        media_root = os.path.abspath(settings.MEDIA_ROOT)
        abs_raw = os.path.abspath(raw)
        if not abs_raw.startswith(media_root):
            return None
        rel = os.path.relpath(abs_raw, media_root)
    rel = rel.lstrip("/")
    try:
        return default_storage.url(rel)
    except Exception:
        media_url = getattr(settings, "MEDIA_URL", "") or "/media/"
        return f"{media_url.rstrip('/')}/{rel}" if rel else None


def _normalize_lang_code(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    code = str(raw).strip()
    if not code:
        return None
    if code in LanguageCode.values:
        return code
    lowered = code.lower().replace("_", "-")
    if lowered in {"fr", "fr-fr"}:
        return LanguageCode.FR_FR
    if lowered in {"ar", "ar-ma"}:
        return LanguageCode.AR_MA
    return None


def _lecture_slug(lecture: Lecture) -> str:
    base = slugify(getattr(lecture, "title", "") or "") or f"lecture-{lecture.pk}"
    return f"s{lecture.section.order}-l{lecture.order}-{base}"[:80]


def resolve_stream_url(lecture: Lecture) -> Optional[str]:
    """Essaye de trouver une URL exploitable pour la vidéo avant de basculer sur le stream backend."""

    # 1) lecture.video.file.url
    video_rel = getattr(lecture, "video", None)
    file_candidate = getattr(video_rel, "file", None)
    url = _field_file_url(file_candidate)
    if url:
        return url

    # 2) lecture.video_url (URL directe)
    url = _s(getattr(lecture, "video_url", ""))
    if url:
        return url

    # 3) lecture.file.url (fallback document)
    url = _field_file_url(getattr(lecture, "file", None))
    if url:
        return url

    # 4) lecture.video_file.video_file.url (certains seeds POC)
    vf = getattr(lecture, "video_file", None)
    nested = getattr(vf, "video_file", None)
    url = _field_file_url(nested)
    if url:
        return url

    # 5) lecture.video_file (FieldFile direct)
    url = _field_file_url(vf)
    if url:
        return url

    # 6) lecture.video_path → MEDIA_ROOT
    url = _path_to_url(getattr(lecture, "video_path", ""))
    if url:
        return url

    try:
        return reverse("learning:stream", args=[lecture.pk])
    except NoReverseMatch:
        return None


def _default_plan_slug() -> str:
    try:
        plan = PricePlan.objects.filter(is_active=True).order_by("display_order", "id").first()
    except (ProgrammingError, OperationalError):
        return ""
    return plan.slug if plan else ""


def _common_lecture_ctx(request, params: Mapping[str, Any]) -> Dict[str, Any]:
    cache_key = "__lecture_common_ctx__"
    cached = getattr(request, cache_key, None)
    if isinstance(cached, dict):
        return cached

    resolver = getattr(request, "resolver_match", None)
    kwargs = resolver.kwargs if resolver and resolver.kwargs else {}
    course_slug = kwargs.get("course_slug")
    lecture_slug = kwargs.get("lecture_slug")

    if not course_slug:
        raise Http404("Course slug missing")

    demo_only = bool(getattr(request, "_demo_only", False))

    lecture_qs = Lecture.objects.filter(is_published=True).order_by("order").prefetch_related("video_variants")
    if demo_only:
        lecture_qs = lecture_qs.filter(is_demo=True)

    sections_qs = Section.objects.filter(is_published=True).order_by("order").prefetch_related(
        Prefetch(
            "lectures",
            queryset=lecture_qs,
        )
    )

    course = getattr(request, "_course", None)
    if course is not None and getattr(course, "slug", None) == course_slug:
        prefetch_related_objects([course], Prefetch("sections", queryset=sections_qs))
    else:
        try:
            course = Course.objects.prefetch_related(
                Prefetch("sections", queryset=sections_qs)
            ).get(slug=course_slug, is_published=True)
        except Course.DoesNotExist as exc:
            raise Http404("Course not found") from exc
        setattr(request, "_course", course)

    course_title = course.get_i18n("title")
    course_description = course.get_i18n("description")

    user = getattr(request, "user", None)
    is_subscribed = False
    if user and getattr(user, "is_authenticated", False):
        is_subscribed = Entitlement.objects.filter(user=user, course=course).exists()

    poster = _s(((params or {}).get("assets") or {}).get("images", {}).get("poster"))
    poster_url = poster or PLACEHOLDER_POSTER

    preview_allowed = bool(user and getattr(user, "is_staff", False) and getattr(request, "GET", {}).get("preview"))
    has_subscription = is_subscribed or preview_allowed

    sections = list(course.sections.all())
    total_lectures = 0
    first_lecture: Optional[Lecture] = None
    slug_lookup: Dict[str, Lecture] = {}
    free_ids: set[int] = set()
    free_quota = int(getattr(course, "free_lectures_count", 0) or 0)
    rank = 0

    for section in sections:
        lectures = list(section.lectures.all())
        if demo_only:
            lectures = [lec for lec in lectures if getattr(lec, "is_demo", False)]
        for lecture in lectures:
            rank += 1
            total_lectures += 1
            if first_lecture is None:
                first_lecture = lecture
            slug_lookup[str(lecture.pk)] = lecture
            slug_lookup[_lecture_slug(lecture)] = lecture
            slug_lookup[f"s{section.order}-l{lecture.order}"] = lecture
            if lecture.is_free or rank <= free_quota:
                free_ids.add(lecture.id)

    current_lecture: Optional[Lecture] = None
    if lecture_slug:
        current_lecture = slug_lookup.get(lecture_slug)
        if current_lecture is None:
            simple_key = lecture_slug.split("-", 2)
            if len(simple_key) >= 2:
                current_lecture = slug_lookup.get("-".join(simple_key[:2]))
        if current_lecture is None and lecture_slug.isdigit():
            current_lecture = slug_lookup.get(lecture_slug)
    if current_lecture is None:
        current_lecture = first_lecture
    if current_lecture is None:
        raise Http404("No lectures available")

    is_current_free = current_lecture.id in free_ids
    has_current_access = has_subscription or is_current_free
    stream_url = resolve_stream_url(current_lecture) if has_current_access else None

    variants = list(current_lecture.video_variants.all())
    available_langs = [variant.lang for variant in variants]
    default_variant = next((variant for variant in variants if getattr(variant, "is_default", False)), None)

    requested_lang = _normalize_lang_code(request.GET.get("lang"))
    if requested_lang and requested_lang in available_langs:
        active_lang = requested_lang
    elif default_variant:
        active_lang = default_variant.lang
    elif available_langs:
        active_lang = available_langs[0]
    else:
        active_lang = requested_lang or LanguageCode.FR_FR

    variant_urls: Dict[str, str] = {}
    if has_current_access:
        try:
            stream_endpoint = reverse("learning:stream", args=[current_lecture.pk])
        except NoReverseMatch:
            stream_endpoint = None
        if stream_endpoint:
            variant_urls = {lang: f"{stream_endpoint}?lang={lang}" for lang in available_langs}
            stream_url = f"{stream_endpoint}?lang={active_lang}"
        elif stream_url and requested_lang:
            stream_url = f"{stream_url}?lang={requested_lang}"
    else:
        stream_url = None

    plan_slug = _s(params.get("plan_slug")) if isinstance(params, Mapping) else ""
    if not plan_slug:
        plan_slug = _default_plan_slug()
    if plan_slug:
        checkout_url = f"/billing/checkout/plan/{plan_slug}/?course={course.slug}"
    else:
        checkout_url = f"/billing/checkout/{course.slug}/"
    enrolled_count = course.entitlements.count() if hasattr(course, "entitlements") else None
    overview_text = _s(course_description or getattr(course, "description", ""))
    certificate_text = _s(getattr(course, "certificate_note", "")) or "Certification disponible après validation."

    instructor = {
        "name": _s(getattr(course, "instructor_name", "")) or course_title or course.title,
        "role": _s(getattr(course, "instructor_title", "")),
        "bio": _s(getattr(course, "instructor_bio", "")) or overview_text,
        "avatar_url": _s(getattr(course, "instructor_avatar", "")) or PLACEHOLDER_AVATAR,
    }

    playlist_sections: List[Dict[str, Any]] = []
    rank_counter = 0
    for section in sections:
        lectures = list(section.lectures.all())
        if demo_only:
            lectures = [lec for lec in lectures if getattr(lec, "is_demo", False)]
        if not lectures:
            continue
        lecture_entries = []
        section_title = section.get_i18n("title")
        for lecture in lectures:
            rank_counter += 1
            lecture_slug_value = _lecture_slug(lecture)
            is_free = lecture.id in free_ids
            is_locked = not (has_subscription or is_free)
            try:
                lecture_url = reverse(
                    "pages:lecture-detail",
                    kwargs={"course_slug": course.slug, "lecture_slug": lecture_slug_value},
                )
            except NoReverseMatch:
                lecture_url = request.path
            lecture_entries.append(
                {
                    "id": lecture.id,
                    "title": lecture.get_i18n("title"),
                    "order": lecture.order,
                    "display_index": f"{section.order}.{lecture.order}",
                    "slug": lecture_slug_value,
                    "url": lecture_url,
                    "is_active": lecture.pk == current_lecture.pk,
                    "is_locked": is_locked,
                    "is_free": is_free,
                    "data_src": resolve_stream_url(lecture) if not is_locked else None,
                }
            )

        playlist_sections.append(
            {
                "id": section.id,
                "title": section_title,
                "order": section.order,
                "collapse_id": f"section{section.id}",
                "is_active": any(entry["is_active"] for entry in lecture_entries),
                "lectures": lecture_entries,
            }
        )

    tab_items = [
        {"id": "overview", "label": "Aperçu"},
        {"id": "certificate", "label": "Certificat"},
        {"id": "instructor", "label": "Formateur"},
    ]

    base_ctx = {
        "course": course,
        "lecture": current_lecture,
        "section_list": playlist_sections,
        "is_subscribed": has_subscription,
        "free_lectures": list(free_ids),
        "checkout_url": checkout_url,
        "poster_url": poster_url,
        "stream_url": stream_url,
        "video_variants": variant_urls,
        "active_lang": active_lang,
        "is_locked": not has_current_access,
        "total_lectures": total_lectures,
        "enrolled_count": enrolled_count,
        "overview_text": overview_text,
        "certificate_text": certificate_text,
        "instructor": instructor,
        "tabs": tab_items,
        "share_url": request.build_absolute_uri(request.path),
        "enrollment_label": "Participants inscrits",
        "share_label": "Partager",
        "overview_heading": "Détails du cours",
        "certificate_heading": "Certificat",
        "instructor_heading": "Formateur",
        "lessons_label": "Nombre de leçons",
        "plan_slug": plan_slug,
    }

    setattr(request, cache_key, base_ctx)
    return base_ctx

# ---------- learning/card ----------
def learning_card(request, params: Mapping[str, Any]) -> Dict[str, Any]:
    anomalies: List[str] = []
    p = dict(params or {})
    _log("RAW(learning_card)", p, anomalies, list(p.keys()))

    # Titres
    title_html = _s(p.get("title_html"))


    # Couleurs/positions
    bg_color = _s(p.get("bg_color"), "#E7F8EE")
    banner_bg = _s(p.get("banner_bg"), "#EDEFF3")
    accent = _s(p.get("accent"), "#309255")
    line_color = _s(p.get("line_color"), "#EDEFF3")
    line_left = _s(p.get("line_left"), "27px")
    line_top = _s(p.get("line_top"), "100px")
    deco_line_enabled = bool(p.get("deco_line_enabled", True))

    intro_items = _norm_text_items(p.get("intro_items"), anomalies, "intro_items")
    for it in intro_items:
        it.pop("icon", None)  # pas d'icône dans l'intro

    features_top = _norm_text_items(p.get("features_top"), anomalies, "features_top")
    features_after = _norm_text_items(p.get("features_after"), anomalies, "features_after")

    feat_eval_raw = _as_dict(p.get("feature_evaluation"))
    feature_evaluation = {"text_html": _s(feat_eval_raw.get("text_html")).strip()} if _s(feat_eval_raw.get("text_html")).strip() else None

    trainers = _norm_trainers(p.get("trainers"))
    price = _i(p.get("price"), 0) or None

    bundle_items = _norm_text_items(p.get("bundle_items"), anomalies, "bundle_items")
    bundle_title = _s(p.get("bundle_title"), "Ce que comprend votre pack :")

    image_static_path = _s(p.get("image_static_path"), "images/candles/pot-bougie-detail-formation.webp")
    image_alt = _s(p.get("image_alt"), "Bougie artisanale")

    cta = _resolve_cta(_as_dict(p.get("cta")), "Je Participe", "fa fa-user-plus me-2")

    ctx = {
        "title_html": title_html,
        "bg_color": bg_color,
        "banner_bg": banner_bg,
        "accent": accent,
        "line_color": line_color,
        "line_left": line_left,
        "line_top": line_top,
        "deco_line_enabled": deco_line_enabled,
        "intro_items": [{"text_html": it["text_html"]} for it in intro_items],
        "features_top": [{"icon": it["icon"], "text_html": it["text_html"]} for it in features_top],
        "trainers": trainers,
        "feature_evaluation": feature_evaluation,
        "price": price,
        "features_after": [{"icon": it["icon"], "text_html": it["text_html"]} for it in features_after],
        "bundle_title": bundle_title,
        "bundle_items": [{"icon": it["icon"], "text_html": it["text_html"]} for it in bundle_items],
        "image_static_path": image_static_path,
        "image_alt": image_alt,
        "cta": cta,
    }
    _log("NORMALIZED(learning_card)", ctx, anomalies, list(p.keys()))
    return ctx

# ---------- learning/content ----------
def learning_content(request, params: Mapping[str, Any]) -> Dict[str, Any]:
    anomalies: List[str] = []
    p = dict(params or {})
    _log("RAW(learning_content)", p, anomalies, list(p.keys()))

    title_html = _s(p.get("title_html"))

    bg_color = _s(p.get("bg_color"), "#ffffff")
    image_static_path = _s(p.get("image_static_path"), "images/candles/candle-learning.webp")
    image_alt = _s(p.get("image_alt"), "Bougie artisanale")

    bubble_color = _s(p.get("bubble_color"), "#4CAF50")
    timeline_line_bg = _s(p.get("timeline_line_bg"), "#E7F8EE")
    timeline_md_left = _s(p.get("timeline_md_left"), "40px")
    timeline_md_top = _s(p.get("timeline_md_top"), "100px")
    timeline_sm_left = _s(p.get("timeline_sm_left"), "33px")
    timeline_sm_top = _s(p.get("timeline_sm_top"), "150px")

    # chapitres
    chapters: List[Dict[str, Any]] = []
    for i, it in enumerate(_as_list_of_dicts(p.get("chapters"))):
        desc = _s(it.get("desc_html")).strip()
        if not desc:
            anomalies.append(f"[chapters[{i}]] desc_html manquant → ignoré")
            continue
        subitems: List[Dict[str, str]] = []
        for j, si in enumerate(_as_list_of_dicts(it.get("subitems"))):
            html = _s(si.get("text_html")).strip()
            if not html:
                anomalies.append(f"[chapters[{i}].subitems[{j}]] vide → ignoré")
                continue
            subitems.append({"text_html": html})
        chapters.append({
            "intro": bool(it.get("intro", False)),
            "mt4": bool(it.get("mt4", False)),
            "border_px": _i(it.get("border_px"), 2),
            "icon": _s(it.get("icon"), "fa fa-circle"),
            "desc_html": desc,
            "subitems": subitems,
        })

    cta = _resolve_cta(_as_dict(p.get("cta")), "Décrouvrir la formation", "fa fa-search me-2")

    ctx = {
        "title_html": title_html,
        "bg_color": bg_color,
        "image_static_path": image_static_path,
        "image_alt": image_alt,
        "bubble_color": bubble_color,
        "timeline_line_bg": timeline_line_bg,
        "timeline_md_left": timeline_md_left,
        "timeline_md_top": timeline_md_top,
        "timeline_sm_left": timeline_sm_left,
        "timeline_sm_top": timeline_sm_top,
        "chapters": chapters,
        "cta": cta,
    }
    _log("NORMALIZED(learning_content)", ctx, anomalies, list(p.keys()))
    return ctx


def learning_highlights(request, params: Mapping[str, Any]) -> Dict[str, Any]:
    """
    Normalise le composant 'learning/highlights' en conservant EXACTEMENT
    la structure, les classes et les styles inline du template fourni.
    """
    anomalies: List[str] = []
    p = dict(params or {})
    _log("RAW(learning_highlights)", p, anomalies, list(p.keys()))

    bg_color = _s(p.get("bg_color"), "#EEFBF3")
    title_html = _s(p.get("title_html"))
    subtitle_html = _s(p.get("subtitle_html"))

    icon_color = _s(p.get("icon_color"), "#309255")
    circle_border_color = _s(p.get("circle_border_color"), "#d3d3d3")
    circle_bg = _s(p.get("circle_bg"), "#ffffff")
    circle_padding = _s(p.get("circle_padding"), "20px")

    items: List[Dict[str, str]] = []
    for i, it in enumerate(_as_list_of_dicts(p.get("items"))):
        icon = _s(it.get("icon")).strip()
        title = _s(it.get("title")).strip()
        text = _s(it.get("text")).strip()
        if not icon or not title or not text:
            anomalies.append(f"[items[{i}]] incomplet → ignoré")
            continue
        items.append({"icon": icon, "title": title, "text": text})

    ctx = {
        "bg_color": bg_color,
        "title_html": title_html,
        "subtitle_html": subtitle_html,
        "icon_color": icon_color,
        "circle_border_color": circle_border_color,
        "circle_bg": circle_bg,
        "circle_padding": circle_padding,
        "items": items,
    }
    _log("NORMALIZED(learning_highlights)", ctx, anomalies, list(p.keys()))
    return ctx


def lecture_layout(request, params: Mapping[str, Any]) -> Dict[str, Any]:
    common = dict(_common_lecture_ctx(request, params))
    return {
        "use_child_compose": True,
        "course": common["course"],
        "lecture": common["lecture"],
        "section_list": common["section_list"],
        "is_subscribed": common["is_subscribed"],
        "free_lectures": common["free_lectures"],
        "is_locked": common["is_locked"],
        "checkout_url": common["checkout_url"],
        "poster_url": common["poster_url"],
        "stream_url": common["stream_url"],
        "total_lectures": common["total_lectures"],
        "enrolled_count": common["enrolled_count"],
        "share_url": common.get("share_url"),
    }


def video_player(request, params: Mapping[str, Any]) -> Dict[str, Any]:
    common = _common_lecture_ctx(request, params)
    return {
        "lecture": common["lecture"],
        "poster_url": common["poster_url"],
        "stream_url": common["stream_url"],
        "video_variants": common.get("video_variants", {}),
        "active_lang": common.get("active_lang"),
        "is_locked": common["is_locked"],
        "video_dom_id": "lecture-video",
        "loading_dom_id": "lecture-video-loading",
        "source_mime": "video/mp4",
        "checkout_url": common["checkout_url"],
    }


def enroll_content(request, params: Mapping[str, Any]) -> Dict[str, Any]:
    common = _common_lecture_ctx(request, params)
    tabs = common.get("tabs", [])
    tab_map = {item["id"]: item for item in tabs}

    overview_tab = tab_map.get("overview", {"id": "overview", "label": "Aperçu"})
    certificate_tab = tab_map.get("certificate", {"id": "certificate", "label": "Certificat"})
    instructor_tab = tab_map.get("instructor", {"id": "instructor", "label": "Formateur"})

    return {
        "course": common["course"],
        "lecture": common["lecture"],
        "enrolled_count": common["enrolled_count"],
        "enrollment_label": common.get("enrollment_label"),
        "overview_tab": overview_tab,
        "certificate_tab": certificate_tab,
        "instructor_tab": instructor_tab,
        "overview_text": common.get("overview_text", ""),
        "certificate_text": common.get("certificate_text", ""),
        "instructor": common.get("instructor", {}),
        "share_url": common.get("share_url"),
        "share_label": common.get("share_label"),
        "total_lectures": common.get("total_lectures"),
        "overview_heading": common.get("overview_heading"),
        "certificate_heading": common.get("certificate_heading"),
        "instructor_heading": common.get("instructor_heading"),
        "lessons_label": common.get("lessons_label"),
    }


def playlist(request, params: Mapping[str, Any]) -> Dict[str, Any]:
    common = _common_lecture_ctx(request, params)
    title = _s((params or {}).get("title"), "Contenu de la formation")
    count_label = _s((params or {}).get("count_label"), "Leçons")

    return {
        "playlist_title": title,
        "count_label": count_label,
        "section_list": common["section_list"],
        "total_lectures": common["total_lectures"],
        "checkout_url": common["checkout_url"],
        "is_subscribed": common["is_subscribed"],
    }
