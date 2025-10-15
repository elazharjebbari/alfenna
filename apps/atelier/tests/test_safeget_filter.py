from django.template import Context, Template
from django.test import SimpleTestCase


class SafeGetFilterTests(SimpleTestCase):
    def test_safeget_returns_value(self) -> None:
        tpl = Template("{% load safeget %}{{ data|safeget:'exists' }}")
        rendered = tpl.render(Context({"data": {"exists": "ok"}}))
        self.assertEqual(rendered, "ok")

    def test_safeget_missing_returns_empty(self) -> None:
        tpl = Template("{% load safeget %}{{ data|safeget:'missing' }}")
        rendered = tpl.render(Context({"data": {"exists": "ok"}}))
        self.assertEqual(rendered, "")

    def test_safeget_handles_non_mapping(self) -> None:
        tpl = Template("{% load safeget %}{{ data|safeget:'missing' }}")
        rendered = tpl.render(Context({"data": None}))
        self.assertEqual(rendered, "")
