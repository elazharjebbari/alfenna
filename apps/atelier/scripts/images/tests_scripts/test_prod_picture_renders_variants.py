"""Validate prod picture rendering produces accessible variant URLs."""
from __future__ import annotations

from html.parser import HTMLParser
from typing import Dict, List

from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage
from django.core.management import call_command
from django.template import engines
from django.test import Client

from apps.common.runscript_harness import binary_harness

TARGET_IMAGES: List[str] = [
    "images/shape/shape-7.png",
    "images/slider/slider-default.png",
]


class _PictureParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.sources: List[Dict[str, str]] = []
        self.img_attrs: Dict[str, str] | None = None

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[override]
        attrs_dict = {k.lower(): (v or "") for k, v in attrs}
        if tag.lower() == "source":
            self.sources.append(attrs_dict)
        elif tag.lower() == "img":
            self.img_attrs = attrs_dict


def _render_picture(rel: str) -> str:
    engine = engines["django"]
    template = engine.from_string("{% load atelier_images %}{% responsive_picture '" + rel + "' alt='diag' %}")
    return template.render({})


def _storage_exists(url: str) -> bool:
    rel = url
    if url.startswith(settings.STATIC_URL):
        rel = url[len(settings.STATIC_URL):]
    rel = rel.lstrip("/")
    return staticfiles_storage.exists(rel)


@binary_harness
def run() -> Dict[str, object]:  # pragma: no cover - integration script
    print("[prod_picture_variants] collectstatic --noinput --clear")
    call_command("collectstatic", "--noinput", "--clear")

    client = Client()
    results: Dict[str, object] = {}

    for image_rel in TARGET_IMAGES:
        html = _render_picture(image_rel)
        parser = _PictureParser()
        parser.feed(html)
        sources = {src.get("type"): src for src in parser.sources}

        if "image/avif" not in sources or "image/webp" not in sources:
            raise AssertionError(f"Expected AVIF and WEBP sources for {image_rel}, got {list(sources.keys())}")

        img_attrs = parser.img_attrs or {}
        if "src" not in img_attrs:
            raise AssertionError(f"Fallback <img> missing for {image_rel}")

        urls_to_check = [sources["image/avif"].get("srcset", ""), sources["image/webp"].get("srcset", ""), img_attrs.get("src", "")]
        urls_to_check = [url for url in urls_to_check if url]

        for url in urls_to_check:
            if not url.startswith(settings.STATIC_URL):
                raise AssertionError(f"Unexpected url {url} for {image_rel}")
            if not _storage_exists(url):
                raise AssertionError(f"Storage missing file for {url}")
            resp = client.get(url)
            if resp.status_code != 200:
                raise AssertionError(f"HTTP {resp.status_code} for {url}")

        results[image_rel] = {
            "html": html,
            "urls": urls_to_check,
        }
        print(f"[prod_picture_variants] {image_rel}: OK ({len(urls_to_check)} assets)")

    return {"ok": True, "results": results}
