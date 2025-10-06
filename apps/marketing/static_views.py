from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, HttpResponse, HttpResponseNotFound


ICONS_ROOT = Path(settings.BASE_DIR) / "static" / "icons"


def _file_or_404(path: Path) -> FileResponse | HttpResponseNotFound:
    if path.exists():
        return FileResponse(open(path, "rb"))
    return HttpResponseNotFound()


def favicon_view(_request):
    # Serve /favicon.ico mapped to static/icons/favicon.ico
    path = ICONS_ROOT / "favicon.ico"
    return _file_or_404(path)


def apple_touch_icon_view(_request):
    # Serve /apple-touch-icon.png mapped to static/icons/apple-touch-icon.png
    path = ICONS_ROOT / "apple-touch-icon.png"
    return _file_or_404(path)


def browserconfig_view(_request):
    # Minimal browserconfig.xml for Windows tiles (optional)
    # Uses a square icon if present; safe to serve minimal content.
    tile_color = getattr(settings, "THEME_COLOR", "#ffffff")
    xml = f"""
<?xml version="1.0" encoding="utf-8"?>
<browserconfig>
  <msapplication>
    <tile>
      <square150x150logo src="/apple-touch-icon.png"/>
      <TileColor>{tile_color}</TileColor>
    </tile>
  </msapplication>
</browserconfig>
""".strip()
    return HttpResponse(xml, content_type="application/xml")


def manifest_view(_request):
    # Minimal Web App Manifest referencing the existing icons
    name = getattr(settings, "SITE_NAME", "Lumière Academy")
    short_name = getattr(settings, "SITE_SHORT_NAME", "lumiereacademy")
    theme_color = getattr(settings, "THEME_COLOR", "#ffffff")
    background_color = getattr(settings, "THEME_BG_COLOR", "#ffffff")
    icons = [
        {"src": "/icons/favicon-16x16.png", "sizes": "16x16", "type": "image/png"},
        {"src": "/icons/favicon-32x32.png", "sizes": "32x32", "type": "image/png"},
        {"src": "/apple-touch-icon.png", "sizes": "180x180", "type": "image/png"},
    ]
    data = {
        "name": name,
        "short_name": short_name,
        "icons": icons,
        "theme_color": theme_color,
        "background_color": background_color,
        "display": "standalone",
    }
    return HttpResponse(json.dumps(data), content_type="application/manifest+json")

