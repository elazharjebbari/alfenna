(function () {
  "use strict";

  if (typeof window === "undefined" || typeof document === "undefined") {
    return;
  }
  if (window.__LL_ANALYTICS_INIT__) {
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
    push({
      event_uuid: uuid(),
      event_type: type,
      ts: nowISO(),
      page_id: base.page_id,
      slot_id: base.slot_id,
      component_alias: base.component_alias,
      payload: payload || {},
    });
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
