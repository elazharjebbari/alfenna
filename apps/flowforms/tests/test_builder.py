from django.test import TestCase
from django import forms

from apps.flowforms.engine import build_form_for_step
from apps.leads.models import Lead

class FlowFormsBuilderTests(TestCase):
    def setUp(self):
        self.lead = Lead.objects.create(
            form_kind="checkout_intent",
            email="old@example.com",
            accept_terms=False,
            idempotency_key="k-1",
        )

    def test_builder_required_and_widgets(self):
        step = {
            "key": "s1",
            "fields": [
                {"name": "email", "type": "email", "required": True, "label": "Votre email"},
                {"name": "phone", "type": "phone", "required": False, "max_length": 32},
                {"name": "accept_terms", "type": "bool", "required": True, "label": "CGU"},
                {"name": "context.note", "type": "textarea", "required": False, "max_length": 200},
            ],
        }
        form = build_form_for_step(step, instance=self.lead)
        self.assertIn("email", form.fields)
        self.assertIsInstance(form.fields["email"], forms.EmailField)
        self.assertTrue(form.fields["email"].required)

        self.assertIn("phone", form.fields)
        self.assertFalse(form.fields["phone"].required)

        self.assertIn("accept_terms", form.fields)
        self.assertIsInstance(form.fields["accept_terms"], forms.BooleanField)
        self.assertTrue(form.fields["accept_terms"].required)

        self.assertIn("context.note", form.fields)
        self.assertIsInstance(form.fields["context.note"], forms.CharField)
        self.assertIsInstance(form.fields["context.note"].widget, forms.Textarea)

        # Validation
        data = {
            "email": "new@example.com",
            "phone": "+212 600 000 000",
            "accept_terms": True,
            "context.note": "hello",
        }
        form = build_form_for_step(step, instance=self.lead)
        form = form.__class__(data=data, instance=self.lead)  # rebind with POSTed data
        self.assertTrue(form.is_valid(), form.errors)
        lead = form.save()
        self.assertEqual(lead.email, "new@example.com")
        self.assertEqual(lead.context.get("note"), "hello")
        self.assertTrue(lead.accept_terms)

    def test_builder_select_choices(self):
        step = {
            "key": "s2",
            "fields": [
                {"name": "invoice_language", "type": "select", "required": True,
                 "choices": [["fr", "Français"], ["en", "English"]]},
                {"name": "context.channel", "type": "radio", "required": True,
                 "choices": ["email", "phone"]},
                {"name": "newsletter_optin", "type": "checkbox", "required": False},  # bool checkbox
            ],
        }
        form = build_form_for_step(step, instance=self.lead)
        self.assertIsInstance(form.fields["invoice_language"], forms.ChoiceField)
        self.assertIsInstance(form.fields["context.channel"].widget, forms.RadioSelect)
        self.assertIsInstance(form.fields["newsletter_optin"], forms.BooleanField)

        data = {
            "invoice_language": "en",
            "context.channel": "email",
            "newsletter_optin": True,
        }
        form = form.__class__(data=data, instance=self.lead)
        self.assertTrue(form.is_valid(), form.errors)
        lead = form.save()
        self.assertEqual(lead.invoice_language, "en")
        self.assertEqual(lead.context.get("channel"), "email")
        self.assertTrue(lead.newsletter_optin)

    def test_builder_context_field_roundtrip(self):
        # initial depuis instance.context
        self.lead.context = {"note": "draft", "city_pref": "rabat"}
        self.lead.save()

        step = {
            "key": "s3",
            "fields": [
                {"name": "context.note", "type": "text", "required": False},
                {"name": "context.city_pref", "type": "select", "required": False,
                 "choices": ["rabat", "casablanca", "marrakech"]},
            ],
        }
        form = build_form_for_step(step, instance=self.lead)
        self.assertEqual(form.fields["context.note"].initial, "draft")
        self.assertEqual(form.fields["context.city_pref"].initial, "rabat")

        data = {"context.note": "updated", "context.city_pref": "casablanca"}
        form = form.__class__(data=data, instance=self.lead)
        self.assertTrue(form.is_valid(), form.errors)
        lead = form.save()
        self.assertEqual(lead.context.get("note"), "updated")
        self.assertEqual(lead.context.get("city_pref"), "casablanca")