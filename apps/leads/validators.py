import re

_email_re = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_phone_re = re.compile(r"^\+?[0-9 \-().]{6,}$")
_postal_re = re.compile(r"^[0-9A-Za-z \-]{2,10}$")

def is_valid_email(v: str) -> bool:
    return bool(v and _email_re.match(v))

def is_valid_phone(v: str) -> bool:
    return bool(v and _phone_re.match(v))

def is_valid_postal(v: str) -> bool:
    return bool(v and _postal_re.match(v))