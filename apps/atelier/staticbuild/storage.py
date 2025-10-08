from __future__ import annotations
import io
import json
import logging
import os
import shutil
import tempfile
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Dict, Iterable, Iterator, List, Optional, Tuple
from urllib.parse import unquote, urlsplit

from django.conf import settings
from django.utils.functional import cached_property

from PIL import Image, ImageOps
from whitenoise.storage import CompressedManifestStaticFilesStorage

# Enregistre le support AVIF si dispo (dégrade si absent)
try:
    import pillow_avif  # type: ignore  # noqa: F401
except Exception:  # pragma: no cover
    pass

log = logging.getLogger("atelier.staticbuild.storage")


@dataclass(frozen=True)
class VariantConfig:
    enabled: List[str]
    max_width: int
    quality_avif: int
    quality_webp: int
    compress_png: int
    process_ext: List[str]


def _cfg() -> VariantConfig:
    c = getattr(settings, "ATELIER_IMAGE_VARIANTS", {})
    enabled = list(c.get("enabled", ["avif", "webp", "png"]))
    max_w = int(c.get("max_width", 1920) or 0)
    q = c.get("quality", {}) or {}
    proc = [e.lower() for e in c.get("process_ext", [".jpg", ".jpeg", ".png"])]
    return VariantConfig(
        enabled=enabled,
        max_width=max_w,
        quality_avif=int(q.get("avif", 50)),
        quality_webp=int(q.get("webp", 85)),
        compress_png=int(q.get("png", 9)),
        process_ext=proc,
    )


def _is_processable_image(path: str) -> bool:
    ext = Path(path).suffix.lower()
    if ext in {".svg", ".gif", ".ico"}:
        return False
    return ext in _cfg().process_ext


def _atomic_write(dst: Path, data: bytes) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=dst.parent, delete=False) as tmp:
        tmp.write(data)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_path = Path(tmp.name)
    tmp_path.replace(dst)


def _file_sha256(p: Path) -> str:
    h = sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _img_to_bytes(img: Image.Image, fmt: str, cfg: VariantConfig) -> bytes:
    buf = io.BytesIO()
    # Réglages format
    if fmt == "AVIF":
        img.save(buf, "AVIF", quality=cfg.quality_avif, speed=4)
    elif fmt == "WEBP":
        img.save(buf, "WEBP", quality=cfg.quality_webp, method=6)
    elif fmt == "PNG":
        img.save(buf, "PNG", optimize=True, compress_level=cfg.compress_png)
    else:
        raise ValueError(f"Format non supporté: {fmt}")
    return buf.getvalue()


def _ensure_mode(img: Image.Image, target_fmt: str) -> Image.Image:
    """
    Garantit un mode compatible selon le format cible (conserve alpha si présent).
    """
    if target_fmt in ("AVIF", "WEBP", "PNG"):
        # WEBP/AVIF/PNG gèrent RGBA. Si P ou LA: convertir proprement.
        if img.mode in ("RGBA", "LA"):
            return img.convert("RGBA")
        if img.mode == "P":
            return img.convert("RGBA")
        if img.mode in ("RGB", "L"):
            return img.convert("RGB")
    return img


def _resize_if_needed(img: Image.Image, max_width: int) -> Image.Image:
    if not max_width or img.width <= max_width:
        return img
    ratio = max_width / float(img.width)
    new_size = (max_width, int(img.height * ratio))
    return img.resize(new_size, Image.Resampling.LANCZOS)


