(function () {
  const LIGHTBOX_CDN = "https://cdn.jsdelivr.net/npm/fslightbox@3.4.1/index.min.js";

  function onReady(fn) {
    if (document.readyState !== "loading") {
      fn();
    } else {
      document.addEventListener("DOMContentLoaded", fn, { once: true });
    }
  }

  function pushDataLayer(eventName, detail) {
    if (!eventName) {
      return;
    }
    try {
      const payload = Object.assign({ event: eventName }, detail || {});
      (window.dataLayer = window.dataLayer || []).push(payload);
    } catch (err) {
      // Fail silently — analytics must never break the UI.
    }
  }

  function ensureLightbox() {
    if (window.fsLightboxInstances || window.refreshFsLightbox) {
      return Promise.resolve();
    }
    return new Promise(function (resolve, reject) {
      if (document.querySelector('script[data-product-lightbox]')) {
        document.addEventListener("product:lightbox-ready", resolve, { once: true });
        return;
      }
      const script = document.createElement("script");
      script.src = LIGHTBOX_CDN;
      script.defer = true;
      script.dataset.productLightbox = "true";
      script.onload = function () {
        document.dispatchEvent(new Event("product:lightbox-ready"));
        resolve();
      };
      script.onerror = function (err) {
        reject(err);
      };
      document.head.appendChild(script);
    });
  }

  function setActiveThumb(thumbs, index) {
    thumbs.forEach(function (btn, idx) {
      const isCurrent = idx === index;
      btn.classList.toggle("active", isCurrent);
      btn.setAttribute("aria-selected", isCurrent ? "true" : "false");
    });
  }

  function initSwiper(root, swiperEl, thumbs, tracking) {
    const slidesCount = swiperEl.querySelectorAll(".swiper-slide").length;
    if (!window.Swiper || slidesCount <= 0) {
      return null;
    }

    const nextBtn = root.querySelector('[data-product-nav="next"]');
    const prevBtn = root.querySelector('[data-product-nav="prev"]');
    const swiper = new window.Swiper(swiperEl, {
      slidesPerView: 1,
      spaceBetween: 24,
      loop: false,
      navigation: {
        nextEl: nextBtn || undefined,
        prevEl: prevBtn || undefined,
      },
      on: {
        slideChange: function () {
          const activeIndex = swiper.realIndex;
          setActiveThumb(thumbs, activeIndex);
          if (tracking.enabled && tracking.mediaEvent) {
            const slide = swiper.slides[swiper.activeIndex];
            const img = slide ? slide.querySelector("img") : null;
            pushDataLayer(tracking.mediaEvent, {
              position: activeIndex,
              src: img ? img.getAttribute("src") : undefined,
            });
          }
        },
      },
    });
    return {
      slideTo: function (index) {
        swiper.slideTo(index);
      },
      next: function () {
        swiper.slideNext();
      },
      prev: function () {
        swiper.slidePrev();
      },
    };
  }

  function initFallback(swiperEl, thumbs, tracking) {
    const slides = Array.from(swiperEl.querySelectorAll(".swiper-slide"));
    const hero = slides[0] ? slides[0].querySelector("img") : null;
    if (!hero) {
      return null;
    }
    let currentIndex = 0;

    function render(index) {
      slides.forEach(function (slide, idx) {
        slide.style.display = idx === index ? "block" : "none";
      });
      setActiveThumb(thumbs, index);
      currentIndex = index;
    }

    render(0);

    thumbs.forEach(function (btn, index) {
      btn.addEventListener("click", function () {
        render(index);
        if (tracking.enabled && tracking.mediaEvent) {
          const src = btn.getAttribute("data-full-src") || hero.getAttribute("src");
          pushDataLayer(tracking.mediaEvent, { position: index, src: src });
        }
      });
    });
    return {
      slideTo: function (index) {
        render(index);
      },
      next: function () {
        const target = (currentIndex + 1) % slides.length;
        render(target);
      },
      prev: function () {
        const target = (currentIndex - 1 + slides.length) % slides.length;
        render(target);
      },
    };
  }

  function initProduct(root) {
    const swiperEl = root.querySelector('[data-product-swiper]');
    const thumbs = Array.from(root.querySelectorAll('[data-product-thumbs] button'));
    const tracking = {
      enabled: root.dataset.trackEnabled === "true",
      viewEvent: root.dataset.eventView || "",
      mediaEvent: root.dataset.eventMedia || "",
    };

    if (tracking.enabled && tracking.viewEvent) {
      pushDataLayer(tracking.viewEvent, {
        product_id: root.dataset.productId,
      });
    }

    let controller = null;
    if (swiperEl) {
      controller = initSwiper(root, swiperEl, thumbs, tracking);
    }
    if (!controller && swiperEl) {
      controller = initFallback(swiperEl, thumbs, tracking);
    }

    thumbs.forEach(function (btn, index) {
      btn.addEventListener("click", function () {
        if (controller && typeof controller.slideTo === "function") {
          controller.slideTo(index);
        }
      });
    });

    const nextBtn = root.querySelector('[data-product-nav="next"]');
    const prevBtn = root.querySelector('[data-product-nav="prev"]');
    if (nextBtn && controller && typeof controller.next === "function") {
      nextBtn.addEventListener("click", function () {
        controller.next();
      });
    }
    if (prevBtn && controller && typeof controller.prev === "function") {
      prevBtn.addEventListener("click", function () {
        controller.prev();
      });
    }

    const lightboxEnabled = root.querySelector('[data-fslightbox]') !== null;
    if (lightboxEnabled) {
      ensureLightbox().catch(function () {
        // ignore — lightbox optional
      }).then(function () {
        if (typeof window.refreshFsLightbox === "function") {
          window.refreshFsLightbox();
        }
      });
    }
  }

  onReady(function () {
    document.querySelectorAll('[data-cmp="product"]').forEach(initProduct);
  });
})();
