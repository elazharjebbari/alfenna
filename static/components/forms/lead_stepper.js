(function () {
  function onReady(cb) {
    if (document.readyState !== "loading") {
      cb();
    } else {
      document.addEventListener("DOMContentLoaded", cb, { once: true });
    }
  }

  function select(root, selector) {
    return root.querySelector(selector);
  }

  function selectAll(root, selector) {
    return Array.from(root.querySelectorAll(selector));
  }

  function uuidv4() {
    if (window.crypto && typeof window.crypto.getRandomValues === "function") {
      const buffer = new Uint8Array(16);
      window.crypto.getRandomValues(buffer);
      buffer[6] = (buffer[6] & 0x0f) | 0x40;
      buffer[8] = (buffer[8] & 0x3f) | 0x80;
      return Array.from(buffer, (byte, index) => {
        const hex = byte.toString(16).padStart(2, "0");
        return (index === 4 || index === 6 || index === 8 || index === 10) ? "-" + hex : hex;
      }).join("");
    }
    const now = Date.now().toString(16);
    return `fallback-${now}-${Math.random().toString(16).slice(2, 10)}`;
  }

  function sanitizePhone(value) {
    const raw = String(value || "");
    const cleaned = raw.replace(/[^0-9+()\-\s]/g, "").replace(/(?!^)\+/g, "").trim();
    if (cleaned.startsWith("00")) {
      return "+" + cleaned.slice(2);
    }
    return cleaned;
  }

  function getConfig(form) {
    const dataset = form.dataset;
    let fieldsMap = {};
    try {
      fieldsMap = JSON.parse(dataset.fieldsMap || "{}") || {};
    } catch (err) {
      fieldsMap = {};
    }
    return {
      steps: parseInt(dataset.steps || "3", 10) || 3,
      actionUrl: form.getAttribute("action") || dataset.actionUrl || "",
      requireSigned: (dataset.requireSigned || "").toLowerCase() === "true",
      signUrl: dataset.signUrl || "",
      fieldsMap,
    };
  }

  function currentStep(form) {
    return parseInt(form.dataset.currentStep || "1", 10) || 1;
  }

  function showStep(form, step) {
    selectAll(form, ".step-pane").forEach((pane) => {
      const isCurrent = String(pane.dataset.step) === String(step);
      pane.classList.toggle("d-none", !isCurrent);
    });
    form.dataset.currentStep = String(step);
  }

  function validateStep(scope) {
    const required = selectAll(scope, "input[required], select[required], textarea[required]");
    for (const field of required) {
      if (!String(field.value || "").trim()) {
        field.classList.add("is-invalid");
        return { ok: false, message: "Complétez les champs requis." };
      }
      field.classList.remove("is-invalid");
    }

    const phoneField = scope.querySelector('input[inputmode="tel"], input[type="tel"]');
    if (phoneField) {
      phoneField.value = sanitizePhone(phoneField.value);
      if (phoneField.value.replace(/\D/g, "").length < 6) {
        phoneField.classList.add("is-invalid");
        return { ok: false, message: "Numéro de téléphone invalide." };
      }
    }

    return { ok: true };
  }

  function readField(form, logicalKey, fieldsMap) {
    const name = fieldsMap[logicalKey] || logicalKey;
    const element = form.querySelector(`[name="${name}"]`);
    return element ? element.value : undefined;
  }

  function buildPayload(form, config) {
    const map = config.fieldsMap || {};
    const payload = {
      form_kind: "contact_full",
      full_name: readField(form, "fullname", map) || "",
      phone: readField(form, "phone", map) || "",
      address: readField(form, "address", map) || "",
      quantity: readField(form, "quantity", map) || undefined,
      offer_key: readField(form, "offer", map) || undefined,
      product: readField(form, "product", map) || undefined,
      promotion_selected: readField(form, "promotion", map) || undefined,
      consent: true,
      context: {},
    };

    Object.keys(payload).forEach((key) => {
      if (payload[key] === undefined || payload[key] === "") {
        delete payload[key];
      }
    });

    return payload;
  }

  async function signPayload(signUrl, payload) {
    const response = await fetch(signUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify({ payload }),
    });

    if (!response.ok) {
      throw new Error(`sign_failed:${response.status}`);
    }

    const data = await response.json().catch(() => ({}));
    if (!data || !data.signed_token) {
      throw new Error("sign_invalid_response");
    }
    return data.signed_token;
  }

  async function collectLead(actionUrl, payload, signedToken) {
    const body = Object.assign({}, payload, signedToken ? { signed_token: signedToken } : null);
    const headers = {
      "Content-Type": "application/json",
      "X-Requested-With": "XMLHttpRequest",
      "X-Idempotency-Key": uuidv4(),
    };

    const response = await fetch(actionUrl, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });

    const output = { status: response.status, data: null };
    try {
      output.data = await response.json();
    } catch (err) {
      output.data = null;
    }
    return output;
  }

  function handleError(message) {
    if (window.Swal && typeof window.Swal.fire === "function") {
      window.Swal.fire("", message, "error");
    }
  }

  function attachStepper(form) {
    const config = getConfig(form);
    const totalSteps = config.steps || 3;
    showStep(form, 1);

    form.addEventListener("click", async (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) {
        return;
      }

      if (target.hasAttribute("data-next")) {
        const pane = select(form, `.step-pane[data-step="${currentStep(form)}"]`);
        const result = validateStep(pane || form);
        if (!result.ok) {
          const message = result.message || "Merci de corriger les champs";
          if (window.Swal && typeof window.Swal.fire === "function") {
            window.Swal.fire("", message, "warning");
          }
          return;
        }

        if (
          target.hasAttribute("data-submit-final") &&
          totalSteps === 3 &&
          currentStep(form) === 2
        ) {
          try {
            const payload = buildPayload(form, config);
            const frozenPayload = JSON.parse(JSON.stringify(payload));
            let signedToken = null;

            if (config.requireSigned) {
              if (!config.signUrl) {
                throw new Error("sign_url_missing");
              }
              signedToken = await signPayload(config.signUrl, frozenPayload);
            }

            const actionUrl = config.actionUrl || form.getAttribute("action") || "";
            if (!actionUrl) {
              throw new Error("collect_url_missing");
            }

            const { status, data } = await collectLead(actionUrl, frozenPayload, signedToken);
            const success = status === 202 || (status === 200 && data && (data.ok || data.status === "ok"));

            if (success) {
              showStep(form, 3);
              return;
            }

            const issues = [];
            if (data && data.errors) {
              Object.entries(data.errors).forEach(([field, messages]) => {
                (messages || []).forEach((message) => {
                  if (typeof message === "string") {
                    issues.push(`${field}: ${message}`);
                  } else if (message && message.message) {
                    issues.push(`${field}: ${message.message}`);
                  }
                });
              });
            }
            const errorMessage =
              (data && (data.detail || data.message)) ||
              issues.join("\n") ||
              "Soumission impossible.";
            handleError(errorMessage);
          } catch (error) {
            const message = (error && error.message) || "Erreur";
            if (message.startsWith("sign_failed")) {
              handleError("Signature indisponible. Merci de réessayer.");
            } else if (message === "sign_invalid_response") {
              handleError("Réponse de signature invalide.");
            } else if (message === "sign_url_missing") {
              handleError("Signature non configurée.");
            } else if (message === "collect_url_missing") {
              handleError("URL de collecte manquante.");
            } else {
              handleError("Erreur lors de l’envoi. Merci de réessayer.");
            }
          }
          return;
        }

        const stepValue = currentStep(form);
        if (stepValue < totalSteps) {
          showStep(form, stepValue + 1);
        }
      }

      if (target.hasAttribute("data-prev")) {
        const stepValue = currentStep(form);
        if (stepValue > 1) {
          showStep(form, stepValue - 1);
        }
      }
    });

    form.addEventListener("submit", (event) => {
      if (totalSteps === 3 && currentStep(form) !== 3) {
        event.preventDefault();
      }
    });
  }

  onReady(() => {
    document.querySelectorAll("[data-form-stepper]").forEach(attachStepper);
  });
})();
