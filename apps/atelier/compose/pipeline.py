# apps/atelier/compose/pipeline.py
from __future__ import annotations
from typing import Dict, Any, List, Tuple, Optional
import logging
import json
from hashlib import sha256
import uuid

from django.template.loader import render_to_string
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe
from django.conf import settings
from django.utils.translation import get_language_info
from django.templatetags.static import static

from apps.atelier.config.loader import get_page_spec, get_experiments_spec
from apps.atelier.components.registry import get as get_component, NamespaceComponentMissing
from apps.atelier.components.utils import split_alias_namespace
from apps.atelier.components.assets import collect_for as collect_assets_for, order_and_dedupe
from apps.atelier.components.contracts import validate as validate_contract, ContractValidationError
from apps.atelier.compose.cache import ttl_for
from apps.atelier.ab.waffle import resolve_variant, is_preview_active
from apps.atelier import services
from apps.atelier.components.metrics import record_impression, should_record
from apps.atelier.i18n import i18n_walk

log = logging.getLogger("atelier.compose.pipeline")

DEFAULT_SITE_VERSION = "core"


def _stable_content_rev(spec: Dict[str, Any]) -> str:
    return (spec.get("content_rev") or "v1") if isinstance(spec, dict) else "v1"


def _json_stable(obj: Any) -> str:
    try:
        return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except Exception:
        return ""


def _short_hex(h: str, n: int = 10) -> str:
    return h[:n]


def _child_ctx_key(parent_alias: str, child_name: str) -> str:
    parent_safe = (parent_alias or "").replace("/", "_").replace("-", "_")
    return f"{parent_safe}__{child_name}"


def _lookup_ctx_value(ctx: Dict[str, Any], path: str) -> Any:
    current: Any = ctx
    for segment in (path or "").split('.'):
        key = segment.strip()
        if not key:
            return None
        if isinstance(current, dict):
            current = current.get(key)
        else:
            current = getattr(current, key, None)
        if current is None:
            return None
    return current


def _resolve_compose_value(payload: Any, ctx: Dict[str, Any]) -> Any:
    if payload is None:
        return None
    if isinstance(payload, str):
        expr = payload.strip()
        if expr.startswith('{{') and expr.endswith('}}'):
            lookup = expr[2:-2].strip()
            return _lookup_ctx_value(ctx, lookup)
        return payload
    if isinstance(payload, dict):
        return {k: _resolve_compose_value(v, ctx) for k, v in payload.items()}
    if isinstance(payload, list):
        return [_resolve_compose_value(item, ctx) for item in payload]
    return payload


