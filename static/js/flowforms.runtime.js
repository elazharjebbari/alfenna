/* flowforms.runtime.js — runtime générique multi-étapes (compose/legacy)
   - Boot sûr (DOMContentLoaded / defer-friendly)
   - Scope config près du root (script[data-ff-config] adjacent)
   - Listeners next/prev/submit
   - Idempotency, signature HMAC (si sign_url), CSRF same-origin
*/
(function () {
  "use strict";

  // ---------- utilitaires ----------
  function $(root, sel) { return (root || document).querySelector(sel); }
  function $all(root, sel) { return Array.from((root || document).querySelectorAll(sel)); }

  function uuid4() {
    const b = crypto.getRandomValues(new Uint8Array(16));
    b[6] = (b[6] & 0x0f) | 0x40;
    b[8] = (b[8] & 0x3f) | 0x80;
    const hex = [...b].map(x => x.toString(16).padStart(2, "0")).join("");
    return `${hex.substr(0, 8)}-${hex.substr(8, 4)}-${hex.substr(12, 4)}-${hex.substr(16, 4)}-${hex.substr(20)}`;
  }

  const PROGRESS_DEFAULT_URL = "/api/leads/progress/";
  const PROGRESS_DEFAULT_FLOW_KEY = "checkout_intent_flow";
  const PROGRESS_STORAGE_KEY = "ff_session";

  function safeLocalStorage() {
    try { return window.localStorage; } catch (_) { return null; }
  }

  function ensureProgressSessionKey(storageKey) {
    const keyName = storageKey || PROGRESS_STORAGE_KEY;
    const store = safeLocalStorage();
    if (!store) {
      return `ff-${uuid4()}`;
    }
    let existing = store.getItem(keyName);
    if (existing && existing.length) {
      return existing;
    }
    existing = `ff-${uuid4()}`;
    try { store.setItem(keyName, existing); } catch (_) { /* ignore quota errors */ }
    return existing;
  }

  function ensureProgressHiddenFields(root, cfg, sessionKey, flowKey) {
    if (!root) return;
    const sessionFieldName = cfg.progress_session_field_name || "ff_session_key";
    let sessionField = root.querySelector(`input[name="${sessionFieldName}"]`);
    if (!sessionField) {
      sessionField = document.createElement("input");
      sessionField.type = "hidden";
      sessionField.name = sessionFieldName;
      sessionField.setAttribute("data-ff-progress-session", "1");
      root.appendChild(sessionField);
    }
    sessionField.value = sessionKey;

    const flowFieldName = cfg.progress_flow_field_name || "ff_flow_key";
    let flowField = root.querySelector(`input[name="${flowFieldName}"]`);
    if (!flowField) {
      flowField = document.createElement("input");
      flowField.type = "hidden";
      flowField.name = flowFieldName;
      flowField.setAttribute("data-ff-progress-flow", "1");
      root.appendChild(flowField);
    }
    flowField.value = flowKey;
  }

  function getCookie(name) {
    const m = document.cookie.match("(^|;)\\s*" + name + "\\s*=\\s*([^;]+)");
    return m ? m.pop() : "";
  }

  // Cherche le <script data-ff-config> le plus proche du root (sibling suivant prioritaire)
  function jsonFromConfigScript(root) {
    // 1) sibling scan après root
    if (root && root.parentElement) {
      let sib = root.nextElementSibling;
      while (sib) {
        if (sib.tagName === "SCRIPT" && sib.hasAttribute("data-ff-config")) {
          try { return JSON.parse(sib.textContent || "{}"); } catch (_) { return {}; }
        }
        sib = sib.nextElementSibling;
      }
      // 2) fallback: chercher dans le parent
      const el2 = root.parentElement.querySelector('script[data-ff-config]');
      if (el2) { try { return JSON.parse(el2.textContent || "{}"); } catch (_) { return {}; } }
    }
    // 3) dernier recours: document
    const el = document.querySelector('script[data-ff-config]');
    if (!el) return {};
    try { return JSON.parse(el.textContent || "{}"); } catch (_) { return {}; }
  }

  function coerce(val, cast) {
    if (cast === "bool") {
      if (typeof val === "boolean") return val;
      const s = String(val).trim().toLowerCase();
      return (s === "1" || s === "true" || s === "on" || s === "yes");
    }
    if (cast === "int") {
      const n = parseInt(val, 10); return Number.isFinite(n) ? n : 0;
    }
    if (cast === "float") {
      const n = parseFloat(val); return Number.isFinite(n) ? n : 0.0;
    }
    if (cast === "date") {
      const d = new Date(val);
      return isNaN(d.getTime()) ? val : d.toISOString();
    }
    return val; // default: string
  }

  function deduceValue(input) {
    const cast = (input.getAttribute("data-ff-cast") || "").trim();
    if (input.type === "checkbox") {
      return cast === "bool" ? !!input.checked : (input.checked ? "on" : "");
    }
    if (input.type === "radio") {
      if (!input.checked) return null;
      return coerce(input.value, cast || "");
    }
    return coerce(input.value, cast || "");
  }

  function parseFieldsMap(root, cfg) {
    let datasetMap = {};
    const raw = root && (root.getAttribute("data-fields-map") || (root.dataset ? root.dataset.fieldsMap : ""));
    if (raw) {
      try { datasetMap = JSON.parse(raw); } catch (_) { datasetMap = {}; }
    }
    const cfgMap = (cfg && (cfg.fields_map || cfg.fieldsMap)) || {};
    if (cfgMap && typeof cfgMap === "object") {
      return Object.assign({}, cfgMap, datasetMap);
    }
    return datasetMap;
  }

  function collectFields(root, cfg, fieldsMap) {
    const out = {};
    fieldsMap = fieldsMap || parseFieldsMap(root, cfg);
    const skipNames = new Set(["csrfmiddlewaretoken"]);

    function assign(key, value) {
      if (value === null || key === "") return;
      out[key] = value;
    }

    $all(root, "[data-ff-field]").forEach(el => {
      const rawName = (el.getAttribute("data-ff-field") || "").trim();
      if (!rawName) return;
      const v = deduceValue(el);
      if (v === null) return;
      const mapped = fieldsMap && fieldsMap[rawName] ? fieldsMap[rawName] : rawName;
      if (skipNames.has(mapped)) return;
      assign(mapped, v);
    });

    $all(root, "input[name], select[name], textarea[name]").forEach(el => {
      const nameAttr = (el.getAttribute("name") || "").trim();
      if (!nameAttr || skipNames.has(nameAttr)) return;
      if (el.type === "radio" && !el.checked) return;
      const v = deduceValue(el);
      if (v === null) return;
      assign(nameAttr, v);
    });

    const phoneKeys = new Set(["phone", "phone_number"]);
    if (fieldsMap && typeof fieldsMap === "object") {
      if (fieldsMap.phone) phoneKeys.add(fieldsMap.phone);
      if (fieldsMap.phone_number) phoneKeys.add(fieldsMap.phone_number);
    }
    phoneKeys.forEach(key => {
      if (typeof out[key] === "string") {
        out[key] = sanitizePhone(out[key]);
      }
    });

    return out;
  }

  function progressAllowList(cfg, stepKey) {
    const map = (cfg && (cfg.progress_steps || cfg.progressSteps)) || {};
    if (map && typeof map === "object" && Array.isArray(map[stepKey])) {
      return map[stepKey];
    }
    return null;
  }

  async function sendProgressUpdate(root, cfg, stepIndex) {
    if (!cfg) return { skipped: true };
    const url = cfg.progress_url || (cfg.backend_config && cfg.backend_config.progress_url) || PROGRESS_DEFAULT_URL;
    if (!url) return { skipped: true };
    const stepKey = typeof stepIndex === "number" ? `step${stepIndex}` : String(stepIndex || "");
    if (!stepKey) return { skipped: true };

    const fieldsMap = parseFieldsMap(root, cfg);
    const allPayload = collectFields(root, cfg, fieldsMap) || {};
    const allowList = progressAllowList(cfg, stepKey);
    const payload = {};
    if (allowList && allowList.length) {
      allowList.forEach((key) => {
        if (Object.prototype.hasOwnProperty.call(allPayload, key)) {
          payload[key] = allPayload[key];
        }
      });
    } else {
      Object.assign(payload, allPayload);
    }

    if (cfg.context && typeof cfg.context === "object") {
      Object.entries(cfg.context).forEach(([key, value]) => {
        if (value !== undefined && value !== null && !Object.prototype.hasOwnProperty.call(payload, key)) {
          payload[key] = value;
        }
      });
    }

    if (!Object.keys(payload).length) {
      return { skipped: true };
    }

    const flowKey = cfg.flow_key || cfg.progress_flow_key || PROGRESS_DEFAULT_FLOW_KEY;
    const sessionKey = ensureProgressSessionKey(cfg.progress_session_storage_key);
    const formKind = cfg.form_kind || cfg.progress_form_kind || "checkout_intent";

    ensureProgressHiddenFields(root, cfg, sessionKey, flowKey);

    const body = {
      flow_key: flowKey,
      session_key: sessionKey,
      form_kind: formKind,
      step: stepKey,
      payload,
    };

    try {
      const resp = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify(body),
        credentials: "same-origin",
      });
      if (!resp.ok) {
        const txt = await resp.text().catch(() => "");
        console.warn("[FlowForms] progress failed", resp.status, txt);
        return { ok: false, status: resp.status };
      }
      return { ok: true, status: resp.status };
    } catch (err) {
      console.warn("[FlowForms] progress error", err);
      return { ok: false, error: err };
    }
  }

  function parseFloatSafe(value) {
    if (value === undefined || value === null || value === "") return null;
    const normalized = typeof value === "string" ? value.replace(",", ".") : value;
    const num = parseFloat(normalized);
    return Number.isFinite(num) ? num : null;
  }

  function checkoutHintsFromDom(root) {
    const node = root && root.querySelector && root.querySelector("[data-checkout-hints]");
    if (!node) return null;
    const data = node.dataset || {};
    const unitFromData = parseFloatSafe(data.unitPrice);
    const promoFromData = parseFloatSafe(data.promoPrice);
    const baseFromData = parseFloatSafe(data.basePrice);
    return {
      unitPrice: unitFromData !== null ? unitFromData : (promoFromData !== null ? promoFromData : baseFromData),
      promoPrice: promoFromData,
      basePrice: baseFromData,
      currency: data.currency || "MAD",
      onlineDiscount: parseFloatSafe(data.onlineDiscount) || 0,
      productId: data.productId || "",
      productSlug: data.productSlug || "",
      productName: data.productName || "",
      bumpPrice: parseFloatSafe(data.bumpPrice),
      bumpCurrency: data.bumpCurrency || "",
    };
  }

  function formatAmount(amount, currency) {
    const cur = currency || "MAD";
    const safe = Number.isFinite(amount) ? amount : 0;
    try {
      const formatted = safe.toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
      return `${formatted} ${cur}`;
    } catch (_) {
      return `${safe.toFixed(2)} ${cur}`;
    }
  }

  function setText(root, selector, text) {
    const el = root && root.querySelector ? root.querySelector(selector) : null;
    if (el) el.textContent = text;
  }

  function toggleVisibility(root, selector, visible) {
    const el = root && root.querySelector ? root.querySelector(selector) : null;
    if (!el) return;
    if (visible) el.classList.remove("d-none"); else el.classList.add("d-none");
  }

  function updateCheckoutSummary(root, hints, totals) {
    if (!totals) return;
    const currency = (hints && hints.currency) || "MAD";
    const subtotal = totals.subtotal || 0;
    const discount = totals.discount || 0;
    const total = totals.total || 0;
    setText(root, "#af-subtotal", formatAmount(subtotal, currency));
    setText(root, "#af-discount", discount > 0 ? `-${formatAmount(discount, currency)}` : formatAmount(0, currency));
    setText(root, "#af-total", formatAmount(total, currency));
    setText(root, "#af-step3-subtotal", formatAmount(subtotal, currency));
    setText(root, "#af-step3-discount", discount > 0 ? `-${formatAmount(discount, currency)}` : formatAmount(0, currency));
    setText(root, "#af-step3-total", formatAmount(total, currency));
    toggleVisibility(root, "#af-step3-discount-row", discount > 0.0001);

    const onlineSpan = root && root.querySelector ? root.querySelector("#af-online-discount") : null;
    if (onlineSpan) {
      const baseDiscount = hints && hints.onlineDiscount ? Number(hints.onlineDiscount) : 0;
      if (discount > 0) {
        onlineSpan.textContent = `-${formatAmount(discount, currency)} de réduction`;
      } else if (baseDiscount > 0) {
        onlineSpan.textContent = `-${formatAmount(baseDiscount, currency)} de réduction`;
      }
    }
  }

  function enrichCheckout(root, finalBody, fieldsMap, hints) {
    if (!hints) return null;
    fieldsMap = fieldsMap || {};
    const paymentField = fieldsMap.payment_method || fieldsMap.paymentMethod || "payment_method";
    const quantityField = fieldsMap.quantity || "quantity";
    const bumpField = fieldsMap.bump || fieldsMap.bump_optin || "bump_optin";
    const paymentRaw = finalBody[paymentField];
    const paymentMethod = (paymentRaw || "").toString().toLowerCase() || "cod";
    const quantityRaw = finalBody[quantityField];
    let quantity = parseInt(quantityRaw, 10);
    if (!Number.isFinite(quantity) || quantity <= 0) quantity = 1;
    const unitPrice = Number.isFinite(hints.unitPrice) ? hints.unitPrice : (Number.isFinite(hints.promoPrice) ? hints.promoPrice : (Number.isFinite(hints.basePrice) ? hints.basePrice : 0));
    const subtotal = Math.max(unitPrice, 0) * quantity;
    const bumpSelected = finalBody[bumpField] !== undefined && finalBody[bumpField] !== null && finalBody[bumpField] !== "" && finalBody[bumpField] !== false && finalBody[bumpField] !== "0";
    const bumpAmount = bumpSelected && Number.isFinite(hints.bumpPrice) ? Math.max(hints.bumpPrice, 0) : 0;
    let discount = 0;
    if (paymentMethod === "online" && Number.isFinite(hints.onlineDiscount) && hints.onlineDiscount > 0) {
      discount = Math.min(hints.onlineDiscount, subtotal);
    }
    const total = Math.max(subtotal - discount + bumpAmount, 0);
    const amountMinor = Math.round(total * 100);
    finalBody.amount_minor = amountMinor;
    finalBody.amount_cents = amountMinor;
    if (!finalBody.currency && hints.currency) {
      finalBody.currency = hints.currency;
    }
    if (!finalBody.product_id && hints.productId) {
      finalBody.product_id = hints.productId;
    }
    if (!finalBody.product_slug && hints.productSlug) {
      finalBody.product_slug = hints.productSlug;
    }
    if (!finalBody.product_name && hints.productName) {
      finalBody.product_name = hints.productName;
    }
    if (!finalBody.course_slug && finalBody.product_slug) {
      finalBody.course_slug = finalBody.product_slug;
    }
    finalBody.online_discount_amount = discount;
    finalBody.online_discount_minor = Math.round(discount * 100);
    finalBody.checkout_bump_amount = bumpAmount;
    finalBody.checkout_bump_minor = Math.round(bumpAmount * 100);
    finalBody.checkout_subtotal_minor = Math.round(subtotal * 100);
    finalBody.checkout_total_minor = amountMinor;
    return {
      subtotal,
      discount,
      bumpAmount,
      total,
      quantity,
      paymentMethod,
      amountMinor,
      currency: hints.currency || "MAD",
    };
  }

  function buildFinalBody(root, cfg) {
    const fieldsMap = parseFieldsMap(root, cfg);
    const payload = collectFields(root, cfg, fieldsMap);
    payload.form_kind = cfg.form_kind || "email_ebook";
    payload.client_ts = (cfg.context && cfg.context.client_ts) || nowIso();
    if (payload.honeypot === undefined) payload.honeypot = "";
    if (payload.accept_terms === undefined) payload.accept_terms = true;
    if (!payload.course_slug) {
      if (cfg.context && cfg.context.product_slug) {
        payload.course_slug = cfg.context.product_slug;
      } else if (cfg.context && cfg.context.product_id) {
        payload.course_slug = String(cfg.context.product_id);
      }
    }

    const mergedCtx = Object.assign({}, (cfg.context || {}), pick(qsParams(), [
      "campaign", "source", "utm_source", "utm_medium", "utm_campaign"
    ]));

    const finalBody = Object.assign({}, payload);
    if (mergedCtx && Object.keys(mergedCtx).length) {
      finalBody.context = mergedCtx;
    } else if (finalBody.context !== undefined) {
      delete finalBody.context;
    }

    const hints = checkoutHintsFromDom(root);
    const checkout = enrichCheckout(root, finalBody, fieldsMap, hints);
    if (checkout) {
      updateCheckoutSummary(root, hints, checkout);
    }

    return { payload, mergedCtx, finalBody, checkout, fieldsMap, hints };
  }

  async function signBody(signUrl, finalBody) {
    const response = await fetch(signUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "X-CSRFToken": getCookie("csrftoken") || "",
      },
      body: JSON.stringify({ payload: finalBody }),
      credentials: "same-origin",
    });
    const data = await response.json().catch(() => ({}));
    if (window.DEBUG_FF) {
      console.debug("[ff] sign status", response.status, data);
    }
    if (!response.ok || !data.signed_token) {
      throw new Error("Signature échouée");
    }
    return data.signed_token;
  }

  function qsParams() {
    const p = new URLSearchParams(window.location.search || "");
    const o = {};
    for (const [k, v] of p.entries()) o[k] = v;
    return o;
  }

  function pick(o, keys) {
    const r = {};
    keys.forEach(k => { if (o[k] !== undefined) r[k] = o[k]; });
    return r;
  }

  function sanitizePhone(value) {
    const raw = String(value || "");
    const cleaned = raw.replace(/[^0-9+()\-\s]/g, "").replace(/(?!^)\+/g, "").trim();
    if (cleaned.startsWith("00")) {
      return "+" + cleaned.slice(2);
    }
    return cleaned;
  }

  function stepElements(root) {
    return $all(root, "[data-ff-step]");
  }

  function numericSteps(root) {
    return stepElements(root)
      .map(s => s.getAttribute("data-ff-step"))
      .filter(id => id && id !== "done")
      .map(id => parseInt(id, 10))
      .filter(n => Number.isFinite(n));
  }

  function getMaxStep(root) {
    const nums = numericSteps(root);
    return nums.length ? Math.max.apply(null, nums) : 1;
  }

  function getCurrentStep(root) {
    const panes = stepElements(root);
    const visible = panes.find(p => !p.classList.contains("d-none") && (p.getAttribute("data-ff-step") || "") !== "done");
    if (!visible) return 1;
    const idx = parseInt(visible.getAttribute("data-ff-step"), 10);
    return Number.isFinite(idx) ? idx : 1;
  }

  function updateProgress(root, targetId) {
    const prog = root.querySelector('[data-ff-progress]');
    if (!prog) return;
    const total = getMaxStep(root);
    if (targetId === "done") {
      prog.textContent = `Étape ${total} / ${total}`;
      return;
    }
    const cur = parseInt(targetId, 10);
    const safeCur = Number.isFinite(cur) ? cur : 1;
    prog.textContent = `Étape ${safeCur} / ${total}`;
  }

  function showStep(root, idxOrDone) {
    const target = String(idxOrDone);
    stepElements(root).forEach(s => {
      const stepId = String(s.getAttribute("data-ff-step") || "");
      s.classList.toggle("d-none", stepId !== target);
    });
    updateProgress(root, target);
  }

  function showFinalStep(root) {
    const finalNumeric = String(getMaxStep(root));
    const steps = stepElements(root);
    const hasNumeric = steps.some(s => String(s.getAttribute("data-ff-step") || "") === finalNumeric);
    if (hasNumeric) {
      showStep(root, finalNumeric);
      return;
    }
    const hasDone = steps.some(s => (s.getAttribute("data-ff-step") || "") === "done");
    if (hasDone) {
      showStep(root, "done");
      return;
    }
    showStep(root, finalNumeric);
  }

  function setBusy(root, busy) {
    if (!root) return;
    if (busy) root.setAttribute("data-ff-busy", "1"); else root.removeAttribute("data-ff-busy");
  }

  function setMsg(root, html) {
    const box = root.querySelector(".ff-form-msg");
    if (box) box.innerHTML = html || "";
  }

  function nowIso() {
    try { return new Date().toISOString(); } catch (_) { return ""; }
  }

  // ---------- noyau ----------
  async function handleSubmit(root, cfg) {
    const endpoint =
      cfg.endpoint_url ||
      (cfg.backend_config && cfg.backend_config.endpoint_url) ||
      "/api/leads/collect/";

    const requireIdem = cfg.require_idempotency !== false; // défaut: true
    const requireSigned = !!(cfg.require_signed_token || cfg.require_signed);
    const signUrl = cfg.sign_url || (cfg.backend_config && cfg.backend_config.sign_url) || "";

    const { payload, mergedCtx, finalBody, fieldsMap } = buildFinalBody(root, cfg);

    if (window.DEBUG_FF) {
      try {
        console.debug("[ff] payload", payload);
        console.debug("[ff] context", mergedCtx);
        console.debug("[ff] finalBody (signed+sent)", finalBody);
      } catch (_) {
        // ignore logging errors
      }
    }

    // 1) Signature si requise
    let signed_token = "";
    setBusy(root, true); setMsg(root, "");
    try {
      if (requireSigned) {
        if (!signUrl) throw new Error("Configuration de signature manquante");
        signed_token = await signBody(signUrl, finalBody);
      }

      const finalBodyToSend = Object.assign({}, finalBody, signed_token ? { signed_token } : {});
      const baseHeaders = {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "X-CSRFToken": getCookie("csrftoken") || "",
      };
      const paymentField = (fieldsMap && (fieldsMap.payment_method || fieldsMap.paymentMethod)) || "payment_method";
      const paymentMethod = (finalBody[paymentField] || "").toString().toLowerCase();

      if (paymentMethod === "online") {
        const checkoutUrl = root.getAttribute("data-checkout-url") || cfg.checkout_url || cfg.checkout_endpoint_url || "/api/checkout/sessions/";
        const checkoutHeaders = Object.assign({}, baseHeaders);
        if (requireIdem) checkoutHeaders["X-Idempotency-Key"] = "ff-" + uuid4();

        const checkoutRes = await fetch(checkoutUrl, {
          method: "POST",
          headers: checkoutHeaders,
          body: JSON.stringify(finalBodyToSend),
          credentials: "same-origin",
        });
        const checkoutTxt = await checkoutRes.text();
        if (window.DEBUG_FF) {
          console.debug("[ff] checkout status", checkoutRes.status, checkoutTxt);
        }
        if (checkoutRes.ok) {
          let session = null;
          try { session = checkoutTxt ? JSON.parse(checkoutTxt) : null; } catch (_) { session = null; }
          const redirectUrl = session && (session.url || session.redirect_url);
          if (redirectUrl) {
            window.location.href = redirectUrl;
            return;
          }
          showFinalStep(root);
          setMsg(root, "");
        } else {
          setMsg(root, "Une erreur est survenue. Merci de réessayer.");
          console.warn("[FlowForms] checkout failed:", checkoutRes.status, checkoutTxt);
        }
        return;
      }

      const headers = Object.assign({}, baseHeaders);
      if (requireIdem) headers["X-Idempotency-Key"] = "ff-" + uuid4();

      const r = await fetch(endpoint, {
        method: "POST",
        headers,
        body: JSON.stringify(finalBodyToSend),
        credentials: "same-origin",
      });

      const txt = await r.text();
      if (window.DEBUG_FF) {
        console.debug("[ff] collect status", r.status, txt);
      }
      if (r.ok) {
        let json = null;
        try { json = txt ? JSON.parse(txt) : null; } catch (_) { json = null; }
        const redirectUrl = json && (json.redirect_url || json.url);
        if (redirectUrl) {
          window.location.href = redirectUrl;
          return;
        }
        showFinalStep(root);
        setMsg(root, "");
      } else {
        // feedback simple — les détails sont en console
        setMsg(root, "Une erreur est survenue. Merci de réessayer.");
        console.warn("[FlowForms] collect failed:", r.status, txt);
      }
    } catch (err) {
      console.error("[FlowForms] submit error:", err);
      setMsg(root, "Une erreur est survenue. Merci de réessayer.");
    } finally {
      setBusy(root, false);
    }
  }

  function wireEvents(root) {
    const cfg = jsonFromConfigScript(root) || {};
    const progressActive = !!(
      cfg.progress_url ||
      (cfg.backend_config && cfg.backend_config.progress_url) ||
      (cfg.progress_steps && Object.keys(cfg.progress_steps).length)
    );

    const refreshCheckout = () => {
      try {
        const fieldsMap = parseFieldsMap(root, cfg);
        const payload = collectFields(root, cfg, fieldsMap);
        const finalBody = Object.assign({}, payload);
        const hints = checkoutHintsFromDom(root);
        const checkout = enrichCheckout(root, finalBody, fieldsMap, hints);
        if (checkout) updateCheckoutSummary(root, hints, checkout);
      } catch (err) {
        if (window.DEBUG_FF) console.warn("[ff] checkout refresh failed", err);
      }
    };

    refreshCheckout();

    root.addEventListener("click", async (e) => {
      const t = e.target;
      if (!t) return;
      if (t.closest("[data-ff-next]")) {
        e.preventDefault();
        const cur = getCurrentStep(root);
        const max = getMaxStep(root);
        if (progressActive && cur < max) {
          try {
            const res = await sendProgressUpdate(root, cfg, cur);
            if (window.DEBUG_FF) console.debug("[ff] progress", cur, res);
          } catch (err) {
            console.warn("[FlowForms] progress threw", err);
          }
        }
        const next = cur < max ? cur + 1 : max;
        showStep(root, next);
        setTimeout(refreshCheckout, 0);
      }
      if (t.closest("[data-ff-prev]")) {
        e.preventDefault();
        const cur = getCurrentStep(root);
        const prev = cur > 1 ? cur - 1 : 1;
        showStep(root, prev);
        setTimeout(refreshCheckout, 0);
      }
    });

    root.addEventListener("change", (event) => {
      const target = event.target;
      if (!target) return;
      if (target.matches("input, select, textarea")) {
        setTimeout(refreshCheckout, 0);
      }
    });

    root.addEventListener("input", (event) => {
      const target = event.target;
      if (!target) return;
      if (target.matches('[data-ff-field="quantity"], [name*="quantity"], input[type="number"], input[data-ff-cast="int"], input[data-ff-cast="float"]')) {
        setTimeout(refreshCheckout, 0);
      }
    });

    root.addEventListener("click", async (e) => {
      const btn = e.target && e.target.closest && e.target.closest("[data-ff-submit]");
      if (!btn) return;
      e.preventDefault();
      await handleSubmit(root, Object.assign({}, cfg));
    });
  }

  function init(root) {
    root = root || document.getElementById("ff-root") || document.querySelector("[data-ff-root]");
    if (!root) return;
    const params = new URLSearchParams(window.location.search || "");
    if (params.get("paid") === "1") {
      showFinalStep(root);
    } else if (root.querySelector('[data-ff-step="1"]')) {
      showStep(root, 1);
    }
    wireEvents(root);
  }

  // Boot idempotent
  function __ff_boot() {
    try {
      const roots = document.querySelectorAll("#ff-root, [data-ff-root]");
      if (!roots.length) return;
      roots.forEach(r => init(r));
    } catch (e) {
      console.error("[FlowForms] init failed:", e);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", __ff_boot, { once: true });
  } else {
    __ff_boot();
  }
})();
