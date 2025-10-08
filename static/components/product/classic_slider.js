(function(){
  function onReady(fn){ document.readyState !== 'loading' ? fn() : document.addEventListener('DOMContentLoaded', fn, {once:true}); }
  onReady(function(){
    var root = document.querySelector('[data-gallery-classic]');
    if (!root) return;

    var heroImg = root.querySelector('#pg-hero-img');
    if (!heroImg) { console.warn('gallery: hero img not found'); return; }

    var thumbs = Array.from(root.querySelectorAll('.pg-thumbs button'));
    var prev = root.querySelector('[data-gallery-prev]');
    var next = root.querySelector('[data-gallery-next]');
    var idx = Math.max(0, thumbs.findIndex(b => b.classList.contains('active')));

    function setActive(i){
      if (!thumbs.length) return;
      idx = (i + thumbs.length) % thumbs.length;
      var b = thumbs[idx];
      var src = b.getAttribute('data-full-src') || heroImg.getAttribute('src');
      var alt = b.getAttribute('data-alt') || heroImg.getAttribute('alt') || '';
      heroImg.setAttribute('src', src);
      if (alt) heroImg.setAttribute('alt', alt);
      thumbs.forEach(t => { t.classList.remove('active'); t.setAttribute('aria-selected','false'); });
      b.classList.add('active'); b.setAttribute('aria-selected','true');
      try { b.scrollIntoView({block:'nearest', inline:'center', behavior:'smooth'}); } catch(e){}
    }

    thumbs.forEach((b, i) => b.addEventListener('click', function(){ setActive(i); }));
    if (prev) prev.addEventListener('click', function(){ setActive(idx - 1); });
    if (next) next.addEventListener('click', function(){ setActive(idx + 1); });

    root.addEventListener('keydown', function(e){
      if (e.key === 'ArrowLeft') { e.preventDefault(); setActive(idx - 1); }
      else if (e.key === 'ArrowRight') { e.preventDefault(); setActive(idx + 1); }
    }, true);

    if (thumbs.length <= 1) {
      if (prev) prev.style.display = 'none';
      if (next) next.style.display = 'none';
    }
  });
})();
