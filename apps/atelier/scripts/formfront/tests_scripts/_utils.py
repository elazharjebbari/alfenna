import json, re, time
from django.conf import settings
from django.test import Client

RE_RUNTIME_TAG = re.compile(r'<script[^>]+src="[^"]*flowforms\.runtime\.js[^"]*"[^>]*>', re.I)
RE_SCRIPT_CONFIG = re.compile(r'<script[^>]*data-ff-config[^>]*>(?P<json>.*?)</script>', re.I | re.S)

def extract_ff_config(html: str):
    m = RE_SCRIPT_CONFIG.search(html)
    if not m: return None
    raw = m.group("json").strip()
    try:
        return json.loads(raw)
    except Exception:
        raw2 = re.sub(r'<!--.*?-->', '', raw, flags=re.S).replace("&quot;", '"')
        return json.loads(raw2)

def get_home_html():
    client = Client(enforce_csrf_checks=True)
    res = client.get("/", follow=True)
    return client, res.status_code, res.content.decode("utf-8", "ignore")

def count(selector: str, html: str) -> int:
    if selector == "ff-root": return len(re.findall(r'data-ff-root', html))
    if selector == "ff-step1": return len(re.findall(r'data-ff-step\s*=\s*"1"', html))
    if selector == "runtime": return 1 if RE_RUNTIME_TAG.search(html) else 0
    return 0

class FlagSwap:
    def __init__(self, name, value):
        self.name, self.value, self.prev = name, value, None
    def __enter__(self):
        self.prev = getattr(settings, self.name, None)
        setattr(settings, self.name, self.value)
    def __exit__(self, exc_type, exc, tb):
        setattr(settings, self.name, self.prev)
