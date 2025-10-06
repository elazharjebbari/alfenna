from __future__ import annotations

import logging
from http import HTTPStatus

from django.conf import settings
from django.http import FileResponse, Http404, HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET

from apps.billing.metrics import record_invoice_download
from apps.billing.models import Order
from apps.billing.services.invoice import get_invoice_service
from apps.messaging.exceptions import TokenExpiredError, TokenInvalidError
from apps.messaging.tokens import TokenService


log = logging.getLogger("billing.invoice")


def _normalize_email(value: str | None) -> str:
    return (value or "").strip().lower()


def _validate_order_claim(order: Order, claims: dict[str, object]) -> tuple[bool, str]:
    claim_order_id = claims.get("order_id")
    try:
        claim_order_id_int = int(claim_order_id)
    except (TypeError, ValueError):
        return False, "order_mismatch"
    if claim_order_id_int != order.id:
        return False, "order_mismatch"

    claim_email = _normalize_email(claims.get("email"))
    expected_email = _normalize_email(order.email)
    if expected_email and claim_email != expected_email:
        return False, "email_mismatch"
    if not expected_email:
        # Defensive stance: refuse if we cannot assert the recipient.
        return False, "missing_order_email"
    return True, ""


@require_GET
def invoice_download_view(request: HttpRequest, order_id: int) -> HttpResponse:
    if not getattr(settings, "INVOICING_ENABLED", False):
        raise Http404

    order = get_object_or_404(Order, pk=order_id)

    token = request.GET.get("t", "").strip()
    if not token:
        record_invoice_download("denied")
        log.info("billing.invoice.download_denied", extra={"order_id": order.id, "reason": "missing_token"})
        return HttpResponseBadRequest("Missing token")

    try:
        payload = TokenService.read_signed(
            token,
            namespace=getattr(settings, "BILLING_INVOICE_TOKEN_NAMESPACE", "billing"),
            purpose=getattr(settings, "BILLING_INVOICE_TOKEN_PURPOSE", "invoice_download"),
            ttl_seconds=getattr(settings, "BILLING_INVOICE_TOKEN_TTL", 60 * 60 * 24 * 14),
        )
    except TokenExpiredError:
        record_invoice_download("denied")
        log.info("billing.invoice.download_denied", extra={"order_id": order.id, "reason": "expired_token"})
        return HttpResponseBadRequest("Token expired")
    except TokenInvalidError:
        record_invoice_download("denied")
        log.info("billing.invoice.download_denied", extra={"order_id": order.id, "reason": "invalid_token"})
        return HttpResponseBadRequest("Invalid token")

    is_valid, reason = _validate_order_claim(order, payload.claims)
    if not is_valid:
        record_invoice_download("denied")
        log.info("billing.invoice.download_denied", extra={"order_id": order.id, "reason": reason})
        return HttpResponseBadRequest("Token mismatch")

    service = get_invoice_service()
    try:
        artifact = service.ensure_invoice_pdf(order)
    except Exception:
        record_invoice_download("denied")
        log.exception("billing.invoice.download_denied", extra={"order_id": order.id, "reason": "generation_failed"})
        return HttpResponse(status=HTTPStatus.INTERNAL_SERVER_ERROR)

    try:
        file_handle = service.storage.open(artifact.storage_path, "rb")
    except FileNotFoundError:
        record_invoice_download("denied")
        log.error(
            "billing.invoice.download_denied",
            extra={"order_id": order.id, "reason": "artifact_missing", "path": artifact.storage_path},
        )
        return HttpResponse(status=HTTPStatus.NOT_FOUND)

    filename = f"invoice-{order.reference or order.id}.pdf"
    response = FileResponse(file_handle, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    response["Cache-Control"] = "private, no-store, max-age=0"

    record_invoice_download("success")
    log.info("billing.invoice.download_success", extra={"order_id": order.id, "path": artifact.storage_path})
    return response