def _merge_params_dict(base: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in (extra or {}).items():
        if value is not None:
            base[key] = value
    return base


def _resolve_alias_expression(alias_expr: Any, ctx: Dict[str, Any]) -> str:
    resolved = _resolve_compose_value(alias_expr, ctx)
    if isinstance(resolved, str):
        return resolved.strip()
    if resolved is None:
        return ""
    return str(resolved).strip()


def _resolve_alias(raw_alias: str, default_namespace: str) -> Tuple[str, str]:
    ns, base = split_alias_namespace(raw_alias, default_namespace)
    return ns, base or raw_alias


def _effective_cacheable(default_cacheable: bool, alias: str, *, namespace: str) -> bool:
    comp = get_component(alias, namespace=namespace)
    rh = (comp.get("render") or {})
    override = rh.get("cacheable", None)
    if override is False:
        return False
    return bool(default_cacheable)


def _hydrate(alias: str, request, params: dict, *, namespace: str) -> Dict[str, Any]:
    from apps.atelier.compose.hydration import load as hydrate
    try:
        ctx = hydrate(alias, request, params or {}, namespace=namespace)
        return ctx if isinstance(ctx, dict) else {}
    except Exception:
        log.exception("Hydration failed for alias=%s", alias)
        return {}


def _validate_ctx(alias: str, ctx: Dict[str, Any], *, where: str, namespace: str) -> None:
    try:
        validate_contract(alias, ctx, namespace=namespace)
    except ContractValidationError as e:
        log.warning("Contract validation failed (%s) alias=%s err=%s", where, alias, e)


def _render_child_inline(child_alias: str, *, request, params: dict, namespace: str) -> str:
    comp = get_component(child_alias, namespace=namespace)
    if not comp or not comp.get("template"):
        return ""
    slot_ctx = {
        "alias": child_alias,
        "alias_base": child_alias,
        "component_namespace": namespace,
        "variant_key": "A",
        "cache": False,
        "cache_key": "",
        "params": params or {},
        "children": _merge_children_effective(
            parent_alias=child_alias,
            slot_children_override={},
            request=request,
            namespace=namespace,
        ),
    }
    page_ctx = {
        "site_version": namespace,
        "id": "",
        "slots": {},
    }
    return _render_parent_with_children(child_alias, request, page_ctx=page_ctx, slot_ctx=slot_ctx)


def _parent_declared_children(parent_alias: str, *, namespace: str) -> Dict[str, Dict[str, Any]]:
    comp = get_component(parent_alias, namespace=namespace) or {}
    declared = (comp.get("compose") or {}).get("children") or {}
    formatted: Dict[str, Dict[str, Any]] = {}
    for cid, meta in declared.items():
        if isinstance(meta, dict):
            formatted[cid] = dict(meta)
        else:
            formatted[cid] = {"alias": str(meta)}
    return formatted


def _merge_children_effective(
    *,
    parent_alias: str,
    slot_children_override: Dict[str, Any],
    request,
    namespace: str,
) -> Dict[str, Dict[str, Any]]:
    declared = _parent_declared_children(parent_alias, namespace=namespace)
    overrides = slot_children_override or {}
    child_ids = sorted(set(list(declared.keys()) + list(overrides.keys())))

    def _as_dict(value: Any) -> Dict[str, Any]:
        return dict(value) if isinstance(value, dict) else {}

    resolved: Dict[str, Dict[str, Any]] = {}
    for cid in child_ids:
        declared_meta = declared.get(cid) or {}
        override_meta = overrides.get(cid) or {}

        declared_alias = declared_meta.get('alias') or ''
        override_alias = override_meta.get('alias') or ''

        declared_variants = declared_meta.get('variants') if isinstance(declared_meta.get('variants'), dict) else {}
        override_variants = override_meta.get('variants') if isinstance(override_meta.get('variants'), dict) else {}

        variants_expr = override_variants or declared_variants or {}
        alias_expr = override_alias or declared_alias
        if not variants_expr:
            if not alias_expr:
                continue
            variants_expr = {"A": alias_expr}
        else:
            if alias_expr and "A" not in variants_expr:
                variants_expr = dict(variants_expr)
                variants_expr["A"] = alias_expr

        namespace_hint = override_meta.get('namespace') or declared_meta.get('namespace') or namespace
        cache_hint = override_meta.get("cache", declared_meta.get("cache"))

        resolved[cid] = {
            "alias": alias_expr,
            "variants": variants_expr,
            "namespace": namespace_hint,
            "with_declared": declared_meta.get('with'),
            "with_override": override_meta.get('with'),
            "params_declared": _as_dict(declared_meta.get('params')),
            "params_override": _as_dict(override_meta.get('params')),
            "cache_hint": cache_hint,
        }

    return resolved


def _children_fingerprint(resolved_children: Dict[str, Dict[str, Any]]) -> Optional[str]:
    if not resolved_children:
        return None
    rows = []
    for cid in sorted(resolved_children.keys()):
        it = resolved_children[cid] or {}
        row = (
            cid,
            it.get("alias", ""),
            _json_stable(it.get("variants") or {}),
            _json_stable(it.get("with_declared") or {}),
            _json_stable(it.get("with_override") or {}),
            _json_stable(it.get("params_declared") or {}),
            _json_stable(it.get("params_override") or {}),
            it.get("namespace", ""),
        )
        rows.append(row)
    payload = _json_stable(rows)
    h = sha256(payload.encode("utf-8")).hexdigest()
    return h


def _parent_cacheable_from_children(
    parent_cacheable_default: bool,
    parent_alias: str,
    resolved_children: Dict[str, Dict[str, Any]],
    *,
    namespace: str,
) -> bool:
    cacheable = _effective_cacheable(parent_cacheable_default, parent_alias, namespace=namespace)
    if not cacheable:
        return False
    for cid, it in resolved_children.items():
        variants = it.get("variants") or {}
        alias_candidate = ""
        if variants:
            for val in variants.values():
                if isinstance(val, str) and "{{" not in val:
                    alias_candidate = val
                    break
        if not alias_candidate:
            alias_candidate = it.get("alias") or ""
        if isinstance(alias_candidate, str) and "{{" in alias_candidate:
            return False
        child_namespace = it.get("namespace") or namespace
        if not alias_candidate:
            continue
        alias_ns, alias_base = _resolve_alias(alias_candidate, child_namespace)
        child_namespace = alias_ns or child_namespace
        if it.get("cache_hint") is False:
            return False
        comp = get_component(alias_base, namespace=child_namespace) or {}
        rh = (comp.get("render") or {})
        if rh.get("cacheable") is False:
            return False
    return True


def _analytics_allowed(request) -> bool:
    if not getattr(settings, "ANALYTICS_ENABLED", True):
        return False
    seg_obj = getattr(request, "_segments", None)
    consent = getattr(seg_obj, "consent", None)
    if consent is None:
        try:
            consent = services.get_segments(request).get("consent", "N")
        except Exception:
            consent = "N"
    return consent == "Y"


def _instrument_slot_html(html: str, page_ctx: Dict[str, Any], slot_ctx: Dict[str, Any], request) -> str:
    if not html:
        return html
    if not _analytics_allowed(request):
        return html

    inst = f"{slot_ctx.get('id') or 'slot'}-{uuid.uuid4().hex[:10]}"
    site_version = slot_ctx.get("component_namespace") or page_ctx.get("site_version") or DEFAULT_SITE_VERSION
    cache_key = (slot_ctx.get("cache_key") or "")[:128]
    attrs = [
        ("data-ll", "comp"),
        ("data-ll-inst", inst),
        ("data-ll-page", str(page_ctx.get("id") or "")),
        ("data-ll-slot", str(slot_ctx.get("id") or "")),
        ("data-ll-alias", str(slot_ctx.get("alias") or "")),
        ("data-ll-alias-base", str(slot_ctx.get("alias_base") or "")),
        ("data-ll-variant", str(slot_ctx.get("variant_key") or "")),
        ("data-ll-site-version", str(site_version)),
        ("data-ll-cache-key", cache_key),
        ("data-ll-content-rev", str(slot_ctx.get("content_rev") or page_ctx.get("content_rev") or "")),
        ("data-ll-request-id", services.get_request_id(request)),
    ]
    attr_html = format_html_join(" ", '{}="{}"', ((k, v) for k, v in attrs if v))
    return format_html('<div {}>{}</div>', attr_html, mark_safe(html))


def _record_slot_impression(request, page_ctx: Dict[str, Any], slot_ctx: Dict[str, Any]) -> None:
    if not _analytics_allowed(request):
        return
    if not should_record(slot_ctx):
        return

    recorded = getattr(request, "_analytics_recorded_slots", None)
    if recorded is None:
        recorded = set()
        request._analytics_recorded_slots = recorded

    key = (
        str(slot_ctx.get("id") or ""),
        str(slot_ctx.get("alias") or ""),
        str(slot_ctx.get("variant_key") or ""),
    )
    if key in recorded:
        return
    recorded.add(key)

    seg_map = services.get_segments(request)
    qa_flag = bool(page_ctx.get("qa_preview") or getattr(getattr(request, "_segments", None), "qa", False))

    record_impression(
        page=str(page_ctx.get("id") or ""),
        slot=str(slot_ctx.get("id") or ""),
        experiment=slot_ctx.get("alias"),
        variant=slot_ctx.get("variant_key"),
        request_id=services.get_request_id(request),
        segments=seg_map,
        qa=qa_flag,
        site_version=slot_ctx.get("component_namespace") or page_ctx.get("site_version") or DEFAULT_SITE_VERSION,
        component_alias=slot_ctx.get("alias_base") or slot_ctx.get("alias"),
        path=request.get_full_path(),
        referer=(request.META.get("HTTP_REFERER") or "")[:512],
        user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:512],
        ip=(request.META.get("REMOTE_ADDR") or "")[:128],
        host=request.get_host() if hasattr(request, "get_host") else "",
    )


