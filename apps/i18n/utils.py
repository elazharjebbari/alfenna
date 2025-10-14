from __future__ import annotations

from typing import Optional

from django.db import models


def model_identifier(instance: models.Model) -> str:
    slug = getattr(instance, "slug", None)
    if slug:
        return str(slug)
    return str(getattr(instance, "pk", ""))


def model_label(instance: models.Model) -> str:
    return f"{instance._meta.app_label}.{instance._meta.model_name}"


def _compose_field_name(field: str, *, suffix: Optional[str] = None, site_version: Optional[str] = None) -> str:
    field_name = field if suffix is None else f"{field}.{suffix}"
    if site_version and site_version not in {"", "core"}:
        field_name = f"{field_name}@{site_version}"
    return field_name


def build_translation_key(
    instance: models.Model,
    field: str,
    *,
    suffix: Optional[str] = None,
    site_version: Optional[str] = None,
) -> str:
    label = model_label(instance)
    identifier = model_identifier(instance)
    field_name = _compose_field_name(field, suffix=suffix, site_version=site_version)
    return f"db:{label}:{identifier}:{field_name}"


def parse_translation_key(key: str) -> tuple[str, str, str]:
    if not isinstance(key, str) or not key.startswith("db:"):
        raise ValueError(f"Clé de traduction invalide: {key!r}")
    try:
        _, model_label_value, object_id, field = key.split(":", 3)
    except ValueError as exc:  # pragma: no cover - garde-fou
        raise ValueError(f"Format de clé inattendu: {key!r}") from exc
    return model_label_value, object_id, field


def split_field_components(field: str) -> tuple[str, Optional[str], Optional[str]]:
    if "@" in field:
        base, site = field.rsplit("@", 1)
    else:
        base, site = field, None

    suffix = None
    if "." in base:
        base_field, suffix = base.split(".", 1)
    else:
        base_field = base

    return base_field, suffix, site
