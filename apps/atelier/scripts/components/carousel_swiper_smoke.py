from apps.atelier.components.registry import get as get_component
from apps.common.runscript_harness import binary_harness


@binary_harness("carousel_swiper_smoke")
def run():
    comp = get_component('carousel_multi/multimedia', namespace='core')
    vendors = (comp.get('assets') or {}).get('vendors') or []
    assert any('swiper-bundle' in v for v in vendors), "Vendor Swiper manquant"
    assets_css = (comp.get('assets') or {}).get('css') or []
    assert any('static/components/carousel_multi/mc-carousel_multi.css' in p for p in assets_css)
    return {"ok": True, "logs": "registry OK + vendors OK"}
