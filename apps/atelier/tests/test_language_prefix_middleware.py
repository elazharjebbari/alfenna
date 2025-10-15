from __future__ import annotations

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.atelier.middleware.language_prefix import LanguagePrefixMiddleware
from apps.atelier.middleware.segments import SegmentResolverMiddleware, Segments
from apps.atelier.middleware.site_version import PathPrefixSiteVersionMiddleware


class LanguagePrefixMiddlewareTests(SimpleTestCase):
    factory = RequestFactory()

    def _language_middleware(self):
        return LanguagePrefixMiddleware(lambda request: request)

    def test_strips_language_prefix_and_sets_attributes(self) -> None:
        middleware = self._language_middleware()
        site_middleware = PathPrefixSiteVersionMiddleware(lambda request: request)
        request = self.factory.get("/maroc/fr/catalogue/offres")

        site_middleware.process_request(request)
        response = middleware.process_request(request)
        self.assertIsNone(response)
        self.assertEqual(request.url_lang, "fr")
        self.assertEqual(request.path_info, "/catalogue/offres")

    def test_sets_cookie_on_response(self) -> None:
        middleware = self._language_middleware()
        request = self.factory.get("/ar/catalogue/offres")
        middleware.process_request(request)

        response = HttpResponse()
        response = middleware.process_response(request, response)
        self.assertIn("lang", response.cookies)
        self.assertEqual(response.cookies["lang"].value, "ar")

    def test_combined_site_version_and_language_prefix(self) -> None:
        site_middleware = PathPrefixSiteVersionMiddleware(lambda request: request)
        language_middleware = self._language_middleware()
        request = self.factory.get("/maroc/ar/produits/pack")

        site_middleware.process_request(request)
        language_middleware.process_request(request)
        self.assertEqual(request.site_version, "ma")
        self.assertEqual(request.url_lang, "ar")
        self.assertEqual(request.path_info, "/produits/pack")

    def test_no_language_prefix_leaves_request_untouched(self) -> None:
        middleware = self._language_middleware()
        request = self.factory.get("/produits/offres")

        middleware.process_request(request)

        self.assertFalse(hasattr(request, "url_lang"))
        self.assertEqual(request.path_info, "/produits/offres")

    @override_settings(LANGUAGE_DEFAULT_SITE_PREFIX="maroc")
    def test_alias_redirects_to_default_site(self) -> None:
        site_middleware = PathPrefixSiteVersionMiddleware(lambda request: request)
        middleware = self._language_middleware()
        request = self.factory.get("/ar/produits/offres")

        site_middleware.process_request(request)
        response = middleware.process_request(request)

        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], "/maroc/ar/produits/offres")


class SegmentResolverMiddlewareTests(SimpleTestCase):
    factory = RequestFactory()

    def _segments_middleware(self):
        return SegmentResolverMiddleware(lambda request: request)

    def test_segments_use_language_prefix_when_present(self) -> None:
        site_middleware = PathPrefixSiteVersionMiddleware(lambda request: request)
        language_middleware = LanguagePrefixMiddleware(lambda request: request)
        segments_middleware = self._segments_middleware()
        request = self.factory.get("/maroc/ar/produits")

        site_middleware.process_request(request)
        language_middleware.process_request(request)
        segments_middleware(request)

        self.assertEqual(request.site_version, "ma")
        self.assertEqual(request._segments.lang, "ar")
        self.assertEqual(request.LANGUAGE_CODE, "ar")

    def test_segments_fall_back_to_accept_language_header(self) -> None:
        segments_middleware = self._segments_middleware()
        request = self.factory.get(
            "/produits",
            HTTP_ACCEPT_LANGUAGE="ar-MA,fr;q=0.7",
        )

        segments_middleware(request)
        self.assertEqual(request._segments.lang, "ar")
        self.assertEqual(request.LANGUAGE_CODE, "ar")

    def test_segments_use_cookie_when_present(self) -> None:
        segments_middleware = self._segments_middleware()
        request = self.factory.get("/produits", HTTP_ACCEPT_LANGUAGE="fr")
        request.COOKIES["lang"] = "ar"

        segments_middleware(request)

        self.assertEqual(request._segments.lang, "ar")

    def test_segments_respect_existing_lang(self) -> None:
        segments_middleware = self._segments_middleware()
        request = self.factory.get("/produits", HTTP_ACCEPT_LANGUAGE="fr")
        request._segments = Segments(lang="ar")

        segments_middleware(request)

        self.assertEqual(request._segments.lang, "ar")
