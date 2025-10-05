from __future__ import annotations
from types import MethodType

from django.contrib.staticfiles.storage import staticfiles_storage
from django.template import Context, Template
from django.test import SimpleTestCase


class ResponsivePictureExistsFilterTests(SimpleTestCase):
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

    def test_sources_skipped_when_files_missing(self) -> None:
        staticfiles_storage.__dict__["variants_index"] = {
            "images/shape/shape-8.png": {
                "avif": "images/shape/shape-8.hash/shape-8.hash.avif",
                "webp": "images/shape/shape-8.hash/shape-8.hash.webp",
                "png": "images/shape/shape-8.hash/shape-8.hash.png",
            }
        }
        self._existing_paths.add("images/shape/shape-8.hash/shape-8.hash.png")

        tpl = Template(
            "{% load atelier_images %}{% responsive_picture 'images/shape/shape-8.png' alt='shape' %}"
        )
        html = tpl.render(Context({}))

        self.assertNotIn('type="image/avif"', html)
        self.assertNotIn('type="image/webp"', html)
        self.assertIn('img src="/static/images/shape/shape-8.hash/shape-8.hash.png"', html)

    def test_fallback_to_original_when_no_variant_exists(self) -> None:
        staticfiles_storage.__dict__["variants_index"] = {
            "images/shape/shape-8.png": {
                "avif": "images/shape/shape-8.hash/shape-8.hash.avif",
            }
        }

        tpl = Template(
            "{% load atelier_images %}{% responsive_picture 'images/shape/shape-8.png' alt='shape' %}"
        )
        html = tpl.render(Context({}))

        self.assertNotIn('type="image/avif"', html)
        self.assertIn('img src="/static/images/shape/shape-8.png"', html)
