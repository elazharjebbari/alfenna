(function(){
  "use strict";

  var bar = document.getElementById("af-buybar-v2");
  if (!bar) return;

  var heroSelector = bar.getAttribute("data-hero") || "#hero";
  var formSelector = bar.getAttribute("data-form-root") || "[data-ff-root]";
  var inputSelector = bar.getAttribute("data-input") || "#ff-fullname";
  var dismissDays = parseInt(bar.getAttribute("data-dismiss-days") || "1", 10) || 1;

  var DISMISS_KEY = "af_buybar_v2_dismiss_until";

  function shouldShow() {
    try {
      var until = parseInt(localStorage.getItem(DISMISS_KEY), 10);
      return !until || Date.now() > until;
    } catch (err) {
      return true;
    }
  }

  function dismiss(days) {
    try {
      var ttl = Math.max(1, days) * 24 * 60 * 60 * 1000;
      localStorage.setItem(DISMISS_KEY, String(Date.now() + ttl));
    } catch (err) {
      /* ignore quota */
    }
  }

  function inViewport(el) {
    if (!el) return false;
    var rect = el.getBoundingClientRect();
    var vh = Math.max(document.documentElement.clientHeight, window.innerHeight || 0);
    return rect.top < vh && rect.bottom > 0;
  }

  function visibilityRatio(el) {
    if (!el) return 0;
    var rect = el.getBoundingClientRect();
    var vh = Math.max(document.documentElement.clientHeight, window.innerHeight || 0);
    var height = Math.max(rect.height, 1);
    var visible = Math.min(rect.bottom, vh) - Math.max(rect.top, 0);
    visible = Math.max(0, visible);
    return Math.max(0, Math.min(1, visible / height));
  }

  function show() {
    bar.classList.add("is-visible");
  }

  function hide() {
    bar.classList.remove("is-visible");
  }

  bar.addEventListener("click", function (event) {
    if (event.target.closest(".af-cta")) {
      event.preventDefault();
      var input = document.querySelector(inputSelector);
      var root = document.querySelector(formSelector);
      var target = input || root;
      if (target) {
        try {
          target.scrollIntoView({ behavior: "smooth", block: "center" });
        } catch (err) {
          target.scrollIntoView();
        }
        if (input) {
          setTimeout(function () {
            try {
              input.focus({ preventScroll: true });
            } catch (err) {
              input.focus();
            }
          }, 220);
        }
      }
    }

    if (event.target.closest(".af-close")) {
      event.preventDefault();
      dismiss(dismissDays);
      hide();
    }
  });

  if (!shouldShow()) return;

  var hero = document.querySelector(heroSelector);
  var formRoot = document.querySelector(formSelector) || document;
  var stepOne = formRoot.querySelector('[data-ff-step="1"]');

  function recompute() {
    if (stepOne && visibilityRatio(stepOne) > 0.4) {
      hide();
      return;
    }

    if (hero) {
      inViewport(hero) ? hide() : show();
    } else {
      (window.scrollY || document.documentElement.scrollTop) > 180 ? show() : hide();
    }
  }

  if ("IntersectionObserver" in window && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    if (hero) {
      new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          entry.isIntersecting ? hide() : show();
        });
      }, { threshold: 0.05 }).observe(hero);
    }

    if (stepOne) {
      new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          entry.intersectionRatio > 0.4 ? hide() : show();
        });
      }, { threshold: [0.2, 0.4, 0.6] }).observe(stepOne);
    }

    setTimeout(recompute, 80);
  } else {
    window.addEventListener("scroll", recompute, { passive: true });
    window.addEventListener("resize", recompute);
    setTimeout(recompute, 80);
  }
})();