def _prepare_slot_output(html: str, page_ctx: Dict[str, Any], slot_ctx: Dict[str, Any], request) -> str:
    if not html:
        return html
    instrumented = _instrument_slot_html(html, page_ctx, slot_ctx, request)
    _record_slot_impression(request, page_ctx, slot_ctx)
    return instrumented


def _render_parent_with_children(
    alias: str,
    request,
    *,
    page_ctx: Dict[str, Any],
    slot_ctx: Dict[str, Any],
) -> str:
    namespace = slot_ctx.get("component_namespace") or page_ctx.get("site_version") or _effective_namespace(request)
    alias_base = slot_ctx.get("alias_base") or alias
    comp = get_component(alias_base, namespace=namespace)
    if not comp or not comp.get("template"):
        return ""

    # 1) Hydrate parent
    slot_params = dict(slot_ctx.get("params") or {})
    ctx = _hydrate(alias_base, request, slot_params, namespace=namespace)

    seg_lang = getattr(getattr(request, "_segments", None), "lang", None)
    lang = seg_lang or getattr(request, "LANGUAGE_CODE", None)
    ctx = i18n_walk(ctx, namespace, lang)

    if "variant_key" not in ctx:
        ctx["variant_key"] = slot_ctx.get("variant_key")

    # 2) Résolution des enfants (si compose actif)
    compose_on = bool(ctx.get("use_child_compose", True))
    resolved_children: Dict[str, Dict[str, Any]] = {}
    if compose_on:
        resolved_children = slot_ctx.get("children") or {}
        if not resolved_children:
            declared = _parent_declared_children(alias_base, namespace=namespace)
            resolved_children = _merge_children_effective(
                parent_alias=alias_base,
                slot_children_override=declared,
                request=request,
                namespace=namespace,
            )

    # 3) Rendu enfants → injecter dans ctx.children
    children_fragments: Dict[str, str] = {}
    for child_name, edef in (resolved_children or {}).items():
        variants_expr = edef.get("variants") or {}
        variants_resolved: Dict[str, str] = {}
        for vkey, expr in variants_expr.items():
            alias_candidate = _resolve_alias_expression(expr, ctx)
            if alias_candidate:
                variants_resolved[str(vkey)] = alias_candidate

        if not variants_resolved:
            alias_expr = edef.get("alias")
            alias_candidate = _resolve_alias_expression(alias_expr, ctx)
            if alias_candidate:
                variants_resolved["A"] = alias_candidate

        if not variants_resolved:
            continue

        try:
            vkey, alias_raw = resolve_variant(f"child_{alias}.{child_name}", variants_resolved, request)
        except Exception:
            alias_raw = next(iter(variants_resolved.values()))
            vkey = "A"

        alias_effective = (alias_raw or variants_resolved.get(vkey) or "").strip()
        if not alias_effective:
            continue

        child_namespace, child_base = _resolve_alias(alias_effective, edef.get("namespace") or namespace)

        params_dict: Dict[str, Any] = {}
        for payload in (edef.get("params_declared"), edef.get("with_declared"), edef.get("with_override")):
            if payload is None:
                continue
            resolved_payload = _resolve_compose_value(payload, ctx)
            if isinstance(resolved_payload, dict):
                _merge_params_dict(params_dict, resolved_payload)

        override_payload = edef.get("params_override")
        if override_payload is not None:
            resolved_override = _resolve_compose_value(override_payload, ctx)
            if isinstance(resolved_override, dict):
                _merge_params_dict(params_dict, resolved_override)
            elif isinstance(override_payload, dict):
                _merge_params_dict(params_dict, override_payload)

        try:
            html = _render_child_inline(child_base, request=request, params=params_dict, namespace=child_namespace)
            key_ns = _child_ctx_key(alias, child_name)
            children_fragments[key_ns] = html
            children_fragments[child_name] = html
        except NamespaceComponentMissing:
            log.exception(
                "Child render failed: parent=%s child_name=%s child_alias=%s",
                alias,
                child_name,
                alias_effective,
            )
            raise
        except Exception:
            log.exception(
                "Child render failed: parent=%s child_name=%s child_alias=%s",
                alias,
                child_name,
                alias_effective,
            )

    if children_fragments:
        ctx_children = dict(ctx.get("children") or {})
        ctx_children.update(children_fragments)
        ctx["children"] = ctx_children

    # 3.bis) Shadow parity (forms/shell uniquement) — fail-soft
    try:
        if alias == "forms/shell" and compose_on:
            from apps.atelier.components.forms.shell.parity import check_parity as _ff_parity
            wiz_compose = (ctx.get("children") or {}).get("wizard", "")
            wiz_shadow = (ctx.get("__shadow_legacy") or {}).get("wizard_html", "")
            parity = _ff_parity(wiz_compose, wiz_shadow)
            log.info(
                "FF Shadow Parity — ok=%s details=%s flow_key=%s",
                parity.get("ok"),
                parity.get("details"),
                (ctx.get("__shadow_legacy") or {}).get("flow_key", ""),
            )
            # On ne lève pas — on laisse le rendu continuer même si parité KO
    except Exception:
        log.exception("Shadow parity check failed (alias=%s).", alias)

    # 4) Valider/rendre parent
    _validate_ctx(alias_base, ctx, where="parent", namespace=namespace)
    return render_to_string(comp["template"], ctx, request=request)



