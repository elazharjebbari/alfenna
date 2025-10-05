from __future__ import annotations

from apps.common.runscript_harness import binary_harness
from apps.content.scripts import (
    seed_from_videos,
    seed_health_check,
    stream_headers_check,
    pages_smoke_demo_learn,
)


@binary_harness
def run(*args, **kwargs):
    results = []

    seed_args = kwargs.get("seed_args")
    if seed_args is None:
        dry_run_result = seed_from_videos.run(script_args=["--dry-run"])
        apply_args = ["--apply", "--publish"]
    else:
        dry_run_result = None
        if isinstance(seed_args, (list, tuple)):
            apply_args = list(seed_args)
        else:
            apply_args = str(seed_args).split()
        if "--apply" not in apply_args:
            apply_args.append("--apply")

    if dry_run_result is not None:
        results.append(dry_run_result)

    apply_result = seed_from_videos.run(script_args=apply_args)
    results.append(apply_result)

    results.append(seed_health_check.run())
    results.append(stream_headers_check.run())
    results.append(pages_smoke_demo_learn.run())

    ok = all(res.get("ok") for res in results)
    return {
        "ok": ok,
        "name": "run_all",
        "duration": 0.0,
        "logs": results,
    }
