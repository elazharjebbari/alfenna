(function () {
  "use strict";

  const configCache = new WeakMap();

  function moneyToInt(text) {
    if (text === undefined || text === null) return 0;
    const normalized = String(text)
      .replace(/\u2212/g, "-")
      .replace(/\u00A0|\u202F/g, " ")
      .trim();
    if (!normalized) return 0;
    const match = normalized.match(/-?\d+(?:[.,]\d+)?/);
    if (!match) return 0;
    const value = parseFloat(match[0].replace(",", "."));
    return Number.isFinite(value) ? Math.round(value) : 0;
  }

  function intToTextMAD(value, currency) {
    const cur = currency || "MAD";
    const safe = Number.isFinite(value) ? value : 0;
    return `${safe} ${cur}`;
  }

  function getRoot(root) {
    if (root && root.hasAttribute && root.hasAttribute("data-ff-root")) return root;
    return document.querySelector("[data-ff-root]");
  }

  function getConfig(root) {
    root = getRoot(root);
    if (!root) return {};
    if (configCache.has(root)) {
      return configCache.get(root) || {};
    }
    const node = root.querySelector('script[data-ff-config]');
    if (!node) {
      configCache.set(root, {});
      return {};
    }
    try {
      const cfg = JSON.parse(node.textContent || "{}") || {};
      configCache.set(root, cfg);
      return cfg;
    } catch (err) {
      console.warn("[stepper.pricing] unable to parse config", err);
      configCache.set(root, {});
      return {};
    }
  }

  function getFieldsMap(root) {
    const cfg = getConfig(root);
    return (cfg.fields_map || cfg.fieldsMap || {});
  }

  function selectorForName(name) {
    if (!name) return "";
    const safe = String(name).replace(/"/g, '\\"');
    return `[name="${safe}"]`;
  }

  function getOfferField(root) {
    const fm = getFieldsMap(root);
    return fm.offer || fm.offer_key || fm.offerKey || "offer_key";
  }

  function getQuantityField(root) {
    const fm = getFieldsMap(root);
    return fm.quantity || "quantity";
  }

  function getCurrencyFallback(root) {
    const field = root && root.querySelector && root.querySelector('[data-ff-currency-field]');
    if (field && field.value) return field.value;
    const hints = root && root.querySelector && root.querySelector('[data-checkout-hints]');
    if (hints && hints.dataset && hints.dataset.currency) return hints.dataset.currency;
    return "MAD";
  }

  function getOnlineDiscount(root) {
    const hints = root && root.querySelector && root.querySelector('[data-checkout-hints]');
    if (hints && hints.dataset && hints.dataset.onlineDiscount) {
      const fromDataset = moneyToInt(hints.dataset.onlineDiscount);
      if (fromDataset) {
        return Math.abs(fromDataset);
      }
    }
    const el = root && root.querySelector && root.querySelector("#af-online-discount");
    if (!el) return 20;
    const fromText = moneyToInt(el.textContent || "");
    return fromText ? Math.abs(fromText) : 20;
  }

  function isPaymentOnline(root) {
    const radio = root && root.querySelector && root.querySelector('section[data-ff-step="3"] .af-pay-option.is-online input[type="radio"]');
    if (!radio) return true;
    return !!radio.checked;
  }

  function readQuantity(root) {
    const fieldName = getQuantityField(root);
    const node = root && root.querySelector && root.querySelector(selectorForName(fieldName));
    let value = node ? parseInt(node.value, 10) : NaN;
    if (!Number.isFinite(value) || value <= 0) {
      const fallback = root && root.querySelector && root.querySelector('[data-ff-quantity-default]');
      const fallbackVal = fallback ? parseInt(fallback.value, 10) : NaN;
      value = Number.isFinite(fallbackVal) && fallbackVal > 0 ? fallbackVal : 1;
    }
    return value;
  }

  function getSelectedOffer(root, offerField) {
    if (!offerField) return null;
    const selector = selectorForName(offerField) + ':checked';
    return root && root.querySelector && root.querySelector(selector);
  }

  function getBumpInput(root) {
    return root && root.querySelector && root.querySelector('#af-bump-optin');
  }

  function computePricing(root) {
    root = getRoot(root);
    if (!root) return null;

    const offerField = getOfferField(root);
    const selectedOffer = getSelectedOffer(root, offerField);
    const quantity = readQuantity(root);

    const packCurrency = (selectedOffer && (selectedOffer.dataset.ffPackCurrency || selectedOffer.dataset.currency)) || getCurrencyFallback(root);
    const packUnitPrice = selectedOffer ? moneyToInt(selectedOffer.dataset.ffPackPrice) : 0;
    const normalizedPackPrice = Number.isFinite(packUnitPrice) ? packUnitPrice : 0;
    const packSlug = selectedOffer ? (selectedOffer.dataset.ffPackSlug || selectedOffer.value || "") : "";

    const bumpInput = getBumpInput(root);
    const bumpUnitRaw = bumpInput ? moneyToInt(bumpInput.dataset.ffComplementaryPrice) : 0;
    const bumpUnitPrice = Number.isFinite(bumpUnitRaw) ? bumpUnitRaw : 0;
    const bumpCurrency = (bumpInput && (bumpInput.dataset.ffComplementaryCurrency || bumpInput.dataset.currency)) || packCurrency;
    const bumpSelected = !!(bumpInput && bumpInput.checked && bumpUnitPrice);
    const bumpTotal = bumpSelected ? bumpUnitPrice : 0;

    const onlineDiscountRaw = getOnlineDiscount(root);
    const onlineDiscount = Number.isFinite(onlineDiscountRaw) ? Math.max(onlineDiscountRaw, 0) : 0;
    const paymentMode = isPaymentOnline(root) ? "online" : "cod";

    const packTotal = Math.max(normalizedPackPrice * quantity, 0);
    const subtotal = Math.max(packTotal + bumpTotal, 0);
    const appliedDiscount = Math.min(onlineDiscount, subtotal);
    const step2Discount = -appliedDiscount;
    const step2Total = Math.max(subtotal + step2Discount, 0);
    const step3Discount = paymentMode === "online" ? step2Discount : 0;
    const step3Total = Math.max(subtotal + step3Discount, 0);

    const currency = packCurrency || bumpCurrency || getCurrencyFallback(root);

    return {
      root,
      offerField,
      pack: {
        slug: packSlug,
        unitPrice: normalizedPackPrice,
        total: packTotal,
        currency,
      },
      bump: {
        unitPrice: bumpUnitPrice,
        total: bumpTotal,
        currency: bumpCurrency || currency,
        selected: bumpSelected,
      },
      discount: {
        online: appliedDiscount,
        currency,
      },
      quantity,
      subtotal,
      totals: {
        step2: {
          subtotal,
          discount: step2Discount,
          total: step2Total,
        },
        step3: {
          subtotal,
          discount: step3Discount,
          total: step3Total,
          paymentMode,
        },
      },
      paymentMode,
      currency,
    };
  }

  function setText(node, text) {
    if (!node) return;
    node.textContent = text;
  }

  function applyTotals(root, state) {
    if (!root || !state || !state.totals) return;
    const currency = state.currency || state.pack.currency || state.discount.currency || getCurrencyFallback(root);
    const step2 = state.totals.step2 || {};
    const step3 = state.totals.step3 || step2;

    const subNode = root.querySelector('#af-subtotal');
    const discNode = root.querySelector('#af-discount');
    const totNode = root.querySelector('#af-total');
    const s3Sub = root.querySelector('#af-step3-subtotal');
    const s3Disc = root.querySelector('#af-step3-discount');
    const s3Tot = root.querySelector('#af-step3-total');

    setText(subNode, intToTextMAD(Math.round(step2.subtotal || 0), currency));
    setText(discNode, intToTextMAD(Math.round(step2.discount || 0), currency));
    setText(totNode, intToTextMAD(Math.round(step2.total || 0), currency));

    setText(s3Sub, intToTextMAD(Math.round(step3.subtotal || 0), currency));
    setText(s3Disc, intToTextMAD(Math.round(step3.discount || 0), currency));
    setText(s3Tot, intToTextMAD(Math.round(step3.total || 0), currency));
  }

  function recalc(root) {
    root = getRoot(root);
    if (!root) return null;
    const state = computePricing(root);
    if (!state) return null;
    root.__afPricingState = state;
    window.__afPricingState = state;
    applyTotals(root, state);
    try {
      root.dispatchEvent(new CustomEvent('af:pricing:changed', { detail: state }));
    } catch (_) {
      // ignore
    }
    return state;
  }

  function handleChange(event) {
    const target = event.target;
    if (!target) return;
    const root = target.closest('[data-ff-root]');
    if (!root) return;
    const offerSelector = selectorForName(getOfferField(root));
    const quantitySelector = selectorForName(getQuantityField(root));

    if (target.matches('input[type="radio"], input[type="checkbox"]')) {
      if (offerSelector && target.matches('[name]') && target.matches(offerSelector)) {
          if (typeof window.ffSyncPackFields === 'function') window.ffSyncPackFields();
          recalc(root);
          return;
      }
      if (target.id === 'af-bump-optin') {
        if (typeof window.ffSyncComplementary === 'function') window.ffSyncComplementary();
        recalc(root);
        return;
      }
      if (target.closest('.af-pay-option')) {
        if (typeof window.ffSyncPaymentField === 'function') window.ffSyncPaymentField();
        recalc(root);
        return;
      }
    }

    if (quantitySelector && target.matches(quantitySelector)) {
      recalc(root);
      return;
    }
    if (target.hasAttribute('data-ff-field') && target.getAttribute('data-ff-field') === 'quantity') {
      recalc(root);
    }
  }

  function handleInput(event) {
    const target = event.target;
    if (!target) return;
    const root = target.closest('[data-ff-root]');
    if (!root) return;
    const quantitySelector = selectorForName(getQuantityField(root));
    if ((quantitySelector && target.matches(quantitySelector)) || target.getAttribute('data-ff-field') === 'quantity') {
      recalc(root);
    }
  }

  function handleClick(event) {
    const target = event.target;
    if (!target) return;
    const root = target.closest('[data-ff-root]');
    if (!root) return;
    if (target.closest('[data-ff-next],[data-ff-prev]')) {
      setTimeout(() => recalc(root), 30);
    }
  }

  function boot() {
    const root = getRoot();
    if (!root) return;
    recalc(root);
    root.addEventListener('change', handleChange, true);
    root.addEventListener('input', handleInput, true);
    root.addEventListener('click', handleClick, true);
  }

  window.ffComputePricingTotals = computePricing;
  window.ffApplyPricingTotals = applyTotals;
  window.ffRecalcPricing = recalc;

  if (document.readyState === 'interactive' || document.readyState === 'complete') {
    setTimeout(boot, 0);
  } else {
    document.addEventListener('DOMContentLoaded', boot, { once: true });
  }
})();
