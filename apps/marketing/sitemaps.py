from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from django.utils import timezone

from .seo_data import sitemap_entries


class MarketingStaticSitemap(Sitemap):
    """Expose key marketing pages for search engines."""

    def items(self):
        return list(sitemap_entries())

    def location(self, item):
        target_name = next((name for name in item.route_names if name.startswith("pages:")), item.route_names[0])
        kwargs = item.sitemap_kwargs or {}
        return reverse(target_name, kwargs=kwargs)

    def changefreq(self, item):  # type: ignore[override]
        return getattr(item, "changefreq", "weekly")

    def priority(self, item):  # type: ignore[override]
        return getattr(item, "priority", 0.6)

    def lastmod(self, item):
        return timezone.now()


sitemaps = {
    "marketing-static": MarketingStaticSitemap(),
}