class VariantManifestStaticFilesStorage(CompressedManifestStaticFilesStorage):
    """
    Sur-classe Manifest:
    - Pendant post_process, pour chaque image collectée (hashée), génère un dossier homonyme
      contenant <stem>.avif / <stem>.webp / <stem>.png (selon enabled).
    - Enrichit le manifest avec une section "_variants" mappant l'original vers les variantes.
    - Idempotent: on régénère uniquement si le "stamp" source a changé ou si un format manque.
    - Dégrade proprement si un encodeur n'est pas disponible.
    """

    # Manifest par défaut: staticfiles.json ; on y ajoute "_variants"
    _variants_map: Dict[str, Dict[str, str]]  # original -> {fmt: variant_rel_path}
    manifest_strict = False
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._variants_map = {}

    # ------------- Manifest enrichi -----------------

    def read_manifest(self) -> Optional[str]:
        content = super().read_manifest()
        if content is None:
            payload = {}
        else:
            try:
                payload = json.loads(content)
            except Exception:
                payload = {}
        variants = payload.get("_variants") or {}
        if isinstance(variants, dict):
            # normaliser en str->dict
            self._variants_map = {str(k): dict(v) for k, v in variants.items()}
        return content

    def post_process(self, *args, **kwargs) -> Iterator[Tuple[str, str, bool]]:
        """
        Délègue à parent, puis génère variantes pour chaque fichier “final”.
        """
        cfg = _cfg()
        for original_path, processed_path, processed in super().post_process(*args, **kwargs):
            try:
                # processed_path = chemin RELATIF hashé (ex: 'img/hero.abc123.jpg')
                if _is_processable_image(processed_path):
                    self._maybe_build_variants(original_path, processed_path, cfg)
            except Exception as e:  # on ne casse jamais collectstatic
                log.warning("Variant build skipped for %s (%s)", processed_path, e, exc_info=True)
            yield original_path, processed_path, processed
        # À la fin, sauvegarder le manifest enrichi
        self._save_manifest_with_variants()

    def _save_manifest_with_variants(self) -> None:
        try:
            with self.manifest_storage.open(self.manifest_name) as manifest:
                payload = json.load(manifest)
        except Exception:
            payload = {}
        payload["_variants"] = self._variants_map
        data = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        tmp = tempfile.NamedTemporaryFile(delete=False)
        try:
            tmp.write(data)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_path = Path(tmp.name)
        finally:
            tmp.close()
        # remplace atomiquement
        with self.manifest_storage.open(self.manifest_name, "wb") as target:
            target.write(tmp_path.read_bytes())
        try:
            tmp_path.unlink()
        except Exception:
            pass

    # ------------- Génération variantes -----------------

    def _maybe_build_variants(self, original_rel: str, hashed_rel: str, cfg: VariantConfig) -> None:
        """
        original_rel: chemin logique (ex: 'img/hero.jpg')
        hashed_rel  : chemin final collecté ('img/hero.abc123.jpg')
        """
        src_fs = Path(self.path(hashed_rel))  # fichier hashé sur disque
        if not src_fs.exists():
            return

        # dossier homonyme: parent / <stem hashé> / <stem hashé>.<fmt>
        stem = Path(hashed_rel).stem      # 'hero.abc123'
        parent = Path(hashed_rel).parent  # 'img'
        variants_dir_rel = str(Path(parent) / stem)        # 'img/hero.abc123'
        variants_dir_fs = Path(self.path(variants_dir_rel))

        # Stamp pour idempotence (dépend du contenu source + cfg)
        stamp_rel = str(Path(variants_dir_rel) / ".stamp")
        stamp_fs = Path(self.path(stamp_rel))
        current_stamp = self._build_stamp(src_fs, cfg)

        if not self._needs_regen(
            original_rel,
            stamp_fs,
            current_stamp,
            cfg,
            variants_dir_fs,
            variants_dir_rel,
            stem,
        ):
            # déjà à jour → remplir le mapping depuis les fichiers présents
            mapping = self._detect_existing_variants(original_rel, variants_dir_rel, stem, cfg)
            if mapping:
                for fmt, hashed_path in mapping.items():
                    self._register_variant_manifest_entry(variants_dir_rel, stem, fmt, hashed_path)
                self._variants_map[original_rel] = mapping
            else:
                self._variants_map.pop(original_rel, None)
            return

        # (Re)générer
        try:
            if variants_dir_fs.exists():
                shutil.rmtree(variants_dir_fs)

            with Image.open(src_fs) as im:
                im.load()
                base = im
                if cfg.max_width:
                    base = _resize_if_needed(base, cfg.max_width)

                mapping: Dict[str, str] = {}

                variants_dir_fs.mkdir(parents=True, exist_ok=True)

                # AVIF
                if "avif" in cfg.enabled:
                    try:
                        avif_img = _ensure_mode(base, "AVIF")
                        avif_bytes = _img_to_bytes(avif_img, "AVIF", cfg)
                        avif_rel = str(Path(variants_dir_rel) / f"{stem}.avif")
                        _atomic_write(Path(self.path(avif_rel)), avif_bytes)
                        hashed_rel = self._normalize_rel(self._finalize_variant_file(avif_rel))
                        mapping["avif"] = hashed_rel
                        self._register_variant_manifest_entry(variants_dir_rel, stem, "avif", hashed_rel)
                    except Exception as e:
                        log.warning("AVIF encode failed for %s: %s", hashed_rel, e)

                # WEBP
                if "webp" in cfg.enabled:
                    try:
                        webp_img = _ensure_mode(base, "WEBP")
                        webp_bytes = _img_to_bytes(webp_img, "WEBP", cfg)
                        webp_rel = str(Path(variants_dir_rel) / f"{stem}.webp")
                        _atomic_write(Path(self.path(webp_rel)), webp_bytes)
                        hashed_rel = self._normalize_rel(self._finalize_variant_file(webp_rel))
                        mapping["webp"] = hashed_rel
                        self._register_variant_manifest_entry(variants_dir_rel, stem, "webp", hashed_rel)
                    except Exception as e:
                        log.warning("WEBP encode failed for %s: %s", hashed_rel, e)

                # PNG (toujours dispo)
                if "png" in cfg.enabled:
                    try:
                        png_img = _ensure_mode(base, "PNG")
                        png_bytes = _img_to_bytes(png_img, "PNG", cfg)
                        png_rel = str(Path(variants_dir_rel) / f"{stem}.png")
                        _atomic_write(Path(self.path(png_rel)), png_bytes)
                        hashed_rel = self._normalize_rel(self._finalize_variant_file(png_rel))
                        mapping["png"] = hashed_rel
                        self._register_variant_manifest_entry(variants_dir_rel, stem, "png", hashed_rel)
                    except Exception as e:
                        log.warning("PNG encode failed for %s: %s", hashed_rel, e)

                # Écrit le stamp + mappe dans manifest
                _atomic_write(stamp_fs, current_stamp.encode("utf-8"))
                if mapping:
                    self._variants_map[original_rel] = mapping
                else:
                    self._variants_map.pop(original_rel, None)

        except Exception as e:
            log.warning("Variant generation error for %s: %s", hashed_rel, e, exc_info=True)

    def _build_stamp(self, src_fs: Path, cfg: VariantConfig) -> str:
        # sur la source hashée (stable) + paramètres clés => idempotence
        return json.dumps(
            {
                "src_sha256": _file_sha256(src_fs),
                "max_width": cfg.max_width,
                "quality": {
                    "avif": cfg.quality_avif,
                    "webp": cfg.quality_webp,
                    "png": cfg.compress_png,
                },
                "enabled": cfg.enabled,
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    def _needs_regen(
        self,
        original_rel: str,
        stamp_fs: Path,
        current_stamp: str,
        cfg: VariantConfig,
        variants_dir_fs: Path,
        variants_dir_rel: str,
        stem: str,
    ) -> bool:
        try:
            if not stamp_fs.exists():
                return True
            if not variants_dir_fs.exists():
                return True
            existing = self._detect_existing_variants(original_rel, variants_dir_rel, stem, cfg)
            for fmt in cfg.enabled:
                rel = existing.get(fmt)
                if not rel or not Path(self.path(rel)).exists():
                    return True
            # stamp diff ?
            if stamp_fs.read_text() != current_stamp:
                return True
            return False
        except Exception:
            return True

    def _detect_existing_variants(
        self,
        original_rel: str,
        variants_dir_rel: str,
        stem: str,
        cfg: VariantConfig,
    ) -> Dict[str, str]:
        mapping: Dict[str, str] = {}

        stored = self._variants_map.get(original_rel)
        if isinstance(stored, dict):
            for fmt in cfg.enabled:
                rel = stored.get(fmt)
                if not rel:
                    continue
                normalized = self._normalize_rel(rel)
                if Path(self.path(normalized)).exists():
                    mapping[fmt] = normalized

        dir_fs = Path(self.path(variants_dir_rel))
        if not dir_fs.exists():
            return mapping

        for fmt in cfg.enabled:
            if fmt in mapping:
                continue
            pattern = f"{stem}.*.{fmt}"
            try:
                candidate = next((p for p in dir_fs.glob(pattern) if p.is_file()), None)
            except Exception:
                candidate = None
            if candidate:
                rel = self._normalize_rel(str(PurePosixPath(variants_dir_rel) / candidate.name))
                if Path(self.path(rel)).exists():
                    mapping[fmt] = rel
        return mapping

    def _register_variant_manifest_entry(
        self,
        variants_dir_rel: str,
        stem: str,
        fmt: str,
        hashed_rel: str,
    ) -> None:
        """Ensure manifest paths contain the mapping for a generated variant."""
        if not hasattr(self, "hashed_files"):
            return
        base_rel = PurePosixPath(variants_dir_rel) / f"{stem}.{fmt}"
        original_rel = self.clean_name(self._normalize_rel(str(base_rel)))
        hashed_clean = self.clean_name(self._normalize_rel(hashed_rel))
        self.hashed_files[self.hash_key(original_rel)] = hashed_clean
        # Évite un double hash quand l'URL hashée repasse dans static()
        self.hashed_files[self.hash_key(hashed_clean)] = hashed_clean

    def _finalize_variant_file(self, variant_rel: str) -> str:
        try:
            hashed_rel = self.hashed_name(variant_rel)
        except Exception as exc:
            log.warning("hashed_name failed for %s: %s", variant_rel, exc)
            return variant_rel

        if hashed_rel == variant_rel:
            return variant_rel

        src_path = Path(self.path(variant_rel))
        dst_path = Path(self.path(hashed_rel))
        if not src_path.exists():
            return hashed_rel

        dst_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            src_path.replace(dst_path)
        except Exception as exc:
            log.warning("Failed to move variant %s -> %s (%s)", src_path, dst_path, exc)
            try:
                shutil.copy2(src_path, dst_path)
                src_path.unlink(missing_ok=True)
            except Exception:
                return variant_rel
        return hashed_rel

    @staticmethod
    def _normalize_rel(path: str) -> str:
        return str(PurePosixPath(path)).lstrip("/")

    # Exposé lecture à runtime (templating)
    @cached_property
    def variants_index(self) -> Dict[str, Dict[str, str]]:
        # Assure que _variants_map est chargé depuis le manifest
        if not self._variants_map:
            self.read_manifest()
        return self._variants_map.copy()

    def hashed_name(self, name: str, content=None, filename: Optional[str] = None) -> str:
        parsed = urlsplit(unquote(name))
        normalized = self.clean_name(self._normalize_rel(parsed.path.strip()))
        hashed_files = getattr(self, "hashed_files", {}) or {}
        if normalized in hashed_files.values():
            return normalized
        return super().hashed_name(name, content=content, filename=filename)

    def url(self, name: str, force: bool = False) -> str:
        """Serve hashed URLs even when DEBUG is active.

        WhiteNoise is configured with ``WHITENOISE_USE_FINDERS = False`` in dev, so
        returning the unhashed path (Django's default in DEBUG) leads to 404s because
        only the hashed artefacts exist in ``STATIC_ROOT``. Forcing the hashed URL
        keeps dev and prod aligned.
        """
        if settings.DEBUG and not force:
            force = True
        return super().url(name, force=force)
