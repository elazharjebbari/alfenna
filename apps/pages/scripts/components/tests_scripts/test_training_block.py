import time
from importlib import import_module

from apps.common.runscript_harness import binary_harness

ANSI = {"G": "\033[92m", "R": "\033[91m", "B": "\033[94m", "X": "\033[0m"}
NAME = "course_detail/training — Hydrateur fallbacks"


@binary_harness
def run():
    started = time.time()
    logs, ok = [], True

    module = import_module("apps.atelier.compose.hydrators.course_detail.hydrators")
    params = {
        "rating_value": 4.5,
        "rating_percentage": "",
        "instructors": [{"name": "Demo"}],
        "reviews": [{"author": "Client"}],
    }
    ctx = module.training(None, params)
    placeholder = getattr(module, "HERO_PLACEHOLDER", "")
    avatar_placeholder = getattr(module, "AVATAR_PLACEHOLDER", "")

    has_hero = ctx.get("hero_image_url") == placeholder
    logs.append(f"Hero fallback appliqué: {has_hero}")
    if not has_hero:
        ok = False

    expected_pct = 90
    pct_ok = ctx.get("rating_percentage") == expected_pct
    logs.append(f"Pourcentage rating calculé ({expected_pct}): {pct_ok}")
    if not pct_ok:
        ok = False

    instructors = ctx.get("instructors", [])
    instructor_ok = bool(instructors) and instructors[0].get("avatar_url") == avatar_placeholder
    logs.append(f"Avatar instructeur fallback: {instructor_ok}")
    if not instructor_ok:
        ok = False

    reviews = ctx.get("reviews", [])
    review_ok = bool(reviews) and reviews[0].get("avatar_url") == avatar_placeholder
    logs.append(f"Avatar avis fallback: {review_ok}")
    if not review_ok:
        ok = False

    duration = round(time.time() - started, 2)
    return {"ok": ok, "name": NAME, "duration": duration, "logs": logs}
