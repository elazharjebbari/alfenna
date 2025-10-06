from __future__ import annotations

from django.test import SimpleTestCase

from apps.atelier.templatetags.assets import exclude_known_vendors


class ExcludeKnownVendorsTest(SimpleTestCase):
    def test_exclude_known_vendors(self) -> None:
        urls = [
            "/static/vendors/x.js",
            "/static/js/app.js",
            "/static/cookies/tarteaucitron.js-1.25.0/tarteaucitron.min.js",
            "/static/js/main.js",
        ]
        result = exclude_known_vendors(urls)
        self.assertIn("/static/js/app.js", result)
        self.assertNotIn("/static/vendors/x.js", result)
        self.assertNotIn("/static/js/main.js", result)
        joined = "|".join(result)
        self.assertNotIn("tarteaucitron", joined)

    def test_empty_iterable_returns_empty_list(self) -> None:
        self.assertEqual(exclude_known_vendors([]), [])
        self.assertEqual(exclude_known_vendors(None), [])
