# apps/flowforms/tests/test_stepper_realpage_e2e.py
import os
import io
import json
import time
import uuid
import pathlib
import traceback
from datetime import datetime

from django.test import override_settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.urls import resolve, Resolver404

from apps.leads.models import Lead, LeadSubmissionLog


PRODUCT_SLUG = "pack-cosmetique-naturel"
PRODUCT_URL = f"/fr/produits/{PRODUCT_SLUG}/"
PROGRESS_PATH = "/api/leads/progress/"
DEFAULT_COLLECT_PATH = "/api/leads/collect/"


def _mkdirp(path: pathlib.Path) -> pathlib.Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


class Reporter:
    """
    Collecte structurée de tout le run :
    - steps (chronologie, durée, notes)
    - requests/responses (headers, body, status)
    - console JS frontend, erreurs, screenshots
    - warnings vs. errors
    - dump final JSON + prints lisibles
    """
    def __init__(self, artifacts_dir: pathlib.Path):
        self.t0 = time.time()
        self.artifacts_dir = _mkdirp(artifacts_dir)
        self.screens_dir = _mkdirp(self.artifacts_dir / "screens")
        self.videos_dir = _mkdirp(self.artifacts_dir / "videos")
        self.data = {
            "meta": {
                "started_at": datetime.utcnow().isoformat() + "Z",
                "artifacts_dir": str(self.artifacts_dir),
            },
            "steps": [],
            "requests": [],
            "responses": [],
            "console": [],
            "warnings": [],
            "errors": [],
            "progress_calls": [],
            "config": {},
            "db": {},
        }

    # ---------- chronologie ----------
    def step(self, name: str):
        return _StepContext(self, name)

    # ---------- logs ----------
    def note(self, msg: str, **extra):
        self.data["steps"].append({
            "ts": time.time() - self.t0,
            "note": msg,
            **({"extra": extra} if extra else {}),
        })

    def warn(self, msg: str, **extra):
        self.data["warnings"].append({
            "ts": time.time() - self.t0,
            "warning": msg,
            **({"extra": extra} if extra else {}),
        })
        print(f"[WARN] {msg}")

    def error(self, msg: str, **extra):
        self.data["errors"].append({
            "ts": time.time() - self.t0,
            "error": msg,
            **({"extra": extra} if extra else {}),
        })
        print(f"[ERR ] {msg}")

    # ---------- console ----------
    def log_console(self, type_: str, text: str, args=None):
        item = {
            "ts": time.time() - self.t0,
            "type": type_,
            "text": text,
        }
        if args:
            item["args"] = args
        self.data["console"].append(item)

    # ---------- réseau ----------
    def log_request(self, req):
        try:
            entry = {
                "ts": time.time() - self.t0,
                "url": req.url,
                "method": req.method,
                "headers": dict(req.headers),
                "post_data": req.post_data or "",
            }
            self.data["requests"].append(entry)
            if PROGRESS_PATH in req.url and req.method == "POST":
                self.data["progress_calls"].append(entry)
        except Exception as e:
            self.warn("log_request failed", exc=str(e))

    def log_response(self, res, body_text=None):
        try:
            entry = {
                "ts": time.time() - self.t0,
                "url": res.url,
                "status": res.status,
                "ok": res.ok,
                "headers": dict(res.headers),
            }
            if body_text is None:
                try:
                    # On essaie JSON d'abord pour faciliter la lecture
                    entry["body_json"] = res.json()
                except Exception:
                    entry["body_text"] = res.text()
            else:
                entry["body_text"] = body_text
            self.data["responses"].append(entry)
        except Exception as e:
            self.warn("log_response failed", exc=str(e))

    # ---------- screenshots ----------
    def screenshot(self, page, label: str) -> str:
        fname = f"{int(time.time()*1000)}_{label}.png".replace(" ", "_")
        fpath = str(self.screens_dir / fname)
        try:
            page.screenshot(path=fpath, full_page=True)
            self.note("screenshot", file=fpath)
        except Exception as e:
            self.warn("screenshot failed", label=label, exc=str(e))
        return fpath

    # ---------- dump final ----------
    def finalize(self):
        self.data["meta"]["finished_at"] = datetime.utcnow().isoformat() + "Z"
        self.data["meta"]["duration_sec"] = round(time.time() - self.t0, 3)
        out = self.artifacts_dir / "report.json"
        out.write_text(json.dumps(self.data, ensure_ascii=False, indent=2))
        # résumé console
        print("\n" + "=" * 72)
        print("RAPPORT E2E — Résumé")
        print("=" * 72)
        print(f"Artifacts: {self.artifacts_dir}")
        print(f"- Steps:     {len(self.data['steps'])}")
        print(f"- Requests:  {len(self.data['requests'])} (progress: {len(self.data['progress_calls'])})")
        print(f"- Responses: {len(self.data['responses'])}")
        print(f"- Console:   {len(self.data['console'])}")
        print(f"- Warnings:  {len(self.data['warnings'])}")
        print(f"- Errors:    {len(self.data['errors'])}")
        print("- DB:", json.dumps(self.data.get("db", {}), ensure_ascii=False))
        print("Rapport JSON →", out)
        print("=" * 72 + "\n")


