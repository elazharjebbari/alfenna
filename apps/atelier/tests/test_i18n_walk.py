from __future__ import annotations

import copy

from django.test import SimpleTestCase

from apps.atelier.i18n.service import i18n_walk


class I18NWalkTests(SimpleTestCase):
    def test_walk_translates_t_markers_recursively(self) -> None:
        payload = {
            "label": "t:fab.whatsapp.label",
            "sections": [
                {
                    "title": "t:faq.title_html",
                    "tabs": [
                        {
                            "label": "t:faq.tabs.objections.label",
                            "items": [
                                {"question": "t:faq.tabs.objections.items.mycoses.question_html"},
                            ],
                        }
                    ],
                }
            ],
        }

        translated = i18n_walk(payload, "ar", "ma")

        self.assertEqual(translated["label"], "هل تحتاج المساعدة؟")
        self.assertIn("الأسئلة", translated["sections"][0]["title"])
        self.assertEqual(translated["sections"][0]["tabs"][0]["label"], "الاعتراضات السريعة")
        self.assertIn("هل تعالج", translated["sections"][0]["tabs"][0]["items"][0]["question"])

    def test_walk_translates_plain_keys_by_lookup(self) -> None:
        payload = {
            "shop": "footer.shop",
            "support_label": "footer.support",
            "nested": {"brand": "footer.brand"},
        }

        translated = i18n_walk(payload, "ar", "ma")

        self.assertEqual(translated["shop"], "المتجر")
        self.assertEqual(translated["support_label"], "الدعم")
        self.assertEqual(translated["nested"]["brand"], "ألفينا")

    def test_walk_does_not_mutate_input_objects(self) -> None:
        payload = {"cta": {"primary": "t:sticky_order.cta.primary"}}
        baseline = copy.deepcopy(payload)

        result = i18n_walk(
            payload,
            "ar",
            "ma",
        )

        self.assertEqual(payload, baseline)
        self.assertIsNot(result, payload)

    def test_walk_ignores_numbers_booleans_and_unknown_structures(self) -> None:
        payload = {
            "count": 3,
            "active": True,
            "items": [1, 2, 3],
        }

        translated = i18n_walk(payload, "ar", "ma")

        self.assertEqual(translated, payload)

    def test_walk_respects_no_i18n_flag(self) -> None:
        payload = {
            "cta": {
                "_no_i18n": True,
                "primary": "Acheter",
            }
        }

        translated = i18n_walk(
            payload,
            "ar",
            "ma",
        )

        self.assertEqual(translated["cta"], payload["cta"])
        self.assertIsNot(translated["cta"], payload["cta"])
