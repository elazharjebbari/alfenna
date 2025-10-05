"""Utilities to synchronise on-disk email templates into the database."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from django.conf import settings

from .models import EmailTemplate


@dataclass
class TemplateDefinition:
    slug: str
    locale: str
    subject: str
    html_body: str
    text_body: str
    source_paths: dict[str, str]


class FileSystemTemplateLoader:
    """Reads e-mail template triplets (subject/html/text) from the filesystem."""

    def __init__(self, *, root: Optional[Path] = None, locale: str = "fr") -> None:
        self.root = Path(root or (settings.BASE_DIR / "templates" / "email"))
        self.locale = locale

    def discover(self) -> Iterable[TemplateDefinition]:
        if not self.root.exists():
            return []
        definitions: list[TemplateDefinition] = []
        for category_dir in sorted(self.root.iterdir()):
            if not category_dir.is_dir():
                continue
            locale_dir = category_dir / self.locale
            if not locale_dir.exists():
                continue
            for subject_file in sorted(locale_dir.glob("*.subject.txt")):
                stem = subject_file.stem.replace(".subject", "")
                html_file = locale_dir / f"{stem}.html"
                text_file = locale_dir / f"{stem}.txt"
                if not html_file.exists() or not text_file.exists():
                    continue
                slug = f"{category_dir.name}/{stem}"
                definitions.append(
                    TemplateDefinition(
                        slug=slug,
                        locale=self.locale,
                        subject=subject_file.read_text(encoding="utf-8").strip(),
                        html_body=html_file.read_text(encoding="utf-8"),
                        text_body=text_file.read_text(encoding="utf-8"),
                        source_paths={
                            "subject": str(subject_file),
                            "html": str(html_file),
                            "text": str(text_file),
                        },
                    )
                )
        return definitions

    def sync(self) -> list[EmailTemplate]:
        updated: list[EmailTemplate] = []
        for definition in self.discover():
            latest = EmailTemplate.objects.filter(
                slug=definition.slug,
                locale=definition.locale,
            ).order_by("-version").first()
            if latest and self._matches(latest, definition):
                updated.append(latest)
                continue
            version = 1 if latest is None else latest.version + 1
            template = EmailTemplate.objects.create(
                slug=definition.slug,
                locale=definition.locale,
                version=version,
                subject=definition.subject,
                html_template=definition.html_body,
                text_template=definition.text_body,
                metadata={"sources": definition.source_paths},
            )
            updated.append(template)
        return updated

    @staticmethod
    def _normalise(content: str) -> str:
        return content.strip().replace("\r\n", "\n")

    def _matches(self, template: EmailTemplate, definition: TemplateDefinition) -> bool:
        return (
            self._normalise(template.subject) == self._normalise(definition.subject)
            and self._normalise(template.html_template) == self._normalise(definition.html_body)
            and self._normalise(template.text_template) == self._normalise(definition.text_body)
        )
