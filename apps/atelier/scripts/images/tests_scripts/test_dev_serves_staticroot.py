"""Vérifie que le dev server (WhiteNoise) sert les variantes depuis STATIC_ROOT."""
from __future__ import annotations
from html.parser import HTMLParser
from typing import Dict, List

from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage
from django.core.management import call_command
from django.template import Template, Context

from apps.common.runscript_harness import binary_harness

REQUIRED_KEY = "images/shape/shape-8.png"
FORMATS = ("avif", "webp")


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


def _strip_static(url: str) -> str:
    prefix = settings.STATIC_URL
    if url.startswith(prefix):
        return url[len(prefix):]
    return url.lstrip("/")


@binary_harness
def run() -> Dict[str, object]:
    issues: List[str] = []

    if not settings.DEBUG:
        issues.append("DEBUG must be True for dev-serving test")
    if not getattr(settings, "WHITENOISE_AUTOREFRESH", False):
        issues.append("WHITENOISE_AUTOREFRESH must be True")
    if getattr(settings, "WHITENOISE_USE_FINDERS", True):
        issues.append("WHITENOISE_USE_FINDERS must be False")

    call_command("collectstatic", interactive=False, verbosity=0, clear=True)
    staticfiles_storage.__dict__.pop("variants_index", None)

    variants_index = getattr(staticfiles_storage, "variants_index", {}) or {}
    mapping = variants_index.get(REQUIRED_KEY)
    if not mapping:
        issues.append(f"Variants manifest missing key: {REQUIRED_KEY}")
        mapping = {}

    tpl = Template("{% load atelier_images %}{% responsive_picture 'images/shape/shape-8.png' %}")
    html = tpl.render(Context({}))

    parser = _PictureParser()
    parser.feed(html)

    for fmt in FORMATS:
        rel = (mapping or {}).get(fmt)
        if not rel:
            continue
        rel = rel.lstrip("/")
        has_file = staticfiles_storage.exists(rel)
        expected_url = settings.STATIC_URL + rel
        present = any(
            source.get("type") == f"image/{fmt}" and source.get("srcset") == expected_url
            for source in parser.sources
        )
        if has_file and not present:
            issues.append(f"Missing <source> for {fmt} ({rel})")
        if not has_file and present:
            issues.append(f"Unexpected <source> for {fmt} despite missing file")

    img_src = parser.img_attrs.get("src", "")
    if not img_src:
        issues.append("Missing <img> fallback")
    else:
        rel = _strip_static(img_src)
        ext = rel.split(".")[-1].lower() if "." in rel else ""
        if ext not in {"png", "jpg", "jpeg"}:
            issues.append(f"Fallback img extension unexpected: {rel}")
        if rel and not staticfiles_storage.exists(rel):
            issues.append(f"Fallback img path missing on disk: {rel}")

    ok = not issues
    if issues:
        print("[test_dev_serves_staticroot] Issues detected:")
        for item in issues:
            print(f"  - {item}")

    return {
        "ok": ok,
        "issues": issues,
        "sources": parser.sources,
        "img": parser.img_attrs,
    }
