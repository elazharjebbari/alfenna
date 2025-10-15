/* eslint-disable no-console */
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

function createWindowContext(consentValue) {
  const dispatched = [];
  function CustomEvent(type, init) {
    this.type = type;
    this.detail = init ? init.detail : undefined;
  }
  function noop() {}
  const document = {
    cookie: consentValue ? `cookie_consent_marketing=${consentValue}` : "",
    body: {
      getAttribute(name) {
        if (name === "data-ll-consent-cookie") return "cookie_consent_marketing";
        if (name === "data-ll-analytics-enabled") return "1";
        return "";
      },
    },
    documentElement: { scrollHeight: 0, clientHeight: 0, scrollTop: 0 },
    querySelectorAll() {
      return [];
    },
    addEventListener: noop,
    removeEventListener: noop,
    readyState: "loading",
    createEvent() {
      return {
        initCustomEvent(type, _bubbles, _cancelable, detail) {
          this.type = type;
          this.detail = detail;
        },
      };
    },
  };
  const window = {
    __dlDebug: false,
    document,
    console: { debug() {} },
    dispatchEvent(evt) {
      dispatched.push(evt);
    },
    addEventListener: noop,
    removeEventListener: noop,
  };
  window.window = window;
  window.CustomEvent = CustomEvent;
  const context = {
    window,
    document,
    CustomEvent,
    setTimeout: noop,
    clearTimeout: noop,
    navigator: {
      sendBeacon: noop,
    },
    fetch: noop,
  };
  window.setTimeout = context.setTimeout;
  window.clearTimeout = context.clearTimeout;
  window.navigator = context.navigator;
  window.fetch = context.fetch;
  vm.createContext(context);
  const source = fs.readFileSync(path.join(__dirname, "analytics.js"), "utf8");
  vm.runInContext(source, context);
  return { window, dispatched };
}

(function runTests() {
  const { window, dispatched } = createWindowContext("yes");
  assert.ok(window.dataLayer, "dataLayer should exist when consent=Y");
  const dl = window.dataLayer;
  const baseLength = dl.length;

  let listenerCalls = 0;
  let lastListenerEvent = null;
  const unsubscribe = dl.on(function (evt) {
    listenerCalls += 1;
    lastListenerEvent = evt;
  });

  const newLength = dl.push({ event_type: "view", page_id: "home" });
  assert.strictEqual(newLength, baseLength + 1, "push should return new length");
  assert.strictEqual(dl.length, newLength, "array length should match new length");

  const stored = dl[dl.length - 1];
  assert.ok(stored.event_uuid, "event should have event_uuid");
  assert.ok(/\d{4}-\d{2}-\d{2}T/.test(stored.ts), "event should have iso timestamp");
  assert.strictEqual(listenerCalls, 1, "listener should be called once");
  assert.ok(lastListenerEvent, "listener should receive payload");
  assert.strictEqual(lastListenerEvent.event_uuid, stored.event_uuid, "listener receives normalized event");
  assert.ok(stored.id_event, "event should include id_event");
  assert.strictEqual(typeof stored.id_event, "string", "id_event should be a string");
  assert.strictEqual(lastListenerEvent.id_event, stored.id_event, "listener receives id_event");

  const emitted = dispatched[dispatched.length - 1];
  assert.ok(emitted, "CustomEvent should be dispatched");
  assert.strictEqual(emitted.type, "datalayer:push", "CustomEvent type should match");
  assert.ok(emitted.detail, "CustomEvent should include detail");
  assert.strictEqual(emitted.detail.event_uuid, stored.event_uuid, "CustomEvent detail should match event");

  const secondLength = dl.push({ event_type: "click", payload: { id: "Hero CTA Secondary" } });
  assert.strictEqual(secondLength, newLength + 1, "second push should append to array");
  const second = dl[dl.length - 1];
  assert.strictEqual(second.ll_event_type, "click", "second event should expose ll_event_type");
  assert.strictEqual(second.id_event, "hero_cta_secondary", "id_event should be slugified from payload id");
  assert.strictEqual(listenerCalls, 2, "listener should be called for second push");
  assert.strictEqual(lastListenerEvent.id_event, second.id_event, "listener should receive second id_event");

  unsubscribe();
  dl.push({ event_type: "click" });
  assert.strictEqual(listenerCalls, 2, "listener should not be called after unsubscribe");

  const noConsentContext = createWindowContext("no");
  assert.ok(!noConsentContext.window.dataLayer, "dataLayer should not exist when consent=N");

  console.log("test_datalayer_push.js OK");
})();
