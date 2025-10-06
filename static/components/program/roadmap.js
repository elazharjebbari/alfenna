(function () {
  /* ---- Analytics util ---- */
  function emit(name, detail) {
    try {
      if (window.dataLayer) dataLayer.push(Object.assign({ event: name }, detail || {}));
      if (window.gtag) gtag('event', name, detail || {});
    } catch (e) {}
  }

  function setupOne(root) {
    if (!root) return;

    var acc   = root.querySelector('.rm-accordion');
    var nodes = Array.from(root.querySelectorAll('.rm-node'));
    var items = acc ? Array.from(acc.querySelectorAll('.accordion-item')) : [];
    if (!acc || !nodes.length || !items.length) return;

    /* ---- helpers ---- */
    function setActive(i, via) {
      nodes.forEach(function (n) {
        n.classList.toggle('is-active', Number(n.dataset.step) === i);
      });

      var body = acc.querySelector('#' + root.id + '-c-' + i);
      if (!body || !window.bootstrap || !window.bootstrap.Collapse) return;

      var c = window.bootstrap.Collapse.getOrCreateInstance(body, { toggle: false });
      c.show();
      emit(root.dataset.evStep || 'roadmap_step_click', { step_index: i, via: via || 'ui' });
    }

    /* ---- clicks sur timeline + label ---- */
    nodes.forEach(function (n) {
      var idx = Number(n.dataset.step);
      var dot = n.querySelector('.rm-dot');
      if (dot) dot.addEventListener('click', function () { setActive(idx, 'timeline'); });
      n.addEventListener('click', function (e) {
        if (e.target.closest('.rm-dot')) return;
        setActive(idx, 'timeline-label');
      });
    });

    /* ---- sync quand un panel s’ouvre ---- */
    acc.addEventListener('shown.bs.collapse', function (ev) {
      var it = ev.target.closest('.accordion-item');
      if (!it) return;
      var i = Number(it.dataset.step || 0);
      nodes.forEach(function (n) { n.classList.toggle('is-active', Number(n.dataset.step) === i); });
      emit(root.dataset.evAccOpen || 'roadmap_accordion_open', { step_index: i });
    });

    /* ---- IO : active le 1er panneau au premier affichage ---- */
    var firstActivated = false;
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting || e.intersectionRatio < 0.4) return;

        emit(root.dataset.evView || 'roadmap_view', { ratio: e.intersectionRatio });
        if (!firstActivated) { setActive(0, 'auto'); firstActivated = true; }

        io.unobserve(root);
      });
    }, { threshold: [0.4] });

    io.observe(root);
  }

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.roadmap').forEach(setupOne);
  });
})();
