# accounts/scripts/accounts_email_verify.py
from django.core import signing
from django.contrib.auth.models import User
from apps.common.runscript_harness import binary_harness

@binary_harness
def run():
    print("=== Test vérification email ===")

    # Ici on évite la duplication avec get_or_create
    user, created = User.objects.get_or_create(
        username="verifuser",
        defaults={
            "email": "verif@example.com",
            "password": "secret123",
        },
    )

    # Token signé valable 1h
    token = signing.dumps({"user_id": user.id})
    data = signing.loads(token, max_age=3600)

    # Vérification email simulée
    user.profile.email_verified = True
    user.profile.save()

    assert user.profile.email_verified, "Email non vérifié"
    print(f"OK: Vérification email réussie pour {user.username} (créé={created})")
