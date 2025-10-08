from __future__ import annotations

from bs4 import BeautifulSoup
from django.template.loader import render_to_string
from django.test import TestCase


class ProductGallerySwiperTests(TestCase):
    fixtures = ["products_pack_cosmetique.json"]

    def test_gallery_renders_with_multiple_images(self) -> None:
        response = self.client.get("/fr/produits/pack-cosmetique-naturel/")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8", "ignore")
        soup = BeautifulSoup(html, "html.parser")

        gallery_main = soup.select_one(".gallery-main.swiper")
        self.assertIsNotNone(gallery_main)
        gallery_thumbs = soup.select_one(".gallery-thumbs.swiper")
        self.assertIsNotNone(gallery_thumbs)

        main_slides = gallery_main.select(".swiper-slide")
        self.assertGreaterEqual(len(main_slides), 3)
        for slide in main_slides:
            self.assertIsNotNone(slide.find("picture"))

        self.assertIsNotNone(gallery_main.select_one(".swiper-button-next"))
        self.assertIsNotNone(gallery_main.select_one(".swiper-button-prev"))
        self.assertIsNotNone(gallery_main.select_one(".swiper-pagination"))

    def test_single_image_partial_hides_thumbs_and_controls(self) -> None:
        single_image = [
            {
                "src": "https://placehold.co/960x720?text=Single",
                "thumb": "https://placehold.co/176x132?text=Single",
                "alt": "Visuel unique",
            }
        ]
        html = render_to_string(
            "components/core/product/_media_swiper.html",
            {"images": single_image, "product": {"name": "Produit Mono"}},
        )
        soup = BeautifulSoup(html, "html.parser")

        self.assertIsNone(soup.select_one(".gallery-thumbs"))
        controls = soup.select(".gallery-main .swiper-button-prev, .gallery-main .swiper-button-next")
        self.assertFalse(controls)
        self.assertIsNone(soup.select_one(".gallery-main .swiper-pagination"))

        picture = soup.find("picture")
        self.assertIsNotNone(picture)
        image = picture.find("img")
        self.assertIsNotNone(image)
        self.assertEqual(image.get("width"), "1200")
        self.assertEqual(image.get("height"), "900")
        self.assertEqual(image.get("loading"), "lazy")
        self.assertEqual(image.get("decoding"), "async")
