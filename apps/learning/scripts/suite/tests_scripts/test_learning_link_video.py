# python manage.py runscript learning_link_video --script-args "--pk=6 --pattern=Bougie_Creme"
# apps/learning/scripts/learning_link_video.py
from __future__ import annotations
import argparse
import shlex
from typing import Optional, List

from django.core.files.storage import default_storage
from django.utils.text import slugify

from apps.content.models import Lecture
from apps.common.runscript_harness import binary_harness


def _print(msg: str) -> None:
    print(msg, flush=True)


def _iter_files(prefix: str) -> List[str]:
    """List all .mp4 under a storage prefix, recursively."""
    results: List[str] = []

    def _walk(p: str) -> None:
        try:
            dirs, files = default_storage.listdir(p)
        except Exception:
            return
        for f in files:
            if f.lower().endswith(".mp4"):
                results.append(f"{p.rstrip('/')}/{f}")
        for d in dirs:
            _walk(f"{p.rstrip('/')}/{d}")

    _walk(prefix.rstrip("/"))
    return sorted(set(results))


def _pick_by_pattern(files: List[str], pattern: str) -> Optional[str]:
    p = pattern.lower()
    for f in files:
        if p in f.lower():
            return f
    return None


def _normalize_candidate(path: str) -> str:
    """
    Accepts:
      - "videos/learning/xxx.mp4" (preferred)
      - "learning/xxx.mp4"        (we’ll try "videos/learning/…")
      - "xxx.mp4"                 (we’ll try "videos/learning/xxx.mp4")
    Returns a storage-relative path that exists, or "".
    """
    rel = (path or "").lstrip("/")
    if not rel:
        return ""
    if default_storage.exists(rel):
        return rel
    if rel.startswith("learning/"):
        alt = f"videos/{rel}"
        if default_storage.exists(alt):
            return alt
    base = f"videos/learning/{rel}"
    if default_storage.exists(base):
        return base
    return ""


@binary_harness
def run(*script_args) -> None:
    """
    Link a video file to a Lecture (sets `video_path`).

    Examples (these will now work):
      python manage.py runscript learning_link_video --script-args "--pk=6 --path=videos/learning/11_-_Pratique_5_Bougie_Creme_KtwWjO.mp4"
      python manage.py runscript learning_link_video --script-args "--pk=6 --pattern=Bougie_Creme"
      python manage.py runscript learning_link_video --script-args "--pk=6 --auto"
      python manage.py runscript learning_link_video --script-args "--pk=6 --path=… --force"
    """

    # 1) Normalize how django-extensions forwards arguments
    # In some versions it sends a SINGLE string containing all args; in others, multiple tokens.
    if len(script_args) == 1 and isinstance(script_args[0], str):
        tokens = shlex.split(script_args[0])
    else:
        # Already a sequence of tokens
        tokens = list(script_args)

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--pk", type=str, required=True)     # parse as string first
    parser.add_argument("--path", type=str, default="")
    parser.add_argument("--pattern", type=str, default="")
    parser.add_argument("--auto", action="store_true")
    parser.add_argument("--force", action="store_true")

    try:
        args = parser.parse_args(tokens)
    except SystemExit:
        _print("== learning_link_video: bad args ==")
        parser.print_help()
        return

    # 2) Convert pk string → int cleanly
    pk_raw = (args.pk or "").strip()
    try:
        pk_val = int(pk_raw)
    except ValueError:
        _print(f"[error] Mauvaise valeur pour --pk: '{pk_raw}'")
        return

    _print("== learning_link_video: start ==")
    _print(f"[args] pk={pk_val} path='{args.path}' pattern='{args.pattern}' auto={args.auto} force={args.force}")

    # 3) Load lecture
    lec = Lecture.objects.filter(pk=pk_val).select_related("section", "course").first()
    if not lec:
        _print(f"[error] Lecture pk={pk_val} introuvable.")
        return

    _print(f"[lecture] pk={lec.pk} course={lec.course_id} '{lec.course.title}' sec={lec.section.order} lec={lec.order}")
    _print(f"[lecture] published? course={lec.course.is_published} lecture={lec.is_published}")
    _print(f"[lecture] current video_path='{lec.video_path or ''}'")

    if getattr(lec, "video_file", None):
        _print("[guard] FileField `video_file` déjà défini. Pas de mise à jour `video_path`.")
        _print("== learning_link_video: end ==")
        return

    if lec.video_path and not args.force:
        _print("[guard] `video_path` déjà défini. Utilise --force pour écraser.")
        _print("== learning_link_video: end ==")
        return

    # 4) Discover available files
    files = _iter_files("videos/learning")
    _print(f"[storage] mp4 trouvés sous 'videos/learning': {len(files)}")
    if files:
        preview = ", ".join(files[:3]) + (" ..." if len(files) > 3 else "")
        _print(f"[storage] exemples: {preview}")
    else:
        _print("[error] Aucun .mp4 trouvé sous media/videos/learning/")
        return

    # 5) Choose file (path > pattern > auto > slug-match > first)
    chosen = ""
    if args.path:
        chosen = _normalize_candidate(args.path)
        if not chosen:
            _print(f"[error] Fichier '{args.path}' introuvable dans le storage.")
            return
        _print(f"[pick] via --path → {chosen}")
    elif args.pattern:
        hit = _pick_by_pattern(files, args.pattern)
        if not hit:
            _print(f"[warn] Aucun fichier ne matche '{args.pattern}'.")
            return
        chosen = hit
        _print(f"[pick] via --pattern → {chosen}")
    elif args.auto:
        chosen = files[0]
        _print(f"[pick] via --auto → {chosen}")
    else:
        title_slug = slugify(lec.title or "")
        hit = _pick_by_pattern(files, title_slug) if title_slug else None
        chosen = hit or files[0]
        _print(f"[pick] fallback → {chosen}")

    # 6) Persist
    lec.video_path = chosen
    lec.save(update_fields=["video_path"])
    _print(f"[ok] Lecture pk={lec.pk} mise à jour: video_path='{lec.video_path}'")
    _print("== learning_link_video: end ✅ ==")
