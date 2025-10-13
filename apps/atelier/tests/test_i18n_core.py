from __future__ import annotations

from django.test import SimpleTestCase

from apps.atelier import i18n


class AtelierI18NTests(SimpleTestCase):
    def setUp(self) -> None:
        i18n._load_namespace.cache_clear()

    def test_load_messages_caching(self):
        info_before = i18n._load_namespace.cache_info()
        messages_fr = i18n.load_messages("core", "fr")
        self.assertIn("footer", messages_fr)
        info_after_first = i18n._load_namespace.cache_info()
        self.assertEqual(info_after_first.misses, info_before.misses + 1)

        # second call should hit the cache
        i18n.load_messages("core", "fr")
        info_after_second = i18n._load_namespace.cache_info()
        self.assertEqual(info_after_second.hits, info_after_first.hits + 1)

    def test_tr_key_hit_and_miss(self):
        translated = i18n.tr("core", "fr", "footer.shop")
        self.assertEqual(translated, "Boutique")

        untouched = i18n.tr("core", "fr", "Plain text sentence")
        self.assertEqual(untouched, "Plain text sentence")

    def test_i18n_walk_nested(self):
        payload = {
            "title": "faq.title",
            "items": ["footer.shop", {"label": "footer.support"}, 42],
            "metadata": ("footer.brand", "unchanged"),
        }

        converted = i18n.i18n_walk(payload, namespace="ma", lang="ar")

        self.assertEqual(converted["title"], "الأسئلة الشائعة")
        self.assertEqual(converted["items"][0], "المتجر")
        self.assertEqual(converted["items"][1]["label"], "الدعم")
        self.assertEqual(converted["items"][2], 42)
        self.assertEqual(converted["metadata"][0], "ألفينا")
        self.assertEqual(converted["metadata"][1], "unchanged")
