(function () {
  "use strict";

  function initialize(root) {
    if (!root || root.__stepperPaymentInitialized) return;
    root.__stepperPaymentInitialized = true;

    const checkoutCfg = window.__CHECKOUT__ || {};
    const paymentNamespace = window.__StepperPayment__ = window.__StepperPayment__ || {};
    if (window.console && typeof window.console.info === 'function') {
      console.info('[stepper.payment] initialize', { hasCheckoutCfg: !!checkoutCfg });
    }
    if (typeof paymentNamespace.handleOnlineSubmit !== 'function') {
      paymentNamespace.handleOnlineSubmit = async function fallbackUnavailable() {
        return false;
      };
    }
    const publishableKey = checkoutCfg.stripePK || checkoutCfg.publishableKey;
    const intentUrl = (checkoutCfg.endpoints && checkoutCfg.endpoints.createIntent) || checkoutCfg.intent_url || checkoutCfg.intentUrl;
    const productSlug = checkoutCfg.productSlug || (function () {
      const hints = root.querySelector('[data-checkout-hints]');
      return hints && hints.dataset ? (hints.dataset.productSlug || "") : "";
    })();

    const paymentContainer = document.getElementById('af-payment-element');
    const paymentWrapper = document.getElementById('af-payment-online');
    const errorsNode = document.getElementById('af-payment-errors') || root.querySelector('.ff-form-msg');

    if (!intentUrl) {
      paymentNamespace.handleOnlineSubmit = async function unavailableOnlineSubmit() {
        if (errorsNode) {
          errorsNode.textContent = 'Paiement en ligne indisponible pour le moment.';
          errorsNode.classList.remove('text-success');
          errorsNode.classList.add('text-danger');
        }
        return false;
      };
      return;
    }

  function parseFieldsMap() {
    let datasetMap = {};
    const raw = root.getAttribute('data-fields-map');
    if (raw) {
      try { datasetMap = JSON.parse(raw); } catch (_) { datasetMap = {}; }
    }
    let scriptMap = {};
    const cfgScript = root.querySelector('script[data-ff-config]') || document.querySelector('script[data-ff-config]');
    if (cfgScript) {
      try {
        const parsed = JSON.parse(cfgScript.textContent || '{}');
        scriptMap = parsed.fields_map || parsed.fieldsMap || {};
      } catch (_) {
        scriptMap = {};
      }
    }
    return Object.assign({}, scriptMap, datasetMap);
  }

  const fieldsMap = parseFieldsMap();
  const paymentFieldName = fieldsMap.payment_mode || fieldsMap.payment_method || 'payment_method';

  function getCookie(name) {
    const match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
    return match ? decodeURIComponent(match[2]) : '';
  }

  const stripeAvailable = !!publishableKey && typeof window !== 'undefined' && typeof window.Stripe === 'function';
  let stripe = null;
  let elements = null;
  let paymentElement = null;
  let currentSecret = "";
  let latestIntentResponse = null;
  let selectionKey = "";
  let ensurePromise = null;

  function currentPackSlugFromDom() {
    const hidden = root.querySelector('[data-ff-pack-slug]');
    if (hidden && hidden.value) {
      return hidden.value;
    }
    const offerFieldName = fieldsMap.offer_key || fieldsMap.offer || 'offer_key';
    const checked = root.querySelector(`[name="${offerFieldName}"]:checked`);
    if (checked) {
      return checked.getAttribute('data-ff-pack-slug') || checked.value || '';
    }
    return checkoutCfg.defaultPackSlug || '';
  }

  const state = {
    selection: { packSlug: currentPackSlugFromDom(), complementarySlugs: [], paymentMode: 'online' },
    totals: null,
    generatedEmail: "",
  };

  function getEmail() {
    const primary = root.querySelector('[data-ff-email-primary]');
    const step3 = root.querySelector('#ff-email');
    const confirm = root.querySelector('[data-ff-email-confirm]');
    const candidates = [step3, primary, confirm];
    for (const el of candidates) {
      if (el && el.value && el.value.trim()) {
        return el.value.trim();
      }
    }
    return '';
  }

  function ensureEmailValue() {
    const explicit = getEmail();
    if (explicit) {
      state.generatedEmail = "";
      return explicit;
    }
    if (!state.generatedEmail) {
      state.generatedEmail = `guest+${Math.random().toString(16).slice(2)}@example.invalid`;
    }
    return state.generatedEmail;
  }

  function getFullName() {
    const node = root.querySelector('#ff-fullname');
    return node && node.value ? node.value.trim() : '';
  }

  function getPhone() {
    const node = root.querySelector('#ff-phone');
    return node && node.value ? node.value.trim() : '';
  }

  function getSessionKey() {
    const input = root.querySelector('[data-ff-session-key]');
    return (input && input.value) || '';
  }

  function getCurrency() {
    return (checkoutCfg.currency || (state.totals && state.totals.currency) || 'MAD').toUpperCase();
  }

  function setMessage(text, kind) {
    if (!errorsNode) return;
    errorsNode.textContent = text || '';
    if (kind === 'success') {
      errorsNode.classList.remove('text-danger');
      errorsNode.classList.add('text-success');
    } else {
      errorsNode.classList.remove('text-success');
      errorsNode.classList.add('text-danger');
    }
  }

  function showPaymentUI(show) {
    if (!paymentWrapper) return;
    if (show) {
      paymentWrapper.removeAttribute('hidden');
    } else {
      paymentWrapper.setAttribute('hidden', 'true');
    }
  }

  function readPaymentMode() {
    const selected = root.querySelector(`[name="${paymentFieldName}"]:checked`);
    return (selected && selected.value) || 'online';
  }

  function detachPaymentElement() {
    if (paymentElement) {
      try { paymentElement.unmount(); } catch (_) { /* ignore */ }
    }
    paymentElement = null;
    elements = null;
    currentSecret = '';
    latestIntentResponse = null;
    showPaymentUI(false);
  }

  function mountPaymentElement(secret) {
    if (!secret) return;
    if (!stripeAvailable) {
      currentSecret = secret;
      showPaymentUI(false);
      return;
    }
    if (!stripe) {
      stripe = Stripe(publishableKey);
    }
    if (!stripe) {
      console.warn('[stepper.payment] Stripe non disponible');
      return;
    }
    if (secret === currentSecret && paymentElement) {
      showPaymentUI(true);
      return;
    }
    currentSecret = secret;
    elements = stripe.elements({ clientSecret: secret, appearance: checkoutCfg.appearance || { theme: 'stripe' } });
    if (paymentElement) {
      try { paymentElement.unmount(); } catch (_) { /* ignore */ }
    }
    if (paymentContainer) {
      paymentElement = elements.create('payment');
      paymentElement.mount(paymentContainer);
      showPaymentUI(true);
    }
  }

  async function ensureIntent(force) {
    if (window.console && typeof window.console.info === 'function') {
      console.info('[stepper.payment] ensureIntent:start', { force, selection: state.selection });
    }
    if (!state.selection.packSlug) {
      state.selection.packSlug = currentPackSlugFromDom();
    }
    if (state.selection.paymentMode !== 'online') {
      detachPaymentElement();
      return null;
    }
    const email = ensureEmailValue();
    if (!email) {
      return null;
    }
    const key = [state.selection.packSlug, state.selection.complementarySlugs.slice().sort().join(','), email].join('::');
    if (latestIntentResponse && selectionKey === key) {
      mountPaymentElement(latestIntentResponse.clientSecret || latestIntentResponse.client_secret);
      return latestIntentResponse;
    }
    if (ensurePromise) {
      return ensurePromise;
    }
    if (!productSlug) {
      console.warn('[stepper.payment] product slug manquant');
      return null;
    }

    const payload = {
      checkout_kind: 'pack',
      product_slug: productSlug,
      pack_slug: state.selection.packSlug,
      complementary_slugs: state.selection.complementarySlugs,
      payment_mode: 'online',
      currency: getCurrency(),
      email,
      ff_session_key: getSessionKey(),
    };

    ensurePromise = fetch(intentUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
        'X-CSRFToken': getCookie('csrftoken'),
      },
      credentials: 'same-origin',
      body: JSON.stringify(payload),
    })
      .then(async (response) => {
        if (!response.ok) {
          const text = await response.text();
          throw new Error(`intent_failed_${response.status}: ${text}`);
        }
        return response.json();
      })
      .then((data) => {
        latestIntentResponse = data || {};
        selectionKey = key;
        const secret = data.clientSecret || data.client_secret;
        if (!secret) {
          throw new Error('intent_missing_client_secret');
        }
        if (window.console && typeof window.console.info === 'function') {
          console.info('[stepper.payment] ensureIntent:success', { selection: state.selection, orderId: data.orderId });
        }
        mountPaymentElement(secret);
        checkoutCfg.latestIntent = data;
        try {
          await fetch(intentUrl, {
            method: 'GET',
            credentials: 'same-origin',
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
          });
        } catch (_) {
          // ignore mirroring failure
        }
        return data;
      })
      .catch((err) => {
        console.warn('[stepper.payment] create intent failed', err);
        detachPaymentElement();
        setMessage('Impossible de préparer le paiement. Vérifiez vos informations ou réessayez.', 'error');
        latestIntentResponse = null;
        return null;
      })
      .finally(() => {
        ensurePromise = null;
      });

    return ensurePromise;
  }

  function handlePricingUpdate(detail) {
    const selection = detail && detail.selection ? detail.selection : {};
    state.selection = {
      packSlug: selection.packSlug || state.selection.packSlug || currentPackSlugFromDom(),
      complementarySlugs: selection.complementarySlugs || state.selection.complementarySlugs || [],
      paymentMode: selection.paymentMode || readPaymentMode() || 'online',
    };
    state.totals = detail && detail.totals ? detail.totals : state.totals;
    if (state.selection.paymentMode === 'online') {
      ensureIntent(false);
    } else {
      detachPaymentElement();
    }
  }

  root.addEventListener('af:pricing:changed', (event) => {
    handlePricingUpdate(event.detail || {});
  });

  root.addEventListener('change', (event) => {
    const target = event.target;
    if (!target) return;
    if (target.matches(`[name="${paymentFieldName}"]`)) {
      state.selection.paymentMode = readPaymentMode();
      if (state.selection.paymentMode === 'online') {
        ensureIntent(false);
      } else {
        detachPaymentElement();
      }
    }
    if (target.matches('[data-ff-email-primary], #ff-email, [data-ff-email-confirm]')) {
      if (state.selection.paymentMode === 'online') {
        ensureIntent(true);
      }
    }
  }, true);

  paymentNamespace.handleOnlineSubmit = async function handleOnlineSubmit(ctx) {
    if (window.console && typeof window.console.info === 'function') {
      console.info('[stepper.payment] handleOnlineSubmit');
    }
    state.selection.paymentMode = readPaymentMode();
    if (state.selection.paymentMode !== 'online') {
      return true;
    }
    const email = ensureEmailValue();
    if (!email) {
      setMessage('Merci de renseigner votre adresse e-mail avant de payer.', 'error');
      const focusTarget = root.querySelector('#ff-email') || root.querySelector('[data-ff-email-primary]');
      if (focusTarget) focusTarget.focus();
      return false;
    }
    try {
      const intent = await ensureIntent(true);
      if (!intent) {
        return false;
      }
    } catch (_) {
      return false;
    }

    let paymentIntent = null;
    let status = 'requires_confirmation';
    let fallbackAmount = 0;

    if (stripeAvailable) {
      if (!stripe || !elements || !paymentElement || !currentSecret) {
        setMessage('Paiement indisponible pour le moment, merci de réessayer.', 'error');
        return false;
      }

      const submitButton = root.querySelector('[data-ff-submit]');
      if (submitButton) submitButton.disabled = true;
      setMessage('', 'error');

      const billingDetails = {
        email,
        name: getFullName() || undefined,
      };
      const phone = getPhone();
      if (phone) billingDetails.phone = phone;

      let result;
      try {
        result = await stripe.confirmPayment({
          elements,
          confirmParams: {
            payment_method_data: {
              billing_details: billingDetails,
            },
          },
          redirect: 'if_required',
        });
      } catch (err) {
        if (submitButton) submitButton.disabled = false;
        console.error('[stepper.payment] confirmPayment error', err);
        setMessage('Le paiement a échoué. Merci de vérifier votre carte ou de réessayer.', 'error');
        return false;
      }

      if (submitButton) submitButton.disabled = false;

      if (result.error) {
        setMessage(result.error.message || 'Le paiement a été refusé.', 'error');
        return false;
      }

      paymentIntent = result.paymentIntent || (latestIntentResponse && latestIntentResponse.paymentIntent);
      if (!paymentIntent) {
        setMessage('Réponse de paiement inattendue.', 'error');
        return false;
      }
      status = paymentIntent.status;
      if (status !== 'succeeded' && status !== 'processing') {
        setMessage('Le paiement doit être confirmé. Merci de suivre les étapes demandées par votre banque.', 'error');
        return false;
      }
      fallbackAmount = paymentIntent.amount
        || (state.totals && (state.totals.total_cents || state.totals.total))
        || 0;
    } else {
      paymentIntent = latestIntentResponse && (latestIntentResponse.paymentIntent || {
        id: (latestIntentResponse.clientSecret || latestIntentResponse.client_secret || '').split('_secret')[0] || '',
        amount: latestIntentResponse.amount || latestIntentResponse.total_cents || 0,
        currency: (latestIntentResponse.currency || getCurrency()).toLowerCase(),
        status: 'requires_confirmation',
      });
      fallbackAmount = (paymentIntent && (paymentIntent.amount || latestIntentResponse.total_cents || latestIntentResponse.total || 0)) || 0;
      status = (paymentIntent && paymentIntent.status) || 'requires_confirmation';
      setMessage('', 'success');
    }

    if (ctx && ctx.finalBody) {
      ctx.finalBody.payment_status = status;
      ctx.finalBody.payment_amount = fallbackAmount;
      ctx.finalBody.payment_currency = (paymentIntent.currency || getCurrency()).toUpperCase();
      ctx.finalBody.stripe_payment_intent_id = paymentIntent.id || currentSecret;
      if (latestIntentResponse && latestIntentResponse.orderId) {
        ctx.finalBody.order_id = latestIntentResponse.orderId;
      }
      ctx.finalBody.payment_confirmed_at = new Date().toISOString();
      if (ctx.finalBodyToSend) {
        ctx.finalBodyToSend.payment_status = ctx.finalBody.payment_status;
        ctx.finalBodyToSend.payment_amount = ctx.finalBody.payment_amount;
        ctx.finalBodyToSend.payment_currency = ctx.finalBody.payment_currency;
        ctx.finalBodyToSend.stripe_payment_intent_id = ctx.finalBody.stripe_payment_intent_id;
        if (ctx.finalBody.order_id) ctx.finalBodyToSend.order_id = ctx.finalBody.order_id;
        ctx.finalBodyToSend.payment_confirmed_at = ctx.finalBody.payment_confirmed_at;
      }
    }

    await new Promise((resolve) => {
      setTimeout(resolve, 500);
    });

    return true;
  };

    // Boot: attempt to prepare payment if already on online mode
    if (readPaymentMode() === 'online') {
      ensureIntent(false);
    }
  }

  function boot() {
    const roots = document.querySelectorAll('[data-ff-root]');
    if (!roots.length) return;
    roots.forEach((root) => {
      initialize(root);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot, { once: true });
  } else {
    boot();
  }
})();
