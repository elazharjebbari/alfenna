from django.db import models

class MarketingGlobal(models.Model):
    """
    Singleton logique (1 seule ligne) pour overrider les defaults SEO/Tracking.
    """
    site_name = models.CharField(max_length=120, blank=True, default="")
    base_url = models.URLField(blank=True, default="")
    default_locale = models.CharField(max_length=12, blank=True, default="fr_FR")
    default_image = models.URLField(blank=True, default="")

    twitter_site = models.CharField(max_length=60, blank=True, default="")
    twitter_creator = models.CharField(max_length=60, blank=True, default="")
    facebook_app_id = models.CharField(max_length=50, blank=True, default="")

    gtm_id = models.CharField("GTM Container ID", max_length=32, blank=True, default="")
    ga4_id = models.CharField("GA4 Measurement ID", max_length=32, blank=True, default="")
    meta_pixel_id = models.CharField(max_length=32, blank=True, default="")
    tiktok_pixel_id = models.CharField(max_length=32, blank=True, default="")

    consent_cookie_name = models.CharField(max_length=64, blank=True, default="cookie_consent_marketing")

    robots_default = models.CharField(
        max_length=64, blank=True, default="index,follow",
        help_text="Valeur par défaut pour les pages publiques"
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Paramètres Marketing globaux"

    def __str__(self):
        return "Paramètres Marketing (globaux)"