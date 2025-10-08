(function () {
  "use strict";

  function onReady(fn) {
    if (document.readyState !== "loading") {
      fn();
    } else {
      document.addEventListener("DOMContentLoaded", fn, { once: true });
    }
  }

  function extractPayload(el) {
    if (!el) {
      return {};
    }
    var extra = {};
    var raw = el.getAttribute("data-ll-payload");
    if (raw) {
      try {
        extra = JSON.parse(raw);
      } catch (err) {
        extra = {};
      }
    }
    var id = el.getAttribute("data-id") || el.getAttribute("data-ll-id");
    if (id) {
      extra = Object.assign({ id: id }, extra);
    }
    return extra;
  }

  function emitClose(el) {
    if (!el || !window.LL || typeof window.LL.click !== "function") {
      return;
    }
    window.LL.click(el, "faq_item_close", extractPayload(el));
  }

  onReady(function () {
    var hasBootstrap = typeof window !== "undefined" && (typeof window.bootstrap !== "undefined" || typeof bootstrap !== "undefined");

    if (hasBootstrap) {
      document.addEventListener("hidden.bs.tab", function (event) {
        emitClose(event.target);
      });
      return;
    }

    document.querySelectorAll(".faq-tab-menu").forEach(function (menu) {
      var active = menu.querySelector(".nav-link.active");
      menu.querySelectorAll(".nav-link").forEach(function (btn) {
        btn.addEventListener("click", function () {
          if (active && active !== btn) {
            emitClose(active);
          }
          active = btn;
        });
      });
    });
  });
})();
