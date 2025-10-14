from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml
from django.test import SimpleTestCase

from apps.atelier.i18n.translation_service import TranslationService


def _iter_tokens(node: Any) -> Iterable[str]:
    if isinstance(node, str):
        stripped = node.strip()
        if stripped.startswith("t:"):
            key = stripped[2:].strip()
            if key:
                yield key
        return

    if isinstance(node, Mapping):
        for value in node.values():
            yield from _iter_tokens(value)
        return

    if isinstance(node, (list, tuple)):
        for item in node:
            yield from _iter_tokens(item)


class I18NManifestCoverageTests(SimpleTestCase):
    fixtures: list[str] = []

    def test_manifest_tokens_have_french_translations(self) -> None:
        tokens_per_namespace: dict[str, set[str]] = {"core": set(), "ma": set()}

        manifest_root = Path("templates")
        for manifest_path in manifest_root.rglob("manifest.yml"):
            namespace = "ma" if "/ma/" in manifest_path.as_posix() else "core"

            try:
                data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            except Exception as exc:  # pragma: no cover - guardrail for malformed YAML
                raise AssertionError(f"Impossible de lire {manifest_path}: {exc}") from exc

            tokens = set(_iter_tokens(data))
            if tokens:
                tokens_per_namespace.setdefault(namespace, set()).update(tokens)

        for namespace, tokens in tokens_per_namespace.items():
            service = TranslationService(locale="fr", site_version=namespace)
            missing: list[str] = []
            for token in sorted(tokens):
                if service.t(token, default=None) == token:
                    missing.append(token)

            if missing:
                raise AssertionError(
                    f"Clés i18n manquantes pour namespace '{namespace}': {missing}"
                )
