"""Playwright E2E tests for analytics.js consent gating."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv
from playwright.sync_api import Browser, BrowserContext, Page, expect

# Load environment variables defined in project .env
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

BASE_URL = os.getenv("E2E_BASE_URL", "http://127.0.0.1:8000")
CONSENT_COOKIE_NAME = os.getenv("CONSENT_COOKIE_NAME", "cookie_consent_marketing")
CONSENT_TRUE_VALUE = os.getenv("CONSENT_TRUE_VALUE", "accept")
HAR_DIR = Path("har")
VIDEO_DIR = Path("videos")


@pytest.fixture(scope="session")
def browser_type_launch_args():
    """Force headed mode to ease debugging (opens real browser window)."""
    return {"headless": False}


@pytest.fixture(scope="session")
def browser_type_launch_args():
    """Force headed Chromium to ease debugging."""
    return {"headless": False}


@pytest.fixture(scope="session", autouse=True)
def ensure_artifact_dirs() -> None:
    """Ensure directories for HAR and video outputs exist before tests run."""
    HAR_DIR.mkdir(parents=True, exist_ok=True)
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)


@pytest.fixture
def context(browser: Browser, request: pytest.FixtureRequest) -> BrowserContext:
    """Create a browser context recording HAR and video, with network hooks."""
    har_path = HAR_DIR / f"{request.node.name}.har"
    network_events: list[str] = []

    context = browser.new_context(
        base_url=BASE_URL,
        record_video_dir=str(VIDEO_DIR),
        record_har_path=str(har_path),
        record_har_content="embed",
    )

    context.add_init_script(
        """
        (function () {
          const beaconCalls = [];
          const fetchCalls = [];
          Object.defineProperty(window, '__collectBeaconCalls__', { value: beaconCalls, writable: false });
          Object.defineProperty(window, '__collectFetchCalls__', { value: fetchCalls, writable: false });

          if (navigator.sendBeacon) {
            const originalBeacon = navigator.sendBeacon.bind(navigator);
            navigator.sendBeacon = function(url, data) {
              beaconCalls.push({ url: url, data: data });
              try {
                return originalBeacon(url, data);
              } catch (err) {
                return false;
              }
            };
          }

          if (window.fetch) {
            const originalFetch = window.fetch.bind(window);
            window.fetch = function(input, init) {
              const url = typeof input === 'string' ? input : (input && input.url) || '';
              if (url.includes('/api/analytics/collect')) {
                fetchCalls.push({ url: url, init: init });
              }
              return originalFetch(input, init);
            };
          }
        })();
        """
    )

    context.on("response", lambda response: network_events.append(f"{response.status} {response.url}"))

    yield context

    print("\n[E2E] Network responses during test:")
    for line in network_events:
        print(f"[E2E]   {line}")
    context.close()


@pytest.fixture
def page(context: BrowserContext, request: pytest.FixtureRequest) -> Page:
    """Create a new page and capture console errors for diagnostics."""
    page = context.new_page()
    page_errors: list[str] = []
    page_console: list[str] = []
    page.on("pageerror", lambda exc: page_errors.append(str(exc)))
    page.on("console", lambda msg: page_console.append(f"{msg.type.upper()}: {msg.text}"))

    yield page

    if page_errors:
        print("\n[E2E] Page errors:")
        for err in page_errors:
            print(f"[E2E]   {err}")
        pytest.fail("Unexpected browser errors; see log above.")

    if page_console:
        print("\n[E2E] Page console log:")
        for line in page_console:
            print(f"[E2E]   {line}")
    page.close()


def _set_consent(context: BrowserContext, enabled: bool) -> None:
    context.clear_cookies()
    if not enabled:
        return
    context.add_cookies([
        {
            "name": CONSENT_COOKIE_NAME,
            "value": CONSENT_TRUE_VALUE,
            "url": BASE_URL,
        }
    ])


def _collect_request_count(page: Page) -> int:
    return page.evaluate(
        """
        () => {
            const beacon = (window.__collectBeaconCalls__ || []).filter(c => (c.url || '').includes('/api/analytics/collect')).length;
            const fetches = (window.__collectFetchCalls__ || []).filter(c => (c.url || '').includes('/api/analytics/collect')).length;
            return beacon + fetches;
        }
        """
    )


def _count_click_events(page: Page) -> int:
    return page.evaluate(
        """
        () => {
            const events = window.__LL_DEBUG_EVENTS__ || [];
            let count = 0;
            for (const evt of events) {
                if ((evt && evt.event_type) === 'click') {
                    count += 1;
                }
            }
            return count;
        }
        """
    )


def _count_enqueued_clicks(page: Page) -> int:
    return page.evaluate(
        """
        () => {
            const events = window.__LL_DEBUG_ENQUEUED__ || [];
            let count = 0;
            for (const evt of events) {
                if ((evt && evt.event_type) === 'click') {
                    count += 1;
                }
            }
            return count;
        }
        """
    )


def test_consent_on_loads_and_collects(page: Page, context: BrowserContext) -> None:
    _set_consent(context, True)
    page.goto("/", wait_until="networkidle")

    page.wait_for_load_state("networkidle")

    # Script inclusion
    try:
        page.wait_for_selector("script[src*='site/analytics.js']", state="attached", timeout=15000)
    except Exception:
        html_snapshot = page.content()
        cookies = context.cookies()
        print("\n[E2E] Script not found. Cookies:", cookies)
        print("[E2E] HTML snapshot (first 1500 chars):", html_snapshot[:1500])
        raise

    # Wrapper presence (server instrumentation)
    page.wait_for_selector("[data-ll='comp']", state="attached", timeout=15000)
    wrappers_count = page.locator("[data-ll='comp']").count()
    print(f"[E2E] Found {wrappers_count} component wrappers")
    assert wrappers_count > 0, "Expected at least one data-ll wrapper"

    # Trigger user interactions
    page.mouse.wheel(0, 1500)
    clickables = page.locator("[data-ll='comp'] a, [data-ll='comp'] button")
    if clickables.count() > 0:
        try:
            clickables.first.click(timeout=3000)
        except Exception:
            pass

    # Allow flush timer to fire and collect network calls
    page.wait_for_timeout(6000)
    try:
        page.wait_for_function("() => (window.__collectBeaconCalls__ || []).length + (window.__collectFetchCalls__ || []).length >= 1", timeout=15000)
    except Exception:
        cookies = context.cookies()
        print("\n[E2E] No collect detected. Cookies:", cookies)
        print("[E2E] Network logs captured see above.")
        raise
    collect_count = _collect_request_count(page)
    print(f"[E2E] collect_count={collect_count}")

    assert collect_count >= 1, "Expected at least one analytics collect request when consent=Y"

    baseline_enqueued_clicks = _count_enqueued_clicks(page)
    print(f"[E2E] baseline_enqueued_clicks={baseline_enqueued_clicks}")

    # Verify clicks on different anchor types are tracked
    injection_ok = page.evaluate(
        """
        (() => {
            const host = document.querySelector('[data-ll="comp"]');
            if (!host) {
                return false;
            }
                const anchorHash = document.createElement('a');
                anchorHash.href = '#';
                anchorHash.textContent = 'LLAnchorHash';
                anchorHash.style.display = 'inline-block';
                anchorHash.style.marginTop = '16px';
                anchorHash.dataset.llClick = 'debug-hash';
                host.appendChild(anchorHash);

                const anchorNav = document.createElement('a');
                anchorNav.href = '/dummy-target';
                anchorNav.textContent = 'LLAnchorNav';
                anchorNav.style.display = 'inline-block';
                anchorNav.style.marginTop = '16px';
                anchorNav.addEventListener('click', function (e) {
                    e.preventDefault();
                });
                anchorNav.dataset.llClick = 'debug-nav';
                host.appendChild(anchorNav);
                return true;
            })()
            """
        )
    assert injection_ok, "Failed to inject test anchors inside analytics wrapper"

    page.wait_for_timeout(800)
    page.evaluate(
        """
        (() => {
            const overlay = document.getElementById('driver-page-overlay');
            if (overlay) {
                overlay.remove();
            }
            const highlight = document.getElementById('driver-page-highlighted-element-stage');
            if (highlight) {
                highlight.remove();
            }
        })()
        """
    )
    page.evaluate(
        """
        () => {
            const hash = document.querySelector('[data-ll="comp"] a[data-ll-click="debug-hash"]');
            if (hash) {
                hash.click();
            }
        }
        """
    )
    page.wait_for_timeout(600)
    page.evaluate(
        """
        () => {
            const nav = document.querySelector('[data-ll\="comp"] a[data-ll-click="debug-nav"]');
            if (nav) {
                nav.click();
            }
        }
        """
    )
    # Trigger observe again to ensure IntersectionObserver sees injected anchors
    page.mouse.wheel(0, 200)

    page.wait_for_timeout(2000)
    final_enqueued_clicks = _count_enqueued_clicks(page)
    debug_enqueued_tail = page.evaluate("() => JSON.stringify((window.__LL_DEBUG_ENQUEUED__ || []).slice(-5))")
    print(f"[E2E] debug_enqueued_tail={debug_enqueued_tail}")
    print(f"[E2E] final_enqueued_clicks={final_enqueued_clicks}")
    assert final_enqueued_clicks >= baseline_enqueued_clicks + 2, "Both injected anchors should enqueue click events"


def test_consent_off_blocks_everything(page: Page, context: BrowserContext) -> None:
    _set_consent(context, False)
    page.goto("/", wait_until="networkidle")

    # Script should be absent
    assert page.query_selector("script[src*='site/analytics.js']") is None

    # There should be no wrappers when consent est refusé
    assert page.locator("[data-ll='comp']").count() == 0

    page.mouse.wheel(0, 1500)
    page.wait_for_timeout(4000)

    collect_count = _collect_request_count(page)
    print(f"[E2E] collect_count_no_consent={collect_count}")
    assert collect_count == 0, "Expected zero analytics collect requests when consent=N"
