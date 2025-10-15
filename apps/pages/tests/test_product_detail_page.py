from __future__ import annotations

from django.test import TestCase
from django.urls import reverse

from apps.marketing.models.models_pricing import PricePlan


class ProductDetailPageTests(TestCase):
    def test_product_detail_route_returns_ok(self) -> None:
        from apps.catalog.models import Product
        from apps.catalog.models.models_catalog import Gallery, GalleryItem

        product = Product.objects.create(
            slug="pack-cosmetique-naturel",
            name="Pack",
            price=349,
            promo_price=329,
            currency="MAD",
        )
        gallery = Gallery.objects.create(slug="participants", is_active=True)
        GalleryItem.objects.create(
            gallery=gallery,
            name="Demo",
            image="images/demo.jpg",
        )

        url = reverse("pages:product-detail-slug", kwargs={"product_slug": product.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("data-cmp=\"product\"", html)
        self.assertTrue(
            ("data-form-stepper" in html) or ("data-ff-root" in html),
            "Stepper markup missing",
        )
        self.assertIn('data-steps="4"', html)
        self.assertIn('data-action-url="/api/leads/collect/"', html)
        self.assertIn('data-sign-url="/api/leads/sign/"', html)
        self.assertIn('data-require-signed="true"', html)

    def test_product_detail_ma_ar_renders_translated_content(self) -> None:
        from apps.catalog.models import Product

        product = Product.objects.create(
            slug="pack-cosmetique-naturel",
            name="Pack Cosmétiques",
            description="Routine quotidienne visage + corps",
            price=349,
            promo_price=329,
            currency="MAD",
        )

        response = self.client.get(f"/maroc/ar/produits/{product.slug}/")
        self.assertEqual(response.status_code, 200)

        html = response.content.decode()
        self.assertIn("100% طبيعي", html)
        self.assertIn("توصيل إلى جميع أنحاء المغرب", html)
        self.assertIn("هل تحتاج المساعدة؟", html)
        self.assertIn("أطلب الحزمة الآن", html)
        self.assertIn("dir=\"rtl\"", html)
        self.assertIn("lang=\"ar\"", html)

    def test_product_detail_ma_ar_smoke_slots_and_vary(self) -> None:
        from apps.catalog.models import Product

        product = Product.objects.create(
            slug="pack-cosmetique-naturel",
            name="Pack Cosmétiques",
            description="Routine quotidienne visage + corps",
            price=349,
            promo_price=329,
            currency="MAD",
        )

        response = self.client.get(f"/maroc/ar/produits/{product.slug}/")
        self.assertEqual(response.status_code, 200)

        vary_header = response.get("Vary", "")
        self.assertIn("lang", vary_header)
        self.assertIn("site_version", vary_header)

        html = response.content.decode()
        # Header / topbar
        self.assertIn("100% طبيعي", html)
        self.assertIn("اطلب الآن", html)
        self.assertIn("الرئيسية", html)
        self.assertIn("دوراتنا", html)
        self.assertIn("تواصل معنا", html)
        self.assertIn("/static/css/rtl", html)
        # Primary CTA & sticky buybar
        self.assertIn("أطلب الحزمة الآن", html)
        self.assertIn("خصم", html)
        # Footer & FAB
        self.assertIn("المتجر", html)
        self.assertIn("الدعم", html)
        self.assertIn("هل تحتاج المساعدة؟", html)


class ProductDetailDbContentTests(TestCase):
    fixtures = ["alfenna/fixtures/product_pack_cosmetique_naturel.json"]

    @classmethod
    def setUpTestData(cls) -> None:
        plan, _ = PricePlan.objects.get_or_create(
            slug="createur",
            defaults=dict(
                title="Createur",
                currency="MAD",
                currency_symbol="MAD",
                price_cents=32900,
                is_active=True,
            ),
        )
        plan.title = "TITRE_DB_SENTINEL"
        plan.features = ["FEATURE_DB_SENTINEL"]
        plan.save()

    def test_fr_page_displays_db_media(self) -> None:
        response = self.client.get("/produits/pack-cosmetique-naturel/", follow=True)

        self.assertEqual(response.status_code, 200)

        html = response.content.decode("utf-8")
        self.assertIn("Pack cosmétique naturel — Édition Spa", html)
        self.assertIn("/static/images/landing-page/product-single/pack-detail-1.webp", html)
        self.assertIn("TITRE_DB_SENTINEL", html)
        self.assertGreaterEqual(html.count("swiper-slide"), 3)
        self.assertNotIn("Pack 1", html)

    def test_ma_ar_page_displays_translated_media(self) -> None:
        response = self.client.get("/maroc/ar/produits/pack-cosmetique-naturel/", follow=True)

        self.assertEqual(response.status_code, 200)

        html = response.content.decode("utf-8")
        self.assertIn("أطلب الحزمة الآن", html)
        self.assertGreaterEqual(html.count("swiper-slide"), 3)
