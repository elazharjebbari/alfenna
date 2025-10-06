import hmac, time, hashlib
from django.conf import settings
from django.core.cache import cache

IDEM_NS = "leads:idem:"
RL_NS_IP = "leads:rl:ip:"
RL_NS_EMAIL = "leads:rl:email:"
DUP_NS = "leads:dup:"

def normalize_email(email: str | None) -> str:
    return (email or "").strip().lower()

# apps/leads/antispam.py
def idempotency_seen(kind: str, key: str, ttl: int = 3600) -> bool:
    """
    True  => déjà vu (rejeu)
    False => 1ère fois (clé enregistrée maintenant)
    Implémentation atomique via cache.add pour éviter les races.
    """
    if not key:
        return False
    ck = f"{IDEM_NS}{kind}:{key}"
    # add() renvoie True si la clé n'existait pas encore
    first_time = cache.add(ck, 1, ttl)
    return not first_time

def verify_signed_token(token: str | None, payload: str, max_age_s: int = 7200) -> bool:
    if not token:
        return False
    try:
        ts_str, sig = token.split(".", 1)
        ts = int(ts_str)
    except Exception:
        return False
    if abs(time.time() - ts) > max_age_s:
        return False
    mac = hmac.new(
        key=(getattr(settings, "LEADS_SIGNING_SECRET", settings.SECRET_KEY)).encode("utf-8"),
        msg=f"{ts}.{payload}".encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(mac, sig)

def dup_fingerprint(form_kind: str, email: str | None = None, phone: str | None = None,
                    course_slug: str | None = None) -> str:
    h = hashlib.md5()
    h.update((form_kind or "").encode())
    h.update((normalize_email(email)).encode())
    h.update((phone or "").encode())
    h.update((course_slug or "").encode())
    return h.hexdigest()

def dup_recent(form_kind: str, fp: str, ttl: int) -> bool:
    k = f"{DUP_NS}{form_kind}:{fp}"
    if cache.get(k):
        return True
    cache.set(k, 1, ttl)
    return False