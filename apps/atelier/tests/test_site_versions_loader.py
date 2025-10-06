from __future__ import annotations

from django.test import SimpleTestCase

from apps.atelier.config.loader import load_config, get_page_spec


class SiteVersionsLoaderTests(SimpleTestCase):
    def test_load_configs_core_and_ma(self) -> None:
        core_meta = load_config("core")["pages"]["online_home"]["meta"]["title"]
        ma_meta = load_config("ma")["pages"]["online_home"]["meta"]["title"]
        self.assertNotEqual(core_meta, ma_meta)

    def test_get_page_spec_falls_back_to_core(self) -> None:
        spec_unknown = get_page_spec("online_home", namespace="unknown")
        spec_core = get_page_spec("online_home", namespace="core")
        self.assertEqual(spec_unknown, spec_core)
