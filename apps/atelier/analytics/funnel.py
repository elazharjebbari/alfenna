"""
Funnel serveur (placeholder).
Étape 1: signatures neutres.
"""

import logging
log = logging.getLogger("atelier.analytics")

def record_lp_view(request, page: str):
    rid = getattr(request, "request_id", "")
    seg = getattr(request, "_segments", None)
    log.info("lp_view page=%s rid=%s seg=%s", page, rid, getattr(seg, "__dict__", {}))

def record_checkout_start(request_id: str, amount, currency, extra=None) -> None:
    return

def record_purchase_success(request_id: str, session_id_hash: str, amount, currency, extra=None) -> None:
    return