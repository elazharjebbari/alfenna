# apps/atelier/compose/hydrators/checkout/hydrators.py
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Optional

from django.conf import settings
from django.http import HttpRequest
from django.utils.translation import gettext as _

from apps.billing.models import Order
from apps.billing.services import PaymentService, PriceService
from apps.marketing.models.models_pricing import PricePlan, PriceFeature


def _country_from_request(request: HttpRequest) -> Optional[str]:
    return (request.GET.get("country") or "").upper() or None


def _resolve_plan(params: dict, request: HttpRequest) -> PricePlan:
    plan = params.get("price_plan")
    if isinstance(plan, PricePlan):
        return plan

    plan_slug = params.get("plan_slug") or params.get("price_plan_slug")
    resolver = getattr(request, "resolver_match", None)
    if not plan_slug and resolver and resolver.kwargs:
        plan_slug = resolver.kwargs.get("plan_slug")
    if plan_slug:
        plan = PricePlan.objects.filter(slug=plan_slug, is_active=True).first()
        if plan:
            return plan

    plan = getattr(request, "_price_plan", None)
    if isinstance(plan, PricePlan):
        return plan

    raise ValueError("Aucun PricePlan disponible pour hydrater le checkout")


def _get_plan_and_currency(request: HttpRequest, params: dict) -> tuple[PricePlan, str]:
    plan = _resolve_plan(params, request)
    currency = PriceService.select_currency(params.get("currency") or request.GET.get("currency"))
    return plan, currency


