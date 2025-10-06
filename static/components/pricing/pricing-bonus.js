/* Spotlight des bonus :
 * - Si un bloc "data-source=server" existe => on ne fait rien (rendu serveur).
 * - Sinon, on regroupe les <li> commençant par "Bonus" en pills + liste, avec icônes heuristiques.
 */
(function () {
  function iconFor(text) {
    const t = (text || "").toLowerCase();
    if (t.includes("deux couleur") || t.includes("2 couleur") || t.includes("color")) return "fa-circle-half-stroke";
    if (t.includes("crème") || t.includes("texture")) return "fa-ice-cream";
    if (t.includes("fondant") || t.includes("parfum")) return "fa-spray-can-sparkles";
    if (t.includes("diagnosti") || t.includes("défaut") || t.includes("solution")) return "fa-screwdriver-wrench";
    if (t.includes("contenant") || t.includes("moule") || t.includes("boîte") || t.includes("container")) return "fa-box-open";
    return "fa-gift";
  }

  function init(cfg) {
    cfg = cfg || {};
    var target = cfg.target_slug || 'starter';
    var visible = Number(cfg.visible_count || 3);
    var label = cfg.label || 'Bonus inclus';
    var moreLabel = cfg.more_label || 'Voir +{n} bonus';
    var lessLabel = cfg.less_label || 'Masquer les bonus';

    var card = document.querySelector('.pack-card[data-plan-slug="' + target + '"]');
    if (!card) return;

    // Si le rendu serveur est présent, on s’arrête.
    if (card.querySelector('.pack-bonus-spotlight[data-source="server"]')) return;

    var featList = card.querySelector('.pack-features');
    if (!featList) return;

    var items = Array.from(featList.querySelectorAll('.pack-feature'));
    var bonusItems = items.filter(function (li) {
      var t = (li.textContent || '').trim();
      return /^Bonus\b/i.test(t);
    });
    if (!bonusItems.length) return;

    // Container spotlight
    var spot = card.querySelector('.pack-bonus-spotlight[data-spotlight="bonus"]');
    if (!spot) {
      spot = document.createElement('section');
      spot.className = 'pack-bonus-spotlight';
      card.insertBefore(spot, featList);
    }
    spot.hidden = false;

    // Header
    var head = document.createElement('header');
    head.className = 'bonus-head';
    head.innerHTML =
      '<span class="bonus-badge" aria-hidden="true">BONUS</span>' +
      '<h4 class="bonus-title">' + escapeHtml(label) + ' <strong>(' + bonusItems.length + ')</strong></h4>';
    spot.appendChild(head);

    // Liste visible (≤ visible)
    var listTop = document.createElement('ul');
    listTop.className = 'bonus-pills';
    bonusItems.slice(0, visible).forEach(function (li) {
      var txt = clean(li.textContent);
      var pill = document.createElement('li');
      pill.className = 'bonus-pill';
      pill.innerHTML = '<i class="fas ' + iconFor(txt) + '" aria-hidden="true"></i><span>' + escapeHtml(txt) + '</span>';
      listTop.appendChild(pill);
      li.style.display = 'none';
      li.dataset.moved = '1';
    });
    spot.appendChild(listTop);

    // Reste en accordéon
    var rest = bonusItems.slice(visible);
    if (rest.length) {
      var wrap = document.createElement('div');
      wrap.className = 'bonus-more';
      wrap.hidden = true;

      var listRest = document.createElement('ul');
      listRest.className = 'bonus-list';

      rest.forEach(function (li) {
        var txt = clean(li.textContent);
        var item = document.createElement('li');
        item.className = 'bonus-item';
        item.innerHTML = '<i class="fas ' + iconFor(txt) + '" aria-hidden="true"></i><span>' + escapeHtml(txt) + '</span>';
        listRest.appendChild(item);
        li.style.display = 'none';
        li.dataset.moved = '1';
      });

      wrap.appendChild(listRest);
      spot.appendChild(wrap);

      var btn = document.createElement('button');
      btn.className = 'bonus-toggle';
      btn.type = 'button';
      btn.setAttribute('aria-expanded', 'false');
      btn.textContent = moreLabel.replace(/\{n\}/g, String(rest.length));
      btn.addEventListener('click', function () {
        var expanded = btn.getAttribute('aria-expanded') === 'true';
        btn.setAttribute('aria-expanded', String(!expanded));
        wrap.hidden = expanded;
        btn.textContent = expanded ? moreLabel.replace(/\{n\}/g, String(rest.length)) : lessLabel;
      });
      spot.appendChild(btn);
    }

    // Micro-impulsion
    setTimeout(function () { head.classList.add('bonus-head--pulse'); }, 250);

    // Utils
    function clean(text) {
      return (text || '').trim().replace(/^Bonus\s*#?\d*\s*[—-]\s*/i, '');
    }
    function escapeHtml(s) {
      var d = document.createElement('div');
      d.textContent = s || '';
      return d.innerHTML;
    }
  }

  window.PricingBonusSpotlight = { init: init };
})();
