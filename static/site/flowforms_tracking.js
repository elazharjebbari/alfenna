(function () {
  "use strict";

  if (typeof window === "undefined" || typeof document === "undefined") {
    return;
  }
  if (window.__FF_TRACKING_INIT__) {
    return;
  }
  window.__FF_TRACKING_INIT__ = true;

  const STATE = {
    sentinel: null,
    root: null,
    config: undefined,
    meta: null,
    lastDomMeta: null,
    pending: [],
    flushInterval: null,
    flushAttempts: 0,
    flowComplete: false,
    invalidSubmitNotified: false,
    complementaries: undefined,
    complementaryMap: undefined,
    complementaryImpressions: new Set(),
  };

  function getSentinel() {
    if (STATE.sentinel && document.body.contains(STATE.sentinel)) {
      return STATE.sentinel;
    }
    STATE.sentinel = document.getElementById("flowforms-sentinel") || null;
    return STATE.sentinel;
  }

  function toInt(value, fallback) {
    const n = parseInt(value, 10);
    if (Number.isFinite(n)) {
      return n;
    }
    return fallback !== undefined ? fallback : 0;
  }

  function readDataset() {
    const sentinel = getSentinel();
    if (!sentinel) {
      return null;
    }
    const ds = sentinel.dataset || {};
    return {
      flow_key: ds.flowKey || "",
      step_key: ds.stepKey || "",
      step_index: toInt(ds.stepIndex, 0),
      step_total: toInt(ds.stepTotal, 0),
    };
  }

  function ensureRoot() {
    if (STATE.root && document.body.contains(STATE.root)) {
      return STATE.root;
    }
    const root = document.querySelector("[data-ff-root]") || document.getElementById("ff-root");
    STATE.root = root || null;
    return STATE.root;
  }

  function parseConfigScript(el) {
    if (!el) {
      return null;
    }
    try {
      return JSON.parse(el.textContent || "{}");
    } catch (err) {
      return null;
    }
  }

  function loadConfig() {
    if (STATE.config !== undefined) {
      return STATE.config;
    }
    let cfg = null;
    const root = ensureRoot();
    if (root && root.parentElement) {
      let sib = root.nextElementSibling;
      while (sib) {
        if (sib.tagName === "SCRIPT" && sib.hasAttribute("data-ff-config")) {
          cfg = parseConfigScript(sib);
          if (cfg) {
            break;
          }
        }
        sib = sib.nextElementSibling;
      }
      if (!cfg) {
        const fallback = root.parentElement.querySelector("script[data-ff-config]");
        cfg = parseConfigScript(fallback);
      }
    }
    if (!cfg) {
      cfg = parseConfigScript(document.querySelector("script[data-ff-config]"));
    }
    STATE.config = cfg;
    return cfg;
  }

  function sanitizeComplementaryItem(item) {
    if (!item || typeof item !== "object") {
      return null;
    }
    const rawSlug = (item.slug !== undefined ? item.slug : (item.value !== undefined ? item.value : ""));
    const slug = String(rawSlug || "").trim();
    if (!slug) {
      return null;
    }
    const titleRaw = item.title !== undefined ? item.title : (item.label !== undefined ? item.label : slug);
    const priceRaw = item.price !== undefined ? item.price : (item.effective_price !== undefined ? item.effective_price : "");
    const currencyRaw = item.currency !== undefined ? item.currency : "";
    const normalized = {
      slug,
      title: String(titleRaw || slug),
      price: priceRaw === null || priceRaw === undefined || priceRaw === "" ? "" : String(priceRaw),
      currency: currencyRaw === null || currencyRaw === undefined || currencyRaw === "" ? "" : String(currencyRaw),
    };
    const image = item.image_src || item.imageSrc || item.image;
    if (image) {
      normalized.image_src = String(image);
    }
    return normalized;
  }

  function getComplementariesList() {
    if (STATE.complementaries !== undefined) {
      return STATE.complementaries;
    }
    const cfg = loadConfig();
    const raw = cfg && cfg.context && cfg.context.complementaries;
    if (!Array.isArray(raw) || !raw.length) {
      STATE.complementaries = [];
      return STATE.complementaries;
    }
    const seen = new Set();
    const list = [];
    raw.forEach((item) => {
      const normalized = sanitizeComplementaryItem(item);
      if (!normalized || seen.has(normalized.slug)) {
        return;
      }
      seen.add(normalized.slug);
      list.push(normalized);
    });
    STATE.complementaries = list;
    return list;
  }

  function getComplementaryMap() {
    if (STATE.complementaryMap !== undefined && STATE.complementaryMap !== null) {
      return STATE.complementaryMap;
    }
    const map = new Map();
    getComplementariesList().forEach((item) => {
      map.set(item.slug, item);
    });
    STATE.complementaryMap = map;
    return map;
  }

  function complementaryPayloadFromSlug(slug) {
    if (!slug) {
      return null;
    }
    const map = getComplementaryMap();
    if (!map.size) {
      return null;
    }
    const base = map.get(slug);
    if (!base) {
      return null;
    }
    return Object.assign({}, base);
  }

  function complementaryPayloadFromElement(el) {
    if (!el) {
      return null;
    }
    const dataset = el.dataset || {};
    const slug = (dataset.ffComplementarySlug || dataset.slug || "").toString().trim();
    if (!slug) {
      return null;
    }
    const payload = complementaryPayloadFromSlug(slug) || { slug: slug };
    if (!payload.title && dataset.ffComplementaryTitle) {
      payload.title = dataset.ffComplementaryTitle;
    }
    if (!payload.price && dataset.ffComplementaryPrice) {
      payload.price = dataset.ffComplementaryPrice;
    }
    if (!payload.currency && dataset.ffComplementaryCurrency) {
      payload.currency = dataset.ffComplementaryCurrency;
    }
    if (payload.image_src === undefined && dataset.ffComplementaryImage) {
      payload.image_src = dataset.ffComplementaryImage;
    }
    payload.title = (payload.title || slug).toString();
    payload.price = payload.price !== null && payload.price !== undefined ? String(payload.price) : "";
    payload.currency = payload.currency !== null && payload.currency !== undefined ? String(payload.currency) : "";
    return payload;
  }

  function stepKeyFromConfig(stepIndex) {
    const cfg = loadConfig();
    if (!cfg || !cfg.schema || !Array.isArray(cfg.schema.steps)) {
      return null;
    }
    const steps = cfg.schema.steps;
    for (let i = 0; i < steps.length; i += 1) {
      const step = steps[i] || {};
      const idx = toInt(step.idx !== undefined ? step.idx : (step.index !== undefined ? step.index : step.step_index), NaN);
      if (Number.isFinite(idx) && idx === stepIndex) {
        return (
          step.key ||
          step.alias ||
          step.slug ||
          step.name ||
          null
        );
      }
    }
    return null;
  }

  function mergeMeta(base, extra) {
    const out = {
      flow_key: (extra && extra.flow_key) || (base && base.flow_key) || "",
      step_key: (extra && extra.step_key) || (base && base.step_key) || "",
      step_index: toInt(extra && extra.step_index, toInt(base && base.step_index, 0)),
      step_total: toInt(extra && extra.step_total, toInt(base && base.step_total, 0)),
    };
    return out;
  }

  function computeDomMeta() {
    const base = mergeMeta(readDataset(), null);
    const root = ensureRoot();
    let flowDone = false;
    if (!root) {
      const cfg = loadConfig();
      if (!base.flow_key && cfg && typeof cfg.flow_key === "string") {
        base.flow_key = cfg.flow_key;
      }
      if (!base.step_index) {
        base.step_index = 1;
      }
      if (!base.step_total) {
        base.step_total = base.step_index;
      }
      base.flow_done = false;
      return base;
    }

    const steps = Array.from(root.querySelectorAll("[data-ff-step]"));
    const numericSteps = [];
    let visibleNumeric = null;
    let lastNumeric = null;

    steps.forEach((el) => {
      const raw = el.getAttribute("data-ff-step") || "";
      if (raw === "done") {
        if (!el.classList.contains("d-none")) {
          flowDone = true;
        }
        return;
      }
      const idx = toInt(raw, NaN);
      if (Number.isFinite(idx)) {
        numericSteps.push({ el, idx });
        if (!lastNumeric || idx >= lastNumeric.idx) {
          lastNumeric = { el, idx };
        }
        if (!el.classList.contains("d-none")) {
          visibleNumeric = { el, idx };
        }
      }
    });

    const total = numericSteps.length || base.step_total || 1;
    let stepIndex = base.step_index || (numericSteps.length ? numericSteps[0].idx : 1);
    let stepKey = base.step_key || "";

    if (visibleNumeric) {
      stepIndex = visibleNumeric.idx;
      const explicitKey = visibleNumeric.el.getAttribute("data-ff-step-key") || "";
      if (explicitKey) {
        stepKey = explicitKey;
      } else {
        const derivedKey = stepKeyFromConfig(stepIndex);
        if (derivedKey) {
          stepKey = derivedKey;
        }
      }
    } else if (flowDone && lastNumeric) {
      stepIndex = lastNumeric.idx;
      const explicitLast = lastNumeric.el.getAttribute("data-ff-step-key") || "";
      if (explicitLast) {
        stepKey = explicitLast;
      } else {
        const derivedLast = stepKeyFromConfig(stepIndex);
        if (derivedLast) {
          stepKey = derivedLast;
        }
      }
    }

    if (!stepKey) {
      const cfgKey = stepKeyFromConfig(stepIndex);
      if (cfgKey) {
        stepKey = cfgKey;
      } else {
        stepKey = `step${stepIndex}`;
      }
    }

    const cfg = loadConfig();
    if (!base.flow_key && cfg && typeof cfg.flow_key === "string") {
      base.flow_key = cfg.flow_key;
    }

    const meta = {
      flow_key: base.flow_key,
      step_key: stepKey,
      step_index: stepIndex,
      step_total: total,
      flow_done: flowDone,
    };
    return meta;
  }

  function setMeta(meta) {
    const sentinel = getSentinel();
    if (!sentinel || !meta) {
      return;
    }
    const normalized = mergeMeta(null, meta);
    sentinel.setAttribute("data-flow-key", normalized.flow_key);
    sentinel.setAttribute("data-step-key", normalized.step_key);
    sentinel.setAttribute("data-step-index", String(normalized.step_index));
    sentinel.setAttribute("data-step-total", String(normalized.step_total));
    STATE.meta = {
      flow_key: normalized.flow_key,
      step_key: normalized.step_key,
      step_index: normalized.step_index,
      step_total: normalized.step_total,
    };
    STATE.lastDomMeta = Object.assign({ flow_done: !!meta.flow_done }, STATE.meta);
  }

  function currentMeta() {
    if (!STATE.meta) {
      const computed = computeDomMeta();
      setMeta(computed);
    }
    if (!STATE.meta) {
      return null;
    }
    return Object.assign({}, STATE.meta);
  }

  function metasEqual(a, b) {
    if (!a || !b) {
      return false;
    }
    return (
      a.flow_key === b.flow_key &&
      a.step_key === b.step_key &&
      Number(a.step_index) === Number(b.step_index) &&
      Number(a.step_total) === Number(b.step_total)
    );
  }

  function flushPending() {
    if (!window.LL || typeof window.LL.emit !== "function") {
      return false;
    }
    while (STATE.pending.length) {
      const item = STATE.pending.shift();
      try {
        window.LL.emit(item.type, item.el, item.payload);
      } catch (err) {
        if (window.console && console.warn) {
          console.warn("[FlowFormsTracking] emit failed", err);
        }
      }
    }
    return true;
  }

  function scheduleFlush() {
    if (STATE.flushInterval) {
      return;
    }
    STATE.flushAttempts = 0;
    STATE.flushInterval = window.setInterval(() => {
      STATE.flushAttempts += 1;
      if (flushPending() || STATE.flushAttempts > 600) {
        clearInterval(STATE.flushInterval);
        STATE.flushInterval = null;
      }
    }, 1000);
  }

  function queueEmit(type, el, payload) {
    if (flushPending()) {
      try {
        window.LL.emit(type, el, payload);
      } catch (err) {
        STATE.pending.push({ type, el, payload });
        scheduleFlush();
      }
      return;
    }
    STATE.pending.push({ type, el, payload });
    scheduleFlush();
  }

  function emitWithMeta(name, meta, extra) {
    const baseMeta = meta ? Object.assign({}, meta) : currentMeta();
    if (!baseMeta) {
      return;
    }
    const payload = Object.assign({ ev: name }, baseMeta, extra || {});
    queueEmit("conversion", document.body, payload);
  }

  function emitComplementaryImpressions(meta) {
    if (!meta) {
      return;
    }
    const stepIndex = Number(meta.step_index);
    if (!Number.isFinite(stepIndex) || stepIndex !== 2) {
      return;
    }
    const complementaries = getComplementariesList();
    if (!complementaries.length) {
      return;
    }
    complementaries.forEach((item) => {
      if (!item.slug || STATE.complementaryImpressions.has(item.slug)) {
        return;
      }
      emitWithMeta("ff_complementary_impression", meta, item);
      STATE.complementaryImpressions.add(item.slug);
    });
  }

  function emitComplementarySelect(payload) {
    if (!payload || !payload.slug) {
      return;
    }
    emitWithMeta("ff_complementary_select", null, payload);
  }

  function emitStepStart(meta) {
    emitWithMeta("ff_step_start", meta, null);
  }

  function emitStepSubmit(meta) {
    emitWithMeta("ff_step_submit", meta, null);
  }

  function emitStepComplete(meta) {
    emitWithMeta("ff_step_complete", meta, null);
  }

  function emitValidationError(meta, count) {
    emitWithMeta("ff_validation_error", meta, { errors_count: count || 1 });
  }

  function emitFlowComplete(meta, extra) {
    emitWithMeta("ff_flow_complete", meta, extra || {});
  }

  function handleInvalid(event) {
    const meta = currentMeta();
    if (!meta) {
      return;
    }
    if (!STATE.invalidSubmitNotified) {
      STATE.invalidSubmitNotified = true;
      emitStepSubmit(meta);
      window.setTimeout(() => {
        STATE.invalidSubmitNotified = false;
      }, 0);
    }
    let errors = 1;
    const form = event.target && (event.target.form || event.target.closest && event.target.closest("form"));
    if (form && form.querySelectorAll) {
      try {
        const invalid = form.querySelectorAll(":invalid");
        if (invalid && invalid.length) {
          errors = invalid.length;
        }
      } catch (err) {}
    }
    emitValidationError(meta, errors);
  }

  function handleFormSubmit(event) {
    const metaBefore = currentMeta();
    if (!metaBefore) {
      return;
    }
    emitStepSubmit(metaBefore);
    let isValid = true;
    const form = event.target;
    if (form && typeof form.checkValidity === "function") {
      try {
        isValid = form.checkValidity();
      } catch (err) {
        isValid = true;
      }
    }
    if (isValid) {
      emitStepComplete(metaBefore);
    }
  }

  function handleTransition() {
    const before = currentMeta();
    if (!before) {
      return;
    }
    emitStepSubmit(before);
    window.setTimeout(() => {
      const afterDom = computeDomMeta();
      if (!afterDom) {
        return;
      }
      if (afterDom.flow_done) {
        if (!STATE.flowComplete) {
          STATE.flowComplete = true;
          emitStepComplete(before);
          emitFlowComplete(before);
          try {
            window.dispatchEvent(new CustomEvent("ll_flow_complete", { detail: Object.assign({}, before) }));
          } catch (err) {
            window.dispatchEvent(new Event("ll_flow_complete"));
          }
        }
        setMeta(afterDom);
        return;
      }
      const after = mergeMeta(before, afterDom);
      if (!metasEqual(after, before)) {
        emitStepComplete(before);
        setMeta(after);
        emitStepStart(currentMeta());
        emitComplementaryImpressions(currentMeta());
      } else {
        setMeta(after);
      }
    }, 0);
  }

  function onClick(event) {
    const target = event.target;
    if (!target) {
      return;
    }
    if (target.closest && target.closest("[data-ff-next]")) {
      handleTransition();
      return;
    }
    if (target.closest && target.closest("[data-ff-submit]")) {
      handleTransition();
    }
  }

  function onComplementaryChange(event) {
    const rawTarget = event.target;
    if (!rawTarget || typeof rawTarget.closest !== "function") {
      return;
    }
    const el = rawTarget.closest("[data-ff-complementary]");
    if (!el) {
      return;
    }
    if (el.matches("input[type='checkbox'], input[type='radio']") && !el.checked) {
      return;
    }
    const payload = complementaryPayloadFromElement(el);
    if (!payload) {
      return;
    }
    emitComplementarySelect(payload);
  }

  function onComplementaryClick(event) {
    const target = event.target;
    if (!target || typeof target.closest !== "function") {
      return;
    }
    const el = target.closest("[data-ff-complementary]");
    if (!el || el.matches("input, select, textarea")) {
      return;
    }
    const payload = complementaryPayloadFromElement(el);
    if (!payload) {
      return;
    }
    emitComplementarySelect(payload);
  }

  function onFlowCompleteSignal(extra) {
    if (STATE.flowComplete) {
      return;
    }
    const meta = currentMeta();
    if (!meta) {
      return;
    }
    emitFlowComplete(meta, extra && typeof extra === "object" ? extra : {});
    STATE.flowComplete = true;
  }

  function findRelevantForm() {
    const sentinel = getSentinel();
    if (!sentinel) {
      return null;
    }
    if (typeof sentinel.closest === "function") {
      const direct = sentinel.closest("form");
      if (direct) {
        return direct;
      }
    }
    if (sentinel.parentElement) {
      const scoped = sentinel.parentElement.querySelector("form");
      if (scoped) {
        return scoped;
      }
    }
    const allForms = document.querySelectorAll("form");
    if (allForms.length === 1) {
      return allForms[0];
    }
    return null;
  }

  function boot() {
    const sentinel = getSentinel();
    if (!sentinel) {
      return;
    }
    const initial = computeDomMeta();
    setMeta(initial);
    emitStepStart(currentMeta());
    emitComplementaryImpressions(currentMeta());

    const form = findRelevantForm();
    if (form) {
      form.addEventListener("submit", handleFormSubmit);
      form.addEventListener("invalid", handleInvalid, true);
    }

    if (STATE.root) {
      STATE.root.addEventListener("change", onComplementaryChange);
      STATE.root.addEventListener("click", onComplementaryClick);
    }

    document.addEventListener("click", onClick);
    window.addEventListener("ll_flow_complete", (event) => {
      onFlowCompleteSignal(event && event.detail);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
