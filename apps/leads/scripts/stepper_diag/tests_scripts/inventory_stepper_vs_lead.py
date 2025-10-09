from __future__ import annotations

import json
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Set

import yaml
from django.apps import apps
from django.conf import settings

from apps.leads.submissions import _ALLOWED_LEAD_FIELDS

BASE_DIR = Path(settings.BASE_DIR)
TEMPLATE_PATH = BASE_DIR / "templates" / "components" / "core" / "forms" / "lead_step3" / "lead_step3.html"
MANIFEST_PATH = BASE_DIR / "templates" / "components" / "core" / "forms" / "lead_step3" / "manifest.yml"
FLOWFORMS_CONFIG_PATH = BASE_DIR / "configs" / "flowforms.yaml"
LEADS_FIELDS_POLICY_PATH = BASE_DIR / "configs" / "leads_fields.yaml"
REPORT_DIR = BASE_DIR / "var" / "stepper_inventory"
REPORT_PATH = REPORT_DIR / "lead_inventory.md"

DEFAULT_FIELD_MAP = {
    "fullname_key": "full_name",
    "phone_key": "phone",
    "email_key": "email",
    "address_line1_key": "address_line1",
    "address_line2_key": "address_line2",
    "city_key": "city",
    "state_key": "state",
    "postal_code_key": "postal_code",
    "country_key": "country",
    "quantity_key": "quantity",
    "offer_key": "offer_key",
    "pack_slug_key": "pack_slug",
    "product_key": "product",
    "promotion_key": "promotion_selected",
    "payment_mode_key": "payment_mode",
    "payment_method_key": "payment_mode",
    "bump_key": "bump_optin",
    "wa_key": "wa_optin",
}

EXPECTED_FIELDS = {
    1: {
        "email",
        "phone",
        "address_line1",
        "address_line2",
        "city",
        "state",
        "postal_code",
        "country",
    },
    2: {
        "pack_slug",
        "context.complementary_slugs",
    },
    3: {
        "payment_mode",
        "email",
    },
}

CONTEXT_PREFIX = "context."


def _normalize_name(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("{{") and raw.endswith("}}"):
        key = raw[2:-2].strip()
        return DEFAULT_FIELD_MAP.get(key, key)
    return raw


def _extract_fields_from_section(body: str) -> Set[str]:
    names: Set[str] = set()
    for match in re.findall(r"(?<![-:])name=\"([^\"]+)\"", body):
        normalized = _normalize_name(match)
        if normalized:
            names.add(normalized)
    return names


def _parse_step_fields(html: str) -> Dict[int, Set[str]]:
    step_fields: Dict[int, Set[str]] = defaultdict(set)
    pattern = re.compile(r"<section[^>]*data-ff-step=\"(\d+)\"[^>]*>(.*?)</section>", re.DOTALL | re.IGNORECASE)
    for match in pattern.finditer(html):
        step = int(match.group(1))
        body = match.group(2)
        step_fields[step].update(_extract_fields_from_section(body))
    return step_fields


def _parse_progress_steps(html: str) -> Dict[str, List[str]]:
    progress: Dict[str, List[str]] = {}
    progress_match = re.search(r"\"progress_steps\"\s*:\s*\{(.*?)\}\s*,", html, re.DOTALL)
    if not progress_match:
        return progress
    block = progress_match.group(1)
    entry_pattern = re.compile(r"\"(step\d+)\"\s*:\s*\[(.*?)\]", re.DOTALL)
    for step_key, raw_list in entry_pattern.findall(block):
        fields: List[str] = []
        for token in raw_list.split(','):
            token = token.strip().strip('"')
            if not token:
                continue
            fields.append(_normalize_name(token))
        progress[step_key] = fields
    return progress


def _load_yaml(path: Path) -> Dict:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _lead_fields() -> Set[str]:
    Lead = apps.get_model("leads", "Lead")
    fields = set()
    for field in Lead._meta.get_fields():
        if getattr(field, "concrete", False) and not field.many_to_many and not field.auto_created:
            fields.add(field.name)
    return fields


def _format_list(items: Iterable[str]) -> str:
    ordered = sorted(items)
    if not ordered:
        return "- (aucun)"
    return "- " + "\n- ".join(ordered)


def _serialize_json(data) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)


