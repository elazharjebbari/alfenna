from __future__ import annotations

from types import SimpleNamespace

from django.test import RequestFactory, SimpleTestCase

from apps.atelier.compose.hydrators.fab import hydrators


class WhatsappHydratorTests(SimpleTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    def _request(self, slug: str = "pack-cosmetique-naturel"):
        request = self.factory.get("/")
        request.resolver_match = SimpleNamespace(kwargs={"product_slug": slug})
        return request

    def test_href_and_vendor_icon(self) -> None:
        params = {
            "phone_tel": "+212719646705",
            "prefill_text": "Bonjour !",
            "icon_mode": "vendor",
            "icon_vendor": "icofont-whatsapp",
            "offset_bottom": "28",
            "offset_right": "22",
        }
        context = hydrators.whatsapp(self._request(), params)
        self.assertTrue(context["href_base"].startswith("https://wa.me/212719646705"))
        self.assertIn("icofont-whatsapp", context["icon_html"])
        self.assertEqual(context["offset_bottom"], 28)
        self.assertEqual(context["offset_right"], 22)
        self.assertEqual(context["label"], params.get("label", "fab.whatsapp.label"))
        self.assertEqual(context["aria_label"], params.get("aria_label", "fab.whatsapp.aria_label"))

    def test_prefill_falls_back_to_slug(self) -> None:
        params = {
            "phone_tel": "+212700000000",
            "prefill_text": "",
        }
        context = hydrators.whatsapp(self._request("pack-demo"), params)
        self.assertIn("pack-demo", context["prefill_text"])

    def test_svg_icon_mode(self) -> None:
        svg = "<svg viewBox=\"0 0 24 24\"></svg>"
        params = {
            "phone_tel": "+212719646705",
            "icon_mode": "svg",
            "icon_svg": svg,
        }
        html = hydrators.whatsapp(self._request(), params)["icon_html"]
        self.assertTrue(html.startswith("<svg"))
