# apps/atelier/components/discovery.py
from __future__ import annotations
import copy
import logging
from pathlib import Path
from typing import Iterable, List, Tuple, Dict, Any, Mapping

import yaml
from django.conf import settings
from django.template.loader import get_template
from django.template.loaders.app_directories import get_app_template_dirs
from django.utils.autoreload import autoreload_started  # <= pas de watch_dir global ici

from apps.atelier.config.loader import FALLBACK_NAMESPACE, list_namespaces, is_valid_namespace

from . import registry

log = logging.getLogger("atelier.components.discovery")

MANIFEST_FILENAMES = ("manifest", "manifest.yml", "manifest.yaml")


class ManifestError(Exception):
    pass


def _template_roots() -> List[Path]:
    roots: List[Path] = []
    # TEMPLATES['DIRS']
    for cfg in getattr(settings, "TEMPLATES", []):
        for d in cfg.get("DIRS", []):
            try:
                roots.append(Path(d))
            except Exception:
                pass
    # App template dirs
    for d in get_app_template_dirs("templates"):
        try:
            roots.append(Path(d))
        except Exception:
            pass
    # Uniques seulement
    uniq: List[Path] = []
    seen = set()
    for r in roots:
        try:
            rp = r.resolve()
        except Exception:
            rp = r
        if rp not in seen:
            uniq.append(r)
            seen.add(rp)
    return uniq


def _find_manifests(root: Path) -> Iterable[Tuple[Path, Path]]:
    matches: List[Tuple[Path, Path]] = []
    if not root.exists():
        return matches
    for mf in root.rglob("*"):
        if mf.is_file() and mf.name in MANIFEST_FILENAMES and "components" in mf.parts:
            matches.append((root, mf))
    return matches


def _deduce_namespace(root: Path, manifest: Path, known_namespaces: set[str]) -> str:
    """Déduit le namespace à partir du chemin du manifest relatif au root."""
    try:
        rel = manifest.relative_to(root)
    except ValueError:
        raise ManifestError(f"Manifest hors scope templates: {manifest}")

    parts = list(rel.parts)
    if "components" not in parts:
        raise ManifestError(f"Manifest invalide (pas de dossier 'components'): {manifest}")

    idx = parts.index("components")
    if idx == 0:
        namespace = FALLBACK_NAMESPACE
    else:
        namespace = parts[idx - 1]

    if namespace not in known_namespaces and namespace != FALLBACK_NAMESPACE:
        raise ManifestError(
            f"Manifest dans namespace inconnu '{namespace}' ({manifest}). Namespaces autorisés: {sorted(known_namespaces)}"
        )

    return namespace if namespace != FALLBACK_NAMESPACE else FALLBACK_NAMESPACE


def _load_yaml(path: Path) -> Dict[str, Any]:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as e:
        raise ManifestError(f"YAML invalide ({path}): {e}") from e


def _closest_templates_root(file_path: Path) -> Path:
    """
    Renvoie le root 'templates' le plus proche pour relativiser un chemin de template.
    """
    for root in _template_roots():
        try:
            file_path.relative_to(root)
            return root
        except Exception:
            continue
    roots = _template_roots()
    return roots[0] if roots else file_path.parent


def _validate_template_exists(tpl: str, *, source: Path) -> None:
    try:
        get_template(tpl)
    except Exception as e:
        raise ManifestError(f"Template introuvable '{tpl}' (déclaré dans {source}): {e}") from e


def _as_mapping(val: Any) -> Mapping[str, Any]:
    return val if isinstance(val, Mapping) else {}


def _as_list_of_str(val: Any) -> List[str]:
    if not isinstance(val, (list, tuple)):
        return []
    out: List[str] = []
    for it in val:
        if isinstance(it, str) and it.strip():
            out.append(it.strip())
    return out


