from __future__ import annotations

import io
import tempfile
from pathlib import Path
from types import MethodType

from django.contrib.staticfiles.storage import staticfiles_storage
from django.template import Context, Template
from django.test import SimpleTestCase, override_settings

from PIL import Image

from apps.atelier.staticbuild.storage import VariantManifestStaticFilesStorage, _cfg


class VariantStaticUrlTests(SimpleTestCase):
    @override_settings(
        ATELIER_IMAGE_VARIANTS={
            "enabled": ["avif", "webp", "png"],
            "max_width": 0,
            "quality": {"avif": 40, "webp": 80, "png": 9},
            "process_ext": [".png"],
        }
    )
    def test_hashed_variant_paths_survive_static_lookup(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = VariantManifestStaticFilesStorage(location=tmpdir, base_url="/static/")

            original_rel = "images/check/sample.png"
            hashed_rel = "images/check/sample.abcdef123456.png"

            # create hashed source file on disk
            img = Image.new("RGB", (32, 32), color="red")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            buf.seek(0)
            target = Path(storage.path(hashed_rel))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(buf.getvalue())

            cfg = _cfg()
            storage._variants_map.clear()

            storage._maybe_build_variants(original_rel, hashed_rel, cfg)

            mapping = storage._variants_map[original_rel]
            variant_path = mapping["webp"]

            self.assertEqual(storage.hashed_name(variant_path), variant_path)
            self.assertEqual(storage.url(variant_path), f"/static/{variant_path}")


class ResponsivePictureVariantFallbackTests(SimpleTestCase):
    def setUp(self) -> None:
        super().setUp()
        self._existing_paths: set[str] = set()

        self._original_exists = staticfiles_storage.exists
        staticfiles_storage.exists = MethodType(
            lambda storage, path: path in self._existing_paths,
            staticfiles_storage,
        )
        self.addCleanup(lambda: setattr(staticfiles_storage, "exists", self._original_exists))

        self._original_url = staticfiles_storage.url
        staticfiles_storage.url = MethodType(
            lambda storage, name, force=False: f"/static/{name}",
            staticfiles_storage,
        )
        self.addCleanup(lambda: setattr(staticfiles_storage, "url", self._original_url))

        self._original_hashed_files = getattr(staticfiles_storage, "hashed_files", {}).copy()
        self.addCleanup(self._restore_hashed_files)
        self.addCleanup(lambda: staticfiles_storage.__dict__.pop("variants_index", None))

    def _restore_hashed_files(self) -> None:
        hashed_files = getattr(staticfiles_storage, "hashed_files", {})
        hashed_files.clear()
        hashed_files.update(self._original_hashed_files)

    def test_missing_avif_is_skipped_but_webp_and_png_render(self) -> None:
        variants_rel = {
            "webp": "images/check/sample.hash/sample.hash.webp",
            "png": "images/check/sample.hash/sample.hash.png",
            "avif": "images/check/sample.hash/sample.hash.avif",
        }

        staticfiles_storage.__dict__["variants_index"] = {
            "images/check/sample.png": variants_rel,
        }

        hashed_files = getattr(staticfiles_storage, "hashed_files", {})
        for rel in variants_rel.values():
            hashed_files[staticfiles_storage.hash_key(rel)] = rel

        self._existing_paths.update({
            "images/check/sample.hash/sample.hash.webp",
            "images/check/sample.hash/sample.hash.png",
        })

        tpl = Template("{% load atelier_images %}{% responsive_picture 'images/check/sample.png' alt='sample' %}")
        html = tpl.render(Context({}))

        self.assertNotIn('type="image/avif"', html)
        self.assertIn('type="image/webp"', html)
        self.assertIn('img src="/static/images/check/sample.hash/sample.hash.png"', html)

    def test_png_is_fallback_when_all_sources_missing(self) -> None:
        variants_rel = {
            "png": "images/check/sample.hash/sample.hash.png",
        }
        staticfiles_storage.__dict__["variants_index"] = {
            "images/check/sample.png": variants_rel,
        }

        hashed_files = getattr(staticfiles_storage, "hashed_files", {})
        for rel in variants_rel.values():
            hashed_files[staticfiles_storage.hash_key(rel)] = rel
        self._existing_paths.add("images/check/sample.hash/sample.hash.png")

        tpl = Template("{% load atelier_images %}{% responsive_picture 'images/check/sample.png' alt='sample' %}")
        html = tpl.render(Context({}))

        self.assertIn('<img src="/static/images/check/sample.hash/sample.hash.png"', html)
