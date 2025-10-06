from __future__ import annotations
from unittest.mock import patch
from types import MethodType

from django.contrib.staticfiles.storage import staticfiles_storage
from django.template import Context, Template
from django.test import SimpleTestCase


class ResponsivePictureVariantsTests(SimpleTestCase):
    def setUp(self) -> None:
        super().setUp()
        self._original_url = staticfiles_storage.url
        staticfiles_storage.url = MethodType(
            lambda storage, name, force=False: f"/static/{name}",
            staticfiles_storage,
        )
        self.addCleanup(lambda: setattr(staticfiles_storage, "url", self._original_url))

        self._existing_paths: set[str] = set()
        self._original_exists = staticfiles_storage.exists
        staticfiles_storage.exists = MethodType(
            lambda storage, name: name in self._existing_paths,
            staticfiles_storage,
        )
        self.addCleanup(lambda: setattr(staticfiles_storage, "exists", self._original_exists))

        if "variants_index" in staticfiles_storage.__dict__:
            original = staticfiles_storage.__dict__["variants_index"]

            def restore() -> None:
                staticfiles_storage.__dict__["variants_index"] = original

            self.addCleanup(restore)
        else:
            self.addCleanup(lambda: staticfiles_storage.__dict__.pop("variants_index", None))

    def test_manifest_lookup_avif_webp_png(self) -> None:
        staticfiles_storage.__dict__["variants_index"] = {
            "images/shape/shape-8.png": {
                "avif": "images/shape/shape-8.hash/shape-8.hash.avif",
                "webp": "images/shape/shape-8.hash/shape-8.hash.webp",
                "png": "images/shape/shape-8.hash/shape-8.hash.png",
            }
        }
        self._existing_paths.update(
            {
                "images/shape/shape-8.hash/shape-8.hash.avif",
                "images/shape/shape-8.hash/shape-8.hash.webp",
                "images/shape/shape-8.hash/shape-8.hash.png",
            }
        )
        tpl = Template(
            "{% load atelier_images %}{% responsive_picture 'images/shape/shape-8.png' alt='shape' %}"
        )
        html = tpl.render(Context({}))

        self.assertIn('type="image/avif"', html)
        self.assertIn('shape-8.hash.avif', html)
        self.assertIn('type="image/webp"', html)
        self.assertIn('shape-8.hash.webp', html)
        self.assertIn('img src="/static/images/shape/shape-8.hash/shape-8.hash.png"', html)

    def test_fallback_when_no_manifest_but_flat_exists(self) -> None:
        staticfiles_storage.__dict__["variants_index"] = {}

        existing = {
            "images/shape/shape-8.avif",
            "images/shape/shape-8.webp",
            "images/shape/shape-8.png",
        }
        self._existing_paths.update(existing)

        def fake_exists(path: str) -> bool:
            return path in existing

        with patch("apps.atelier.templatetags.atelier_images._exists", side_effect=fake_exists):
            tpl = Template(
                "{% load atelier_images %}{% responsive_picture 'images/shape/shape-8' alt='shape' %}"
            )
            html = tpl.render(Context({}))

        self.assertIn('type="image/avif"', html)
        self.assertIn('images/shape/shape-8.avif', html)
        self.assertIn('type="image/webp"', html)
        self.assertIn('images/shape/shape-8.webp', html)
        self.assertIn('img src="/static/images/shape/shape-8.png"', html)

    def test_manifest_lookup_with_nested_original(self) -> None:
        staticfiles_storage.__dict__["variants_index"] = {
            "images/logo/logo.webp": {
                "avif": "images/logo/logo.hash/logo.hash.avif",
                "webp": "images/logo/logo.hash/logo.hash.webp",
                "png": "images/logo/logo.hash/logo.hash.png",
            }
        }
        self._existing_paths.update(
            {
                "images/logo/logo.hash/logo.hash.avif",
                "images/logo/logo.hash/logo.hash.webp",
                "images/logo/logo.hash/logo.hash.png",
            }
        )

        tpl = Template(
            "{% load atelier_images %}{% responsive_picture 'images/logo' alt='logo' %}"
        )
        html = tpl.render(Context({}))

        self.assertIn('type="image/avif"', html)
        self.assertIn('images/logo/logo.hash/logo.hash.avif', html)
        self.assertIn('type="image/webp"', html)
        self.assertIn('images/logo/logo.hash/logo.hash.webp', html)
        self.assertIn('img src="/static/images/logo/logo.hash/logo.hash.png"', html)
