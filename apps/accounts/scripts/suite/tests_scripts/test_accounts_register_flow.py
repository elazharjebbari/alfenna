from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from apps.common.runscript_harness import binary_harness
from apps.messaging.models import OutboxEmail

User = get_user_model()


@binary_harness
def run(*args):
    print("== accounts_register_flow: start ==")

    email = "flow-register@example.com"
    User.objects.filter(email=email).delete()

    client = Client()
    response = client.post(
        reverse("accounts:register"),
        data={
            "full_name": "Flow Register",
            "email": email,
            "password1": "RegisterPass123!",
            "password2": "RegisterPass123!",
            "marketing_opt_in": "on",
        },
        follow=False,
    )
    assert response.status_code in (302, 303), f"Unexpected status: {response.status_code}"
    check_email_url = reverse("pages:check_email")
    assert response["Location"].startswith(check_email_url), "Expected redirect to check_email page"

    user = User.objects.get(email=email)
    assert user.profile is not None, "Profile not created"

    outbox = None
    for candidate in OutboxEmail.objects.filter(purpose="email_verification"):
        recipients = candidate.to or []
        if email in recipients:
            outbox = candidate
            break
    assert outbox is not None, "Verification email not enqueued"

    follow = client.get(check_email_url)
    assert follow.status_code == 200, "Check email page not reachable"

    print("== accounts_register_flow: OK ✅ ==")