def _effective_namespace(request, explicit: str | None = None) -> str:
    if explicit:
        return explicit
    return getattr(request, "site_version", DEFAULT_SITE_VERSION) or DEFAULT_SITE_VERSION


def build_page_spec(page_id: str, request, *, namespace: str | None = None, extra: dict | None = None) -> Dict[str, Any]:
    ns = _effective_namespace(request, namespace)
    seg_lang = getattr(getattr(request, "_segments", None), "lang", None)
    lang = seg_lang or getattr(request, "LANGUAGE_CODE", None)
    log.info("build_page_spec page_id=%s site_version=%s lang=%s", page_id, ns, lang)
    lang_bidi = False
    lang_code = (lang or getattr(settings, "LANGUAGE_CODE", "en")) or "en"
    try:
        lang_info = get_language_info(lang_code)
        lang_bidi = bool(lang_info.get("bidi"))
    except KeyError:
        lang_bidi = False

    spec = get_page_spec(page_id, namespace=ns) or {}
    slots_def: Dict[str, Any] = spec.get("slots") or {}
    page_qa_preview = False
    base_rev = _stable_content_rev(spec)
    page_rev = f"{base_rev}|ff:cb:{1 if settings.CHATBOT_ENABLED else 0}"
    _ = get_experiments_spec(request=request)
    seg = services.get_segments(request)
    segments_qa = bool(getattr(getattr(request, "_segments", None), "qa", False))

    # ⬇️ Récupère proprement les kwargs d'URL (ex: {"course_slug": "..."}).
    route_kwargs: Dict[str, Any] = {}
    rm = getattr(request, "resolver_match", None)
    if rm and isinstance(getattr(rm, "kwargs", None), dict):
        route_kwargs.update(rm.kwargs)
    # Optionnel : la vue peut déjà avoir posé des kwargs “forcés”
    if isinstance(getattr(request, "_route_kwargs", None), dict):
        route_kwargs.update(request._route_kwargs)

    out_slots: Dict[str, Dict[str, Any]] = {}

    for sid, s in slots_def.items():
        if not isinstance(s, dict):
            continue

        variant_key = "A"
        raw_alias = s.get("component") or sid
        alias_ns, alias_base = _resolve_alias(raw_alias, ns)
        alias_effective = raw_alias
        slot_experiment = s.get("experiment") or f"{page_id}.{sid}"
        slot_preview_active = False

        if "variants" in s:
            variants = s.get("variants") or {}
            variant_key, variant_alias = resolve_variant(slot_experiment, variants, request)
            alias_ns, alias_base = _resolve_alias(variant_alias, ns)
            alias_effective = variant_alias
            slot_preview_active = bool(s.get("experiment") and is_preview_active(request, slot_experiment))

        qa_flag = bool(slot_preview_active or segments_qa)
        page_qa_preview = page_qa_preview or slot_preview_active

        if not settings.CHATBOT_ENABLED:
            alias_to_check = str(alias_effective or "")
            raw_comp = str(raw_alias or "")
            if raw_comp.startswith("chatbot/") or alias_to_check.startswith("chatbot/"):
                log.info("feature_flag.chatbot: stripped slot id=%s alias=%s", sid, alias_effective)
                continue

        slot_children_override = dict(s.get("children") or {})
        resolved_children = _merge_children_effective(
            parent_alias=alias_base,
            slot_children_override=slot_children_override,
            request=request,
            namespace=alias_ns,
        )

        ch_fpr = _children_fingerprint(resolved_children)
        if ch_fpr:
            content_rev_eff = f"{page_rev}|ch:{_short_hex(ch_fpr)}"
        else:
            content_rev_eff = page_rev

        cacheable_default = bool(s.get("cache", True))
        cacheable = _parent_cacheable_from_children(
            cacheable_default, alias_base, resolved_children, namespace=alias_ns
        )

        cache_key = ""
        if cacheable:
            cache_key = services.build_cache_key(
                page_id=page_id,
                slot_id=sid,
                variant_key=variant_key,
                segments=seg,
                content_rev=content_rev_eff,
                qa=qa_flag,
                site_version=alias_ns,
            )

        children_aliases: List[str] = []
        for edef in resolved_children.values():
            variants = edef.get("variants") or {}
            if variants:
                children_aliases.extend([str(val) for val in variants.values() if val])
            else:
                alias_expr = edef.get("alias")
                if alias_expr:
                    children_aliases.append(str(alias_expr))

        # ⬇️ MERGE DES PARAMS (sans casser l’existant)
        # 1) params du manifest (priorité la plus forte, on ne les écrase pas)
        merged_params = dict(s.get("params") or {})
        # 2) kwargs d’URL : comblent seulement les clés manquantes
        for k, v in route_kwargs.items():
            merged_params.setdefault(k, v)
        # 3) extra explicite : peut volontairement override le manifest
        if extra:
            for k, v in extra.items():
                if v is not None:
                    merged_params[k] = v

        out_slots[sid] = {
            "id": sid,
            "alias": alias_effective,
            "alias_base": alias_base,
            "component_namespace": alias_ns,
            "variant_key": variant_key,
            "cache": cacheable,
            "cache_key": cache_key,
            "params": merged_params,
            "children": resolved_children,
            "content_rev": content_rev_eff,
            "children_aliases": children_aliases,
            "qa_preview": slot_preview_active,
        }

    return {
        "id": page_id,
        "slots": out_slots,
        "assets": {"css": [], "js": [], "head": []},
        "qa_preview": page_qa_preview,
        "content_rev": page_rev,
        "site_version": ns,
        "lang": lang,
        "language_bidi": lang_bidi,
    }


