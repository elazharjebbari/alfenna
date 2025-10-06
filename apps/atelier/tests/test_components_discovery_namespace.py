from __future__ import annotations

import textwrap
from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase, override_settings
from django.conf import settings

from apps.atelier.components import discovery
from apps.atelier.components.registry import (
    get as get_component,
    NamespaceComponentMissing,
    InvalidNamespaceError,
)
from apps.atelier.components import registry
from apps.atelier.config.loader import FALLBACK_NAMESPACE, list_namespaces


class ComponentsDiscoveryNamespaceTests(SimpleTestCase):
    def _templates_override(self, extra_dir: str):
        templates = []
        for cfg in settings.TEMPLATES:
            new_cfg = cfg.copy()
            dirs = list(new_cfg.get("DIRS", []))
            new_cfg["DIRS"] = [extra_dir] + dirs
            templates.append(new_cfg)
        return templates

    def test_manifest_outside_allowed_namespace_rejected(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            other_manifest = root / "other" / "components" / "demo" / "manifest"
            other_manifest.parent.mkdir(parents=True)
            (root / "other" / "components" / "demo" / "template.html").write_text("demo", encoding="utf-8")
            other_manifest.write_text(
                textwrap.dedent(
                    """
                    alias: other/demo
                    template: other/components/demo/template.html
                    """
                ).strip(),
                encoding="utf-8",
            )

            with override_settings(TEMPLATES=self._templates_override(tmp)):
                count, warnings = discovery.discover(override_existing=True)

        self.assertTrue(any("namespace inconnu" in w for w in warnings))
        with self.assertRaises(InvalidNamespaceError):
            get_component("other/demo", namespace="other", fallback=False)

    def test_namespace_detection_from_path(self) -> None:
        if "ma" not in list_namespaces():
            self.skipTest("Namespace 'ma' not available in configs")

        alias = "test/ma_component"
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            tpl_path = root / "ma" / "components" / "demo" / "template.html"
            tpl_path.parent.mkdir(parents=True)
            tpl_path.write_text("MA component", encoding="utf-8")
            manifest = tpl_path.parent / "manifest"
            manifest.write_text(
                textwrap.dedent(
                    """
                    alias: test/ma_component
                    template: ma/components/demo/template.html
                    """
                ).strip(),
                encoding="utf-8",
            )

            with override_settings(TEMPLATES=self._templates_override(tmp)):
                count, warnings = discovery.discover(override_existing=True)
                self.assertEqual(len(warnings), 0)
                self.assertGreaterEqual(count, 1)

            meta = get_component(alias, namespace="ma", fallback=False)
            self.assertEqual(meta["template"], "ma/components/demo/template.html")

        # Cleanup registered test component
        registry._COMPONENTS.get("ma", {}).pop(alias, None)  # type: ignore[attr-defined]
