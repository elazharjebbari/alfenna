from django.conf import settings
from django.test import Client
from django.urls import reverse

from apps.atelier.config.loader import clear_config_cache
from apps.common.runscript_harness import binary_harness
from apps.content.scripts import seed_stream_demo


@binary_harness
def run(*args, **kwargs):
    clear_config_cache()
    seed_stream_demo.run()

    client = Client()
    url = reverse("pages:lecture", kwargs={"course_slug": "stream-demo"})
    response = client.get(url)

    assert response.status_code == 302, f"Anonymous user should be redirected, got {response.status_code}"

    login_url = settings.LOGIN_URL or "/accounts/login/"
    assert login_url in response.url, "Redirect should point to login"

    return {"ok": True, "name": "lecture_guard_login_required", "duration": 0.0, "logs": []}
