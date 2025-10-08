/* Al Fenna – Product Gallery v4 (Swiper) */
(function () {
  function onReady(fn) {
    (document.readyState !== 'loading') ? fn() :
      document.addEventListener('DOMContentLoaded', fn, { once: true });
  }

  function initOne(root) {
    var trackSlide = function (idx) {
      if (typeof window !== 'undefined' && window.LL && typeof window.LL.click === 'function') {
        window.LL.click(root, 'gallery_slide_change', { to_idx: idx });
      }
    };

    // Fallback click-to-swap si Swiper n'est pas présent
    if (typeof window.Swiper === 'undefined') {
      const mainImgs = Array.from(root.querySelectorAll('.gallery-main .swiper-slide'));
      const thumbs = Array.from(root.querySelectorAll('.gallery-thumbs .swiper-slide'));
      if (!mainImgs.length || !thumbs.length) return;

      function show(i) {
        mainImgs.forEach((s, idx) => s.style.display = (idx === i ? 'block' : 'none'));
        thumbs.forEach((t, idx) => t.classList.toggle('swiper-slide-thumb-active', idx === i));
        trackSlide(i);
      }
      thumbs.forEach((t, i) => t.addEventListener('click', () => show(i)));
      show(0);
      return; // stop ici
    }

    // THUMBS
    const thumbs = new Swiper(root.querySelector('.gallery-thumbs'), {
      direction: 'horizontal',
      slidesPerView: 5,
      spaceBetween: 10,
      freeMode: true,
      watchSlidesProgress: true,
      slideToClickedSlide: true,
      a11y: { enabled: true },
      breakpoints: {
        992: { direction: 'vertical', slidesPerView: 5, spaceBetween: 10 }
      }
    });

    // MAIN
    const main = new Swiper(root.querySelector('.gallery-main'), {
      slidesPerView: 1,
      centeredSlides: true,
      spaceBetween: 10,
      speed: 380,
      zoom: { maxRatio: 2.5 },
      navigation: {
        nextEl: root.querySelector('.gallery-main .swiper-button-next'),
        prevEl: root.querySelector('.gallery-main .swiper-button-prev')
      },
      pagination: { el: root.querySelector('.gallery-main .swiper-pagination'), clickable: true },
      keyboard: { enabled: true, onlyInViewport: true },
      observer: true, observeParents: true,
      a11y: {
        enabled: true,
        prevSlideMessage: 'Image précédente',
        nextSlideMessage: 'Image suivante',
        slideLabelMessage: 'Image {{index}} sur {{slidesLength}}'
      },
      thumbs: { swiper: thumbs },
      on: {
        init(sw) {
          // cacher contrôles si une seule image
          if (sw.slides.length <= 1) {
            sw.navigation?.nextEl && (sw.navigation.nextEl.style.display = 'none');
            sw.navigation?.prevEl && (sw.navigation.prevEl.style.display = 'none');
            sw.pagination?.el && (sw.pagination.el.style.display = 'none');
            root.querySelector('.gallery-thumbs')?.classList.add('d-none');
          }
          // Accessibilité: rendre focusables les thumbs
          root.querySelectorAll('.gallery-thumbs .swiper-slide').forEach((el, i) => {
            el.setAttribute('tabindex', '0');
            el.setAttribute('role', 'tab');
            el.setAttribute('aria-label', 'Miniature ' + (i + 1));
          });
        },
        slideChangeTransitionStart(sw) {
          // micro-anim d'entrée
          const current = sw.slides[sw.activeIndex];
          const img = current && current.querySelector('.gallery-main-img');
          if (img) {
            img.classList.add('is-enter');
            requestAnimationFrame(() => img.classList.add('is-enter-active'));
          }
        },
        slideChangeTransitionEnd(sw) {
          const prev = sw.slides[sw.previousIndex];
          const imgPrev = prev && prev.querySelector('.gallery-main-img');
          if (imgPrev) imgPrev.classList.remove('is-enter', 'is-enter-active');
          trackSlide(sw.activeIndex);
        }
      }
    });

    // Bonus : survol des vignettes (desktop) → navigue
    const thumbsEl = root.querySelector('.gallery-thumbs');
    if (thumbsEl && window.matchMedia('(hover:hover)').matches) {
      thumbsEl.addEventListener('mouseover', (ev) => {
        const slide = ev.target.closest('.swiper-slide');
        if (!slide) return;
        const slides = Array.from(slide.parentNode.children);
        const idx = slides.indexOf(slide);
        if (idx >= 0) main.slideTo(idx);
      });
    }

    // Raccourcis clavier Home/End
    root.addEventListener('keydown', (e) => {
      if (e.key === 'Home') { e.preventDefault(); main.slideTo(0); }
      if (e.key === 'End')  { e.preventDefault(); main.slideTo(main.slides.length - 1); }
    });
  }

  onReady(function () {
    document.querySelectorAll('[data-af-gallery]').forEach(initOne);
  });
})();
