from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory
from django.urls import resolve, reverse

from apps.atelier.config.loader import clear_config_cache
from apps.atelier.compose.hydrators.learning.hydrators import lecture_layout
from apps.common.runscript_harness import binary_harness
from apps.content.scripts import seed_stream_demo


@binary_harness
def run(*args, **kwargs):
    clear_config_cache()
    seed_stream_demo.run()

    path = reverse("pages:lecture", kwargs={"course_slug": "stream-demo"})
    request = RequestFactory().get(path)
    request.user = AnonymousUser()
    request.resolver_match = resolve(path)

    ctx = lecture_layout(request, {"assets": {"images": {"poster": ""}}})
    poster_url = ctx.get("poster_url")

    assert poster_url and poster_url.startswith("https://placehold.co/960x540"), "Fallback poster should be used"

    return {"ok": True, "name": "lecture_poster_fallback", "duration": 0.0, "logs": []}
