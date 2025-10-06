"""Check availability of responsive_picture assets locally and on production."""
from __future__ import annotations

import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Dict, List, Tuple

from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage
from django.template import engines
from django.test import Client

from apps.common.runscript_harness import binary_harness

TARGET_SOURCES: List[str] = [
    "images/logo",
    "images/shape/shape-8",
    "images/components/learning/content/default",
]
DEFAULT_PROD_ORIGIN = "https://www.lumiereacademy.com"


@dataclass
class _UrlStatus:
    url: str
    rel: str
    local_exists: bool | None
    local_path: str | None
    local_status: int | None
    prod_status: int | None
    prod_error: str | None


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


def _render(rel: str) -> Tuple[str, List[str]]:
    engine = engines["django"]
    template = engine.from_string(
        "{% load atelier_images %}{% responsive_picture '" + rel + "' alt='diag' %}"
    )
    html = template.render({})
    parser = _PictureParser()
    parser.feed(html)

    urls: List[str] = []
    for source in parser.sources:
        url = source.get("srcset")
        if url:
            urls.append(url)
    if parser.img_attrs and parser.img_attrs.get("src"):
        urls.append(parser.img_attrs["src"])
    return html, urls


def _normalize(url: str) -> str:
    base = settings.STATIC_URL or "/static/"
    if url.startswith(base):
        return url[len(base):].lstrip("/")
    return url.lstrip("/")


def _head(url: str, timeout: float = 5.0) -> Tuple[int | None, str | None]:
    request = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:  # type: ignore[arg-type]
            return resp.status, None
    except urllib.error.HTTPError as exc:
        return exc.code, None
    except Exception as exc:  # pragma: no cover - diagnostic path
        return None, str(exc)


@binary_harness
def run() -> Dict[str, object]:  # pragma: no cover - diagnostic script
    prod_origin = os.getenv("PROD_ORIGIN", DEFAULT_PROD_ORIGIN).rstrip("/")
    base_static = settings.STATIC_URL.rstrip("/") or "/static"

    summary: Dict[str, object] = {
        "prod_origin": prod_origin,
        "static_url": base_static,
        "targets": {},
    }
    ok = True
    client = Client()

    for rel in TARGET_SOURCES:
        html, urls = _render(rel)
        statuses: List[_UrlStatus] = []

        print(f"[static_assets_probe] {rel}")
        for url in urls:
            rel_path = _normalize(url)
            local_exists = None
            local_path = None
            try:
                local_exists = staticfiles_storage.exists(rel_path)
            except Exception as exc:
                print(f"  ! exists() error for {rel_path}: {exc}")

            try:
                local_path = staticfiles_storage.path(rel_path)
            except Exception:
                local_path = None

            local_status = None
            try:
                response = client.get(url)
                local_status = response.status_code
                if local_status != 200:
                    ok = False
            except Exception as exc:
                print(f"  ! local GET error for {url}: {exc}")
                local_status = None

            prod_url = f"{prod_origin}{url}"
            status, error = _head(prod_url)
            if status is None or status >= 400:
                ok = False

            statuses.append(
                _UrlStatus(
                    url=url,
                    rel=rel_path,
                    local_exists=local_exists,
                    local_path=local_path,
                    local_status=local_status,
                    prod_status=status,
                    prod_error=error,
                )
            )

            print(
                f"  - {url} -> exists={local_exists} path={local_path or '-'} local_status={local_status} prod_status={status}"
                + (f" error={error}" if error else "")
            )

        summary["targets"][rel] = {
            "html": html,
            "assets": [status.__dict__ for status in statuses],
        }

    summary["ok"] = ok
    return summary
