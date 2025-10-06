// static/site/core.js
// Utilitaires globaux minimalistes, sûrs partout

(function () {
  "use strict";

  // Lazy images (IntersectionObserver → fallback)
  function lazyImagesInit() {
    var lazyImages = [].slice.call(document.querySelectorAll("img.lazy"));
    if (!lazyImages.length) return;

    if ("IntersectionObserver" in window) {
      var obs = new IntersectionObserver(function (entries, observer) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            var img = entry.target;
            var src = img.getAttribute("data-src");
            if (src) img.src = src;
            img.classList.remove("lazy");
            observer.unobserve(img);
          }
        });
      });
      lazyImages.forEach(function (img) { obs.observe(img); });
    } else {
      // Fallback
      lazyImages.forEach(function (img) {
        var src = img.getAttribute("data-src");
        if (src) img.src = src;
        img.classList.remove("lazy");
      });
    }
  }

  // CSRF cookie helper (utile pour fetch POST)
  function getCookie(name) {
    var cookieValue = null;
    if (document.cookie && document.cookie !== "") {
      var cookies = document.cookie.split(";");
      for (var i = 0; i < cookies.length; i++) {
        var cookie = cookies[i].trim();
        if (cookie.substring(0, name.length + 1) === (name + "=")) {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
          break;
        }
      }
    }
    return cookieValue;
  }

  // Expose en global si besoin
  window.__atelier = window.__atelier || {};
  window.__atelier.getCookie = getCookie;

  // Boot
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", lazyImagesInit);
  } else {
    lazyImagesInit();
  }
})();
