from django import forms
from django.test import SimpleTestCase

from apps.flowforms.engine.forms_builder import build_form_for_step


class FormsBuilderChoicesTests(SimpleTestCase):
    def test_radio_pack_slug_renders_inputs(self):
        step_cfg = {
            "key": "step2",
            "title": "Choix du pack",
            "fields": [
                {
                    "name": "pack_slug",
                    "type": "radio",
                    "required": True,
                    "choices": [["solo", "Pack Solo"], ["duo", "Pack Duo"]],
                }
            ],
            "ctas": [{"action": "next", "label": "Continuer"}],
        }

        form = build_form_for_step(step_cfg)
        field = form.fields["pack_slug"]

        self.assertIsInstance(field.widget, forms.RadioSelect)
        self.assertEqual(list(field.widget.choices), [("solo", "Pack Solo"), ("duo", "Pack Duo")])

        rendered = str(form["pack_slug"])
        self.assertIn('type="radio"', rendered)
        self.assertIn('value="solo"', rendered)
        self.assertIn('value="duo"', rendered)

    def test_select_currency_renders_options(self):
        step_cfg = {
            "key": "step3",
            "title": "Validation",
            "fields": [
                {
                    "name": "currency",
                    "type": "select",
                    "required": True,
                    "choices": [["MAD", "MAD"], ["EUR", "EUR"]],
                }
            ],
            "ctas": [{"action": "next", "label": "Confirmer"}],
        }

        form = build_form_for_step(step_cfg)
        field = form.fields["currency"]

        self.assertIsInstance(field.widget, forms.Select)
        self.assertEqual(list(field.widget.choices), [("MAD", "MAD"), ("EUR", "EUR")])

        rendered = str(form["currency"])
        self.assertIn("<select", rendered)
        self.assertIn('value="MAD"', rendered)
        self.assertIn('value="EUR"', rendered)

    def test_checkbox_multiple_renders_inputs(self):
        step_cfg = {
            "key": "stepx",
            "title": "Extras",
            "fields": [
                {
                    "name": "context.complementary_slugs",
                    "type": "checkbox",
                    "required": False,
                    "choices": [["oil", "Huile"], ["mask", "Masque"]],
                }
            ],
            "ctas": [{"action": "next", "label": "Suite"}],
        }

        form = build_form_for_step(step_cfg)
        field = form.fields["context.complementary_slugs"]

        self.assertIsInstance(field.widget, forms.CheckboxSelectMultiple)
        self.assertEqual(list(field.widget.choices), [("oil", "Huile"), ("mask", "Masque")])

        rendered = str(form["context.complementary_slugs"])
        self.assertIn('type="checkbox"', rendered)
        self.assertIn('value="oil"', rendered)
        self.assertIn('value="mask"', rendered)

    def test_radio_without_choices_raises(self):
        step_cfg = {
            "key": "step2",
            "title": "Choix du pack",
            "fields": [
                {"name": "pack_slug", "type": "radio", "required": True},
            ],
            "ctas": [{"action": "next", "label": "Continuer"}],
        }

        with self.assertRaises(ValueError):
            build_form_for_step(step_cfg)