def _format_amount(cents: int) -> Decimal:
    return (Decimal(cents) / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _format_price_display(cents: int, currency: str) -> str:
    return f"{_format_amount(max(cents, 0))} {currency}"


def _int_or_none(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _decimal_or_default(value: Any, default: Decimal = Decimal("0.00")) -> Decimal:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (TypeError, ValueError, ArithmeticError):
        return default


def _format_percent(percent: Decimal) -> str:
    pct = percent.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    pct_str = f"{pct}"
    if pct_str.endswith(".0"):
        pct_str = pct_str[:-2]
    return f"{pct_str}%"


def _daily_amount_display(amount_cents: int, currency: str) -> str:
    daily_amount = (Decimal(amount_cents) / Decimal("100")) / Decimal("365")
    rounded = daily_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    rounded_str = f"{rounded:.2f}"
    return _("≈{amount} {currency} / jour").format(amount=rounded_str, currency=currency)


def _plan_features(plan: PricePlan) -> list[str]:
    qs = PriceFeature.objects.filter(plan=plan, included=True).order_by("sort_order")
    features = [feat.label for feat in qs]
    if features:
        return features
    return [
        "Accès à vie aux vidéos",
        "Support de démarrage",
        "Guide PDF et ressources",
        "Communauté privée",
    ]


def hydrate_order_summary(request: HttpRequest, params: dict) -> Dict[str, Any]:
    plan, currency = _get_plan_and_currency(request, params)

    amount_total_param = _int_or_none(params.get("amount_total_cents"))
    list_price_param = _int_or_none(params.get("list_price_cents"))
    discount_pct_param = _decimal_or_default(params.get("discount_pct"), Decimal("0.00"))
    tax_amount_param = _int_or_none(params.get("tax_amount_cents")) or 0

    if amount_total_param is None:
        totals = PriceService.compute_total_from_plan(plan, currency)
        amount_total_cents = totals.get("amount_total", totals.get("final_amount_cents", 0))
        list_price_cents = totals.get("list_price_cents") or amount_total_cents
        discount_pct = totals.get("discount_pct", Decimal("0.00"))
        tax_amount_cents = totals.get("tax_amount", 0)
    else:
        amount_total_cents = amount_total_param
        list_price_cents = list_price_param or getattr(plan, "old_price_cents", None) or amount_total_cents
        discount_pct = discount_pct_param
        tax_amount_cents = tax_amount_param

    amount_total_cents = max(int(amount_total_cents or 0), 0)
    list_price_cents = max(int(list_price_cents or amount_total_cents), 0)
    tax_amount_cents = max(int(tax_amount_cents or 0), 0)

    savings_cents = max(list_price_cents - amount_total_cents, 0)
    if savings_cents and not discount_pct:
        discount_pct = (Decimal(savings_cents) / Decimal(list_price_cents) * Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    show_economy = bool(params.get("show_economy", True)) and savings_cents > 0
    show_daily = bool(params.get("show_daily_approx", True)) and amount_total_cents > 0

    features = _plan_features(plan)
    primary_limit_val = params.get("features_primary_limit", 5)
    try:
        primary_limit = max(int(primary_limit_val), 1)
    except (TypeError, ValueError):
        primary_limit = 5
    primary_features = features[:primary_limit]
    extra_features = features[primary_limit:]

    social_proof_text = params.get("social_proof_text") or _("★ 4,8/5 — 500+ avis")
    guarantee_text = params.get("guarantee_text") or _("Garantie satisfaite ou remboursée 14 jours")
    more_label = params.get("features_more_label") or _("Voir tout le contenu")

    order_bump = params.get("order_bump") or {}
    if not isinstance(order_bump, dict) or not order_bump.get("title"):
        order_bump = None

    current_price_display = _format_price_display(amount_total_cents, currency)
    old_price_display = _format_price_display(list_price_cents, currency) if list_price_cents > amount_total_cents else None
    savings_display = _format_price_display(savings_cents, currency)
    savings_percent_display = _format_percent(discount_pct) if show_economy else ""
    daily_display = _daily_amount_display(amount_total_cents, currency) if show_daily else ""

    country_value = _country_from_request(request) or ""

    return {
        "heading": params.get("heading") or _("Votre offre"),
        "title": plan.title,
        "plan_title": plan.title,
        "plan_badge": getattr(plan, "ribbon_label", ""),
        "currency": currency,
        "country": country_value,
        "amount_cents": amount_total_cents,
        "display_price": current_price_display,
        "list_price_cents": list_price_cents,
        "list_price_display": old_price_display,
        "benefits": features,
        "primary_features": primary_features,
        "extra_features": extra_features,
        "has_extra_features": bool(extra_features),
        "features_more_label": more_label,
        "show_economy": show_economy,
        "savings_display": savings_display,
        "savings_percent_display": savings_percent_display,
        "show_daily": show_daily,
        "daily_display": daily_display,
        "social_proof_text": social_proof_text,
        "guarantee_text": guarantee_text,
        "tax_amount_cents": tax_amount_cents,
        "tax_amount_display": _format_price_display(tax_amount_cents, currency) if tax_amount_cents else "",
        "order_bump": order_bump,
        "discount_pct": str(discount_pct),
        "plan_slug": plan.slug,
    }


def _bool_from_param(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def hydrate_payment_form(request: HttpRequest, params: dict) -> Dict[str, Any]:
    plan, currency = _get_plan_and_currency(request, params)
    totals = PriceService.compute_total_from_plan(plan, currency)
    publishable_key = settings.STRIPE_PUBLISHABLE_KEY

    client_secret = None
    order_id = None
    course = getattr(request, "_checkout_course", None)

    user = getattr(request, "user", None)
    if user and getattr(user, "is_authenticated", False):
        order, payload = PaymentService.create_or_update_order_and_intent(
            user=request.user,
            email=(request.user.email or ""),
            price_plan=plan,
            currency=currency,
            course=course,
        )
        client_secret = payload.get("client_secret")
        order_id = order.id

    return {
        "stripe_publishable_key": publishable_key,
        "client_secret": client_secret,
        "order_id": order_id,
        "plan_id": plan.id,
        "plan_slug": plan.slug,
        "plan_title": plan.title,
        "course_id": getattr(course, "id", None),
        "course_slug": getattr(course, "slug", ""),
        "currency": totals["currency"],
        "amount_cents": totals["final_amount_cents"],
        "amount_total": _format_amount(totals["final_amount_cents"]),
        "amount_total_display": f"{_format_amount(totals['final_amount_cents'])} {totals['currency']}",
        "show_coupon_link": _bool_from_param(params.get("show_coupon_link"), True),
        "coupon_label": params.get("coupon_label") or _("Code promo"),
        "coupon_placeholder": params.get("coupon_placeholder") or _("ENTRERMONCODE"),
        "submit_state": False,
        "cta_label": params.get("cta_label") or _("Payer et accéder maintenant"),
        "login_url_name": settings.LOGIN_URL,
    }


def hydrate_express_buttons(request: HttpRequest, params: dict) -> Dict[str, Any]:
    _, currency = _get_plan_and_currency(request, params)
    currency_upper = currency.upper()
    show_payment_request = _bool_from_param(params.get("show_payment_request"), True) and currency_upper not in {"MAD"}

    providers = []
    providers_param = params.get("providers") or []
    if isinstance(providers_param, dict):
        providers_param = [providers_param]
    if not providers_param:
        providers_param = [
            {"id": "apple_pay", "label": "Apple Pay"},
            {"id": "google_pay", "label": "Google Pay"},
            {"id": "stripe_link", "label": "Stripe Link"},
        ]

    for provider in providers_param:
        if not isinstance(provider, dict):
            continue
        label = provider.get("label") or provider.get("name")
        if not label:
            continue
        providers.append(
            {
                "id": provider.get("id") or label.lower().replace(" ", "_"),
                "label": label,
                "cta": provider.get("cta") or _("Payer avec {provider} — accès immédiat").format(provider=label),
                "icon": provider.get("icon", ""),
            }
        )

    return {
        "show_payment_request": show_payment_request,
        "providers": providers if show_payment_request else [],
        "headline": params.get("headline") or _("Payer en un tap"),
        "helper": params.get("helper") or _("Choisissez votre portefeuille préféré et accédez instantanément."),
    }


def hydrate_legal_info(request: HttpRequest, params: dict) -> Dict[str, Any]:
    try:
        _plan_obj, currency = _get_plan_and_currency(request, params)
    except Exception:  # plan optionnel pour le bloc légal
        currency = (params.get("currency") or request.GET.get("currency") or "EUR").upper()

    def _points() -> list[dict[str, str]]:
        raw_points = params.get("compact_points") or []
        if not raw_points:
            raw_points.extend(
                [
                    {"icon": "lock", "text": _("Paiement 100% sécurisé via Stripe (TLS/HTTPS)")},
                    {"icon": "rotate-left", "text": _("Garantie satisfait ou remboursé 14 jours, sans justificatif")},
                    {"icon": "bolt", "text": _("Accès immédiat à l’espace d’apprentissage après validation")},
                ]
            )
        normalized: list[dict[str, str]] = []
        for item in raw_points:
            if isinstance(item, str):
                normalized.append({"icon": "dot", "text": item})
                continue
            if isinstance(item, dict):
                text = item.get("text") or item.get("label")
                if not text:
                    continue
                normalized.append({"icon": (item.get("icon") or "dot"), "text": text})
        return normalized

    def _faq_items() -> list[dict[str, str]]:
        defaults = [
            {
                "question": _("Et si je n’ai pas de matériel ?"),
                "answer": _("Pas d’inquiétude : nous listons le nécessaire et les alternatives maison dans le module 1."),
                "href": "#programme",
            },
            {
                "question": _("Combien de temps ça prend ?"),
                "answer": _("Comptez 2 heures pour votre première bougie, puis 7 jours pour devenir autonome."),
                "href": "#planning",
            },
            {
                "question": _("Et si je change d’avis ?"),
                "answer": _("Vous êtes remboursé·e sous 14 jours sur simple demande depuis votre espace membre."),
                "href": "/cgv/",
            },
        ]
        raw_faq = params.get("faq_items") or defaults
        normalized: list[dict[str, str]] = []
        for item in raw_faq:
            if not isinstance(item, dict):
                continue
            question = (item.get("question") or "").strip()
            answer = (item.get("answer") or "").strip()
            if not question or not answer:
                continue
            normalized.append(
                {
                    "question": question,
                    "answer": answer,
                    "href": item.get("href") or item.get("cta_href") or "",
                }
            )
        return normalized

    compact = _bool_from_param(params.get("compact"), True)

    legal_links = params.get("legal_links") or [
        {"label": _("Conditions générales de vente"), "href": "/cgv/"},
        {"label": _("Politique de confidentialité"), "href": "/confidentialite/"},
        {"label": _("Politique de remboursement"), "href": "/cgv/#remboursement"},
    ]

    price_notice = params.get("price_notice") or _("Montant TTC — devise : {currency}").format(currency=currency)

    return {
        "security_badges": _bool_from_param(params.get("security_badges"), True),
        "legal_links": legal_links,
        "compact": compact,
        "compact_points": _points(),
        "price_notice": price_notice,
        "faq_heading": params.get("faq_heading") or _("Questions fréquentes"),
        "faq_items": _faq_items(),
    }


def _fmt_and_merge(texts, mapping):
    out = []
    for t in (texts or []):
        try:
            out.append(t.format(**mapping))
        except Exception:
            out.append(t)
    return out


def hydrate_thank_you_message(request: HttpRequest, params: dict) -> Dict[str, Any]:
    """Construit le message 'Merci' à partir des params (pages.yml) + contexte runtime."""
    plan = params.get("price_plan")
    if not isinstance(plan, PricePlan):
        plan = getattr(request, "_price_plan", None)
    plan_title = getattr(plan, "title", "") or ""

    order_id = (request.GET.get("order") or "").strip()
    order_email = ""
    if order_id.isdigit():
        order_email = (
            Order.objects.filter(id=int(order_id))
            .values_list("email", flat=True)
            .first()
            or ""
        )

    user_email = getattr(getattr(request, "user", None), "email", "") or ""
    email = order_email or user_email

    mapping = {
        "plan_title": plan_title,
        "email": email or "votre e-mail",
        "order_id": order_id or "",
    }

    title = params.get("title") or "Paiement confirmé — merci 🙌"
    paragraphs = params.get("paragraphs") or [
        "Votre paiement pour <strong>{plan_title}</strong> a bien été reçu.",
        "Un e-mail de confirmation sera envoyé à <strong>{email}</strong>.",
    ]
    info_box = params.get("info_box") or {
        "title": "Et maintenant ?",
        "paragraphs": [
            "Vous recevrez les prochaines étapes par e-mail.",
            "Contactez-nous en cas de besoin — nous répondons rapidement.",
        ],
    }
    contact_email = params.get("contact_email") or "support@lumiereacademy.com"

    return {
        "title": title.format(**mapping),
        "paragraphs": _fmt_and_merge(paragraphs, mapping),
        "info_box": {
            "title": (info_box.get("title") or "").format(**mapping),
            "paragraphs": _fmt_and_merge(info_box.get("paragraphs") or [], mapping),
        },
        "contact_email": contact_email,
        "show_go_to_course": bool(params.get("show_go_to_course", False)),
        "course_url": params.get("course_url") or "",
    }
