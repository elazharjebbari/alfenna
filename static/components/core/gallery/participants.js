(function () {
  function onReady(fn){ if(document.readyState!=="loading"){ fn(); } else { document.addEventListener("DOMContentLoaded", fn); } }

  onReady(function(){
    var grid = document.getElementById("lpGalleryGrid");
    if (!grid) return;

    var initialVisible = parseInt(grid.getAttribute("data-initial-visible") || "0", 10);
    var step = parseInt(grid.getAttribute("data-reveal-step") || "4", 10);
    var useLb = grid.getAttribute("data-lightbox") === "1";

    var cards = Array.prototype.slice.call(grid.querySelectorAll(".lp-card"));
    var moreBtn = document.getElementById("lpGalleryMoreBtn");

    // Progressive reveal
    function visibleCount(){
      return cards.filter(function(c){ return !c.hasAttribute("hidden"); }).length;
    }
    function revealNext(n){
      var shown = 0;
      for (var i=0; i<cards.length && shown<n; i++){
        if (cards[i].hasAttribute("hidden")) {
          cards[i].removeAttribute("hidden");
          shown++;
        }
      }
      if (visibleCount() >= cards.length && moreBtn) moreBtn.parentElement.style.display = "none";
    }

    // Init hidden state & IntersectionObserver for fade-in
    cards.forEach(function(card, idx){
      if (initialVisible && idx >= initialVisible) card.setAttribute("hidden", "");
    });
    if (moreBtn && visibleCount() >= cards.length) { moreBtn.parentElement.style.display = "none"; }

    var observer = ("IntersectionObserver" in window) ? new IntersectionObserver(function(entries){
      entries.forEach(function(entry){
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        }
      });
    }, {rootMargin: "80px"}) : null;

    cards.forEach(function(card){
      if (observer) observer.observe(card);
      else card.classList.add("is-visible");
    });

    if (moreBtn) {
      moreBtn.addEventListener("click", function(){
        revealNext(step);
      });
    }

    // Lightbox basique & accessible
    if (useLb) {
      var lb = document.getElementById("lb");
      var lbImg = document.getElementById("lbImg");
      var lbCaption = document.getElementById("lbCaption");
      var lbPrev = document.getElementById("lbPrev");
      var lbNext = document.getElementById("lbNext");
      var lbClose = document.getElementById("lbClose");

      var links = Array.prototype.slice.call(grid.querySelectorAll(".lp-card a"));
      var current = -1;
      var lastFocus = null;

      function openAt(i){
        current = i;
        var a = links[current];
        if (!a) return;
        lbImg.setAttribute("src", a.getAttribute("href"));
        var alt = (a.querySelector("img") || {}).alt || "";
        lbImg.setAttribute("alt", alt);
        lbCaption.textContent = a.getAttribute("data-caption") || alt || "";
        lb.setAttribute("aria-hidden", "false");
        document.body.style.overflow = "hidden";
        lastFocus = document.activeElement;
        (lbClose || lb).focus();
      }
      function closeLb(){
        lb.setAttribute("aria-hidden", "true");
        lbImg.removeAttribute("src");
        document.body.style.overflow = "";
        if (lastFocus && lastFocus.focus) lastFocus.focus();
      }
      function show(delta){
        if (current < 0) return;
        current = (current + delta + links.length) % links.length;
        openAt(current);
      }

      grid.addEventListener("click", function(e){
        var a = e.target.closest(".lp-card a");
        if (!a) return;
        e.preventDefault();
        var i = links.indexOf(a);
        if (i >= 0) openAt(i);
      });

      if (lbClose) lbClose.addEventListener("click", closeLb);
      if (lbPrev) lbPrev.addEventListener("click", function(){ show(-1); });
      if (lbNext) lbNext.addEventListener("click", function(){ show(1); });

      document.addEventListener("keydown", function(e){
        if (lb.getAttribute("aria-hidden") === "true") return;
        if (e.key === "Escape") closeLb();
        if (e.key === "ArrowLeft") show(-1);
        if (e.key === "ArrowRight") show(1);
      });

      // Fermer en cliquant derrière l'image
      lb.addEventListener("click", function(e){
        if (e.target === lb) closeLb();
      });
    }
  });
})();
