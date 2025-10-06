from django.contrib.sitemaps import Sitemap
from django.utils import timezone
from apps.catalog.models.models import Course

class CourseSitemap(Sitemap):
    changefreq = 'weekly'
    priority = 0.7

    def items(self):
        return Course.objects.published()

    def lastmod(self, obj: Course):
        return obj.updated_at or obj.published_at or timezone.now()

sitemaps = {
    'courses': CourseSitemap(),
}