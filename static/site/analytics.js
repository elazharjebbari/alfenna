(function () {
  "use strict";

  if (typeof window === "undefined" || typeof document === "undefined") {
    return;
  }
  if (window.__LL_ANALYTICS_INIT__) {
    return;
  }

  const TRUE_VALUES = ["1", "true", "yes", "y", "on", "accept", "granted"];

  function hasTrue(value) {
    if (value === null || value === undefined) {
      return false;
    }
    const normalized = String(value).trim().toLowerCase();
    return TRUE_VALUES.indexOf(normalized) !== -1;
  }

  function readCookie(name) {
    if (!name || typeof document === "undefined" || !document.cookie) {
      return "";
    }
    const pattern = "(?:^|; )" + name.replace(/([.$?*|{}()\[\]\\/+^])/g, "\\$1") + "=([^;]*)";
    const match = document.cookie.match(new RegExp(pattern));
    return match ? decodeURIComponent(match[1]) : "";
  }

  function consentCookieName() {
    const body = document.body || document.documentElement;
    if (!body) {
      return "cookie_consent_marketing";
    }
    if (body.dataset && body.dataset.llConsentCookie) {
      return body.dataset.llConsentCookie;
    }
    if (typeof body.getAttribute === "function") {
      const attr = body.getAttribute("data-ll-consent-cookie");
      if (attr) {
        return attr;
      }
    }
    return "cookie_consent_marketing";
  }

  function analyticsAllowed() {
    const body = document.body || document.documentElement;
    const attrEnabled = body && typeof body.getAttribute === "function"
      ? body.getAttribute("data-ll-analytics-enabled")
      : "";
    const attrAllows = attrEnabled ? hasTrue(attrEnabled) : true;
    if (!attrAllows) {
      return false;
    }
    const cookieName = consentCookieName();
    if (!cookieName) {
      return true;
    }
    const cookieValue = readCookie(cookieName);
    if (!cookieValue) {
      return false;
    }
    return hasTrue(cookieValue);
  }

  if (!analyticsAllowed()) {
    return;
  }

  window.__LL_ANALYTICS_INIT__ = true;

  const queue = [];
  const MAX_BATCH = 20;
  const URL = "/api/analytics/collect/";
  const hasBeacon = typeof navigator !== "undefined" && typeof navigator.sendBeacon === "function";
  const FLUSH_DELAY_MS = 2000;
  let flushTimer = null;

  const nowISO = () => new Date().toISOString();
  const uuid = () => {
    const cryptoRef = typeof crypto !== "undefined" ? crypto : null;
    if (cryptoRef && cryptoRef.randomUUID) {
      return cryptoRef.randomUUID();
    }
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
      const r = Math.random() * 16 | 0;
      const v = c === "x" ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  };

  const canNormalize = typeof String.prototype.normalize === "function";
  const stripDiacritics = (value) => {
    if (!value) {
      return "";
    }
    if (!canNormalize) {
      return String(value);
    }
    try {
      return String(value).normalize("NFD").replace(/[\u0300-\u036f]/g, "");
    } catch (err) {
      return String(value);
    }
  };

  function toSlugPart(value) {
    if (value === null || value === undefined) {
      return "";
    }
    const stripped = stripDiacritics(value);
    const lower = stripped.toLowerCase();
    const cleaned = lower.replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
    return cleaned.slice(0, 80);
  }

  function resolveEventId(evt) {
    if (!evt || typeof evt !== "object") {
      return uuid();
    }
    const payload = evt.payload || {};
    const preferred = payload.id
      || payload.event_id
      || payload.eventId
      || payload.element_id
      || payload.elementId
      || payload.name;
    const preferredSlug = toSlugPart(preferred);
    if (preferredSlug) {
      return preferredSlug;
    }

    const derivedParts = [
      toSlugPart(evt.page_id),
      toSlugPart(evt.slot_id),
      toSlugPart(evt.component_alias),
      toSlugPart(payload.ev || payload.event),
      toSlugPart(evt.event_type),
    ].filter(Boolean);

    if (derivedParts.length) {
      return derivedParts.join("__").slice(0, 120);
    }

    return evt.event_uuid || uuid();
  }

  function ensureDataLayer() {
    const existing = window.dataLayer;
    const dl = Array.isArray(existing) ? existing : [];
    if (!Array.isArray(existing)) {
      window.dataLayer = dl;
    }
    if (dl.__ll_patched__) {
      return dl;
    }

    const listeners = [];
    const originalPush = Array.prototype.push;

    const eventContext = (entry) => {
      const rawEvent =
        entry.event_type
        || entry.eventType
        || entry.ll_event_type
        || entry.event
        || "";
      let eventType = "";
      if (typeof rawEvent === "string") {
        eventType = rawEvent.startsWith("ll_") ? rawEvent.slice(3) : rawEvent;
      }
      return {
        event_type: eventType || "",
        page_id: entry.page_id || entry.ll_page_id || "",
        slot_id: entry.slot_id || entry.ll_slot_id || "",
        component_alias: entry.component_alias || entry.ll_component_alias || "",
      };
    };

    const normalizeEntry = (entry) => {
      const base = entry && typeof entry === "object" ? entry : { value: entry };
      const normalized = Object.assign({}, base);
      normalized.payload = Object.assign({}, base && base.payload && typeof base.payload === "object" ? base.payload : {});
      normalized.ts = normalized.ts || nowISO();
      normalized.event_uuid = normalized.event_uuid || uuid();

      const context = eventContext(normalized);
      if (!normalized.ll_event_type && context.event_type) {
        normalized.ll_event_type = context.event_type;
      }
      if (!normalized.ll_page_id && context.page_id) {
        normalized.ll_page_id = context.page_id;
      }
      if (!normalized.ll_slot_id && context.slot_id) {
        normalized.ll_slot_id = context.slot_id;
      }
      if (!normalized.ll_component_alias && context.component_alias) {
        normalized.ll_component_alias = context.component_alias;
      }
      if (!normalized.event || typeof normalized.event !== "string") {
        normalized.event = context.event_type ? `ll_${context.event_type}` : "ll_event";
      }

      const idSource = Object.assign({}, context, {
        payload: normalized.payload,
        event_uuid: normalized.event_uuid,
      });

      normalized.id_event = normalized.id_event || resolveEventId(idSource);
      normalized.event_uuid = normalized.event_uuid || idSource.event_uuid;
      return normalized;
    };

    const notify = (entry) => {
      const snapshot = listeners.slice();
      for (let i = 0; i < snapshot.length; i += 1) {
        const fn = snapshot[i];
        if (typeof fn === "function") {
          try {
            fn(entry);
          } catch (err) {}
        }
      }
      try {
        if (typeof window.dispatchEvent === "function" && typeof window.CustomEvent === "function") {
          const evt = new window.CustomEvent("datalayer:push", { detail: entry });
          window.dispatchEvent(evt);
        }
      } catch (err) {}
    };

    dl.on = function on(fn) {
      if (typeof fn !== "function") {
        return () => {};
      }
      listeners.push(fn);
      return function unsubscribe() {
        const idx = listeners.indexOf(fn);
        if (idx !== -1) {
          listeners.splice(idx, 1);
        }
      };
    };

    dl.push = function pushWithNormalize() {
      let length = dl.length;
      for (let i = 0; i < arguments.length; i += 1) {
        const normalized = normalizeEntry(arguments[i]);
        length = originalPush.call(dl, normalized);
        notify(normalized);
      }
      return length;
    };

    dl.__ll_patched__ = true;
    return dl;
  }

  const dataLayer = ensureDataLayer();

  function ctx(el) {
    const slot = el && el.closest ? el.closest("[data-ll-slot-id]") : null;
    const slotAlias = slot && slot.getAttribute("data-ll-alias");
    const elementAlias = el && el.getAttribute ? el.getAttribute("data-ll-alias") : null;
    return {
      page_id: (slot && slot.getAttribute("data-ll-page-id")) || "product_detail",
      slot_id: (slot && slot.getAttribute("data-ll-slot-id")) || "",
      component_alias: slotAlias || elementAlias || "",
    };
  }

  function push(evt) {
    queue.push(evt);
    if (queue.length >= MAX_BATCH) {
      flush();
      return;
    }
    scheduleFlush();
  }

  function flush() {
    clearFlushTimer();
    if (!queue.length) {
      return;
    }
    const batch = queue.splice(0, queue.length);
    const payload = JSON.stringify({ events: batch });
    if (hasBeacon) {
      const blob = new Blob([payload], { type: "application/json" });
      navigator.sendBeacon(URL, blob);
      return;
    }
    fetch(URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: payload,
      keepalive: true,
    }).catch(() => {
      batch.forEach((evt) => queue.push(evt));
    });
  }

  function clearFlushTimer() {
    if (flushTimer !== null) {
      clearTimeout(flushTimer);
      flushTimer = null;
    }
  }

  function scheduleFlush() {
    clearFlushTimer();
    flushTimer = setTimeout(() => {
      flushTimer = null;
      flush();
    }, FLUSH_DELAY_MS);
  }

  const LL = window.LL = window.LL || {};

  LL.emit = function emit(type, el, payload) {
    const base = ctx(el || document.body);
    const event = {
      event_uuid: uuid(),
      event_type: type,
      ts: nowISO(),
      page_id: base.page_id,
      slot_id: base.slot_id,
      component_alias: base.component_alias,
      payload: payload || {},
    };
    push(event);
    return event;
  };

  LL.view = function view(el) {
    LL.emit("view", el, {});
  };

  LL.click = function click(el, name, extra) {
    const payload = Object.assign({ ev: name || "" }, extra || {});
    LL.emit("click", el, payload);
  };

  LL.scroll = function scroll(pct) {
    LL.emit("scroll", document.body, { scroll_pct: pct });
  };

  LL.heatmap = function heatmap(el, x, y) {
    LL.emit("heatmap", el, { x: x, y: y });
  };

  LL.flush = flush;

  (function () {
    function mirrorToDataLayer(evt) {
      try {
        const dl = ensureDataLayer();
        if (!evt || typeof evt !== "object") {
          return;
        }
        const payloadSource = evt.payload || {};
        const payload = Object.assign({}, payloadSource);
        const eventNameRaw = evt.event_type === "conversion"
          ? (payload.ev || payload.event || "")
          : `ll_${evt.event_type}`;
        const flat = Object.assign({
          event: eventNameRaw || "ll_event",
          ll_event_type: evt.event_type,
          ll_page_id: evt.page_id || "",
          ll_slot_id: evt.slot_id || "",
          ll_component_alias: evt.component_alias || "",
          event_uuid: evt.event_uuid || "",
          id_event: resolveEventId(evt),
        }, payload);
        flat.id_event = flat.id_event || resolveEventId(evt);
        flat.event_uuid = flat.event_uuid || evt.event_uuid || "";
        dl.push(flat);
      } catch (err) {}
    }

    const originalEmit = LL.emit;
    LL.emit = function emit(type, el, payload) {
      const evt = originalEmit.call(LL, type, el, payload);
      try {
        mirrorToDataLayer(evt);
      } catch (err) {}
      return evt;
    };
  })();

  function bootViews() {
    const targets = document.querySelectorAll("[data-ll-slot-id]");
    if (!("IntersectionObserver" in window)) {
      targets.forEach((el) => LL.view(el));
      return;
    }
    const io = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          LL.view(entry.target);
          io.unobserve(entry.target);
        }
      });
    }, { threshold: 0.35 });
    targets.forEach((el) => io.observe(el));
  }

  function bootClicks() {
    document.addEventListener("click", (ev) => {
      const target = ev.target && (ev.target.closest("[data-ll-click]") || ev.target.closest("[data-ev]"));
      if (!target) {
        return;
      }
      const name = target.getAttribute("data-ll-click") || target.getAttribute("data-ev") || "";
      let extra = {};
      const payloadRaw = target.getAttribute("data-ll-payload");
      if (payloadRaw) {
        try {
          extra = JSON.parse(payloadRaw);
        } catch (err) {
          extra = {};
        }
      }
      const stableId = target.getAttribute("data-id") || target.getAttribute("data-ll-id");
      if (stableId) {
        extra = Object.assign({ id: stableId }, extra);
      }
      LL.click(target, name, extra);
    });
  }

  function bootHeatmap() {
    const root = document.querySelector("main") || document.body;
    if (!root || !root.addEventListener) {
      return;
    }
    root.addEventListener("click", (ev) => {
      const rect = root.getBoundingClientRect();
      const x = (ev.clientX - rect.left) / rect.width;
      const y = (ev.clientY - rect.top) / rect.height;
      if (x >= 0 && x <= 1 && y >= 0 && y <= 1) {
        LL.heatmap(root, x, y);
      }
    });
  }

  function bootScroll() {
    const marks = [25, 50, 75, 90];
    const passed = { 0: true };
    const handler = () => {
      const docEl = document.documentElement;
      const maxScroll = docEl.scrollHeight - docEl.clientHeight;
      if (maxScroll <= 0) {
        return;
      }
      const pct = Math.round((docEl.scrollTop / maxScroll) * 100);
      marks.forEach((mark) => {
        if (!passed[mark] && pct >= mark) {
          passed[mark] = true;
          LL.scroll(mark);
        }
      });
    };
    window.addEventListener("scroll", handler, { passive: true });
  }

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") {
      flush();
    }
  });
  window.addEventListener("pagehide", flush);
  window.addEventListener("beforeunload", flush);

  const boot = () => {
    bootViews();
    bootClicks();
    bootHeatmap();
    bootScroll();
  };

  if (document.readyState !== "loading") {
    boot();
  } else {
    document.addEventListener("DOMContentLoaded", boot);
  }
})();
