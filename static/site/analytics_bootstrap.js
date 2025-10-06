(function () {
  'use strict';

  var w = window;
  var d = document;
  var booted = false;
  var TRUE_VALUES = ['1', 'true', 'yes', 'y', 'on', 'accept'];

  function readCookie(name) {
    if (!name || !d || !d.cookie) {
      return '';
    }
    var pattern = '(?:^|; )' + name.replace(/([.$?*|{}()\[\]\\/+^])/g, '\\$1') + '=([^;]*)';
    var match = d.cookie.match(new RegExp(pattern));
    return match ? decodeURIComponent(match[1]) : '';
  }

  function hasTrue(value) {
    if (value === null || value === undefined) {
      return false;
    }
    var normalized = String(value).trim().toLowerCase();
    return TRUE_VALUES.indexOf(normalized) !== -1;
  }

  function consentCookieName() {
    var body = d.body || d.documentElement;
    if (body && body.dataset && body.dataset.llConsentCookie) {
      return body.dataset.llConsentCookie;
    }
    return 'cookie_consent_marketing';
  }

  function analyticsScriptSrc() {
    if (w.__LL_ANALYTICS_SRC__) {
      return String(w.__LL_ANALYTICS_SRC__);
    }
    var body = d.body || d.documentElement;
    if (body && body.dataset && body.dataset.llAnalyticsSrc) {
      return body.dataset.llAnalyticsSrc;
    }
    return '/static/site/analytics.js';
  }

  function loadAnalytics() {
    if (booted) {
      return;
    }
    booted = true;
    var target = d.head || d.getElementsByTagName('head')[0] || d.body || d.documentElement;
    if (!target) {
      return;
    }
    var script = d.createElement('script');
    script.src = analyticsScriptSrc();
    script.defer = true;
    script.setAttribute('data-ll-analytics-loader', 'bootstrapped');
    target.appendChild(script);
  }

  function handleEntry(entry) {
    if (!entry || typeof entry !== 'object') {
      return;
    }
    if (entry.event !== 'll_consent_update') {
      return;
    }
    var state = entry.analytics_storage;
    if (typeof state === 'string' && state.toLowerCase() === 'granted') {
      loadAnalytics();
    }
  }

  function processEntries(entries) {
    if (!entries || !entries.length) {
      return;
    }
    for (var i = 0; i < entries.length; i += 1) {
      try {
        handleEntry(entries[i]);
      } catch (err) {}
    }
  }

  try {
    if (hasTrue(readCookie(consentCookieName()))) {
      loadAnalytics();
    }
  } catch (err) {}

  var dataLayer = w.dataLayer = w.dataLayer || [];
  processEntries(dataLayer);

  var originalPush = dataLayer.push;
  if (typeof originalPush !== 'function') {
    originalPush = Array.prototype.push;
  }

  dataLayer.push = function () {
    var args = Array.prototype.slice.call(arguments);
    var result = originalPush.apply(dataLayer, args);
    for (var i = 0; i < args.length; i += 1) {
      try {
        handleEntry(args[i]);
      } catch (err) {}
    }
    return result;
  };
})();
