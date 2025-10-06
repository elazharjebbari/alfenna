(function () {
  /* ---- Analytics util ---- */
  function emit(name, detail) {
    try {
      if (window.dataLayer) dataLayer.push(Object.assign({ event: name }, detail || {}));
      if (window.gtag)     gtag('event', name, detail || {});
    } catch (e) {}
  }

  function toggleItem(li, open) {
    if (!li) return;
    var btn  = li.querySelector('.eco-badge');
    var desc = li.querySelector('.eco-desc');
    var isOpen = (open != null) ? !!open : !li.classList.contains('is-open');

    li.classList.toggle('is-open', isOpen);
    if (btn)  btn.setAttribute('aria-expanded', String(isOpen));
    if (desc) desc.hidden = !isOpen;
  }

  function setupOne(root) {
    if (!root) return;
    var list   = root.querySelector('.eco-list');
    var items  = Array.from(list.querySelectorAll('.eco-item'));
    if (!items.length) return;

    // Click: ouvre/ferme
    items.forEach(function (li, idx) {
      var btn = li.querySelector('.eco-badge');
      if (!btn) return;
      btn.addEventListener('click', function () {
        var willOpen = !li.classList.contains('is-open');
        // ferme les autres (accordéon doux)
        items.forEach(function (other) {
          if (other !== li) toggleItem(other, false);
        });
        toggleItem(li, willOpen);
        if (willOpen) emit(root.dataset.evOpen || 'eco_item_open', { index: idx });
      });
    });

    // IO: vue + ouverture par défaut
    var startIndex = Math.max(0, Math.min(
      parseInt(root.getAttribute('data-start-open') || '0', 10) || 0,
      items.length - 1
    ));
    var seen = false;
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting || e.intersectionRatio < 0.35) return;
        if (!seen) {
          emit(root.dataset.evView || 'eco_view', { ratio: e.intersectionRatio });
          toggleItem(items[startIndex], true);
          seen = true;
        }
        io.unobserve(root);
      });
    }, { threshold: [0.35] });
    io.observe(root);

    // CTA analytics
    var cta = root.parentElement.querySelector('.eco-cta');
    if (cta && cta.dataset.ev) {
      cta.addEventListener('click', function () { emit(cta.dataset.ev, { loc: 'eco' }); });
    }

    // Driver (1 step) – safe, aucune fuite horizontale
    var wantsTour = (root.getAttribute('data-tour') || '').toLowerCase() !== 'false';
    var tourKey   = 'ecoTour:' + root.id;
    if (wantsTour && window.Driver && localStorage.getItem(tourKey) !== '1') {
      var firstBtn = items[0] && items[0].querySelector('.eco-badge');
      if (firstBtn) {
        try {
          document.documentElement.classList.add('driver-enabled');
          var driver = new window.Driver({
            allowClose: true, animate: true, opacity: 0.5
          });
          driver.defineSteps([{
            element: firstBtn,
            popover: {
              title: 'Écologie & qualité',
              description: root.getAttribute('data-tour-text') ||
                'Touchez un badge pour découvrir nos choix écologiques.'
            }
          }]);
          var cleanup = function(){ document.documentElement.classList.remove('driver-enabled'); };
          var _reset  = driver.reset.bind(driver);
          driver.reset = function(){ cleanup(); _reset(); };
          driver.start();
          localStorage.setItem(tourKey, '1');
        } catch (err) {
          document.documentElement.classList.remove('driver-enabled');
        }
      }
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.eco').forEach(function (host) {
      // récupère les options transmises via l’hydrateur
      var start = parseInt(host.getAttribute('data-start-open'), 10);
      if (isNaN(start)) host.setAttribute('data-start-open', '0');
      setupOne(host);
    });
  });
})();
