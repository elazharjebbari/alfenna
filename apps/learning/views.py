import logging
import mimetypes
import os
import re
import hashlib
from datetime import datetime, timezone

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.files.storage import default_storage
from django.core.cache import cache
from django.http import (
    Http404,
    HttpResponse,
    HttpResponseNotAllowed,
    HttpResponseNotModified,
    StreamingHttpResponse,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.http import http_date, parse_http_date_safe
from django.views import View

from apps.content.models import Lecture, LectureVideoVariant, LanguageCode
from .models import Progress, LectureComment
from ..content.mixins import GatedLectureAccessMixin, LectureAccessRequiredMixin

log = logging.getLogger("stream")

CHUNK_BYTES = getattr(settings, "VIDEO_STREAM_CHUNK_BYTES", 512 * 1024)  # 512KB par défaut
COMMENT_THROTTLE_SECONDS = 15
PROGRESS_THROTTLE_SECONDS = 3

_range_re = re.compile(r"bytes=(\d*)-(\d*)", re.I)


def _stat_storage_path(path: str) -> tuple[str, int, int]:
    normalized = (path or "").strip().lstrip("/")
    if not normalized:
        raise Http404("Chemin vidéo vide.")

    if not default_storage.exists(normalized):
        raise Http404("La ressource vidéo est introuvable (variant/path).")

    try:
        abs_path = default_storage.path(normalized)
        stat = os.stat(abs_path)
        return normalized, stat.st_size, int(stat.st_mtime)
    except Exception:
        size = default_storage.size(normalized)
        return normalized, size, 0


def _storage_path_and_size(lecture: Lecture):
    if hasattr(lecture, "video_file") and getattr(lecture, "video_file"):
        return _stat_storage_path(lecture.video_file.name)

    if hasattr(lecture, "video_path") and lecture.video_path:
        raw = lecture.video_path.strip()
        if os.path.isabs(raw):
            media_root = os.path.abspath(settings.MEDIA_ROOT)
            abs_raw = os.path.abspath(raw)
            if not abs_raw.startswith(media_root + os.sep):
                raise Http404("Chemin vidéo hors MEDIA_ROOT")
            candidate = os.path.relpath(abs_raw, media_root)
        else:
            candidate = raw.lstrip("/")

        if not default_storage.exists(candidate):
            alt = os.path.join("videos", candidate)
            if default_storage.exists(alt):
                candidate = alt
            else:
                basename = os.path.basename(candidate)
                alt2 = os.path.join("videos", basename)
                if default_storage.exists(alt2):
                    candidate = alt2
                else:
                    raise Http404("La ressource vidéo est introuvable (path).")

        return _stat_storage_path(candidate)

    raise Http404("Aucun champ vidéo exploitable sur Lecture.")


def _normalize_lang_code(raw: str | None) -> str | None:
    if not raw:
        return None
    code = raw.strip()
    if not code:
        return None
    if code in LanguageCode.values:
        return code
    lowered = code.lower().replace("_", "-")
    if lowered in {"fr", "fr-fr"}:
        return LanguageCode.FR_FR
    if lowered in {"ar", "ar-ma"}:
        return LanguageCode.AR_MA
    return None


def _pick_lang(request) -> str | None:
    query = _normalize_lang_code(request.GET.get("lang"))
    if query:
        return query

    header = request.META.get("HTTP_ACCEPT_LANGUAGE", "")
    for chunk in header.split(","):
        token = chunk.strip()
        if not token:
            continue
        lang_part = token.split(";", 1)[0]
        choice = _normalize_lang_code(lang_part)
        if choice:
            return choice
    return None


def _variant_path_and_size(lecture: Lecture, preferred: str | None, user_id=None):
    variant: LectureVideoVariant | None = None
    if preferred:
        variant = lecture.video_variants.filter(lang=preferred).first()

    if not variant:
        variant = lecture.video_variants.filter(is_default=True).first()

    if not variant:
        variant = lecture.video_variants.order_by('lang').first()

    if variant:
        try:
            path, size, mtime = _stat_storage_path(variant.path_in_storage())
            return path, size, mtime, variant.lang
        except Http404:
            log.warning(
                "stream_variant_missing user=%s lecture=%s course=%s lang=%s path=%s",
                user_id,
                lecture.pk,
                lecture.course_id,
                variant.lang,
                variant.path_in_storage(),
            )

    path, size, mtime = _storage_path_and_size(lecture)
    fallback_lang = LanguageCode.FR_FR
    return path, size, mtime, fallback_lang


def _etag_for(path: str, size: int, mtime: int) -> str:
    # ETag faible: hash sur path+size+mtime, stable et peu coûteux
    raw = f"{path}:{size}:{mtime}".encode("utf-8")
    return f'W/"{hashlib.md5(raw).hexdigest()}"'


def _parse_range(range_header: str, size: int):
    """
    Retourne (start, end) inclusifs pour le range demandé.
    Supporte "bytes=start-end", "-end" et "start-".
    """
    m = _range_re.match(range_header or "")
    if not m:
        return None

    start_s, end_s = m.groups()
    if start_s == "" and end_s == "":
        return None

    if start_s and end_s:
        start = int(start_s)
        end = int(end_s)
        if start > end or start >= size:
            return "invalid"
        end = min(end, size - 1)
        return (start, end)

    if start_s and not end_s:
        start = int(start_s)
        if start >= size:
            return "invalid"
        return (start, size - 1)

    # Suffix range: "-N" = derniers N octets
    if not start_s and end_s:
        length = int(end_s)
        if length == 0:
            return "invalid"
        if length >= size:
            return (0, size - 1)
        return (size - length, size - 1)

    return None


class VideoStreamView(LectureAccessRequiredMixin, View):
    """
    Streaming binaire avec support Range 206, HEAD, ETag/Last-Modified.
    Utilise le mixin de gating existant pour ne rien casser.
    """
    def head(self, request, pk: int):
        return self._serve(request, pk, head_only=True)

    def get(self, request, pk: int):
        return self._serve(request, pk, head_only=False)

    def _serve(self, request, pk: int, head_only: bool):
        # le mixin a normalement posé self.lecture; sinon fallback propre:
        lecture = getattr(self, "lecture", None)
        if lecture is None or getattr(lecture, "pk", None) != pk:
            lecture = get_object_or_404(Lecture, pk=pk)
        # Gating déjà validé par LectureAccessRequiredMixin

        requested_lang = _pick_lang(request)
        path, size, mtime, active_lang = _variant_path_and_size(
            lecture,
            requested_lang,
            getattr(request.user, "id", None),
        )
        if size <= 0:
            raise Http404("La ressource vidéo est vide.")
        etag = _etag_for(path, size, mtime)
        last_modified_http = http_date(mtime) if mtime else None

        # Conditional requests
        if_none_match = request.META.get("HTTP_IF_NONE_MATCH")
        if_modified_since = request.META.get("HTTP_IF_MODIFIED_SINCE")
        if if_none_match == etag or (
            last_modified_http and if_modified_since and parse_http_date_safe(if_modified_since) == mtime
        ):
            return HttpResponseNotModified()

        content_type, _ = mimetypes.guess_type(path)
        if not content_type:
            content_type = "video/mp4"

        # Range parsing
        range_header = request.META.get("HTTP_RANGE")
        start, end = 0, size - 1
        status_code = 206
        content_length = size

        if range_header:
            rng = _parse_range(range_header, size)
            if rng == "invalid":
                resp = HttpResponse(status=416)
                resp["Content-Range"] = f"bytes */{size}"
                log.warning(
                    "stream_invalid_range user=%s lecture=%s course=%s range=%s size=%s",
                    getattr(request.user, "id", None),
                    lecture.pk,
                    lecture.course_id,
                    range_header,
                    size,
                )
                return resp
            if rng:
                start, end = rng
                content_length = end - start + 1
        else:
            # Pas de Range explicite, on force bytes=0- pour compat players.
            range_header = f"bytes={start}-"

        # Ouvre le fichier en storage
        f = default_storage.open(path, "rb")
        try:
            f.seek(start)
        except Exception:
            # storage non seekable: fallback lecture intégrale avec skip manuel
            for _ in range(start // CHUNK_BYTES):
                f.read(CHUNK_BYTES)

        # Réponse
        if head_only:
            resp = HttpResponse(status=status_code, content_type=content_type)
            f.close()
        else:
            def chunk_gen(file_obj, remaining):
                bytes_left = remaining
                try:
                    while bytes_left > 0:
                        chunk = file_obj.read(min(CHUNK_BYTES, bytes_left))
                        if not chunk:
                            break
                        bytes_left -= len(chunk)
                        yield chunk
                finally:
                    file_obj.close()

            resp = StreamingHttpResponse(
                chunk_gen(f, content_length),
                status=status_code,
                content_type=content_type,
            )

        # Headers obligatoires
        resp["Accept-Ranges"] = "bytes"
        resp["Content-Length"] = str(content_length)
        if status_code == 206:
            resp["Content-Range"] = f"bytes {start}-{end}/{size}"
        if last_modified_http:
            resp["Last-Modified"] = last_modified_http
        resp["ETag"] = etag

        # Sécurité / Cache
        # Premium → no-store; Free (si tu veux) pourrait avoir un max-age court
        resp["Cache-Control"] = "private, no-store"
        resp["X-Content-Type-Options"] = "nosniff"
        resp["X-Frame-Options"] = "DENY"

        log.info(
            "stream_response user=%s lecture=%s course=%s lang=%s range=%s-%s/%s status=%s reason=%s method=%s",
            getattr(request.user, "id", None),
            lecture.pk,
            lecture.course_id,
            active_lang,
            start,
            end,
            size,
            status_code,
            getattr(self, "access_decision_reason", None) or "allowed",
            request.method,
        )

        resp["Content-Language"] = active_lang.replace("_", "-")
        existing_vary = resp.get("Vary")
        if existing_vary:
            tokens = [token.strip() for token in existing_vary.split(",") if token.strip()]
            if "Accept-Language" not in tokens:
                tokens.append("Accept-Language")
            resp["Vary"] = ", ".join(dict.fromkeys(tokens))
        else:
            resp["Vary"] = "Accept-Language"
        return resp


class ProgressUpdateView(LoginRequiredMixin, LectureAccessRequiredMixin, View):
    """
    Met à jour la progression utilisateur pour une lecture.
    POST form-data ou JSON: position_ms (int), completed (bool).
    Throttle léger pour éviter le spam.
    """

    def post(self, request, pk: int):
        lecture = get_object_or_404(Lecture, pk=pk)
        # Throttle
        key = f"learning:progress_throttle:{request.user.id}:{pk}"
        if cache.get(key):
            return JsonResponse({"ok": True, "throttled": True})
        cache.set(key, 1, PROGRESS_THROTTLE_SECONDS)

        position_ms = request.POST.get("position_ms") or (request.JSON.get("position_ms") if hasattr(request, "JSON") else None)
        completed = request.POST.get("completed") or (request.JSON.get("completed") if hasattr(request, "JSON") else None)

        try:
            position_ms = int(position_ms) if position_ms is not None else None
        except Exception:
            position_ms = None
        completed_flag = str(completed).lower() in ("1", "true", "yes", "on")

        obj, _ = Progress.objects.get_or_create(user=request.user, lecture=lecture)
        if position_ms is not None:
            obj.last_position_ms = max(0, position_ms)
        if completed_flag:
            obj.is_completed = True
            obj.completed_at = datetime.now(timezone.utc)
        obj.save(update_fields=["last_position_ms", "is_completed", "completed_at", "last_viewed_at"])

        return JsonResponse({"ok": True, "completed": obj.is_completed, "pos": obj.last_position_ms})


class CommentCreateView(LoginRequiredMixin, LectureAccessRequiredMixin, View):
    """
    Crée un commentaire. Throttle léger pour éviter l’abus.
    """

    def post(self, request, pk: int):
        lecture = get_object_or_404(Lecture, pk=pk)

        # Throttle
        key = f"learning:comment_throttle:{request.user.id}:{pk}"
        if cache.get(key):
            messages.warning(request, "Calme. Attends un peu avant de republier.")
            return redirect(self._back_to_lecture(lecture))
        cache.set(key, 1, COMMENT_THROTTLE_SECONDS)

        body = (request.POST.get("body") or "").strip()
        if len(body) < 3:
            messages.error(request, "Ton commentaire est trop court.")
            return redirect(self._back_to_lecture(lecture))
        if len(body) > 2000:
            messages.error(request, "C’est un roman. 2000 caractères max.")
            return redirect(self._back_to_lecture(lecture))

        LectureComment.objects.create(user=request.user, lecture=lecture, body=body)
        messages.success(request, "Commentaire ajouté.")
        return redirect(self._back_to_lecture(lecture))

    def get(self, request, pk: int):
        return HttpResponseNotAllowed(["POST"])

    def _back_to_lecture(self, lecture):
        # Retourne l’URL canonique de la leçon, avec fallback pk si besoin
        return lecture.get_absolute_url()
