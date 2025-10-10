(function () {
  "use strict";

  function $(root, sel) { return root.querySelector(sel); }
  function $all(root, sel) { return Array.from(root.querySelectorAll(sel)); }

  function parseConfig(root) {
    const node = root.querySelector('script[data-ff-config]');
    if (!node) { console.error("[FF] data-ff-config introuvable sous data-ff-root"); return null; }
    try { const cfg = JSON.parse(node.textContent || "{}"); console.debug("[FF] config", cfg); return cfg; }
    catch (e) { console.error("[FF] config JSON invalide", e); return null; }
  }

  function currentStep(root) {
    const steps = $all(root, '[data-ff-step]');
    const idx = steps.findIndex(s => !s.classList.contains('d-none'));
    return idx >= 0 ? idx + 1 : 1;
  }

  function gotoStep(root, n) {
    const steps = $all(root, '[data-ff-step]');
    steps.forEach((s, i) => s.classList.toggle('d-none', i + 1 !== n));
    const pills = $all(document, '.af-stepper .af-pill');
    pills.forEach((pill, i) => pill.classList.toggle('is-active', i + 1 === n));
  }

  function ensureSessionKey(root, cfg) {
    const name = (cfg.progress_session_field_name || "ff_session_key");
    let input = $(root, `input[name="${name}"]`);
    if (!input) { input = document.createElement('input'); input.type="hidden"; input.name=name; root.appendChild(input); }
    let val = (input.value || "").trim();
    if (!val) {
      const storageKey = cfg.progress_session_storage_key || "ff_session";
      try {
        val = localStorage.getItem(storageKey) || "";
        if (!val) { val = (crypto && crypto.randomUUID ? crypto.randomUUID() : String(Date.now())); localStorage.setItem(storageKey, val); }
      } catch { val = String(Date.now()); }
      input.value = val;
    }
    console.debug("[FF] ff_session_key", val);
    return val;
  }

  function idempotencyKey(cfg, ffSessionKey, stepIdx) {
    const flowKey = cfg.flow_key || "checkout_intent_flow";
    const key = `flow:${flowKey}:${ffSessionKey}:step:${stepIdx}`;
    console.debug("[FF] X-Idempotency-Key", key);
    return key;
  }

  function findInputsByName(root, name) { return $all(root, `[name="${CSS.escape(name)}"]`); }

  function valueOf(root, name) {
    const inputs = findInputsByName(root, name);
    if (!inputs.length) return undefined;
    if (inputs[0].type === "radio") { const c = inputs.find(i=>i.checked); return c ? c.value : ""; }
    if (inputs[0].type === "checkbox") { const vals = inputs.filter(i=>i.checked).map(i=>i.value || "1"); return vals.length <= 1 ? (vals[0] || "") : vals; }
    if (inputs.length > 1) return inputs.map(i=>i.value).filter(Boolean);
    return inputs[0].value;
  }

  function clearInvalid(input) {
    input.classList.remove("is-invalid");
    const fb = input.parentNode && input.parentNode.querySelector(".invalid-feedback");
    if (fb) fb.style.display = "none";
  }

  function markInvalid(input, message) {
    input.classList.add("is-invalid");
    let fb = input.parentNode && input.parentNode.querySelector(".invalid-feedback");
    if (!fb) { fb = document.createElement("div"); fb.className="invalid-feedback"; input.parentNode && input.parentNode.appendChild(fb); }
    fb.style.display = "block";
    fb.textContent = message || "Champ requis.";
  }

  function validateStep(root, cfg, stepIdx) {
    const stepKey = `step${stepIdx}`;
    const required = (cfg.progress_steps && cfg.progress_steps[stepKey]) || [];
    console.debug("[FF] validate", stepKey, required);
    const missing = [];
    required.forEach((name) => {
      const inputs = findInputsByName(root, name);
      if (!inputs.length) { console.warn("[FF] champ déclaré mais introuvable dans le DOM:", name); return; }
      inputs.forEach(clearInvalid);
      const val = valueOf(root, name);
      const empty = (val === undefined || val === null || val === "" || (Array.isArray(val) && val.length === 0));
      if (empty) { markInvalid(inputs[0], "Ce champ est requis."); missing.push(name); }
    });
    if (missing.length) console.warn("[FF] missing", missing);
    return missing;
  }

  function collectStepPayload(root, cfg, stepIdx) {
    const stepKey = `step${stepIdx}`;
    const names = (cfg.progress_steps && cfg.progress_steps[stepKey]) || [];
    const data = {};
    names.forEach((name) => { const v = valueOf(root, name); if (v !== undefined) data[name] = v; });
    data.form_kind = cfg.form_kind || "checkout_intent";
    data.flow_key = cfg.flow_key || "checkout_intent_flow";
    data.ff_session_key = ensureSessionKey(root, cfg);
    console.debug("[FF] payload", stepKey, data);
    return data;
  }

  function syncDerived(root) {
    if (window.ffSyncPackFields) { try { window.ffSyncPackFields(); } catch (e) { console.error("[FF] ffSyncPackFields error", e); } }
  }

  async function postProgress(root, cfg, stepIdx, payload) {
    const ffSessionKey = payload.ff_session_key;
    const idem = idempotencyKey(cfg, ffSessionKey, stepIdx);
    const url = cfg.progress_url || "/api/leads/progress/";
    console.debug("[FF] POST", url);
    const res = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Idempotency-Key": idem
      },
      body: JSON.stringify(payload)
    });
    const json = await res.json().catch(()=> ({}));
    console.debug("[FF] response", res.status, json);
    if (!res.ok) {
      const errors = json && json.errors ? json.errors : {};
      Object.entries(errors).forEach(([name, msg]) => {
        const inputs = findInputsByName(root, name);
        if (inputs && inputs.length) markInvalid(inputs[0], Array.isArray(msg) ? msg[0] : String(msg));
      });
      const msgNode = root.querySelector(".ff-form-msg");
      if (msgNode && json.message) msgNode.textContent = json.message;
      throw new Error("progress failed");
    }
    return json;
  }

  function bind(root) {
    const cfg = parseConfig(root);
    if (!cfg) return;
    console.debug("[FF] bind on", root);

    root.addEventListener("click", async function (ev) {
      const btnNext = ev.target.closest("[data-ff-next]");
      const btnPrev = ev.target.closest("[data-ff-prev]");
      if (!btnNext && !btnPrev) return;

      ev.preventDefault();
      ev.stopPropagation();

      if (btnPrev) { gotoStep(root, Math.max(1, currentStep(root) - 1)); return; }

      const stepIdx = currentStep(root);
      syncDerived(root);
      const missing = validateStep(root, cfg, stepIdx);
      if (missing.length) return;

      const payload = collectStepPayload(root, cfg, stepIdx);
      const ffSessionKey = payload.ff_session_key;
      const idem = idempotencyKey(cfg, ffSessionKey, stepIdx);
      payload._idempotency_key = idem;
      btnNext.disabled = true;
      try { await postProgress(root, cfg, stepIdx, payload); gotoStep(root, stepIdx + 1); }
      catch { /* erreurs déjà rendues et loguées */ }
      finally { btnNext.disabled = false; }
    }, true);
  }

  document.addEventListener("DOMContentLoaded", function () {
    const forms = $all(document, 'form[data-ff-root]');
    console.debug("[FF] forms found", forms.length);
    forms.forEach(bind);
  });
})();
