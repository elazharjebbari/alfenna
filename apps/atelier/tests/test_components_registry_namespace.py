from __future__ import annotations

from django.test import SimpleTestCase

from apps.atelier.components import registry
from apps.atelier.components.registry import NamespaceComponentMissing
from apps.atelier.config.loader import FALLBACK_NAMESPACE


class ComponentRegistryNamespaceTests(SimpleTestCase):
    def tearDown(self) -> None:
        bucket_core = registry._COMPONENTS.get(FALLBACK_NAMESPACE, {})  # type: ignore[attr-defined]
        bucket_core.pop("test/alias", None)
        bucket_core.pop("test/alias_override", None)
        bucket_ma = registry._COMPONENTS.get("ma", {})  # type: ignore[attr-defined]
        bucket_ma.pop("test/alias_override", None)

    def test_component_lookup_falls_back_to_core(self) -> None:
        registry.register(
            "test/alias",
            template_path="components/core/_blank.html",
            namespace=FALLBACK_NAMESPACE,
        )

        meta = registry.get("test/alias", namespace="ma")
        self.assertEqual(meta["template"], "components/core/_blank.html")

    def test_component_override_in_namespace(self) -> None:
        registry.register(
            "test/alias_override",
            template_path="components/core_template.html",
            namespace=FALLBACK_NAMESPACE,
        )
        registry.register(
            "test/alias_override",
            template_path="components/ma_template.html",
            namespace="ma",
        )

        ma_meta = registry.get("test/alias_override", namespace="ma", fallback=True)
        self.assertEqual(ma_meta["template"], "components/ma_template.html")

    def test_component_not_found_raises(self) -> None:
        with self.assertRaises(NamespaceComponentMissing):
            registry.get("test/unknown_alias", namespace="ma", fallback=False)
