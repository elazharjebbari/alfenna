(function () {
  /* ---------- Analytics wrapper ---------- */
  function emit(name, detail) {
    try {
      if (window.dataLayer) dataLayer.push(Object.assign({ event: name }, detail || {}));
      if (window.gtag) gtag('event', name, detail || {});
    } catch (e) {}
  }

  /* ---------- Core (range + reveal) ---------- */
  function setupOne(root) {
    if (!root) return;
    var range  = root.querySelector('.ba-range');
    var after  = root.querySelector('.ba-after');
    var handle = root.querySelector('.ba-handle');
    var isRtl  = root.getAttribute('data-ba-rtl') === '1';

    var supportsClip = CSS && CSS.supports && CSS.supports('clip-path', 'inset(0 50% 0 0)');

    function setVal(v, fireDrag) {
      v = Math.max(0, Math.min(100, v | 0));
      if (supportsClip) {
        after.style.setProperty('--wipe', v + '%');
      } else {
        after.style.width = v + '%';
        after.style.left = 0;
        after.style.right = 'auto';
      }
      handle.style.left = 'calc(' + v + '%)';
      if (range) {
        range.value = v;
        range.setAttribute('aria-valuenow', String(v));
      }
      if (fireDrag) {
        emit(root.getAttribute('data-ev-drag') || 'ba_drag', { percent: v });
        if (window.LL && typeof window.LL.click === 'function') {
          window.LL.click(root, 'ba_drag', { percent: v });
        }
      }
    }

    if (range) {
      range.addEventListener('input', function () { setVal(range.value, true); });
      range.addEventListener('change', function () {
        var v = parseInt(range.value, 10) || 0;
        if (v >= 70) emit(root.getAttribute('data-ev-snap-after') || 'ba_snap_after', { percent: v });
        emit(root.getAttribute('data-ev-drag-end') || 'ba_drag_end', { percent: v });
        if (window.LL && typeof window.LL.click === 'function') {
          window.LL.click(root, 'ba_snap', { to: v >= 70 ? 'after' : 'before', percent: v });
        }
      });
      // clavier
      range.addEventListener('keydown', function (e) {
        var step = e.shiftKey ? 10 : 5;
        if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
          setVal((parseInt(range.value, 10) || 0) + (e.key === 'ArrowRight' ? step : -step), true);
          e.preventDefault();
        }
      });
    }

    // snaps 0/50/100
    var section = root.closest('.ba-section');
    section && section.querySelectorAll('.ba-snap').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var to = parseInt(btn.getAttribute('data-snap-to'), 10) || 0;
        setVal(to, true);
        if (to >= 70) emit(root.getAttribute('data-ev-snap-after') || 'ba_snap_after', { percent: to, via: 'btn' });
        emit(root.getAttribute('data-ev-drag-end') || 'ba_drag_end', { percent: to, via: 'btn' });
        if (window.LL && typeof window.LL.click === 'function') {
          window.LL.click(root, 'ba_snap', { to: to >= 70 ? 'after' : 'before', percent: to });
        }
      });
    });

    // KPI pills
    root.querySelectorAll('[data-ev="ba_kpi_click"]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        emit('ba_kpi_click', { text: btn.textContent.trim() });
      });
    });

    // Preload + view event
    var seen = false, preloaded = false;
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting && e.intersectionRatio >= 0.25 && !preloaded) {
          preloaded = true;
          var img = root.querySelector('.ba-after img');
          if (img && img.loading === 'lazy') img.loading = 'eager';
        }
        if (e.isIntersecting && e.intersectionRatio >= 0.6 && !seen) {
          seen = true;
          emit(root.getAttribute('data-ev-view') || 'ba_view', { ratio: e.intersectionRatio });
        }
      });
    }, { threshold: [0.25, 0.6] });
    io.observe(root);

    // init
    var start = parseInt((range && range.value) || after.style.getPropertyValue('--wipe')) || 50;
    root.classList.toggle('is-rtl', isRtl);
    setVal(start, false);
  }

  function setupHint(node) {
    if (!node) return;
    var key = node.getAttribute('data-hint-key');
    if (key) {
      try {
        if (localStorage.getItem(key)) {
          node.classList.add('is-hidden');
          return;
        }
      } catch (err) {}
    }
    var btn = node.querySelector('[data-ba-hint-close]');
    if (btn) {
      btn.addEventListener('click', function () {
        node.classList.add('is-hidden');
        if (key) {
          try { localStorage.setItem(key, '1'); } catch (err) {}
        }
      });
    }
  }

  /* ---------- Boot ---------- */
  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.ba-wipe').forEach(setupOne);
    document.querySelectorAll('[data-ba-hint]').forEach(setupHint);

    // CTA analytics
    document.querySelectorAll('.ba-cta[data-ev]').forEach(function (a) {
      a.addEventListener('click', function () {
        emit(a.getAttribute('data-ev'), { loc: 'ba_section' });
      });
    });
  });
})();
