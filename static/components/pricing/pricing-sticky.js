/* Pilotage sticky compacte mobile
 * Hypothèses:
 *  - packs.html rend un bloc .vs-sticky pour le plan ciblé
 *  - data attributes:
 *      data-for   = slug du plan cible (ex: "starter")
 *      data-hide-cta = "1" pour masquer si CTA visible
 *      data-threshold = px de scroll avant affichage
 *      data-max-vp   = largeur max viewport (ex: 991)
 */
(function(){
  document.addEventListener('DOMContentLoaded', function(){
    var sticky = document.querySelector('.vs-sticky');
    if(!sticky) return;

    var targetSlug = sticky.getAttribute('data-for') || 'starter';
    var hideIfCta  = sticky.getAttribute('data-hide-cta') === '1';
    var threshold  = parseInt(sticky.getAttribute('data-threshold') || '160', 10);
    var maxVp      = parseInt(sticky.getAttribute('data-max-vp') || '991', 10);

    // Désactive au-delà du viewport max
    if (Math.max(document.documentElement.clientWidth, window.innerWidth || 0) > maxVp){
      sticky.hidden = true;
      return;
    }

    // Cible: la carte du plan
    var card = document.querySelector('.pack-card[data-plan-slug="'+targetSlug+'"]');
    var cta  = card ? card.querySelector('.pack-cta .btn') : null;

    function inView(el){
      if(!el) return false;
      var r = el.getBoundingClientRect();
      return r.top < (window.innerHeight - 20) && r.bottom > 0;
    }

    function evaluate(){
      if (window.scrollY < threshold){ sticky.hidden = true; sticky.classList.remove('is-visible'); return; }
      if (hideIfCta && inView(cta)){ sticky.hidden = true; sticky.classList.remove('is-visible'); return; }
      sticky.hidden = false;
      sticky.classList.add('is-visible');
    }

    // Première évaluation + abonnements
    evaluate();
    window.addEventListener('scroll', evaluate, {passive:true});
    window.addEventListener('resize', evaluate);

    // Affinage: hide dès que la carte devient majoritairement visible
    if ('IntersectionObserver' in window && card){
      var io = new IntersectionObserver(function(entries){
        entries.forEach(function(e){
          if (e.isIntersecting){ sticky.hidden = true; sticky.classList.remove('is-visible'); }
        });
      }, {threshold: 0.5});
      io.observe(card);
    }
  });
})();
