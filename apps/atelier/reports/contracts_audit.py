from __future__ import annotations
import json
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from types import SimpleNamespace

from django.conf import settings

from apps.atelier.components.registry import all_aliases, get as get_component, NamespaceComponentMissing
from apps.atelier.components.contracts import ContractValidationError, validate as validate_contract
from apps.atelier.compose.hydration import load as hydrate_component
from apps.atelier.config.registry import pages as get_pages_registry
from apps.atelier.config.loader import FALLBACK_NAMESPACE

# Utiliser la dataclass Segments pour un faux request
try:
    from apps.atelier.middleware.segments import Segments
except Exception:
    Segments = None  # fallback si nécessaire


@dataclass
class Issue:
    severity: str  # "ERROR" | "WARN" | "INFO" | "OK"
    alias: str
    page_id: Optional[str]  # peut être None si audit “standalone”
    slot_id: Optional[str]
    field: Optional[str]  # chaîne libre issue du message (si parsée)
    code: str  # ex: "contract.missing", "contract.type", "hydrate.error", "params.extra"
    message: str
    notes: Optional[str] = None


@dataclass
class ItemResult:
    alias: str
    page_id: Optional[str]
    slot_id: Optional[str]
    status: str  # "OK" | "WARN" | "ERROR"
    issues: List[Issue]


@dataclass
class AuditSummary:
    started_at: str
    env: str
    git_sha: Optional[str]
    content_rev: Optional[str]
    total_components: int
    total_checks: int
    ok: int
    warn: int
    error: int
    duration_seconds: float


def _now_ts() -> str:
    return datetime.utcnow().strftime("%Y%m%d-%H%M%S")


def _outdir(base: Optional[str]) -> Path:
    root = Path(base or "reports/contracts")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _mk_dummy_request() -> Any:
    # Faux request minimaliste, stable
    seg = None
    if Segments:
        seg = Segments(lang="fr", device="d", consent="N", source="", campaign="", qa=False)
    req = SimpleNamespace()
    req.request_id = f"audit-{_now_ts()}"
    req._segments = seg or {"lang": "fr", "device": "d", "consent": "N", "source": "", "campaign": "", "qa": False}
    req.GET = {}
    req.COOKIES = {}
    req.META = {"HTTP_USER_AGENT": "contracts-audit"}
    req.headers = {"Accept-Language": "fr"}
    user = SimpleNamespace(is_authenticated=False, first_name="")
    req.user = user
    req.site_version = FALLBACK_NAMESPACE
    return req


def _parse_contract_error_message(msg: str) -> List[Issue]:
    """
    contracts.validate lève/LOG un message du type:
      "[contracts] alias=... erreurs={'cta.url': 'champ requis...', 'promotion_pct':'type invalide: ...'}"
    On essaie d’en tirer des champs/erreurs lisibles. Fallback = 1 issue globale.
    """
    issues: List[Issue] = []
    try:
        # heuristique simple
        start = msg.find("erreurs=")
        if start >= 0:
            payload = msg[start + len("erreurs="):].strip()
            if payload.startswith("{") and payload.endswith("}"):
                data = eval(payload, {"__builtins__": {}})  # dict simple, champs -> str
                if isinstance(data, dict):
                    for k, v in data.items():
                        issues.append(Issue(
                            severity="ERROR",
                            alias="", page_id=None, slot_id=None,
                            field=str(k), code="contract.field", message=str(v)))
                    return issues
    except Exception:
        pass
    issues.append(Issue(
        severity="ERROR", alias="", page_id=None, slot_id=None,
        field=None, code="contract.error", message=msg))
    return issues


def _validate(alias: str, ctx: dict, namespace: str = FALLBACK_NAMESPACE) -> Tuple[str, List[Issue]]:
    """
    Retourne (status, issues)
    - OK: aucune erreur
    - WARN: pas utilisé ici (réservé à extensions futures)
    - ERROR: erreurs de contrat détectées
    """
    try:
        validate_contract(alias, ctx, namespace=namespace)
        return "OK", []
    except NamespaceComponentMissing as e:
        return "ERROR", [Issue(
            severity="ERROR", alias=alias, page_id=None, slot_id=None,
            field=None, code="contract.missing", message=str(e))]
    except ContractValidationError as e:
        extracted = _parse_contract_error_message(str(e))
        for it in extracted:
            it.alias = alias
        return "ERROR", extracted
    except Exception as e:
        return "ERROR", [Issue(
            severity="ERROR", alias=alias, page_id=None, slot_id=None,
            field=None, code="validate.exception", message=str(e))]


def _hydrate(alias: str, request: Any, params: Optional[dict], namespace: str = FALLBACK_NAMESPACE) -> Tuple[dict, List[Issue]]:
    try:
        ctx = hydrate_component(alias, request, params or {}, namespace=namespace)
        if not isinstance(ctx, dict):
            return {}, [Issue(severity="ERROR", alias=alias, page_id=None, slot_id=None,
                              field=None, code="hydrate.nondict", message="Hydrator returned non-dict.")]
        return ctx, []
    except Exception as e:
        return {}, [Issue(severity="ERROR", alias=alias, page_id=None, slot_id=None,
                          field=None, code="hydrate.exception", message=str(e))]


