from __future__ import annotations
from django.core.checks import register, Warning, Error
from .components import registry
from .config.registry import pages as get_pages_registry


@register()
def registry_not_empty_check(app_configs, **kwargs):
    # Pas bloquant: simple Warning si aucun composant
    if not registry.all_aliases():
        return [Warning("Aucun composant enregistré dans le registre Atelier.",
                        hint="Ajoute un manifest sous templates/components/** ou vérifie la découverte.",
                        id="atelier.W001")]
    return []


@register()
def vendors_shape_check(app_configs, **kwargs):
    # Vérification légère des assets
    errors = []
    for alias in registry.all_aliases():
        meta = registry.get(alias)
        assets = (meta.get("assets") or {})
        for key in ("css", "js", "head", "vendors"):
            if key not in assets:
                errors.append(Error(
                    f"Composant {alias}: clef assets.{key} absente.",
                    hint="Déclare assets: {css:[], js:[], head:[], vendors:[]}",
                    id="atelier.E001"))
    return errors


@register()
def manifest_integrity_check(app_configs, **kwargs):
    """
    Soft-check: hydrate.python importable, render.cacheable de type correct.
    """
    warns = []
    for alias in registry.all_aliases():
        meta = registry.get(alias)
        hyd = meta.get("hydrate") or {}
        dotted = (hyd.get("python") or "").strip()
        if dotted:
            try:
                from django.utils.module_loading import import_string
                import_string(dotted)
            except Exception:
                warns.append(Warning(
                    f"Hydrateur non importable: {alias} -> {dotted}",
                    hint="Vérifie le dotted path ou retire 'python' du manifest.",
                    id="atelier.W010"
                ))
        rnd = meta.get("render") or {}
        if "cacheable" in rnd and not isinstance(rnd["cacheable"], (bool, type(None))):
            warns.append(Warning(
                f"render.cacheable invalide pour {alias}: {rnd.get('cacheable')!r}",
                hint="Doit être bool ou omis.",
                id="atelier.W011"
            ))
    return warns


@register()
def pages_params_vs_whitelist_check(app_configs, **kwargs):
    """
    Si pages.yml fournit des params pour un slot, vérifier qu'ils appartiennent
    à la whitelist hydrate.params du composant concerné.
    """
    warns = []
    pages = get_pages_registry() or {}
    for pid, pspec in pages.items():
        slots = (pspec or {}).get("slots") or {}
        for sid, sdef in slots.items():
            sdef = sdef or {}
            variants = sdef.get("variants") or {}
            params = sdef.get("params") or {}
            if not params:
                continue
            for _k, alias in variants.items():
                meta = registry.get(alias)
                wl = set(((meta.get("hydrate") or {}).get("params") or {}).keys())
                extra = [k for k in params.keys() if k not in wl]
                if wl and extra:
                    warns.append(Warning(
                        f"Params hors whitelist pour {pid}.{sid} -> {alias}: {extra}",
                        hint=f"Déclare ces clés dans hydrate.params du manifest '{alias}' "
                             f"ou retire-les du slot.",
                        id="atelier.W020"
                    ))
    return warns
