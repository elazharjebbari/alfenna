"""Quick SEO smoke checks for marketing routes."""
from __future__ import annotations

from html.parser import HTMLParser

from django.test import Client
from django.urls import reverse


class _Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.meta = {}
        self.links = []
        self._in_title = False
        self.title = ""

    def handle_starttag(self, tag, attrs):  # type: ignore[override]
        attrs_dict = {k.lower(): (v or "") for k, v in attrs}
        if tag.lower() == "meta":
            key = attrs_dict.get("name") or attrs_dict.get("property")
            if key:
                self.meta[key.lower()] = attrs_dict.get("content", "")
        elif tag.lower() == "link":
            if attrs_dict.get("rel", "").lower() == "canonical":
                self.links.append(attrs_dict.get("href", ""))
        elif tag.lower() == "title":
            self._in_title = True

    def handle_data(self, data):  # type: ignore[override]
        if self._in_title:
            text = data.strip()
            if text:
                self.title += text

    def handle_endtag(self, tag):  # type: ignore[override]
        if tag.lower() == "title":
            self._in_title = False


_ROUTES = [
    ("home", "/", "index,follow"),
    ("contact", reverse("pages:contact"), "index,follow"),
    ("learn", reverse("pages:learn"), "index,follow"),
    ("demo", reverse("pages:demo-default"), "index,follow"),
    ("faq", reverse("pages:faq"), "index,follow"),
    ("packs", reverse("pages:packs"), "index,follow"),
    ("login", reverse("pages:login"), "noindex,nofollow"),
]


def _check(client: Client, path: str, expected_robots: str) -> tuple[bool, str]:
    response = client.get(path, follow=True)
    status = response.status_code
    if status != 200:
        return False, f"status={status}"
    parser = _Parser()
    parser.feed(response.content.decode())
    robots = parser.meta.get("robots", "")
    canonical = parser.links[0] if parser.links else ""
    issues = []
    if not parser.title:
        issues.append("title")
    if not parser.meta.get("description"):
        issues.append("description")
    if robots != expected_robots:
        issues.append(f"robots:{robots}")
    if not canonical:
        issues.append("canonical")
    return (not issues, ",".join(issues) or "ok")


def run_all():
    client = Client()
    for label, path, robots in _ROUTES:
        ok, details = _check(client, path, robots)
        status = "OK" if ok else "KO"
        print(f"[{status}] {label}: {details}")


def run():
    run_all()
