from __future__ import annotations

from django.test import SimpleTestCase, override_settings

from apps.adsbridge import conf


class AdsConfTests(SimpleTestCase):
    def test_invalid_mode_defaults_to_on(self) -> None:
        with override_settings(ADS_S2S_MODE="invalid"):
            self.assertEqual(conf.current_mode(), "on")

    def test_capture_flags(self) -> None:
        with override_settings(ADS_S2S_MODE="capture"):
            state = conf.describe_mode()
            self.assertTrue(state.capture)
            self.assertFalse(state.upload)
            self.assertEqual(conf.hold_reason(), "Capture mode active")
            self.assertFalse(conf.should_enqueue())

    def test_mock_flags(self) -> None:
        with override_settings(ADS_S2S_MODE="mock"):
            state = conf.describe_mode()
            self.assertEqual(state.mode, "mock")
            self.assertTrue(state.mock)
            self.assertTrue(conf.should_enqueue())
            self.assertIn("mock", conf.mode_message())
