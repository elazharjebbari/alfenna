"""
Teste validate_batch + persist_events directement (sans endpoint HTTP).
Exécution: python manage.py runscript analytics_ingest_smoke
"""
from datetime import datetime, timezone
from apps.atelier.analytics import ingest
from apps.common.runscript_harness import binary_harness

@binary_harness
def run():
    print("=== analytics_ingest_smoke ===")
    payload = {
        "request_id": "req-smoke-123",
        "consent": "Y",
        "events": [
            {"type": "cta_click", "ts": datetime.now(timezone.utc).isoformat(), "props": {"cta_id": "hero_primary"}},
            {"type": "video_play", "ts": datetime.now(timezone.utc).isoformat(), "props": {"video_id": "lp_intro_1"}},
            {"type": "scroll", "ts": datetime.now(timezone.utc).isoformat(), "props": {"depth": 90}},
        ],
    }
    try:
        ingest.validate_batch(payload)
        ingest.persist_events(payload["events"], payload["request_id"], payload["consent"])
        print("=> Analytics ingest OK ✅")
    except Exception as e:
        raise AssertionError(f"Ingest a échoué: {e}")