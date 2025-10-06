"""Render responsive_picture for a small set of assets for diagnostics."""
from __future__ import annotations

from html.parser import HTMLParser
from typing import Dict, List

from django.conf import settings
from django.template import engines

from apps.common.runscript_harness import binary_harness

TARGET_SOURCES: List[str] = [
    "images/logo",
    "images/shape/shape-8",
    "images/components/learning/content/default",
]


class _PictureParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.sources: List[Dict[str, str]] = []
        self.img_attrs: Dict[str, str] | None = None

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[override]
        attrs_dict = {k.lower(): (v or "") for k, v in attrs}
        lower = tag.lower()
        if lower == "source":
            self.sources.append(attrs_dict)
        elif lower == "img":
            self.img_attrs = attrs_dict


def _render_picture(src: str) -> str:
    engine = engines["django"]
    template = engine.from_string(
        "{% load atelier_images %}{% responsive_picture '" + src + "' alt='probe' %}"
    )
    return template.render({})


@binary_harness
def run() -> Dict[str, object]:  # pragma: no cover - diagnostic script
    base_url = settings.STATIC_URL.rstrip("/") or "/static"
    results: Dict[str, object] = {}

    for rel in TARGET_SOURCES:
        html = _render_picture(rel)
        parser = _PictureParser()
        parser.feed(html)

        urls: List[str] = []
        for source in parser.sources:
            url = source.get("srcset")
            if url:
                urls.append(url)
        if parser.img_attrs and parser.img_attrs.get("src"):
            urls.append(parser.img_attrs["src"])

        print(f"[render_picture_probe] {rel} -> {len(urls)} urls")
        for url in urls:
            print(f"  - {url}")

        results[rel] = {
            "html": html,
            "urls": urls,
        }

        if any(not url.startswith(base_url) for url in urls):
            print(f"  WARNING: some urls do not start with STATIC_URL ({base_url})")

    return {"ok": True, "results": results, "static_url": base_url}
