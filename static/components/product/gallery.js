document.addEventListener('DOMContentLoaded', function () {
  if (typeof Swiper === 'undefined') {
    return;
  }

  var thumbsEl = document.querySelector('.gallery-thumbs');
  var thumbs = null;

  if (thumbsEl) {
    thumbs = new Swiper('.gallery-thumbs', {
      direction: 'horizontal',
      slidesPerView: 5,
      spaceBetween: 8,
      freeMode: true,
      watchSlidesProgress: true,
      preloadImages: true,
      breakpoints: {
        992: {
          direction: 'vertical',
          slidesPerView: 5,
          spaceBetween: 8
        }
      },
      a11y: { enabled: true }
    });
  }

  var mainOptions = {
    speed: 350,
    spaceBetween: 10,
    centeredSlides: true,
    slidesPerView: 1,
    preloadImages: true,
    navigation: {
      nextEl: '.gallery-main .swiper-button-next',
      prevEl: '.gallery-main .swiper-button-prev'
    },
    pagination: {
      el: '.gallery-main .swiper-pagination',
      clickable: true
    },
    keyboard: {
      enabled: true,
      onlyInViewport: true
    },
    zoom: { maxRatio: 2 },
    observer: true,
    observeParents: true,
    a11y: {
      enabled: true,
      prevSlideMessage: 'Image précédente',
      nextSlideMessage: 'Image suivante',
      slideLabelMessage: 'Image {{index}} sur {{slidesLength}}'
    },
    on: {
      init: function (sw) {
        if (sw.slides.length <= 1) {
          if (sw.navigation && sw.navigation.nextEl) {
            sw.navigation.nextEl.style.display = 'none';
          }
          if (sw.navigation && sw.navigation.prevEl) {
            sw.navigation.prevEl.style.display = 'none';
          }
          if (sw.pagination && sw.pagination.el) {
            sw.pagination.el.style.display = 'none';
          }
          var thumbsContainer = document.querySelector('.gallery-thumbs');
          if (thumbsContainer) {
            thumbsContainer.classList.add('d-none');
          }
        }
      }
    }
  };

  if (thumbs) {
    mainOptions.thumbs = { swiper: thumbs };
  }

  var main = new Swiper('.gallery-main', mainOptions);

  if (thumbsEl && window.matchMedia('(hover:hover)').matches) {
    thumbsEl.addEventListener('mouseover', function (event) {
      var slide = event.target.closest('.swiper-slide');
      if (!slide) {
        return;
      }
      var wrapper = slide.parentNode;
      if (!wrapper) {
        return;
      }
      var slides = Array.prototype.slice.call(wrapper.children);
      var idx = slides.indexOf(slide);
      if (idx >= 0) {
        main.slideTo(idx);
      }
    });
  }

  var fsBtn = document.querySelector('.gallery-fullscreen');
  var container = document.getElementById('product-gallery');
  if (fsBtn && container) {
    fsBtn.addEventListener('click', function () {
      if (!document.fullscreenElement) {
        container.requestFullscreen && container.requestFullscreen();
      } else {
        document.exitFullscreen && document.exitFullscreen();
      }
    });
  }
});