def run():  # pragma: no cover - executed via runscript
    started = time.time()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    html = TEMPLATE_PATH.read_text(encoding="utf-8")
    step_fields = _parse_step_fields(html)
    progress_steps = _parse_progress_steps(html)

    manifest = _load_yaml(MANIFEST_PATH)
    flowforms_config = _load_yaml(FLOWFORMS_CONFIG_PATH)
    leads_policy = _load_yaml(LEADS_FIELDS_POLICY_PATH)

    lead_fields = _lead_fields()
    whitelist = set(_ALLOWED_LEAD_FIELDS)

    collected_all: Set[str] = set()
    for fields in step_fields.values():
        collected_all.update(fields)

    expected_all: Set[str] = set()
    for fields in EXPECTED_FIELDS.values():
        expected_all.update(fields)

    expected_lead_fields = {f for f in expected_all if not f.startswith(CONTEXT_PREFIX)}
    missing_in_lead = sorted(expected_lead_fields - lead_fields)
    missing_in_whitelist = sorted(expected_lead_fields - whitelist)

    collected_not_in_lead = sorted(
        f for f in collected_all
        if not f.startswith(CONTEXT_PREFIX) and f not in lead_fields
    )
    collected_not_in_whitelist = sorted(
        f for f in collected_all
        if not f.startswith(CONTEXT_PREFIX) and f in lead_fields and f not in whitelist
    )

    interesting_lead_fields = {
        "email",
        "phone",
        "address_line1",
        "address_line2",
        "city",
        "state",
        "postal_code",
        "country",
        "pack_slug",
        "payment_mode",
    }
    never_collected = sorted(
        f for f in interesting_lead_fields
        if f in lead_fields and f not in collected_all
    )

    report_lines: List[str] = []
    report_lines.append("# Stepper vs Lead Inventory")
    report_lines.append("")

    report_lines.append("## Sources analysées")
    report_lines.append(f"- manifest: `{MANIFEST_PATH}`")
    report_lines.append(f"- template: `{TEMPLATE_PATH}`")
    report_lines.append(f"- flowforms config: `{FLOWFORMS_CONFIG_PATH}`")
    report_lines.append(f"- leads policy: `{LEADS_FIELDS_POLICY_PATH}`")
    report_lines.append("- serializers: `apps/leads/serializers.py::DynamicLeadSerializer`")
    report_lines.append("- whitelist: `apps/leads/submissions.py::_ALLOWED_LEAD_FIELDS`")
    report_lines.append("- modèle Lead: `apps/leads/models.py::Lead`")
    report_lines.append("")

    report_lines.append("## Stepper – champs collectés par étape")
    for step in sorted(step_fields.keys()):
        collected = sorted(step_fields[step])
        expected = sorted(EXPECTED_FIELDS.get(step, []))
        missing_expected = sorted(set(expected) - set(collected))
        extras = sorted(set(collected) - set(expected))
        report_lines.append(f"### Étape {step}")
        report_lines.append("- fields_collectés_step_{step}:".replace("{step}", str(step)))
        report_lines.append(_format_list(collected).replace("- -", "-"))
        if expected:
            report_lines.append("- fields_attendus_step_{step}:".replace("{step}", str(step)))
            report_lines.append(_format_list(expected).replace("- -", "-"))
        if missing_expected:
            report_lines.append("- manquants_vs_attendus:")
            report_lines.append(_format_list(missing_expected).replace("- -", "-"))
        if extras:
            report_lines.append("- extra_vs_attendus:")
            report_lines.append(_format_list(extras).replace("- -", "-"))
        report_lines.append("")

    report_lines.append("## Flowforms config (progress_steps)")
    if progress_steps:
        for key, fields in sorted(progress_steps.items()):
            report_lines.append(f"- {key}: {fields}")
    else:
        report_lines.append("- (aucun bloc progress_steps détecté)")
    report_lines.append("")

    checkout_flow = {}
    for flow in flowforms_config.get("flows", []):
        if flow.get("key") == "checkout_intent_flow":
            checkout_flow = flow
            break
    if checkout_flow:
        report_lines.append("## Flowforms YAML – checkout_intent_flow")
        report_lines.append("- steps:")
        for step in checkout_flow.get("steps", []):
            field_names = [field.get("name") for field in step.get("fields", [])]
            report_lines.append(f"  - {step.get('key')}: {field_names}")
        report_lines.append("")

    checkout_policy = leads_policy.get("form_kinds", {}).get("checkout_intent", {}).get("fields", {})
    if checkout_policy:
        report_lines.append("## Policy checkout_intent – champs déclarés")
        policy_fields = sorted(checkout_policy.keys())
        report_lines.append("- " + ", ".join(policy_fields))
        report_lines.append("")

    report_lines.append("## Lead vs Stepper – synthèse")
    report_lines.append(f"- fields_lead (total={len(lead_fields)}):")
    report_lines.append(_format_list(sorted(lead_fields)))
    report_lines.append(f"- fields_whitelist (total={len(whitelist)}):")
    report_lines.append(_format_list(sorted(whitelist)))
    report_lines.append(f"- collected_all (total={len(collected_all)}):")
    report_lines.append(_format_list(sorted(collected_all)))
    report_lines.append("")

    if collected_not_in_lead:
        report_lines.append("- collectés_mais_pas_dans_lead:")
        report_lines.append(_format_list(collected_not_in_lead))
    if collected_not_in_whitelist:
        report_lines.append("- collectés_dans_lead_mais_pas_whitelist:")
        report_lines.append(_format_list(collected_not_in_whitelist))
    if missing_in_lead:
        report_lines.append("- attendus_absents_du_lead:")
        report_lines.append(_format_list(missing_in_lead))
    if missing_in_whitelist:
        report_lines.append("- attendus_absents_de_la_whitelist:")
        report_lines.append(_format_list(missing_in_whitelist))
    if never_collected:
        report_lines.append("- jamais_collectés_mais_existent_dans_lead:")
        report_lines.append(_format_list(never_collected))
    report_lines.append("")

    manifest_json = _serialize_json(manifest)
    report_lines.append("## Manifest brut")
    report_lines.append("```")
    report_lines.append(manifest_json)
    report_lines.append("```")

    REPORT_PATH.write_text("\n".join(report_lines), encoding="utf-8")

    duration = round(time.time() - started, 3)
    logs = [
        f"steps={sorted(step_fields.keys())}",
        f"collected={len(collected_all)}",
        f"missing_lead={missing_in_lead}",
        f"missing_whitelist={missing_in_whitelist}",
    ]
    return {"ok": True, "name": __name__, "duration": duration, "logs": logs}
