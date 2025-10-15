(function () {
  "use strict";

  const configCache = new WeakMap();
  const checkoutCfg = (typeof window !== 'undefined' && window.__CHECKOUT__) ? window.__CHECKOUT__ : {};

  let cachedProductSlug = checkoutCfg.productSlug || '';
  let previewUrlCache = null;
  let previewController = null;
  let latestPreviewKey = '';
  let initialTotalsApplied = false;

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

  function centsToUnits(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return 0;
    return Math.round(number / 100);
  }

  function formatCurrency(value, currency) {
    const safeCurrency = (currency || 'MAD').toUpperCase();
    const number = Number(value);
    const normalized = Number.isFinite(number) ? number : 0;
    const formatted = normalized.toLocaleString('fr-FR', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
    const withUnicodeMinus = normalized < 0 ? formatted.replace('-', '\u2212') : formatted;
    return `${withUnicodeMinus} ${safeCurrency}`;
  }

  function getRoot(root) {
    if (root && root.hasAttribute && root.hasAttribute('data-ff-root')) return root;
    return document.querySelector('[data-ff-root]');
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
      const cfg = JSON.parse(node.textContent || '{}') || {};
      configCache.set(root, cfg);
      return cfg;
    } catch (err) {
      console.warn('[stepper.pricing] unable to parse config', err);
      configCache.set(root, {});
      return {};
    }
  }

  function getFieldsMap(root) {
    const cfg = getConfig(root);
    return (cfg.fields_map || cfg.fieldsMap || {});
  }

  function selectorForName(name) {
    if (!name) return '';
    const safe = String(name).replace(/"/g, '\\"');
    return `[name="${safe}"]`;
  }

  function getOfferField(root) {
    const fm = getFieldsMap(root);
    return fm.offer || fm.offer_key || fm.offerKey || 'offer_key';
  }

  function getQuantityField(root) {
    const fm = getFieldsMap(root);
    return fm.quantity || 'quantity';
  }

  function getCurrencyFallback(root) {
    const field = root && root.querySelector && root.querySelector('[data-ff-currency-field]');
    if (field && field.value) return field.value;
    const hints = root && root.querySelector && root.querySelector('[data-checkout-hints]');
    if (hints && hints.dataset && hints.dataset.currency) return hints.dataset.currency;
    return checkoutCfg.currency || 'MAD';
  }

  function getOnlineDiscount(root) {
    const hints = root && root.querySelector && root.querySelector('[data-checkout-hints]');
    if (hints && hints.dataset && hints.dataset.onlineDiscount) {
      const fromDataset = moneyToInt(hints.dataset.onlineDiscount);
      if (fromDataset) {
        return Math.abs(fromDataset);
      }
    }
    const el = root && root.querySelector && root.querySelector('#af-online-discount');
    if (!el) return 20;
    const fromText = moneyToInt(el.textContent || '');
    return fromText ? Math.abs(fromText) : 20;
  }

  function isPaymentOnline(root) {
    const radio = root && root.querySelector && root.querySelector('section[data-ff-step="3"] .af-pay-option.is-online input[type="radio"]');
    if (!radio) return true;
    return !!radio.checked;
  }

  function readComplementarySlugs(root) {
    const nodes = root && root.querySelectorAll ? root.querySelectorAll('[data-ff-complementary]') : [];
    const result = [];
    nodes.forEach((node) => {
      const el = /** @type {HTMLElement} */ (node);
      if (el.matches('input[type="checkbox"], input[type="radio"]')) {
        if (!el.checked) return;
      } else if ((el.getAttribute('aria-pressed') || '') !== 'true') {
        return;
      }
      const slug = el.getAttribute('data-ff-complementary-slug') || el.getAttribute('value') || '';
      if (slug) {
        result.push(slug.trim());
      }
    });
    return result;
  }

  function getBumpInput(root) {
    return root && root.querySelector && root.querySelector('#af-bump-optin');
  }

  function ensureProductSlug(root) {
    if (cachedProductSlug) return cachedProductSlug;
    const hints = root && root.querySelector && root.querySelector('[data-checkout-hints]');
    if (hints && hints.dataset && hints.dataset.productSlug) {
      cachedProductSlug = hints.dataset.productSlug;
      return cachedProductSlug;
    }
    const productField = root && root.querySelector && root.querySelector('[data-ff-product]');
    if (productField && productField.value) {
      cachedProductSlug = productField.value;
    }
    return cachedProductSlug || '';
  }

  function getPreviewUrl() {
    if (previewUrlCache !== null) return previewUrlCache;
    const endpoints = checkoutCfg.endpoints || {};
    previewUrlCache = endpoints.preview || endpoints.previewTotals || checkoutCfg.previewUrl || '';
    return previewUrlCache;
  }

  function getCookie(name) {
    const match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
    return match ? decodeURIComponent(match[2]) : '';
  }

  function setText(node, text) {
    if (!node) return;
    node.textContent = text;
  }

  function applyTotals(root, state) {
    if (!root || !state || !state.totals) return;
    const currency = state.totals.currency || state.currency || getCurrencyFallback(root);
    const step2 = state.totals.step2 || {};
    const step3 = state.totals.step3 || step2;

    const subNode = root.querySelector('#af-subtotal');
    const discNode = root.querySelector('#af-discount');
    const totNode = root.querySelector('#af-total');
    const s3Sub = root.querySelector('#af-step3-subtotal');
    const s3Disc = root.querySelector('#af-step3-discount');
    const s3Tot = root.querySelector('#af-step3-total');

    setText(subNode, formatCurrency(step2.subtotal ?? 0, currency));
    setText(discNode, formatCurrency(step2.discount ?? 0, currency));
    setText(totNode, formatCurrency(step2.total ?? 0, currency));

    setText(s3Sub, formatCurrency(step3.subtotal ?? 0, currency));
    setText(s3Disc, formatCurrency(step3.discount ?? 0, currency));
    setText(s3Tot, formatCurrency(step3.total ?? 0, currency));
  }

  function applyServerTotals(root, state, preview) {
    if (!state || !preview || typeof preview !== 'object') return false;

    const subtotalCents = Number(preview.subtotal ?? preview.subtotal_cents ?? (preview.cents && preview.cents.subtotal) ?? 0);
    const discountCents = Number(preview.discount ?? preview.discount_cents ?? (preview.cents && preview.cents.discount) ?? 0);
    const totalCents = Number(preview.total ?? preview.total_cents ?? (preview.cents && preview.cents.total) ?? Math.max(subtotalCents - discountCents, 0));
    const availableDiscountCents = Number(
      preview.available_discount ?? preview.availableDiscount ?? (preview.cents && preview.cents.available_discount) ?? discountCents,
    );
    const currency = (preview.currency || state.currency || getCurrencyFallback(root) || 'MAD').toUpperCase();

    const subtotalUnits = centsToUnits(subtotalCents);
    const onlineDiscountUnits = centsToUnits(Math.min(availableDiscountCents, subtotalCents));
    const appliedDiscountUnits = centsToUnits(Math.min(discountCents, subtotalCents));
    const totalOnlineUnits = Math.max(subtotalUnits - onlineDiscountUnits, 0);
    const totalAppliedUnits = Math.max(subtotalUnits - appliedDiscountUnits, 0);

    const paymentMode = (preview.payment_mode || preview.paymentMode || state.selection.paymentMode || 'online').toLowerCase();

    state.currency = currency;
    state.subtotal = subtotalUnits;
    state.discount = state.discount || {};
    state.discount.online = onlineDiscountUnits;
    state.discount.currency = currency;

    state.selection.paymentMode = paymentMode;
    state.selection.subtotalCents = subtotalCents;
    state.selection.totalCents = totalCents;
    state.selection.discountCents = discountCents;
    state.selection.availableDiscountCents = availableDiscountCents;
    state.selection.currency = currency;
    state.selection.subtotalUnits = subtotalUnits;
    state.selection.totalUnits = state.totals.step3.total;

    state.totals = state.totals || {};
    state.totals.currency = currency;
    state.totals.step2 = {
      subtotal: subtotalUnits,
      discount: -onlineDiscountUnits,
      total: totalOnlineUnits,
    };
    state.totals.step3 = {
      subtotal: subtotalUnits,
      discount: -appliedDiscountUnits,
      total: paymentMode === 'online' ? totalOnlineUnits : totalAppliedUnits,
      paymentMode,
    };
    state.totals.subtotal = subtotalUnits;
    state.totals.discount = state.totals.step3.discount;
    state.totals.total = state.totals.step3.total;
    state.totals.cents = {
      subtotal: subtotalCents,
      discount: discountCents,
      total: totalCents,
      available_discount: availableDiscountCents,
    };
    state.totals.subtotal_cents = subtotalCents;
    state.totals.discount_cents = discountCents;
    state.totals.total_cents = totalCents;

    if (preview.pack) {
      state.pack = state.pack || {};
      state.pack.slug = preview.pack.slug || state.pack.slug;
      state.pack.currency = (preview.pack.currency || currency).toUpperCase();
      state.pack.unitPrice = centsToUnits(preview.pack.amount || 0);
      state.pack.total = state.pack.unitPrice * (preview.pack.quantity || 1);
      state.pack.title = preview.pack.title || state.pack.title;
    }

    if (Array.isArray(preview.complementaries)) {
      state.complementaries = preview.complementaries.map((line) => ({
        slug: line.slug,
        title: line.title,
        amount: centsToUnits(line.amount || 0),
        currency: (line.currency || currency).toUpperCase(),
        quantity: line.quantity || 1,
      }));
    }

    state.server = {
      response: preview,
      cents: state.totals.cents,
    };

    return true;
  }

  function finalizeState(root, state) {
    if (!root || !state) return state;
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

  function maybeApplyInitialTotals(root, state) {
    if (initialTotalsApplied) return false;
    const totals = checkoutCfg.totals;
    if (!totals) return false;
    const defaultPackSlug = (checkoutCfg.pack && checkoutCfg.pack.slug) || checkoutCfg.defaultPackSlug || state.selection.packSlug;
    if (defaultPackSlug && state.selection.packSlug && state.selection.packSlug !== defaultPackSlug) {
      return false;
    }
    const preview = {
      subtotal: totals.subtotal,
      discount: totals.discount,
      total: totals.total,
      currency: checkoutCfg.currency || getCurrencyFallback(root),
      available_discount: totals.discount,
      payment_mode: 'online',
      pack: checkoutCfg.pack || null,
      complementaries: checkoutCfg.complementaries || [],
    };
    initialTotalsApplied = true;
    applyServerTotals(root, state, preview);
    finalizeState(root, state);
    return true;
  }

  function previewSelectionKey(productSlug, selection) {
    const parts = [
      productSlug || '',
      selection.packSlug || '',
      (selection.complementarySlugs || []).slice().sort().join(','),
      selection.paymentMode || 'online',
    ];
    return parts.join('|');
  }

  function fetchPreviewForState(root, state, productSlug, previewUrl) {
    if (!previewUrl) {
      finalizeState(root, state);
      return;
    }
    if (!productSlug || !state.selection.packSlug) {
      finalizeState(root, state);
      return;
    }

    const selection = state.selection;
    const key = previewSelectionKey(productSlug, selection);
    latestPreviewKey = key;

    if (previewController) {
      try { previewController.abort(); } catch (_) { /* ignore */ }
    }
    previewController = new AbortController();

    const payload = {
      product_slug: productSlug,
      pack_slug: selection.packSlug,
      complementary_slugs: selection.complementarySlugs || [],
      payment_mode: selection.paymentMode || 'online',
      currency: (checkoutCfg.currency || state.currency || getCurrencyFallback(root)).toUpperCase(),
    };

    fetch(previewUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
        'X-CSRFToken': getCookie('csrftoken'),
      },
      credentials: 'same-origin',
      signal: previewController.signal,
      body: JSON.stringify(payload),
    })
      .then((response) => {
        if (!response.ok) {
          return response.text().then((text) => {
            throw new Error(`preview_failed_${response.status}: ${text}`);
          });
        }
        return response.json();
      })
      .then((data) => {
        if (latestPreviewKey !== key) return;
        applyServerTotals(root, state, data || {});
        finalizeState(root, state);
      })
      .catch((err) => {
        if (err && err.name === 'AbortError') return;
        console.warn('[stepper.pricing] preview fetch failed', err);
        if (!state.server) {
          finalizeState(root, state);
        }
      });
  }

  function computePricing(root) {
    root = getRoot(root);
    if (!root) return null;

    const offerField = getOfferField(root);
    const selectedOffer = offerField ? root.querySelector(selectorForName(offerField) + ':checked') : null;
    const quantityField = getQuantityField(root);
    const quantityNode = quantityField ? root.querySelector(selectorForName(quantityField)) : null;
    let quantity = quantityNode ? parseInt(quantityNode.value, 10) : NaN;
    if (!Number.isFinite(quantity) || quantity <= 0) {
      const fallback = root.querySelector('[data-ff-quantity-default]');
      const fallbackVal = fallback ? parseInt(fallback.value, 10) : NaN;
      quantity = Number.isFinite(fallbackVal) && fallbackVal > 0 ? fallbackVal : 1;
    }

    const packCurrency = (selectedOffer && (selectedOffer.dataset.ffPackCurrency || selectedOffer.dataset.currency)) || getCurrencyFallback(root);
    const packUnitPrice = selectedOffer ? moneyToInt(selectedOffer.dataset.ffPackPrice) : 0;
    const normalizedPackPrice = Number.isFinite(packUnitPrice) ? packUnitPrice : 0;
    const packSlug = selectedOffer ? (selectedOffer.dataset.ffPackSlug || selectedOffer.value || '') : '';
    const packTitle = selectedOffer ? (selectedOffer.dataset.ffPackTitle || selectedOffer.getAttribute('data-ff-pack-title') || '') : '';

    const complementarySlugs = readComplementarySlugs(root);
    const bumpInput = getBumpInput(root);
    const bumpUnitRaw = bumpInput ? moneyToInt(bumpInput.dataset.ffComplementaryPrice) : 0;
    const bumpUnitPrice = Number.isFinite(bumpUnitRaw) ? bumpUnitRaw : 0;
    const bumpCurrency = (bumpInput && (bumpInput.dataset.ffComplementaryCurrency || bumpInput.dataset.currency)) || packCurrency;
    const bumpSelected = !!(bumpInput && bumpInput.checked && bumpUnitPrice);
    const bumpTotal = bumpSelected ? bumpUnitPrice : 0;

    const onlineDiscountRaw = getOnlineDiscount(root);
    const onlineDiscount = Number.isFinite(onlineDiscountRaw) ? Math.max(onlineDiscountRaw, 0) : 0;
    const paymentMode = isPaymentOnline(root) ? 'online' : 'cod';

    const packTotal = Math.max(normalizedPackPrice * quantity, 0);
    const subtotal = Math.max(packTotal + bumpTotal, 0);
    const appliedDiscount = Math.min(onlineDiscount, subtotal);
    const step2Discount = -appliedDiscount;
    const step2Total = Math.max(subtotal + step2Discount, 0);
    const step3Discount = paymentMode === 'online' ? step2Discount : 0;
    const step3Total = Math.max(subtotal + step3Discount, 0);

    const currency = packCurrency || bumpCurrency || getCurrencyFallback(root);

    return {
      root,
      offerField,
      pack: {
        slug: packSlug,
        unitPrice: normalizedPackPrice,
        total: subtotal,
        currency,
        title: packTitle,
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
        subtotal,
        discount: step3Discount,
        total: step3Total,
        currency,
      },
      paymentMode,
      currency,
      selection: {
        packSlug,
        complementarySlugs,
        paymentMode,
        quantity,
      },
    };
  }

  function recalc(root) {
    root = getRoot(root);
    if (!root) return null;

    const state = computePricing(root);
    if (!state) return null;

    const productSlug = ensureProductSlug(root);
    const previewUrl = getPreviewUrl();

    const usedInitial = maybeApplyInitialTotals(root, state);

    if (!previewUrl || !productSlug || !state.selection.packSlug) {
      if (!usedInitial) {
        finalizeState(root, state);
      }
      return state;
    }

    fetchPreviewForState(root, state, productSlug, previewUrl);
    if (!usedInitial && !state.server) {
      // Ensure UI does not stay stale while waiting for the first response
      applyTotals(root, state);
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
      if (target.hasAttribute('data-ff-complementary')) {
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
