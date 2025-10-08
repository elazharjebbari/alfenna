from __future__ import annotations

from django.template.loader import render_to_string
from django.test import SimpleTestCase

from apps.atelier.compose.hydrators.footer import hydrators as footer_hydrators


class FooterComponentTests(SimpleTestCase):
    def test_footer_hydrator_populates_links_contact(self) -> None:
        params = {
            "links_contact": [
                {"label": "Support WhatsApp", "url": "https://api.whatsapp.com/send?phone=212600000000"},
            ],
            "links_quick": [],
            "links_shop": [],
        }

        ctx = footer_hydrators.footer_main(None, params)

        self.assertIn("links_contact", ctx)
        self.assertEqual(ctx["links_contact"][0]["url"], "https://api.whatsapp.com/send?phone=212600000000")

    def test_footer_template_renders_contact_links(self) -> None:
        html = render_to_string(
            "components/core/footer/footer.html",
            {
                "links_shop": [{"label": "Pack", "url": "/pack"}],
                "links_contact": [
                    {"label": "WhatsApp", "url": "https://api.whatsapp.com/send?phone=212600000000"},
                    {"label": "Conseils", "url": "/conseils"},
                ],
                "links_quick": [],
                "socials": [],
                "address_url": "",
                "address_text": "",
                "email": "",
                "phone_tel": "",
                "phone_display": "",
                "opening_hours": "",
                "year": 2025,
            },
        )

        self.assertIn("https://api.whatsapp.com/send?phone=212600000000", html)
        self.assertIn("WhatsApp", html)
