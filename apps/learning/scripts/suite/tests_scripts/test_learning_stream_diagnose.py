# python manage.py runscript learning_stream_diagnose --script-args="--pk=6"
# apps/learning/scripts/learning_stream_diagnose.py
from __future__ import annotations
import os
import traceback
from dataclasses import dataclass
from typing import Optional, Tuple

from django.conf import settings
from django.core.files.storage import default_storage
from django.test import Client
from django.urls import reverse, NoReverseMatch

from apps.content.models import Lecture
from apps.catalog.models.models import Course

# On réutilise la même logique que la vue pour comprendre où ça coince.
from apps.learning.views import _storage_path_and_size, _parse_range, _etag_for
from apps.common.runscript_harness import binary_harness


@dataclass
class Args:
    pk: Optional[int] = None
    login_superuser: bool = True
    range_header: str = "bytes=0-1023"


def _parse_args(argv) -> Args:
    a = Args()
    for arg in argv:
        if arg.startswith("--pk="):
            try:
                a.pk = int(arg.split("=", 1)[1])
            except Exception:
                pass
        elif arg == "--no-login":
            a.login_superuser = False
        elif arg.startswith("--range="):
            a.range_header = arg.split("=", 1)[1]
    return a


def _pick_lecture(pk: Optional[int]) -> Lecture:
    if pk:
        lec = Lecture.objects.select_related("section", "course").get(pk=pk)
        print(f"[pick] Lecture par pk: {lec.pk} — {lec.title}")
        return lec
    lec = (
        Lecture.objects.select_related("section", "course")
        .filter(is_published=True, course__is_published=True)
        .order_by("course_id", "section__order", "order")
        .first()
    )
    assert lec, "Aucune lecture publiée trouvée. Seed le catalogue."
    print(f"[pick] Lecture auto: pk={lec.pk} — {lec.title}")
    return lec


def _debug_storage_candidates(lecture: Lecture) -> Tuple[Optional[str], Optional[int], Optional[int]]:
    """
    Affiche toutes les pistes testées par la vue pour retrouver le fichier,
    et retourne la première candidate existante si trouvée.
    """
    print("\n[storage] === Diagnostic des chemins ===")
    print(f"[storage] MEDIA_ROOT: {settings.MEDIA_ROOT}")
    print(f"[storage] Storage: {default_storage.__class__.__name__}")

    # 1) FileField
    if hasattr(lecture, "video_file") and getattr(lecture, "video_file"):
        name = lecture.video_file.name
        print(f"[storage] video_file.name: {name} exists? {default_storage.exists(name)}")
        if default_storage.exists(name):
            try:
                abs_path = default_storage.path(name)
                st = os.stat(abs_path)
                print(f"[storage] -> FOUND via FileField. size={st.st_size} mtime={int(st.st_mtime)}")
                return name, st.st_size, int(st.st_mtime)
            except Exception as e:
                size = default_storage.size(name)
                print(f"[storage] -> FileField exists mais pas de .path(). fallback size={size}")
                return name, size, 0
        else:
            print("[storage] video_file présent mais introuvable dans le storage (exists=False).")

    # 2) video_path (string)
    raw = (getattr(lecture, "video_path", "") or "").lstrip("/")
    print(f"[storage] video_path raw: '{raw}'")
    candidates = []
    if raw:
        candidates.append(raw)  # tel quel
        if not raw.startswith("videos/"):
            candidates.append(f"videos/{raw}")  # sous vidéos/
        base = os.path.basename(raw)
        candidates.append(base)                # basename
        candidates.append(f"videos/{base}")    # vidéos/basename

    # Pour être très verbeux, on liste aussi le dossier videos/learning si dispo
    try:
        _, files = default_storage.listdir("videos/learning")
        print(f"[storage] listdir('videos/learning') -> {len(files)} fichiers (extrait: {files[:3]})")
    except Exception as e:
        print(f"[storage] listdir('videos/learning') impossible: {e}")

    for c in candidates:
        ok = default_storage.exists(c)
        print(f"[storage] test exists('{c}') -> {ok}")
        if ok:
            try:
                abs_path = default_storage.path(c)
                st = os.stat(abs_path)
                print(f"[storage] -> FOUND '{c}' size={st.st_size} mtime={int(st.st_mtime)}")
                return c, st.st_size, int(st.st_mtime)
            except Exception:
                size = default_storage.size(c)
                print(f"[storage] -> FOUND '{c}' (pas de .path()), fallback size={size}")
                return c, size, 0

    print("[storage] AUCUNE CANDIDATE TROUVÉE. La vue lèvera Http404.")
    return None, None, None


