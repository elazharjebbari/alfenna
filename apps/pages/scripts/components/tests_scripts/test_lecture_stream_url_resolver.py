from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory
from django.urls import resolve, reverse

from apps.atelier.config.loader import clear_config_cache
from apps.atelier.compose.hydrators.learning.hydrators import lecture_layout, resolve_stream_url
from apps.common.runscript_harness import binary_harness
from apps.content.models import Lecture
from apps.content.scripts import seed_stream_demo


@binary_harness
def run(*args, **kwargs):
    clear_config_cache()
    seed_stream_demo.run()

    path = reverse("pages:lecture", kwargs={"course_slug": "stream-demo"})
    request = RequestFactory().get(path)
    request.user = AnonymousUser()
    request.resolver_match = resolve(path)

    base_ctx = lecture_layout(request, {})
    assert base_ctx.get("stream_url") is None, "Locked lecture should not expose stream url"
    assert base_ctx.get("is_locked") is True, "Context should mark locked state"

    sections = base_ctx.get("section_list", [])
    premium_slug = None
    for section in sections:
        for item in section.get("lectures", []):
            if item.get("is_locked"):
                premium_slug = item.get("slug")
                break
        if premium_slug:
            break
    assert premium_slug, "Seed should provide a locked lecture"

    premium_path = reverse("pages:lecture-detail", kwargs={"course_slug": "stream-demo", "lecture_slug": premium_slug})
    premium_request = RequestFactory().get(premium_path)
    premium_request.user = AnonymousUser()
    premium_request.resolver_match = resolve(premium_path)

    locked_ctx = lecture_layout(premium_request, {})
    assert locked_ctx.get("stream_url") is None, "Locked lecture must return no stream url"

    lecture = Lecture.objects.get(pk=locked_ctx["lecture"].pk)
    direct_url = resolve_stream_url(lecture)
    assert direct_url, "Resolver should return a fallback URL"

    return {"ok": True, "name": "lecture_stream_url_resolver", "duration": 0.0, "logs": []}
