"""Central SEO placeholders and routing helpers for marketing pages."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Tuple

# Namespaces that expose marketing routes. Keep aligned with project urls.
_MARKETING_NAMESPACES: Tuple[str, ...] = ("pages", "pages_ma", "pages_fr")


@dataclass(frozen=True)
class SeoPage:
    """Declarative SEO placeholder for a route.

    Attributes
    ----------
    key:
        Stable identifier used across sitemap/tests/allowlists.
    name:
        Human readable label (debug/logs only).
    slug:
        Short slug used in log output (defaults to key when omitted).
    route_names:
        Django route names that map to this page (namespaced).
    paths:
        Known absolute paths (starting with "/") resolved by this page.
    title:
        Placeholder <title> template (format with site_name before use).
    description:
        Placeholder meta description template.
    og_type:
        Default Open Graph type.
    twitter_card:
        Default Twitter Card value.
    image:
        Fallback OG/Twitter image (relative or absolute URL).
    robots:
        Robots directive to use in production (ex: "index,follow").
    changefreq:
        Optional sitemap hint.
    priority:
        Optional sitemap priority.
    sitemap_kwargs:
        kwargs passed to reverse() when building sitemap URLs.
    """

    key: str
    name: str
    route_names: Tuple[str, ...]
    paths: Tuple[str, ...]
    title: str
    description: str
    og_type: str = "website"
    twitter_card: str = "summary_large_image"
    image: str = "/static/img/og-default.png"
    robots: str = "index,follow"
    changefreq: str = "weekly"
    priority: float = 0.5
    sitemap_kwargs: Dict[str, str] | None = None

    @property
    def slug(self) -> str:
        return self.key


def _namespaced(route: str) -> Tuple[str, ...]:
    return tuple(f"{ns}:{route}" for ns in _MARKETING_NAMESPACES)


SEO_PAGE_CONFIG: Dict[str, SeoPage] = {
    "home": SeoPage(
        key="home",
        name="Accueil",
        route_names=_namespaced("home"),
        paths=("/", "/maroc/", "/france/"),
        title="{site_name} — Formation fabrication de bougies artisanales",
        description="Découvrez les programmes {site_name} et apprenez à créer des bougies artisanales à votre rythme.",
        priority=0.9,
    ),
    "contact": SeoPage(
        key="contact",
        name="Contact",
        route_names=_namespaced("contact"),
        paths=("/contact", "/contact/", "/maroc/contact", "/france/contact"),
        title="{site_name} — Contact",
        description="Contactez {site_name} pour toute question sur nos formations en ligne.",
        priority=0.7,
    ),
    "learn": SeoPage(
        key="learn",
        name="Parcours",
        route_names=_namespaced("learn"),
        paths=("/learn/", "/maroc/learn/", "/france/learn/"),
        title="{site_name} — Parcours d'apprentissage",
        description="Explorez les cours {site_name} pour progresser étape par étape dans la fabrication de bougies.",
        priority=0.7,
    ),
    "demo": SeoPage(
        key="demo",
        name="Démo",
        route_names=_namespaced("demo"),
        paths=("/demo/",),
        title="{site_name} — Démo vidéo",
        description="Découvrez un aperçu du contenu {site_name} avec notre démo vidéo offerte.",
        sitemap_kwargs={"course_slug": "bougies-naturelles"},
        priority=0.6,
    ),
    "login": SeoPage(
        key="login",
        name="Connexion",
        route_names=_namespaced("login"),
        paths=("/login/", "/maroc/login/", "/france/login/"),
        title="{site_name} — Connexion",
        description="Accédez à votre espace {site_name} pour reprendre vos cours.",
        robots="noindex,nofollow",
        priority=0.3,
    ),
    "faq": SeoPage(
        key="faq",
        name="FAQ",
        route_names=_namespaced("faq"),
        paths=("/faq/", "/maroc/faq/", "/france/faq/"),
        title="{site_name} — FAQ",
        description="Retrouvez les réponses aux questions fréquentes sur les formations {site_name}.",
        priority=0.5,
    ),
    "packs": SeoPage(
        key="packs",
        name="Packs",
        route_names=_namespaced("packs"),
        paths=("/packs", "/packs/", "/maroc/packs", "/france/packs"),
        title="{site_name} — Packs & offres",
        description="Choisissez le pack {site_name} adapté à votre projet de fabrication de bougies.",
        priority=0.6,
    ),
}

# Reverse index: route name/path -> page key.
PAGE_KEY_BY_ROUTE: Dict[str, str] = {}
PATH_TO_PAGE_KEY: Dict[str, str] = {}

for key, spec in SEO_PAGE_CONFIG.items():
    for route in spec.route_names:
        PAGE_KEY_BY_ROUTE[route] = key
    for path in spec.paths:
        PATH_TO_PAGE_KEY[path] = key


def get_page_key_from_route(route_name: str | None) -> str | None:
    if not route_name:
        return None
    return PAGE_KEY_BY_ROUTE.get(route_name)


def get_page_key_from_path(path: str | None) -> str | None:
    if not path:
        return None
    return PATH_TO_PAGE_KEY.get(path)


def sitemap_entries() -> Iterable[SeoPage]:
    desired_order = ("home", "contact", "learn", "demo", "login", "faq", "packs")
    for key in desired_order:
        spec = SEO_PAGE_CONFIG.get(key)
        if spec:
            yield spec


DEFAULT_NONPROD_ALLOWLIST = tuple(
    key for key, spec in SEO_PAGE_CONFIG.items() if spec.robots.startswith("index")
)
