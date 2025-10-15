from __future__ import annotations

from django.template import Context, Template
from django.test import SimpleTestCase

from apps.leads.utils.fields_map import DEFAULT_FIELDS_MAP, normalize_fields_map


class NormalizeFieldsMapTests(SimpleTestCase):
    def test_defaults_include_payment_aliases(self) -> None:
        result = normalize_fields_map()
        self.assertIn('payment_method', result)
        self.assertIn('payment_mode', result)
        self.assertEqual(result['payment_method'], result['payment_mode'])

    def test_override_payment_method_propagates_to_mode(self) -> None:
        result = normalize_fields_map({'payment_method': 'pay_field'})
        self.assertEqual(result['payment_method'], 'pay_field')
        self.assertEqual(result['payment_mode'], 'pay_field')

    def test_override_payment_mode_propagates_to_method(self) -> None:
        result = normalize_fields_map({'payment_mode': 'mode_field'})
        self.assertEqual(result['payment_method'], 'mode_field')
        self.assertEqual(result['payment_mode'], 'mode_field')

    def test_compact_address_populates_address_line1(self) -> None:
        result = normalize_fields_map({'address': 'shipping_address'})
        self.assertEqual(result['address_line1'], 'shipping_address')

    def test_returns_new_dict_each_call(self) -> None:
        first = normalize_fields_map()
        second = normalize_fields_map()
        self.assertIsNot(first, second)
        first['payment_method'] = 'changed'
        self.assertNotEqual(first['payment_method'], second['payment_method'])


class DefaultFieldsMapTests(SimpleTestCase):
    def test_default_map_contains_expected_keys(self) -> None:
        expected_keys = {
            'fullname',
            'phone',
            'email',
            'payment_method',
            'payment_mode',
        }
        self.assertTrue(expected_keys.issubset(DEFAULT_FIELDS_MAP.keys()))

    def test_safeget_template_filter_handles_missing_key(self) -> None:
        tpl = Template("{% load safeget %}{{ data|safeget:'missing' }}")
        rendered = tpl.render(Context({'data': {'existing': 'value'}}))
        self.assertEqual(rendered, '')
