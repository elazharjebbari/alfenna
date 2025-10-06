"""Test d'intégration: collectstatic + rendu slider avec variantes AVIF/WEBP."""
from __future__ import annotations
from html.parser import HTMLParser
from typing import Dict, List

from django.contrib.staticfiles.storage import staticfiles_storage
from django.core.management import call_command
from django.template.loader import render_to_string

from apps.common.runscript_harness import binary_harness


class _PictureParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.sources: List[Dict[str, str]] = []
        self.img_attrs: Dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: List[tuple[str, str]]) -> None:
        mapping = {k: v for k, v in attrs}
        if tag == "source":
            self.sources.append(mapping)
        elif tag == "img":
            self.img_attrs = mapping


def _build_context() -> Dict[str, object]:
    style = {
        "show_shapes_desktop": True,
        "show_shapes_mobile": True,
        "layout": "default",
        "mobile_price_mode": "strip",
    }
    rating = {"value": None, "count": None}
    price = {
        "before": None,
        "before_str": "",
        "current": "99",
        "current_str": "99",
        "currency": "EUR",
        "cost_per_day_str": "",
        "label_only": "",
        "discount_pct": None,
    }
    context: Dict[str, object] = {
        "style": style,
        "rating": rating,
        "price": price,
        "cta": None,
        "cta_secondary": None,
        "badge_html": None,
        "title_sub": None,
        "title_main": None,
        "description": None,
        "proof_text": None,
        "micro_progress_html": None,
        "safety_note": None,
        "timer_deadline_ts": None,
        "trust_badges": [],
        "video_url": None,
        "ab_variant": "test",
        "slider_image": "images/slider/slider-default.png",
    }
    return context


@binary_harness
def run() -> Dict[str, object]:
    call_command("collectstatic", interactive=False, verbosity=0)
    staticfiles_storage.__dict__.pop("variants_index", None)

    html = render_to_string("components/core/slider/slider.html", _build_context())

    parser = _PictureParser()
    parser.feed(html)

    avif_sources = [s for s in parser.sources if s.get("type") == "image/avif"]
    webp_sources = [s for s in parser.sources if s.get("type") == "image/webp"]
    img_src = parser.img_attrs.get("src", "")
    has_png_or_jpg = img_src.lower().endswith(".png") or img_src.lower().endswith(".jpg")

    ok = bool(avif_sources and webp_sources and has_png_or_jpg)
    if not ok:
        print("[variant_pipeline] Sources:", parser.sources)
        print("[variant_pipeline] Img:", parser.img_attrs)

    return {
        "ok": ok,
        "sources": parser.sources,
        "img": parser.img_attrs,
    }
