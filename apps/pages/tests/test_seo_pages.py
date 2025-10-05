from __future__ import annotations

from collections import defaultdict
from html.parser import HTMLParser

from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import Course
from apps.content.models import Lecture, Section


class _HeadParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.meta: dict[tuple[str, str], list[str]] = defaultdict(list)
        self.links: list[dict[str, str]] = []
        self.titles: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[override]
        attrs_dict = {k.lower(): (v or "") for k, v in attrs}
        if tag.lower() == "meta":
            if "name" in attrs_dict:
                key = attrs_dict["name"].lower()
                self.meta[("name", key)].append(attrs_dict.get("content", ""))
            if "property" in attrs_dict:
                key = attrs_dict["property"].lower()
                self.meta[("property", key)].append(attrs_dict.get("content", ""))
        elif tag.lower() == "link":
            if "rel" in attrs_dict:
                attrs_dict["rel"] = attrs_dict["rel"].lower()
            self.links.append(attrs_dict)
        elif tag.lower() == "title":
            self._in_title = True

    def handle_data(self, data: str) -> None:  # type: ignore[override]
        if self._in_title:
            text = data.strip()
            if text:
                self.titles.append(text)

    def handle_endtag(self, tag: str) -> None:  # type: ignore[override]
        if tag.lower() == "title":
            self._in_title = False

    def first_meta(self, key_type: str, key_name: str) -> str:
        values = self.meta.get((key_type, key_name.lower())) or self.meta.get((key_type, key_name))
        if not values:
            return ""
        for value in values:
            if value:
                return value
        return ""


class MarketingSeoTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        course = Course.objects.create(
            title="Bougies naturelles",
            slug="bougies-naturelles",
            description="Démo du programme",
            is_published=True,
        )
        section = Section.objects.create(course=course, title="Section 1", order=1, is_published=True)
        Lecture.objects.create(
            course=course,
            section=section,
            title="Introduction",
            order=1,
            is_published=True,
            is_demo=True,
        )

    def _parse(self, response) -> _HeadParser:
        parser = _HeadParser()
        parser.feed(response.content.decode())
        return parser

    def _assert_indexable_page(self, url: str) -> None:
        response = self.client.get(url, follow=True)
        self.assertEqual(response.status_code, 200)
        parser = self._parse(response)

        self.assertTrue(parser.titles, "<title> tag missing")
        description = parser.first_meta("name", "description")
        self.assertTrue(description, "meta description missing")

        canonical = None
        for link in parser.links:
            if link.get("rel") == "canonical":
                canonical = link.get("href")
                break
        self.assertIsNotNone(canonical, "canonical link missing")
        expected_path = response.wsgi_request.path
        expected_canonical = f"http://testserver{expected_path}"
        self.assertEqual(canonical, expected_canonical)

        robots = parser.first_meta("name", "robots")
        self.assertEqual(robots, "index,follow")

        og_title = parser.first_meta("property", "og:title")
        og_desc = parser.first_meta("property", "og:description")
        og_type = parser.first_meta("property", "og:type")
        og_url = parser.first_meta("property", "og:url")
        og_image = parser.first_meta("property", "og:image")
        self.assertTrue(og_title)
        self.assertTrue(og_desc)
        self.assertTrue(og_type)
        self.assertEqual(og_url, expected_canonical)
        self.assertTrue(og_image)

        twitter_card = parser.first_meta("name", "twitter:card")
        twitter_title = parser.first_meta("name", "twitter:title")
        twitter_desc = parser.first_meta("name", "twitter:description")
        twitter_image = parser.first_meta("name", "twitter:image")
        self.assertTrue(twitter_card)
        self.assertTrue(twitter_title)
        self.assertTrue(twitter_desc)
        self.assertTrue(twitter_image)

    def test_home_seo_tags_present_and_indexable(self) -> None:
        self._assert_indexable_page("/")

    def test_contact_seo_ok(self) -> None:
        self._assert_indexable_page(reverse("pages:contact"))

    def test_learn_seo_ok(self) -> None:
        self._assert_indexable_page(reverse("pages:learn"))

    def test_demo_seo_ok(self) -> None:
        self._assert_indexable_page(reverse("pages:demo-default"))

    def test_faq_seo_ok(self) -> None:
        self._assert_indexable_page(reverse("pages:faq"))

    def test_packs_seo_ok(self) -> None:
        self._assert_indexable_page(reverse("pages:packs"))

    def test_login_is_noindex(self) -> None:
        response = self.client.get(reverse("pages:login"))
        self.assertEqual(response.status_code, 200)
        parser = self._parse(response)
        robots = parser.first_meta("name", "robots")
        self.assertEqual(robots, "noindex,nofollow")

    def test_sitemap_contains_expected_pages(self) -> None:
        response = self.client.get(reverse("sitemap"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        expected_paths = [
            "/",
            reverse("pages:contact"),
            reverse("pages:learn"),
            reverse("pages:demo", kwargs={"course_slug": "bougies-naturelles"}),
            reverse("pages:login"),
            reverse("pages:faq"),
            reverse("pages:packs"),
        ]
        for path in expected_paths:
            self.assertIn(f"http://testserver{path}", content)

    def test_robots_txt_points_to_sitemap(self) -> None:
        response = self.client.get("/robots.txt")
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("Sitemap: http://testserver/sitemap.xml", body)
        self.assertIn("Disallow: /admin/", body)
        self.assertIn("Disallow: /accounts/", body)
        directives = [line.strip() for line in body.splitlines() if line.strip()]
        self.assertNotIn("Disallow: /", directives)
