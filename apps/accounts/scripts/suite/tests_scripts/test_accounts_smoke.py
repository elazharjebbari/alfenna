# scripts/accounts_smoke.py
import uuid
from django.contrib.auth.models import User
from apps.common.runscript_harness import binary_harness

@binary_harness
def run():
    print("=== Smoke test Accounts ===")

    # Générer un username unique à chaque run
    username = f"testuser_{uuid.uuid4().hex[:6]}"
    email = f"{username}@example.com"

    # On crée ou met à jour l'utilisateur
    user, created = User.objects.update_or_create(
        username=username,
        defaults={"email": email},
    )
    # Définir un mot de passe (set_password gère le hash correctement)
    user.set_password("secret123")
    user.save()

    # Vérifier que le profil est bien auto-créé
    assert hasattr(user, "profile"), "Profil étudiant non créé automatiquement"

    print(f"OK: Profil {'créé' if created else 'mis à jour'} pour {user.username}")
