from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.test import Client
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.common.runscript_harness import binary_harness

User = get_user_model()


@binary_harness
def run(*args):
    print("== accounts_password_reset_flow: start ==")

    email = "flow-reset@example.com"
    user, _ = User.objects.update_or_create(
        email=email,
        defaults={"username": "flow-reset-user"},
    )
    user.set_password("OldPass123!")
    user.save()

    client = Client()

    request_response = client.post(
        reverse("accounts:password_reset"),
        data={"email": email},
        follow=False,
    )
    assert request_response.status_code in (302, 303), f"Unexpected status: {request_response.status_code}"
    done_url = reverse("accounts:password_reset_done")
    assert request_response["Location"].startswith(done_url), "Should redirect to done page"

    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    confirm_url = reverse("accounts:password_reset_confirm", kwargs={"uidb64": uid, "token": token})

    alias_response = client.get(f"/mot-de-passe-oublie/definir/{uid}/{token}/")
    assert alias_response.status_code == 301, "French alias should redirect"
    assert alias_response["Location"].endswith(confirm_url), "Alias should preserve uid/token"

    qs_response = client.get("/accounts/reset/confirm/", {"uid": uid, "token": token, "next": "/cours/"})
    assert qs_response.status_code == 302, "Fallback should redirect"
    assert qs_response["Location"] == f"{confirm_url}?next=%2Fcours%2F", "Fallback must keep next"

    confirm_get = client.get(confirm_url)
    if confirm_get.status_code in (301, 302, 303):
        redirected_url = confirm_get["Location"]
        assert redirected_url.endswith("/set-password/"), "Redirect should target set-password step"
        confirm_get = client.get(redirected_url)
    assert confirm_get.status_code == 200, "Confirm page not accessible"
    post_url = confirm_get.wsgi_request.path

    new_password = "NewPass456!"
    confirm_post = client.post(
        post_url,
        data={
            "new_password1": new_password,
            "new_password2": new_password,
        },
        follow=False,
    )
    complete_url = reverse("accounts:password_reset_complete")
    assert confirm_post.status_code in (302, 303), f"Unexpected confirm POST status: {confirm_post.status_code}"
    assert confirm_post["Location"].startswith(complete_url), "Should redirect to complete page"

    complete_response = client.get(complete_url)
    assert complete_response.status_code == 200, "Complete page not reachable"

    login_response = client.post(
        reverse("accounts:login"),
        data={"username": user.username, "password": new_password},
        follow=False,
    )
    assert login_response.status_code in (302, 303), "Login with new password failed"

    print("== accounts_password_reset_flow: OK ✅ ==")