@binary_harness
def run(*script_args):
    print("== learning_stream_diagnose: start ==")
    args = _parse_args(script_args)
    print(f"[args] pk={args.pk} login_superuser={args.login_superuser} range='{args.range_header}'")

    # 1) cible
    lecture = _pick_lecture(args.pk)
    course = lecture.course
    print(f"[lecture] pk={lecture.pk} course={course.id} '{course.title}' sec={lecture.section.order} lec={lecture.order}")
    print(f"[lecture] published? course={course.is_published} lecture={lecture.is_published}")
    print(f"[lecture] video_file? {bool(getattr(lecture, 'video_file', None))} video_path='{getattr(lecture, 'video_path', '')}'")

    # 2) vérifie les candidats storage
    cpath, csize, cmtime = _debug_storage_candidates(lecture)

    # 3) Essaye d'appeler directement la fonction _storage_path_and_size
    print("\n[probe] _storage_path_and_size() …")
    try:
        spath, ssize, smtime = _storage_path_and_size(lecture)
        print(f"[probe] OK -> path='{spath}' size={ssize} mtime={smtime} etag={_etag_for(spath, ssize, smtime)}")
    except Exception as e:
        print("[probe] _storage_path_and_size a levé une exception:")
        traceback.print_exc()

    # 4) URL du stream
    print("\n[url] Résolution de l’URL de stream …")
    try:
        url = reverse("learning:stream", args=[lecture.pk])
        print(f"[url] learning:stream => {url}")
    except NoReverseMatch:
        # fallback: hard-coded
        url = f"/learning/stream/{lecture.pk}/"
        print(f"[url] NoReverseMatch. On teste URL fallback: {url}")

    # 5) client HTTP (login superuser pour bypass tout gating)
    client = Client()
    if args.login_superuser:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        su, _ = User.objects.get_or_create(username="diag_admin", defaults={"email": "diag@example.com", "is_staff": True, "is_superuser": True})
        client.force_login(su)
        print("[auth] connecté en tant que superuser diag_admin")

    # 6) HEAD
    print("\n[HEAD] Requête HEAD …")
    r = client.head(url)
    print(f"[HEAD] status={r.status_code} headers=")
    for k, v in r.headers.items():
        if k.lower() in ("etag", "last-modified", "accept-ranges", "content-length", "content-range", "content-type"):
            print(f"    {k}: {v}")

    if r.status_code == 404:
        print("\n[HEAD] 404 => le storage n’a pas trouvé de ressource. Cf. section [storage] ci-dessus.")
        print("         Corrige lecture.video_path (ex: 'learning/<fichier>.mp4' ou 'videos/learning/<fichier>.mp4').")
        print("         Ou bien affecte temporairement un dummy et relance.")
        print("== learning_stream_diagnose: end (404) ==")
        return

    # 7) GET Range
    print("\n[GET] Requête GET avec Range …")
    r = client.get(url, HTTP_RANGE=args.range_header)
    print(f"[GET] status={r.status_code} headers=")
    for k, v in r.headers.items():
        if k.lower() in ("etag", "last-modified", "accept-ranges", "content-length", "content-range", "content-type"):
            print(f"    {k}: {v}")

    # 8) Sanity sur 206
    if r.status_code not in (200, 206):
        print(f"[GET] ⚠️ status inattendu ({r.status_code}).")
    else:
        print(f"[GET] ✅ OK ({r.status_code}). Flux partiel attendu si Range valide.")

    print("\n== learning_stream_diagnose: end ==")
