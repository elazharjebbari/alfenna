from django.utils.functional import cached_property
from django.utils.html import strip_tags
from django.utils.safestring import mark_safe
from django.conf import settings
from meta.views import Meta

from .helpers import get_global_config, clean_canonical

class SeoViewMixin:
    """
    - Lit self.meta_* définis par la vue (title/description/type/image/url…)
    - Fait tomber sur des defaults si manquants (config marketing)
    - Expose `meta` (django-meta) et `seo_jsonld` dans le contexte
    """
    meta_title = None
    meta_description = None
    meta_image = None    # URL absolue de préférence
    meta_type = None     # og:type (ex: 'product', 'website'…)
    meta_url = None      # canonical absolu
    meta_twitter_card = None
    meta_robots = None

    seo_jsonld = None    # dict ou list de dicts (pas une string)

    @cached_property
    def _marketing_cfg(self) -> dict:
        return get_global_config()

    def dispatch(self, request, *args, **kwargs):
        self.request = request
        response = super().dispatch(request, *args, **kwargs)
        self._stash_seo_override(request)
        return response

    def _stash_seo_override(self, request):
        override = dict(getattr(request, "_seo_override", {}) or {})
        mapping = (
            ("title", getattr(self, "meta_title", None)),
            ("description", getattr(self, "meta_description", None)),
            ("image", getattr(self, "meta_image", None)),
            ("og_type", getattr(self, "meta_type", None)),
            ("url", getattr(self, "meta_url", None)),
            ("robots", getattr(self, "meta_robots", None)),
            ("twitter_card", getattr(self, "meta_twitter_card", None)),
        )
        updated = False
        for key, value in mapping:
            if value:
                override[key] = value
                updated = True
        if updated:
            request._seo_override = override
        return override

    def build_meta(self):
        request = getattr(self, "request", None)
        cfg = self._marketing_cfg

        title = (self.meta_title or cfg["meta_defaults"].get("title") or "").strip()
        description = strip_tags(self.meta_description or cfg["meta_defaults"].get("description") or "")
        image = self.meta_image or cfg["meta_defaults"].get("image") or ""
        object_type = self.meta_type or "website"
        url = self.meta_url or (clean_canonical(request) if request else "")

        return Meta(
            # title
            title=title,
            use_title_tag=True,
            # generic
            description=description,
            image=image or None,
            url=url or None,
            # og
            object_type=object_type,
            site_name=cfg["site_name"],
            # twitter
            twitter_site=cfg["meta_defaults"].get("twitter_site") or None,
            twitter_creator=cfg["meta_defaults"].get("twitter_creator") or None,
            twitter_card="summary_large_image",
            # facebook/app id
            og_app_id=cfg["meta_defaults"].get("og_app_id") or None,
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # 1) meta (django-meta)
        ctx["meta"] = self.build_meta()
        # 2) seo_jsonld (dict/list) => le template le sérialisera
        if self.seo_jsonld:
            ctx["seo_jsonld"] = self.seo_jsonld
        return ctx
