"""
URL configuration for alfenna project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.contrib import admin
from django.contrib.sitemaps import views as sitemap_views
from django.http import HttpResponseNotFound
from django.urls import include, path, re_path
from django.views.generic import RedirectView

from apps.marketing.static_views import (
    favicon_view,
    apple_touch_icon_view,
    browserconfig_view,
    manifest_view,
)

from apps.catalog.sitemaps import sitemaps as catalog_sitemaps
from apps.marketing.sitemaps import sitemaps as marketing_sitemaps  # NEW
from apps.marketing.views import robots_txt
from django.conf.urls.static import static


sitemaps = {}
sitemaps.update(catalog_sitemaps)
sitemaps.update(marketing_sitemaps)

urlpatterns = [
    path('admin/', admin.site.urls),
    # Root-level static conveniences for SEO/UA compatibility
    path('favicon.ico', favicon_view),
    path('apple-touch-icon.png', apple_touch_icon_view),
    path('site.webmanifest', manifest_view),
    path('browserconfig.xml', browserconfig_view),
    path(
        "password-reset/done/",
        RedirectView.as_view(pattern_name="accounts:password_reset_done", permanent=True),
    ),
    path(
        "password-reset/",
        RedirectView.as_view(pattern_name="accounts:password_reset", permanent=True),
    ),
    path(
        "mot-de-passe-oublie/definir/<uidb64>/<token>/",
        RedirectView.as_view(pattern_name="accounts:password_reset_confirm", permanent=True),
    ),
    # path('', include('OnlineLearning.urls')),
    path("accounts/", include("apps.accounts.urls", namespace="accounts")),

    # Lecture AVANT les routes catalog pour matcher les sous-chemins
    path('cours/', include(('apps.content.urls', 'content'), namespace='content')),
    # Catalogue (liste et détail)
    path('cours/', include(('apps.catalog.urls', 'catalog'), namespace='catalog')),

    path('sitemap.xml', sitemap_views.sitemap, {'sitemaps': sitemaps}, name='sitemap'),
    path('robots.txt', robots_txt, name='robots-txt'),
    path('billing/', include(('apps.billing.urls', 'billing'), namespace='billing')),
    path("learning/", include("apps.learning.urls", namespace="learning")),
    path("email/", include(("apps.messaging.urls", "messaging"), namespace="messaging")),
    path("api/leads/", include(("apps.leads.urls", "leads"), namespace="leads")),
    path("api/checkout/", include(("apps.checkout.urls", "checkout"), namespace="checkout")),
    path("api/analytics/", include(("apps.atelier.analytics.urls", "analytics"), namespace="analytics")),
    path("flows/", include(("apps.flowforms.urls", "flowforms"), namespace="flowforms")),
]

urlpatterns += [
    path("", include(("apps.pages.urls", "pages"), namespace="pages")),
]
def _chatbot_disabled_view(*args, **kwargs):
    return HttpResponseNotFound()


if settings.CHATBOT_ENABLED:
    urlpatterns.append(
        path("api/chat/", include(("apps.chatbot.urls", "chatbot"), namespace="chatbot")),
    )
else:
    urlpatterns.append(re_path(r"^api/chat/.*$", _chatbot_disabled_view))


# Static/media en dev
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += [
        path("", include(("apps.atelier.urls_shim", "shim")))  # expose register/login/etc.
    ]

if getattr(settings, "ENABLE_STATIC_DEBUG_VIEW", False):
    from apps.atelier.scripts.images import print_runtime_static

    urlpatterns += print_runtime_static.urlpatterns
