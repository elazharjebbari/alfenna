# scripts/accounts_login_flow.py
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse
from apps.common.runscript_harness import binary_harness

@binary_harness
def run(*args):
    print("== accounts_login_flow: start ==")

    u, _ = User.objects.get_or_create(username="flow_user", defaults={"email": "flow@example.com"})
    u.set_password("s3cret123")
    u.is_active = True
    u.save()

    c = Client()
    url_login = reverse("accounts:login")

    # Échecs pour chauffer le throttle
    for _ in range(3):
        resp = c.post(url_login, {"username": "flow_user", "password": "wrong"})  # <- username
        assert resp.status_code in (200, 400, 429), f"Unexpected status on invalid login: {resp.status_code}"

    # Succès
    resp = c.post(url_login, {"username": "flow_user", "password": "s3cret123", "remember_me": True}, follow=True)
    assert resp.status_code in (200, 302), f"Unexpected status on valid login: {resp.status_code}"
    assert c.session.get("_auth_user_id"), "User not authenticated after valid login"

    # Logout POST
    url_logout = reverse("accounts:logout")
    resp = c.get(url_logout)
    assert resp.status_code == 405, "Logout GET should be 405"
    resp = c.post(url_logout, follow=True)
    assert resp.status_code in (200, 302), "Logout POST failed"

    print("== accounts_login_flow: OK ✅ ==")
