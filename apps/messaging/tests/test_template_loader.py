from __future__ import annotations

import tempfile
from pathlib import Path

from django.test import TestCase

from apps.messaging.models import EmailTemplate
from apps.messaging.template_loader import FileSystemTemplateLoader


class FileSystemTemplateLoaderTests(TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)
        self.locale = "fr"
        self.category = "diagnostic"
        self._write_template(
            category=self.category,
            name="activation",
            subject="Subject v1",
            html="<p>HTML v1</p>",
            text="Text v1",
        )

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def _write_template(self, *, category: str, name: str, subject: str, html: str, text: str) -> None:
        base = self.root / category / self.locale
        base.mkdir(parents=True, exist_ok=True)
        (base / f"{name}.subject.txt").write_text(subject, encoding="utf-8")
        (base / f"{name}.html").write_text(html, encoding="utf-8")
        (base / f"{name}.txt").write_text(text, encoding="utf-8")

    def test_sync_creates_template_once(self) -> None:
        loader = FileSystemTemplateLoader(root=self.root, locale=self.locale)
        created = loader.sync()
        self.assertEqual(len(created), 1)

        slug = f"{self.category}/activation"
        template = EmailTemplate.objects.get(slug=slug, locale=self.locale)
        self.assertEqual(template.subject, "Subject v1")

        # Running sync again without changes should keep the same version
        loader.sync()
        self.assertEqual(
            EmailTemplate.objects.filter(slug=slug, locale=self.locale).count(),
            1,
        )

    def test_sync_creates_new_version_on_change(self) -> None:
        loader = FileSystemTemplateLoader(root=self.root, locale=self.locale)
        loader.sync()

        # Update content to force a new version
        self._write_template(
            category=self.category,
            name="activation",
            subject="Subject v2",
            html="<p>HTML v2</p>",
            text="Text v2",
        )

        loader.sync()
        slug = f"{self.category}/activation"
        templates = EmailTemplate.objects.filter(slug=slug, locale=self.locale).order_by("version")
        self.assertEqual(templates.count(), 2)
        self.assertEqual(templates.last().version, 2)
        self.assertEqual(templates.last().subject, "Subject v2")