def _normalize_manifest(data: Dict[str, Any], *, source: Path) -> Dict[str, Any]:
    """
    Schéma minimal attendu (on **préserve** aussi hydrate/render/compose/params) :
    {
      alias: "header/struct",
      template: "components/header/header_struct.html",
      params: {...},                           # <= défauts manifest (config-first)
      assets: { head:[], css:[], js:[], vendors:[] },
      contract: { required:{}, optional:{} },
      hydrate: { module, func, ... },          # (facultatif) - on préserve tel quel
      render: { cacheable, ttl, vary_on, qa_isolation },  # (facultatif)
      compose: { children: {name: alias, ...} }           # (facultatif)
    }
    """
    alias = (data.get("alias") or "").strip()
    template = (data.get("template") or "").strip()

    if not alias:
        raise ManifestError(f"Champ 'alias' manquant ({source})")
    if not template:
        candidate = source.parent / "component.html"
        if candidate.exists():
            template = str(candidate.relative_to(_closest_templates_root(candidate)))
        else:
            raise ManifestError(f"Champ 'template' manquant et aucun 'component.html' adjacent ({source})")

    # params (défauts manifest)
    params_in = _as_mapping(data.get("params"))
    params = dict(params_in)

    # assets (normalisés avec clés standards)
    assets_in = _as_mapping(data.get("assets"))
    assets = {
        "head": list(assets_in.get("head") or []),
        "css": list(assets_in.get("css") or []),
        "js": list(assets_in.get("js") or []),
        "vendors": list(assets_in.get("vendors") or []),
    }

    # contract
    contract_in = _as_mapping(data.get("contract"))
    contract = {
        "required": dict(contract_in.get("required") or {}),
        "optional": dict(contract_in.get("optional") or {}),
    }

    # hydrate (préservé tel quel)
    hydrate = dict(_as_mapping(data.get("hydrate")))

    # render (on préserve plusieurs champs usuels)
    render_in = _as_mapping(data.get("render"))
    render: Dict[str, Any] = {}
    if "cacheable" in render_in:
        render["cacheable"] = bool(render_in.get("cacheable"))
    if "ttl" in render_in:
        try:
            render["ttl"] = int(render_in.get("ttl") or 0)
        except Exception:
            render["ttl"] = 0
    if "vary_on" in render_in:
        render["vary_on"] = _as_list_of_str(render_in.get("vary_on"))
    if "qa_isolation" in render_in:
        render["qa_isolation"] = bool(render_in.get("qa_isolation"))

    # compose.children (mapping name -> alias)
    compose_in = _as_mapping(data.get("compose"))
    children_in = _as_mapping(compose_in.get("children"))
    children: Dict[str, Dict[str, Any]] = {}
    for name, meta in children_in.items():
        if not isinstance(name, str):
            continue
        child_id = name.strip()
        if not child_id:
            continue

        entry: Dict[str, Any] = {}

        if isinstance(meta, str):
            alias_value = meta.strip()
            if not alias_value:
                continue
            entry["alias"] = alias_value
        elif isinstance(meta, dict):
            alias_value = str(meta.get("alias") or "").strip()
            if not alias_value:
                continue
            entry["alias"] = alias_value

            if "with" in meta:
                entry["with"] = meta["with"]
            if "params" in meta:
                entry["params"] = meta["params"]
            variants = meta.get("variants")
            if isinstance(variants, dict):
                entry["variants"] = variants
            namespace_override = meta.get("namespace")
            if isinstance(namespace_override, str) and namespace_override.strip():
                entry["namespace"] = namespace_override.strip()
            if "cache" in meta:
                entry["cache"] = meta["cache"]
        else:
            continue

        children[child_id] = entry

    compose = {"children": children} if children else {}

    params_in = _as_mapping(data.get("params"))
    params = dict(params_in) if params_in else {}

    # Final
    out = {
        "alias": alias,
        "template": template,
        "assets": assets,
        "contract": contract,
    }
    if params:
        out["params"] = params                   # ⬅️ NEW: remonter params dans le registry
    if hydrate:
        out["hydrate"] = hydrate
    if render:
        out["render"] = render
    if compose:
        out["compose"] = compose

    aliases = _as_list_of_str(data.get("aliases"))
    if aliases:
        out["aliases"] = aliases

    return out


def discover(*, override_existing: bool = False) -> Tuple[int, List[str]]:
    """
    Parcourt tous les templates roots & app template dirs, cherche components/**/manifest.yaml.
    Enregistre chaque composant dans le registre.

    Retourne: (nb_enregistres, warnings)
    """
    warnings: List[str] = []
    items: List[dict] = []

    roots = _template_roots()
    if not roots:
        log.warning("Aucun templates root trouvé (TEMPLATES.DIRS + app dirs).")
        return (0, ["No template roots"])

    manifests: List[Tuple[Path, Path]] = []
    for r in roots:
        manifests.extend(list(_find_manifests(r)))

    if not manifests:
        log.info("Aucun manifest trouvé sous templates/components/**/.")
        return (0, [])

    known_namespaces = set(list_namespaces())

    for root, mf in manifests:
        try:
            data = _load_yaml(mf)
            norm = _normalize_manifest(data, source=mf)
            _validate_template_exists(norm["template"], source=mf)

            try:
                namespace = _deduce_namespace(root, mf, known_namespaces)
            except ManifestError as e:
                log.error(str(e))
                warnings.append(str(e))
                continue

            aliases_extra = norm.pop("aliases", [])
            primary_alias = norm["alias"]
            alias_candidates = [primary_alias]
            for extra_alias in aliases_extra:
                if extra_alias and extra_alias not in alias_candidates:
                    alias_candidates.append(extra_alias)

            for alias_value in alias_candidates:
                if registry.exists(alias_value, namespace=namespace, include_fallback=False) and not override_existing:
                    msg = (
                        f"Collision alias '{alias_value}' dans namespace '{namespace}' — manifest ignoré ({mf}), "
                        "override=False"
                    )
                    log.warning(msg)
                    warnings.append(msg)
                    continue

                item = copy.deepcopy(norm)
                item["alias"] = alias_value
                item["namespace"] = namespace
                items.append(item)

        except ManifestError as e:
            msg = f"[ManifestError] {e}"
            log.error(msg)
            warnings.append(msg)
        except Exception as e:
            msg = f"[Unexpected] {mf}: {e}"
            log.exception(msg)
            warnings.append(msg)

    if items:
        registry.bulk_register(items, override=override_existing)
    return (len(items), warnings)


def _watch_for_manifests(sender, **kwargs):
    for root in _template_roots():
        candidates = [root / "components"]
        for ns in list_namespaces():
            candidates.append(root / ns / "components")
        for comp in candidates:
            if comp.exists():
                sender.watch_dir(str(comp), "*.yml")
                sender.watch_dir(str(comp), "*.yaml")
    log.debug("Autoreload: watching templates/components/** for manifest changes.")


def enable_dev_autoreload():
    if getattr(settings, "DEBUG", False):
        autoreload_started.connect(_watch_for_manifests)
        log.debug("Autoreload activé pour manifests (DEBUG=True).")
