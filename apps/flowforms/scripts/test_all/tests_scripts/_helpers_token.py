import time, hmac, hashlib, json
from django.conf import settings

def make_signed_token(body: dict, *, age: int = 0) -> str:
    ts = int(time.time() - age)
    body_wo = {k: v for k, v in body.items() if k != "signed_token"}
    msg = hashlib.md5(json.dumps(body_wo, sort_keys=True).encode("utf-8")).hexdigest()
    mac = hmac.new(getattr(settings, "LEADS_SIGNING_SECRET", settings.SECRET_KEY).encode("utf-8"),
                   f"{ts}.{msg}".encode("utf-8"),
                   hashlib.sha256).hexdigest()
    return f"{ts}.{mac}"