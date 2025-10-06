from django.test import RequestFactory
from apps.atelier.compose.pipeline import render_page
from apps.common.runscript_harness import binary_harness

@binary_harness
def run():
    rf = RequestFactory()
    req = rf.get("/")
    r1 = render_page(req, "online_home", content_rev="smoke")
    r2 = render_page(req, "online_home", content_rev="smoke")
    print("len1=", len(r1.get("fragments", {})), "len2=", len(r2.get("fragments", {})))