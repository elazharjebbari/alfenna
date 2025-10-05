from __future__ import annotations

from django.test import RequestFactory, SimpleTestCase

from apps.atelier.middleware.site_version import PathPrefixSiteVersionMiddleware


class PathPrefixSiteVersionMiddlewareTests(SimpleTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.middleware = PathPrefixSiteVersionMiddleware(lambda request: request)

    def test_prefix_mapping_core(self) -> None:
        request = self.factory.get("/")
        self.middleware.process_request(request)
        self.assertEqual(request.site_version, "core")
        self.assertEqual(request.path_info, "/")

    def test_prefix_mapping_ma_root(self) -> None:
        request = self.factory.get("/maroc/")
        self.middleware.process_request(request)
        self.assertEqual(request.site_version, "ma")
        self.assertEqual(request.path_info, "/")

    def test_prefix_mapping_ma_nested(self) -> None:
        request = self.factory.get("/maroc/test")
        self.middleware.process_request(request)
        self.assertEqual(request.site_version, "ma")
        self.assertEqual(request.path_info, "/test")
