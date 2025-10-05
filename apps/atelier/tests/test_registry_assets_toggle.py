from __future__ import annotations

import copy

from django.test import SimpleTestCase, override_settings

from apps.atelier.components import registry


class RegistryAssetsToggleTest(SimpleTestCase):
    def setUp(self) -> None:
        self._components = registry._COMPONENTS  # type: ignore[attr-defined]
        self._snapshot = copy.deepcopy(self._components)
        self._components.clear()

    def tearDown(self) -> None:
        self._components.clear()
        for namespace, components in self._snapshot.items():
            self._components[namespace] = components

    @override_settings(ATELIER_DISABLE_REGISTERED_ASSETS=True)
    def test_register_strips_assets_globally(self) -> None:
        registry.register(
            "x/test",
            "components/core/_blank.html",
            assets={
                "css": ["/a.css"],
                "js": ["/a.js"],
                "head": ["<meta>"],
                "vendors": ["vx"],
            },
        )
        meta = registry.get("x/test")
        self.assertEqual(meta["assets"], {"css": [], "js": [], "head": [], "vendors": []})

    @override_settings(
        ATELIER_DISABLE_REGISTERED_ASSETS=False,
        ATELIER_STRIP_REGISTRY_ALIASES=["only/this"],
    )
    def test_register_strips_assets_for_selected_alias(self) -> None:
        registry.register(
            "only/this",
            "components/core/_blank.html",
            assets={"css": ["/a.css"]},
        )
        only = registry.get("only/this")
        self.assertEqual(only["assets"].get("css"), [])

        registry.register(
            "keep/that",
            "components/core/_blank.html",
            assets={"css": ["/b.css"]},
        )
        keep = registry.get("keep/that")
        self.assertEqual(keep["assets"].get("css"), ["/b.css"])
