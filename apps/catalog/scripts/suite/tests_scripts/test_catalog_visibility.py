from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from apps.catalog.models.models import Course
from apps.content.models import Section, Lecture
from apps.common.runscript_harness import binary_harness

@binary_harness
def run(*args):
    print("== catalog_visibility: start ==")

    # Créer un cours brouillon (non publié)
    draft = Course.objects.create(title='Brouillon', slug='cours-brouillon', description='-', is_published=False)
    s = Section.objects.create(course=draft, title='Section', order=1, is_published=True)
    Lecture.objects.create(course=draft, section=s, title='Leçon', order=1, is_published=True)

    c = Client()
    # Draft ne doit pas apparaître
    resp = c.get(reverse('catalog:list'))
    assert b'Brouillon' not in resp.content, "Un cours brouillon apparaît en public"

    resp = c.get(draft.get_absolute_url())
    assert resp.status_code in (404, 302), "Le détail d'un brouillon ne doit pas être public"

    # Staff preview doit le voir
    staff, _ = User.objects.get_or_create(username='staff', defaults={'is_staff': True, 'is_superuser': True})
    staff.set_password('x')
    staff.save()
    assert c.login(username='staff', password='x'), "Login staff échoué"
    resp = c.get(draft.get_absolute_url() + '?preview=1')
    assert resp.status_code == 200 and b'Brouillon' in resp.content, "Preview staff n'affiche pas le brouillon"

    print("== catalog_visibility: OK ✅ ==")