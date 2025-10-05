# apps/learning/scripts/learning_comments.py
from __future__ import annotations
from django.test import Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from apps.content.models import Lecture
from apps.learning.models import LectureComment
from apps.billing.models import Entitlement
from apps.common.runscript_harness import binary_harness

@binary_harness
def run(*args):
    print("== learning_comments: start ==")

    lec = (
        Lecture.objects
        .select_related("section", "course")
        .filter(section__course__is_published=True, is_published=True)
        .first()
    )
    assert lec, "Aucune lecture publiée"
    course = lec.course

    User = get_user_model()
    u, _ = User.objects.get_or_create(username="comment_tester", defaults={"email": "c@ex.com"})
    u.set_password("p@ss1234"); u.save()

    # S'assure qu'on a le droit d'accéder (évite un faux négatif si la leçon n'est pas free)
    Entitlement.objects.get_or_create(user=u, course=course)

    c = Client()
    assert c.login(username="comment_tester", password="p@ss1234")

    url = reverse("learning:comment", args=[lec.id])
    r = c.post(url, {"body": "Merci pour cette leçon."}, follow=False)

    # La vue redirige vers la page de la leçon → 302 attendu
    assert r.status_code == 302, f"POST commentaire doit rediriger (302), obtenu {r.status_code}"
    # On suit la redirection pour s'assurer que la cible existe
    r2 = c.get(r["Location"])
    assert r2.status_code == 200, f"Page de redirection injoignable: {r2.status_code}"

    # Commentaire créé ?
    assert LectureComment.objects.filter(user=u, lecture=lec).exists(), "Commentaire non trouvé en DB"
    print("== learning_comments: OK ✅ ==")
