from __future__ import annotations

from dataclasses import dataclass

from django.test import RequestFactory

from apps.atelier.middleware.language_prefix import LanguagePrefixMiddleware
from apps.atelier.middleware.segments import SegmentResolverMiddleware
from apps.atelier.middleware.site_version import PathPrefixSiteVersionMiddleware
from apps.common.runscript_harness import binary_harness


@dataclass
class ExpectedOutcome:
    path: str
    accept_language: str | None
    expected_site: str
    expected_lang: str
    expect_redirect: str | None = None


TEST_CASES = [
    ExpectedOutcome(path="/", accept_language="ar-MA,fr;q=0.7", expected_site="core", expected_lang="ar"),
    ExpectedOutcome(path="/fr/produits/offres", accept_language="fr", expected_site="ma", expected_lang="fr", expect_redirect="/maroc/fr/produits/offres"),
    ExpectedOutcome(path="/maroc/ar/produits/offres", accept_language=None, expected_site="ma", expected_lang="ar"),
    ExpectedOutcome(path="/france/en/produits/offres", accept_language=None, expected_site="fr", expected_lang="en"),
]


@binary_harness
def run():
    site_middleware = PathPrefixSiteVersionMiddleware(lambda request: request)
    language_middleware = LanguagePrefixMiddleware(lambda request: request)
    segments_middleware = SegmentResolverMiddleware(lambda request: request)
    factory = RequestFactory()

    logs = []
    ok = True

    for case in TEST_CASES:
        headers = {}
        if case.accept_language:
            headers["HTTP_ACCEPT_LANGUAGE"] = case.accept_language
        request = factory.get(case.path, **headers)
        response = site_middleware.process_request(request)
        if response is None:
            response = language_middleware.process_request(request)

        redirect_location = None
        if response is not None:
            redirect_location = response["Location"]
        else:
            segments_middleware(request)

        log_entry = {
            "path": case.path,
            "site_version": getattr(request, "site_version", None),
            "lang": getattr(getattr(request, "_segments", None), "lang", None),
            "redirect": redirect_location,
        }
        logs.append(
            f"path={case.path} lang={log_entry['lang']} site_version={log_entry['site_version']} redirect={redirect_location}"
        )

        if redirect_location != case.expect_redirect:
            ok = False
            continue

        if redirect_location is None:
            if (
                log_entry["site_version"] != case.expected_site
                or log_entry["lang"] != case.expected_lang
            ):
                ok = False

    return {"ok": ok, "name": "lang_prefix_smoke", "logs": logs}
