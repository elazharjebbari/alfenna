"""Fetch a single static asset from a prod server instance."""
from __future__ import annotations

import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict

from django.contrib.staticfiles.storage import staticfiles_storage

from apps.common.runscript_harness import binary_harness

TARGET_REL = "images/shape/shape-21.830790d4c146/shape-21.830790d4c146.d63c7713da4e.avif"


def _parse_args(raw: str | None) -> Dict[str, str]:
    args: Dict[str, str] = {}
    if not raw:
        return args
    for part in raw.split():
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        args[key.strip()] = value.strip()
    return args


def _storage_listing() -> Dict[str, object]:
    rel_dir = "/".join(TARGET_REL.split("/")[:-1])
    info: Dict[str, object] = {"rel_dir": rel_dir}
    try:
        dir_path = staticfiles_storage.path(rel_dir)
        info["fs_path"] = dir_path
        if Path(dir_path).exists():
            entries = []
            for child in sorted(Path(dir_path).iterdir()):
                try:
                    stat = child.stat()
                    entries.append({"name": child.name, "size": stat.st_size})
                except FileNotFoundError:
                    continue
            info["entries"] = entries
    except Exception as exc:  # pragma: no cover - diagnostic helper
        info["error"] = str(exc)
    return info


@binary_harness
def run(*, script_args: str = "") -> Dict[str, object]:  # pragma: no cover - integration helper
    args = _parse_args(script_args)
    base = args.get("base", "https://127.0.0.1:8004")
    verify_ssl = args.get("verify_ssl", "1")

    url = base.rstrip("/") + "/static/" + TARGET_REL
    print(f"[e2e_fetch_one_prod] GET {url}")

    context = None
    if verify_ssl == "0":
        context = ssl._create_unverified_context()

    req = urllib.request.Request(url, headers={"User-Agent": "diag-fetch/1.0"})
    result: Dict[str, object] = {"url": url, "args": args}

    try:
        with urllib.request.urlopen(req, context=context, timeout=10) as resp:
            body = resp.read()
            result["status"] = resp.status
            result["headers"] = dict(resp.headers.items())
            result["body_length"] = len(body)
            print(f"[e2e_fetch_one_prod] status={resp.status} len={len(body)}")
    except urllib.error.HTTPError as exc:
        result["status"] = exc.code
        result["error"] = str(exc)
        result["body_length"] = getattr(exc, "length", 0)
        print(f"[e2e_fetch_one_prod] HTTPError {exc.code}: {exc}")
        if exc.code == 404:
            listing = _storage_listing()
            result["storage_listing"] = listing
            print("[e2e_fetch_one_prod] Directory listing:", listing)
    except Exception as exc:
        result["status"] = 0
        result["error"] = str(exc)
        print(f"[e2e_fetch_one_prod] ERROR: {exc}")

    result["ok"] = result.get("status") == 200
    return result