class _StepContext:
    def __init__(self, rep: Reporter, name: str):
        self.rep = rep
        self.name = name
        self.t0 = None

    def __enter__(self):
        self.t0 = time.time()
        self.rep.note(f"BEGIN {self.name}")
        return self

    def __exit__(self, typ, value, tb):
        dt = round(time.time() - self.t0, 3)
        self.rep.note(f"END   {self.name}", duration_sec=dt)
        if typ:
            buf = "".join(traceback.format_exception(typ, value, tb))
            self.rep.error(f"Exception in step '{self.name}'", traceback=buf)
        # ne supprime pas l’exception: laisser pytest/django la gérer si nécessaire
        return False


@override_settings(ALLOWED_HOSTS=["*"])
class StepperRealPageE2ETest(StaticLiveServerTestCase):
    host = "127.0.0.1"

    def setUp(self):
        try:
            resolve(PRODUCT_URL)
        except Resolver404:
            self.skipTest(f"Route {PRODUCT_URL} introuvable (vérifie urls/i18n_patterns).")

    # -------- helpers --------
    def _artifacts_dir(self) -> pathlib.Path:
        base = pathlib.Path.cwd() / "artifacts" / "flowforms_e2e"
        uid = datetime.utcnow().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
        return _mkdirp(base / uid)

    def _wait_runtime_ready(self, page, rep: Reporter):
        # root
        page.wait_for_selector('form[data-ff-root]', timeout=15000)
        rep.note("form[data-ff-root] OK")
        # JSON config attaché (non visible)
        page.wait_for_selector('script[data-ff-config]', state="attached", timeout=10000)
        rep.note("script[data-ff-config] attached")
        # runtime prêt: fetch + bouton next
        page.wait_for_function(
            "() => !!window.fetch && !!document.querySelector('[data-ff-step] [data-ff-next]')",
            timeout=15000
        )
        rep.note("runtime ready (fetch + [data-ff-next])")

    def test_stepper_realpage_end_to_end(self):
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

        email = f"e2e.real+{uuid.uuid4().hex[:6]}@example.com"
        headless = os.environ.get("HEADLESS", "1") not in ("0", "false", "False")
        want_video = os.environ.get("VIDEO", "0") in ("1", "true", "True")

        rep = Reporter(self._artifacts_dir())
        rep.note("ENV", HEADLESS=headless, VIDEO=want_video, PRODUCT_URL=PRODUCT_URL, email=email)

        # ----------- PHASE 1: navigateur (aucun ORM ici) -----------
        with sync_playwright() as pw:
            launch_kw = {"headless": headless}
            if want_video:
                # enregistre la vidéo du run (par contexte)
                launch_kw["headless"] = True  # Playwright exige souvent headless pour la vidéo fiable en CI
            browser = pw.chromium.launch(**launch_kw)
            ctx_kw = {}
            if want_video:
                ctx_kw["record_video_dir"] = str(rep.videos_dir)
            ctx = browser.new_context(**ctx_kw)
            page = ctx.new_page()

            # Console front → reporter
            def _on_console(msg):
                try:
                    rep.log_console(msg.type, msg.text, [a.json_value() for a in msg.args] if msg.args else None)
                except Exception:
                    rep.log_console(msg.type, msg.text)
            page.on("console", _on_console)

            # Requests/responses → reporter
            page.on("request", rep.log_request)
            page.on("response", rep.log_response)

            # Intercepter progress pour dupliquer headers + body
            def capture(route):
                req = route.request
                if PROGRESS_PATH in req.url and req.method == "POST":
                    try:
                        rep.note("capture progress", url=req.url, headers=dict(req.headers))
                        rep.data["progress_calls"].append({
                            "ts": time.time() - rep.t0,
                            "url": req.url,
                            "headers": dict(req.headers),
                            "post_data": req.post_data or "",
                        })
                    except Exception as e:
                        rep.warn("capture progress failed", exc=str(e))
                route.continue_()
            page.route(f"**{PROGRESS_PATH}**", capture)

            with rep.step("NAVIGATE product page"):
                page.goto(self.live_server_url + PRODUCT_URL, wait_until="networkidle")
                rep.screenshot(page, "01_landing")
                self._wait_runtime_ready(page, rep)

            with rep.step("READ ff-config"):
                ffconf_text = page.eval_on_selector(
                    "script[data-ff-config]", "el => el && el.textContent || ''"
                ) or "{}"
                try:
                    ffconf = json.loads(ffconf_text)
                except Exception:
                    rep.error("ff-config illisible (JSON)")
                    ffconf = {}
                rep.data["config"] = ffconf
                endpoint_url = ffconf.get("endpoint_url") or DEFAULT_COLLECT_PATH
                steps_cfg = (ffconf.get("progress_steps") or {})
                fields_map = ffconf.get("fields_map") or {}
                rep.note("ff-config parsed", endpoint=endpoint_url, steps=list(steps_cfg.keys()))
                # Sanity config — pack_slug doit être tracké au step2
                step2 = [*steps_cfg.get("step2", [])]
                if not any("pack_slug" in s for s in step2):
                    rep.warn("progress_steps.step2 ne contient pas pack_slug", step2=step2)

            # ----- STEP 1 — remplissage tolérant (ID ou name)
            def fill(primary, fallback, val, label):
                try:
                    page.locator(primary).wait_for(state="visible", timeout=1200)
                    page.fill(primary, val)
                    rep.note("fill OK", field=label, selector=primary, value=val)
                except PWTimeout:
                    page.fill(fallback, val)
                    rep.note("fill OK (fallback)", field=label, selector=fallback, value=val)
                except Exception as e:
                    rep.warn("fill failed", field=label, primary=primary, fallback=fallback, exc=str(e))

            with rep.step("STEP1 fill & next"):
                fill("#ff-fullname", 'input[name="full_name"]', "E2E User", "fullname")
                fill("#ff-phone", 'input[name="phone"]', "0612345678", "phone")
                fill("#ff-email-step1", 'input[name="email"]', email, "email")
                fill("#ff-address-line1", 'input[name="address_line1"]', "Rue 123", "address_line1")
                fill("#ff-city", 'input[name="city"]', "Casablanca", "city")
                fill("#ff-postal", 'input[name="postal_code"]', "20000", "postal_code")
                try:
                    page.select_option("#ff-country", "MA")
                    rep.note("select country", value="MA")
                except Exception:
                    rep.warn("select country failed")

                with page.expect_response(lambda r: r.url.endswith(PROGRESS_PATH) and r.request.method == "POST") as resp1:
                    page.click('[data-ff-step="1"] [data-ff-next]')
                rep.screenshot(page, "02_after_step1")
                r1 = resp1.value
                # Log la réponse brute pour diagnostic
                rep.log_response(r1)

                if not r1.ok:
                    rep.error("progress step1 HTTP error", status=r1.status, url=r1.url)
                else:
                    # 200 OK → parse body pour voir les erreurs back éventuelles
                    try:
                        j = r1.json()
                        if j.get("errors"):
                            rep.warn("progress step1 returned errors", errors=j["errors"])
                    except Exception:
                        pass

            # ----- STEP 2 — DUO + bump + ffSyncPackFields
            with rep.step("STEP2 pick pack & next"):
                page.wait_for_selector('[data-ff-step="2"]:not(.d-none)', timeout=10000)
                # Forcer la sync du pack juste avant collecte
                try:
                    page.evaluate("() => { if (window.ffSyncPackFields) window.ffSyncPackFields(); }")
                    rep.note("ffSyncPackFields invoked")
                except Exception as e:
                    rep.warn("ffSyncPackFields failed", exc=str(e))

                # Choisir DUO si présent, sinon le premier
                chosen_pack = "duo"
                try:
                    page.click('label.af-card-radio[data-id="duo"]', force=True)
                    rep.note("pack chosen", code="duo")
                except Exception:
                    page.click('label.af-card-radio', force=True)
                    chosen_pack = page.eval_on_selector('label.af-card-radio input[type="radio"]', "el => el && el.value || ''") or "unknown"
                    rep.note("pack chosen (fallback first)", code=chosen_pack)

                # Bump (si disponible)
                try:
                    page.check("#af-bump-optin", force=True)
                    rep.note("bump checked")
                except Exception:
                    rep.note("bump not present or unchecked")

                # Vérifie le hidden pack_slug rempli par le front
                try:
                    hidden_pack = page.eval_on_selector('[data-ff-pack-slug]', "el => el && el.value || ''")
                    rep.note("hidden pack_slug", value=hidden_pack)
                except Exception:
                    rep.warn("cannot read hidden pack_slug")

                # POST progress step2
                with page.expect_response(lambda r: r.url.endswith(PROGRESS_PATH) and r.request.method == "POST") as resp2:
                    page.click('[data-ff-step="2"] [data-ff-next]')
                rep.screenshot(page, "03_after_step2")
                r2 = resp2.value
                rep.log_response(r2)

                # Vérifie la présence du header X-Idempotency-Key sur la dernière capture
                if rep.data["progress_calls"]:
                    last = rep.data["progress_calls"][-1]
                    headers = {k.lower(): v for k, v in (last.get("headers") or {}).items()}
                    if "x-idempotency-key" not in headers:
                        rep.warn("X-Idempotency-Key manquant sur progress step2")
                    else:
                        rep.note("Idempotency header OK", key=headers.get("x-idempotency-key"))

                    # Vérifie que pack_slug est dans le payload
                    if '"pack_slug"' not in (last.get("post_data") or ""):
                        rep.warn("progress step2 payload sans pack_slug", body=last.get("post_data") or "")

                if not r2.ok:
                    rep.error("progress step2 HTTP error", status=r2.status, url=r2.url)
                else:
                    try:
                        j2 = r2.json()
                        if j2.get("errors"):
                            rep.warn("progress step2 returned errors", errors=j2["errors"])
                    except Exception:
                        pass

            # ----- STEP 3 — COD + accept_terms + submit
            with rep.step("STEP3 pay&submit"):
                page.wait_for_selector('[data-ff-step="3"]:not(.d-none)', timeout=10000)
                try:
                    page.click('section[data-ff-step="3"] label.af-pay-option:not(.is-online)')
                    rep.note("payment selected", mode="cod")
                except Exception:
                    rep.note("payment default remains")

                try:
                    page.check('input[name="accept_terms"]', force=True)
                    rep.note("accept_terms checked")
                except Exception:
                    rep.note("accept_terms absent or already checked")

                try:
                    page.fill("#ff-email", email)
                except Exception:
                    pass

                # Attendre la REPONSE de submit (XHR), pas une navigation
                endpoint_url = rep.data["config"].get("endpoint_url") or DEFAULT_COLLECT_PATH
                with page.expect_response(lambda r: r.url.endswith(endpoint_url) and r.request.method == "POST") as resp_submit:
                    page.click('[data-ff-step="3"] [data-ff-submit]')
                rep.screenshot(page, "04_after_submit")
                rs = resp_submit.value
                rep.log_response(rs)

                # Puis l’apparition de la step 4
                try:
                    page.wait_for_selector('[data-ff-step="4"][data-thank-you]:not(.d-none)', timeout=10000)
                    rep.note("thank-you visible")
                    rep.screenshot(page, "05_thank_you")
                except Exception as e:
                    rep.warn("thank-you not visible", exc=str(e))

                if not rs.ok:
                    rep.error("collect HTTP error", status=rs.status, url=rs.url)
                    try:
                        rep.error("collect body", body=rs.text())
                    except Exception:
                        pass

            # Fermer le contexte Playwright
            ctx.close()
            browser.close()

        # ----------- PHASE 2: assertions DB (hors boucle async) -----------
        with rep.step("DB assertions"):
            lead = Lead.objects.filter(form_kind="checkout_intent", email=email).order_by("-id").first()
            if not lead:
                rep.error("Lead non trouvé en DB après step2", email=email)
                self.fail("Lead non créé après step2")

            rep.data["db"]["lead_id"] = lead.id
            rep.data["db"]["pack_slug"] = getattr(lead, "pack_slug", "")
            rep.data["db"]["context"] = lead.context or {}
            if rep.data["db"]["pack_slug"] != "duo":
                rep.warn("pack_slug DB != 'duo'", found=rep.data["db"]["pack_slug"])

            comp = (lead.context or {}).get("complementary_slugs", [])
            rep.data["db"]["complementary_slugs"] = comp
            if not comp:
                rep.note("complementary_slugs vide (OK si bump désactivé sur cette page)")

            log = LeadSubmissionLog.objects.filter(lead=lead, flow_key="checkout_intent_flow").order_by("-created_at").first()
            if log:
                payload = log.payload or {}
                rep.data["db"]["final_payload"] = payload
                if not (payload.get("pack_slug") == "duo" or payload.get("offer_key") == "duo"):
                    rep.warn("Snapshot final sans pack 'duo'", payload=payload)
            else:
                rep.warn("Aucun LeadSubmissionLog trouvé")

        # ---------- rapport final ----------
        rep.finalize()

        # Assertions dures minimales (le reste est en warnings détaillés)
        self.assertIsNotNone(rep.data["db"].get("lead_id"), "Lead non créé")
        # On exige au moins 2 progress calls (step1 + step2)
        self.assertGreaterEqual(len(rep.data["progress_calls"]), 2, "Progress calls insuffisants (step1/step2)")