def render_slot_fragment(page_ctx: Dict[str, Any], slot_ctx: Dict[str, Any], request) -> Dict[str, str]:
    alias_raw = slot_ctx.get("alias") or ""
    ns_default = page_ctx.get("site_version") or _effective_namespace(request)
    alias_ns = slot_ctx.get("component_namespace") or ns_default
    alias_base = slot_ctx.get("alias_base") or split_alias_namespace(alias_raw, alias_ns)[1]
    comp = get_component(alias_base, namespace=alias_ns)
    if not comp or not comp.get("template"):
        return {"html": ""}

    log.info(
        "render_slot_fragment page=%s slot=%s site_version=%s",
        page_ctx.get("id"),
        slot_ctx.get("id"),
        alias_ns,
    )

    cacheable = bool(slot_ctx.get("cache", True))
    cache_key = (slot_ctx.get("cache_key") or "").strip()
    if cacheable and not cache_key:
        seg = services.get_segments(request)
        slot_preview_active = bool(slot_ctx.get("qa_preview"))
        segments_qa = bool(getattr(getattr(request, "_segments", None), "qa", False))
        qa_flag = bool(slot_preview_active or page_ctx.get("qa_preview") or segments_qa)
        cache_key = services.build_cache_key(
            page_id=str(page_ctx.get("id") or ""),
            slot_id=str(slot_ctx.get("id") or ""),
            variant_key=str(slot_ctx.get("variant_key") or "A"),
            segments=seg,
            content_rev=str(slot_ctx.get("content_rev") or page_ctx.get("content_rev") or "v1"),
            qa=qa_flag,
            site_version=alias_ns,
        )

    fc = services.FragmentCache(request=request)

    if cacheable and cache_key:
        cached = fc.get(cache_key)
        if cached is not None:
            output_html = _prepare_slot_output(cached, page_ctx, slot_ctx, request)
            return {"html": output_html}

    raw_html = _render_parent_with_children(alias_base, request, page_ctx=page_ctx, slot_ctx=slot_ctx)

    if cacheable and cache_key:
        ttl = ttl_for(slot_ctx.get("id") or "", slot_ctx.get("alias_base") or alias_base)
        fc.set(cache_key, raw_html, ttl)

    output_html = _prepare_slot_output(raw_html, page_ctx, slot_ctx, request)
    return {"html": output_html}


