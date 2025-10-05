from __future__ import annotations

import importlib
import inspect
from pathlib import Path

from django.test import TestCase

from apps.atelier.components.registry import get as reg_get


class CarouselSwiperTests(TestCase):
    def setUp(self):
        self.meta = reg_get("carousel_multi/swiper", namespace="core")

    def test_registry_resolves_alias(self):
        template_path = Path("templates") / self.meta["template"]
        self.assertTrue(template_path.exists(), f"Template missing: {template_path}")

    def test_hydrator_is_callable_with_two_params(self):
        hydrate_meta = self.meta.get("hydrate", {})
        module = importlib.import_module(hydrate_meta["module"])
        func = getattr(module, hydrate_meta["func"])
        self.assertTrue(callable(func))
        signature = inspect.signature(func)
        self.assertEqual(len(signature.parameters), 2)