def _iterate_checks() -> Iterable[Tuple[str, Optional[str], Optional[str], Optional[dict], List[Issue]]]:
    """
    Génère des cas de validation:
    - Par alias seul (manifest-driven sans params)
    - Par page/slot quand pages.yml fournit params pour ce slot + compare whitelist
    """
    # 1) alias standalone
    for alias in sorted(all_aliases()):
        yield alias, None, None, None, []

    # 2) par page/slot avec params
    all_pages = get_pages_registry() or {}
    for page_id, pspec in all_pages.items():
        slots = (pspec or {}).get("slots") or {}
        for slot_id, sdef in slots.items():
            sdef = sdef or {}
            variants = sdef.get("variants") or {}
            params = sdef.get("params") or {}
            for _key, alias in variants.items():
                issues: List[Issue] = []
                if params:
                    wl = set(((get_component(alias, namespace=FALLBACK_NAMESPACE).get("hydrate") or {}).get("params") or {}).keys())
                    if wl:
                        extra = [k for k in params.keys() if k not in wl]
                        if extra:
                            issues.append(Issue(
                                severity="WARN", alias=alias, page_id=page_id, slot_id=slot_id,
                                field=",".join(extra), code="params.extra",
                                message=f"Clés hors whitelist: {extra}"
                            ))
                yield alias, page_id, slot_id, dict(params), issues


def run_audit(*, outdir: Optional[str] = None, env: Optional[str] = None,
              content_rev: Optional[str] = None, git_sha: Optional[str] = None) -> Tuple[
    AuditSummary, List[ItemResult]]:
    started = time.time()
    request = _mk_dummy_request()

    results: List[ItemResult] = []
    total, ok, warn, error = 0, 0, 0, 0

    for alias, page_id, slot_id, params, pre_issues in _iterate_checks():
        total += 1
        namespace = getattr(request, "site_version", FALLBACK_NAMESPACE)
        ctx, hyd_issues = _hydrate(alias, request, params, namespace=namespace)
        issues = list(pre_issues)
        if hyd_issues:
            issues.extend(hyd_issues)
            results.append(ItemResult(alias=alias, page_id=page_id, slot_id=slot_id, status="ERROR", issues=issues))
            error += 1
            continue

        status, v_issues = _validate(alias, ctx, namespace=namespace)
        issues.extend(v_issues)

        if any(i.severity == "ERROR" for i in issues):
            error += 1
            results.append(ItemResult(alias=alias, page_id=page_id, slot_id=slot_id, status="ERROR", issues=issues))
        elif issues:
            warn += 1
            results.append(ItemResult(alias=alias, page_id=page_id, slot_id=slot_id, status="WARN", issues=issues))
        else:
            ok += 1
            results.append(ItemResult(alias=alias, page_id=page_id, slot_id=slot_id, status="OK", issues=[]))

    duration = round(time.time() - started, 3)
    summary = AuditSummary(
        started_at=datetime.utcnow().isoformat(timespec="seconds") + "Z",
        env=str(env or getattr(settings, "ENV_NAME", "dev")),
        git_sha=git_sha,
        content_rev=content_rev,
        total_components=len(all_aliases()),
        total_checks=total,
        ok=ok, warn=warn, error=error,
        duration_seconds=duration,
    )

    # Écriture des artefacts
    out = _outdir(outdir)
    stamp = _now_ts()
    jsonl_path = out / f"{stamp}_stream.jsonl"
    md_path = out / f"{stamp}_report.md"

    # JSONL
    with jsonl_path.open("w", encoding="utf-8") as f:
        header = {"_meta": "contracts_audit", "summary": asdict(summary)}
        f.write(json.dumps(header, ensure_ascii=False) + "\n")
        for item in results:
            if item.issues:
                for iss in item.issues:
                    rec = {"alias": item.alias, "page_id": item.page_id, "slot_id": item.slot_id,
                           "severity": iss.severity, "code": iss.code, "field": iss.field, "message": iss.message}
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            else:
                rec = {"alias": item.alias, "page_id": item.page_id, "slot_id": item.slot_id,
                       "severity": "OK", "code": "contract.ok", "field": None, "message": "OK"}
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # Markdown (sans dépendance externe)
    lines: List[str] = []
    lines.append(f"# Rapport contrats — {stamp}")
    lines.append("")
    lines.append(f"- Environnement: **{summary.env}**")
    if summary.git_sha:
        lines.append(f"- Git SHA: `{summary.git_sha}`")
    if summary.content_rev:
        lines.append(f"- content_rev: `{summary.content_rev}`")
    lines.append(f"- Durée: **{summary.duration_seconds}s**")
    lines.append("")
    lines.append(
        f"**Checks:** {summary.total_checks} | **OK:** {summary.ok} | **WARN:** {summary.warn} | **ERROR:** {summary.error}")
    lines.append("")
    # Top issues
    bad = [r for r in results if r.status != "OK"]
    if bad:
        lines.append("## Problèmes détectés")
        lines.append("")
        lines.append("| Alias | Page.Slot | Severity | Code | Field | Message |")
        lines.append("|---|---|---|---|---|---|")
        for it in bad:
            for iss in it.issues:
                pslot = f"{iss.page_id}.{iss.slot_id}" if iss.page_id and iss.slot_id else "—"
                lines.append(
                    f"| `{it.alias}` | {pslot} | {iss.severity} | `{iss.code}` | `{iss.field or ''}` | {iss.message} |")
        lines.append("")
    else:
        lines.append("## Aucun problème détecté ✅")
        lines.append("")
    # OK items (court)
    oks = [r for r in results if r.status == "OK"]
    if oks:
        lines.append("## Composants OK (échantillon)")
        lines.append("")
        sample = oks[: min(20, len(oks))]
        lines.append("| Alias | Page.Slot |")
        lines.append("|---|---|")
        for it in sample:
            pslot = f"{it.page_id}.{it.slot_id}" if it.page_id and it.slot_id else "—"
            lines.append(f"| `{it.alias}` | {pslot} |")
        if len(oks) > len(sample):
            lines.append(f"\n… et {len(oks) - len(sample)} de plus.")
        lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")

    return summary, results
