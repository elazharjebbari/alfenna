from __future__ import annotations

from django.conf import settings
from django.test import SimpleTestCase


class CompressorSettingsTest(SimpleTestCase):
    def test_compressor_enabled_and_finders(self) -> None:
        self.assertIs(settings.COMPRESS_ENABLED, True)
        self.assertIn("compressor.finders.CompressorFinder", settings.STATICFILES_FINDERS)
