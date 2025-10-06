(function () {
  'use strict';

  if (window.__LL_ANALYTICS_INIT__) {
    return;
  }
  window.__LL_ANALYTICS_INIT__ = true;

  var doc = document;
  if (!doc) {
    return;
  }

  var body = doc.body || doc.documentElement;
  var CONSENT_COOKIE = (body && body.dataset && body.dataset.llConsentCookie) || 'cookie_consent_marketing';
  var API_ENDPOINT = '/api/analytics/collect/';
  var BATCH_SIZE = 15;
  var MAX_QUEUE = 100;
  var FLUSH_INTERVAL_MS = 4000;
  var HEATMAP_SAMPLE_RATE = 0.2;
  var PAGE_SLOT_ID = '__page__';

  var CONSENT_TRUE_SET = ['1', 'true', 'yes', 'y', 'on', 'accept'];
  var VALID_EVENT_TYPES = { view: true, click: true, scroll: true, heatmap: true };
  var MAX_ID_LENGTH = 128;

  function safeString(value, maxLen) {
    if (value === null || value === undefined) {
      return '';
    }
    var str = String(value).trim();
    if (!str) {
      return '';
    }
    if (maxLen && str.length > maxLen) {
      return str.slice(0, maxLen);
    }
    return str;
  }

  function defaultPageId() {
    if (state.pageId) {
      return state.pageId;
    }
    var attr = body.getAttribute('data-page-id') || body.getAttribute('data-ll-page') || '';
    if (attr && attr.trim()) {
      return safeString(attr, MAX_ID_LENGTH);
    }
    var path = (window.location && window.location.pathname) || '/';
    var slug = path.replace(/[^a-zA-Z0-9_-]+/g, '-').replace(/^-+|-+$/g, '');
    if (!slug) {
      slug = 'page';
    }
    return safeString(slug, MAX_ID_LENGTH);
  }

  function isoTimestamp(value) {
    if (!value) {
      return nowIso();
    }
    if (value instanceof Date) {
      if (isNaN(value.getTime())) {
        return nowIso();
      }
      return value.toISOString();
    }
    if (typeof value === 'number') {
      if (!isFinite(value)) {
        return nowIso();
      }
      return new Date(value).toISOString();
    }
    var parsed = new Date(value);
    if (isNaN(parsed.getTime())) {
      return nowIso();
    }
    return parsed.toISOString();
  }

  function eventSource(input) {
    if (!input) {
      return null;
    }
    if (input.detail && typeof input.detail === 'object') {
      return input.detail;
    }
    return input;
  }

  function deriveEventType(source) {
    var raw = source.event_type || source.event || source.type || source.name;
    if (!raw) {
      return '';
    }
    var eventType = String(raw).trim().toLowerCase();
    if (VALID_EVENT_TYPES[eventType]) {
      return eventType;
    }
    return '';
  }

  function sanitizePayload(payload) {
    if (!payload || typeof payload !== 'object') {
      return {};
    }
    var clean = {};
    Object.keys(payload).forEach(function (key) {
      var val = payload[key];
      if (val !== undefined) {
        clean[key] = val;
      }
    });
    return clean;
  }

  function normalizePayload(eventType, source) {
    var payload = sanitizePayload(source.payload);
    if (eventType === 'scroll') {
      var raw = source.scroll_pct;
      if (raw === undefined || raw === null) {
        raw = payload.scroll_pct;
      }
      if (raw === undefined || raw === null) {
        return null;
      }
      var pct = Number(raw);
      if (!isFinite(pct)) {
        return null;
      }
      payload.scroll_pct = clamp(pct, 0, 100);
    } else if (eventType === 'heatmap') {
      var rawX = source.x;
      if (rawX === undefined || rawX === null) {
        rawX = payload.x;
      }
      var rawY = source.y;
      if (rawY === undefined || rawY === null) {
        rawY = payload.y;
      }
      if (rawX === undefined || rawX === null || rawY === undefined || rawY === null) {
        return null;
      }
      var xNum = Number(rawX);
      var yNum = Number(rawY);
      if (!isFinite(xNum) || !isFinite(yNum)) {
        return null;
      }
      payload.x = clamp(xNum, 0, 1);
      payload.y = clamp(yNum, 0, 1);
      if (payload.sample_rate !== undefined) {
        var sr = Number(payload.sample_rate);
        if (!isFinite(sr)) {
          delete payload.sample_rate;
        } else {
          payload.sample_rate = sr;
        }
      }
    }
    return payload;
  }

  function normalizeEvent(input) {
    var source = eventSource(input);
    if (!source || typeof source !== 'object') {
      return null;
    }
    var eventType = deriveEventType(source);
    if (!eventType) {
      return null;
    }
    var pageId = safeString(source.page_id || source.page || state.pageId || defaultPageId(), MAX_ID_LENGTH);
    if (!pageId) {
      return null;
    }
    state.pageId = pageId;
    if (source.site_version || source.siteVersion) {
      state.siteVersion = safeString(source.site_version || source.siteVersion, 48);
    } else if (!state.siteVersion) {
      state.siteVersion = safeString(body.getAttribute('data-ll-site-version') || 'core', 48);
    }
    if (source.request_id || source.requestId) {
      state.requestId = safeString(source.request_id || source.requestId, 64);
    }

    var payload = normalizePayload(eventType, source);
    if (payload === null) {
      return null;
    }

    var slotId = safeString(source.slot_id || source.slot || '', MAX_ID_LENGTH);
    var alias = safeString(source.component_alias || source.alias || '', MAX_ID_LENGTH);

    return {
      event_uuid: safeString(source.event_uuid || '', 64) || uuid(),
      event_type: eventType,
      ts: isoTimestamp(source.ts),
      page_id: pageId,
      slot_id: slotId,
      component_alias: alias,
      payload: payload
    };
  }

  function readCookie(name) {
    var match = (typeof document.cookie === 'string' ? document.cookie : '').match(new RegExp('(?:^|; )' + name.replace(/([.$?*|{}()\[\]\\\/\+^])/g, '\\$1') + '=([^;]*)'));
    return match ? decodeURIComponent(match[1]) : '';
  }

  function hasConsent() {
    var val = readCookie(CONSENT_COOKIE).toLowerCase();
    return CONSENT_TRUE_SET.indexOf(val) !== -1;
  }

  if (!hasConsent()) {
    return;
  }

  var state = {
    queue: [],
    flushing: false,
    flushTimer: null,
    viewed: new Set(),
    scrollMarks: new Set(),
    pageId: '',
    siteVersion: '',
    requestId: '',
  };

  function uuid() {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) {
      return crypto.randomUUID();
    }
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
      var r = Math.random() * 16 | 0;
      var v = c === 'x' ? r : (r & 0x3 | 0x8);
      return v.toString(16);
    });
  }

  function nowIso() {
    return (new Date()).toISOString();
  }

  function clamp(num, min, max) {
    if (num < min) { return min; }
    if (num > max) { return max; }
    return num;
  }

  function baseFromElement(el) {
    var out = {
      page_id: state.pageId,
      slot_id: '',
      component_alias: '',
      site_version: state.siteVersion,
      request_id: state.requestId,
      variant: '',
    };
    if (!el || !el.dataset) {
      return out;
    }
    if (el.dataset.llPage) {
      state.pageId = el.dataset.llPage;
      out.page_id = el.dataset.llPage;
    }
    if (el.dataset.llSiteVersion) {
      state.siteVersion = el.dataset.llSiteVersion;
      out.site_version = el.dataset.llSiteVersion;
    }
    if (el.dataset.llRequestId) {
      state.requestId = el.dataset.llRequestId;
      out.request_id = el.dataset.llRequestId;
    }
    out.slot_id = el.dataset.llSlot || '';
    out.component_alias = el.dataset.llAlias || '';
    out.variant = el.dataset.llVariant || '';
    return out;
  }

  function autoMarkClickables(container) {
    if (!container || !container.querySelectorAll) {
      return;
    }
    var alias = (container.dataset && (container.dataset.llAlias || container.dataset.llSlot)) || 'cta';
    var nodes = container.querySelectorAll('a, button');
    Array.prototype.forEach.call(nodes, function (node, idx) {
      if (!node || !node.dataset) {
        return;
      }
      if (node.dataset.llClick) {
        return;
      }
      var text = (node.textContent || '').trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40);
      var id = alias + '-' + (text || (node.tagName || 'el').toLowerCase()) + '-' + idx;
      node.dataset.llClick = id;
    });
  }

  function enqueue(input) {
    var event = normalizeEvent(input);
    if (!event) {
      return null;
    }
    state.queue.push(event);
    if (typeof window !== 'undefined') {
      window.__LL_DEBUG_ENQUEUED__ = window.__LL_DEBUG_ENQUEUED__ || [];
      try {
        window.__LL_DEBUG_ENQUEUED__.push(JSON.parse(JSON.stringify(event)));
      } catch (err) {
        window.__LL_DEBUG_ENQUEUED__.push(Object.assign({}, event));
      }
    }
    if (state.queue.length > MAX_QUEUE) {
      state.queue = state.queue.slice(state.queue.length - MAX_QUEUE);
    }
    if (state.queue.length >= BATCH_SIZE) {
      flushQueue();
    } else if (!state.flushTimer) {
      state.flushTimer = setTimeout(flushQueue, FLUSH_INTERVAL_MS);
    }
    return event;
  }

  var dataLayer = window.dataLayer = window.dataLayer || [];
  if (!dataLayer.__llWrapped) {
    var dlListeners = typeof Set === 'function' ? new Set() : [];
    var originalPush = dataLayer.push.bind(dataLayer);

    function dispatchCustomEvent(payload) {
      if (typeof window === 'undefined') {
        return;
      }
      try {
        var evt = new window.CustomEvent('datalayer:push', { detail: payload });
        window.dispatchEvent(evt);
        return;
      } catch (err) {
        if (document && document.createEvent) {
          var fallback = document.createEvent('CustomEvent');
          fallback.initCustomEvent('datalayer:push', false, false, payload);
          window.dispatchEvent(fallback);
        }
      }
    }

    function notifyListeners(payload) {
      if (!payload) {
        return;
      }
      if (dlListeners instanceof Set) {
        dlListeners.forEach(function (listener) {
          try {
            listener(payload);
          } catch (err) {
            if (console && console.debug) {
              console.debug('datalayer listener error', err);
            }
          }
        });
      } else {
        for (var i = 0; i < dlListeners.length; i += 1) {
          var fn = dlListeners[i];
          if (typeof fn === 'function') {
            try {
              fn(payload);
            } catch (err) {
              if (console && console.debug) {
                console.debug('datalayer listener error', err);
              }
            }
          }
        }
      }
      dispatchCustomEvent(payload);
    }

    dataLayer.on = function (listener) {
      if (typeof listener !== 'function') {
        return function () {};
      }
      if (dlListeners instanceof Set) {
        dlListeners.add(listener);
      } else {
        dlListeners.push(listener);
      }
      return function () {
        if (dlListeners instanceof Set) {
          dlListeners.delete(listener);
        } else {
          for (var i = dlListeners.length - 1; i >= 0; i -= 1) {
            if (dlListeners[i] === listener) {
              dlListeners.splice(i, 1);
            }
          }
        }
      };
    };

    dataLayer.push = function () {
      var args = Array.prototype.slice.call(arguments);
      var result = originalPush.apply(dataLayer, args);
      if (args.length) {
        var payload = args[args.length - 1];
        if (payload && typeof payload === 'object') {
          var normalized = enqueue(payload);
          if (normalized) {
            notifyListeners(normalized);
          }
        }
      }
      return result;
    };

    dataLayer.__llWrapped = true;

    if (dataLayer.length) {
      var seed = dataLayer.slice();
      dataLayer.length = 0;
      for (var i = 0; i < seed.length; i += 1) {
        dataLayer.push(seed[i]);
      }
    }
  }

  function sendBatch(events) {
    var payload = JSON.stringify({ events: events });
    if (navigator.sendBeacon) {
      try {
        var ok = navigator.sendBeacon(API_ENDPOINT, new Blob([payload], { type: 'application/json' }));
        if (ok) {
          return Promise.resolve(true);
        }
      } catch (err) {
        // sendBeacon failed, fallback to fetch below
      }
    }
    return fetch(API_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: payload,
      keepalive: true,
      credentials: 'same-origin'
    }).then(function () { return true; }).catch(function () { return false; });
  }

 function flushQueue() {
    if (state.flushing) {
      return;
    }
    if (state.flushTimer) {
      clearTimeout(state.flushTimer);
      state.flushTimer = null;
    }
    if (!state.queue.length) {
      return;
    }
    var events = state.queue.slice();
    state.queue.length = 0;
    if (events.length) {
      if (typeof window !== 'undefined') {
        window.__LL_DEBUG_EVENTS__ = window.__LL_DEBUG_EVENTS__ || [];
        Array.prototype.push.apply(window.__LL_DEBUG_EVENTS__, events);
      }
    }
    state.flushing = true;
    sendBatch(events).finally(function () {
      state.flushing = false;
    });
  }

  function recordView(entry, el) {
    if (!el || !el.dataset) {
      return;
    }
    var inst = el.dataset.llInst;
    if (!inst || state.viewed.has(inst)) {
      return;
    }
    state.viewed.add(inst);
    var base = baseFromElement(el);
    enqueue({
      event_type: 'view',
      page_id: base.page_id,
      slot_id: base.slot_id,
      component_alias: base.component_alias,
      site_version: base.site_version,
      request_id: base.request_id,
      payload: {
        variant: base.variant,
        visibility_ratio: entry && typeof entry.intersectionRatio === 'number' ? Math.round(entry.intersectionRatio * 100) / 100 : 1,
        viewport_height: window.innerHeight || 0,
      }
    });
  }

  function setupIntersectionObserver() {
    if (!('IntersectionObserver' in window)) {
      var nodes = doc.querySelectorAll('[data-ll="comp"]');
      for (var i = 0; i < nodes.length; i += 1) {
        autoMarkClickables(nodes[i]);
        recordView(null, nodes[i]);
      }
      return;
    }
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          recordView(entry, entry.target);
        }
      });
    }, { threshold: [0.2, 0.5, 0.75] });
    var current = doc.querySelectorAll('[data-ll="comp"]');
    Array.prototype.forEach.call(current, function (el) {
      observer.observe(el);
      autoMarkClickables(el);
    });

    var mo = new MutationObserver(function (mutations) {
      mutations.forEach(function (mutation) {
        mutation.addedNodes.forEach(function (node) {
          if (!(node instanceof HTMLElement)) {
            return;
          }
          if (node.matches && node.matches('[data-ll="comp"]')) {
            observer.observe(node);
            autoMarkClickables(node);
          }
          if (node.querySelectorAll) {
            var matches = node.querySelectorAll('[data-ll="comp"]');
            Array.prototype.forEach.call(matches, function (el) {
              observer.observe(el);
              autoMarkClickables(el);
            });
          }
        });
      });
    });
    mo.observe(doc.documentElement, { childList: true, subtree: true });
  }

  function handleClick(evt) {
    var target = evt.target instanceof Element ? evt.target : null;
    var container = target ? target.closest('[data-ll="comp"]') : null;
    var base = baseFromElement(container);

    var clickable = target ? target.closest('[data-ll-click]') : null;
    if (clickable) {
      var text = clickable.textContent || '';
      enqueue({
        event_type: 'click',
        page_id: base.page_id,
        slot_id: base.slot_id,
        component_alias: base.component_alias,
        site_version: base.site_version,
        request_id: base.request_id,
        payload: {
          click_id: clickable.dataset.llClick || '',
          tag: clickable.tagName || '',
          text: text.trim().slice(0, 120),
        }
      });
    }

    if (Math.random() <= HEATMAP_SAMPLE_RATE) {
      var vw = window.innerWidth || 1;
      var vh = window.innerHeight || 1;
      var relX = clamp(evt.clientX / vw, 0, 1);
      var relY = clamp(evt.clientY / vh, 0, 1);
      enqueue({
        event_type: 'heatmap',
        page_id: base.page_id,
        slot_id: base.slot_id,
        component_alias: base.component_alias,
        site_version: base.site_version,
        request_id: base.request_id,
        payload: {
          x: Math.round(relX * 10000) / 10000,
          y: Math.round(relY * 10000) / 10000,
          sample_rate: HEATMAP_SAMPLE_RATE,
        }
      });
    }
  }

  var scrollMarks = [25, 50, 75, 90, 100];
  var scrollTick = false;

  function handleScroll() {
    if (scrollTick) {
      return;
    }
    scrollTick = true;
    (window.requestAnimationFrame || window.setTimeout)(function () {
      scrollTick = false;
      var docEl = document.documentElement || document.body;
      var scrollTop = window.pageYOffset || docEl.scrollTop || 0;
      var height = (docEl.scrollHeight || 0) - (window.innerHeight || 0);
      if (height <= 0) {
        return;
      }
      var ratio = clamp(scrollTop / height, 0, 1) * 100;
      for (var i = 0; i < scrollMarks.length; i += 1) {
        var mark = scrollMarks[i];
        if (ratio >= mark && !state.scrollMarks.has(mark)) {
          state.scrollMarks.add(mark);
          enqueue({
            event_type: 'scroll',
            page_id: state.pageId,
            slot_id: PAGE_SLOT_ID,
            component_alias: PAGE_SLOT_ID,
            site_version: state.siteVersion,
            request_id: state.requestId,
            payload: {
              scroll_pct: mark,
              page_path: window.location.pathname + window.location.search,
            }
          });
        }
      }
    });
  }

  function setupListeners() {
    document.addEventListener('click', handleClick, true);
    window.addEventListener('scroll', handleScroll, { passive: true });
    window.addEventListener('beforeunload', flushQueue, { passive: true });
    window.addEventListener('visibilitychange', function () {
      if (document.visibilityState === 'hidden') {
        flushQueue();
      }
    });
    window.addEventListener('pagehide', flushQueue, { passive: true });
  }

 setupIntersectionObserver();
  setupListeners();
  if (typeof window !== 'undefined') {
    window.__LL_DEBUG_FLUSH = flushQueue;
  }
})();