def collect_page_assets(page_ctx: Dict[str, Any]) -> Dict[str, list]:
    aliases: List[str] = []
    for s in (page_ctx.get("slots") or {}).values():
        a = s.get("alias")
        if a and "{{" not in str(a):
            aliases.append(a)
        for ch_alias in (s.get("children_aliases") or []):
            if ch_alias and "{{" not in str(ch_alias):
                aliases.append(ch_alias)
    namespace = page_ctx.get("site_version") or DEFAULT_SITE_VERSION
    collected = collect_assets_for(aliases, namespace=namespace)
    assets = order_and_dedupe(collected)
    if bool(page_ctx.get("language_bidi")):
        rtl_href = static("css/rtl.css")
        css_list = assets.setdefault("css", [])
        if rtl_href not in css_list:
            css_list.append(rtl_href)
    return assets


def render_page(request, page_id: str, content_rev: str, *, namespace: str | None = None) -> Dict[str, Any]:
    page_ctx = build_page_spec(page_id, request, namespace=namespace)

    fragments: Dict[str, str] = {}
    fc = services.FragmentCache(request=request)

    for slot_id, slot_ctx in (page_ctx.get("slots") or {}).items():
        cacheable = bool(slot_ctx.get("cache", True))
        cache_key = (slot_ctx.get("cache_key") or "").strip()

        if cacheable and cache_key:
            cached = fc.get(cache_key)
            if cached is not None:
                fragments[slot_id] = _prepare_slot_output(cached, page_ctx, slot_ctx, request)
                continue

        raw_html = _render_parent_with_children(slot_ctx.get("alias_base") or slot_ctx.get("alias"), request, page_ctx=page_ctx, slot_ctx=slot_ctx)
        fragments[slot_id] = _prepare_slot_output(raw_html, page_ctx, slot_ctx, request)

        if cacheable and cache_key:
            fc.set(cache_key, raw_html, ttl_for(slot_id, slot_ctx.get("alias_base") or slot_ctx.get("alias") or ""))

    page_assets = collect_page_assets(page_ctx)
    return {"fragments": fragments, "assets": page_assets}
