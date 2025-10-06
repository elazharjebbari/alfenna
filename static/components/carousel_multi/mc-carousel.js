/* Carrousel ergonomique : drag, molette horizontale, progress bar,
   pause médias hors écran, onboarding Driver.js. */
(function () {
  if (typeof window === "undefined") return;
  const $all = (r, s) => Array.from(r.querySelectorAll(s));

  const debounce = (fn, t=120) => {
    let id; return (...a) => { clearTimeout(id); id = setTimeout(() => fn(...a), t); };
  };

  class MCCarousel {
    constructor(root) {
      this.root = root;
      this.viewport = root.querySelector(".mc-viewport");
      this.track = root.querySelector(".mc-track");
      this.slides = $all(this.track, ".mc-slide");
      this.progress = root.querySelector(".mc-progress-bar");
      this.hint = root.querySelector(".mc-hint");
      this.media = $all(this.track, ".mc-media-el, video.mc-video, audio.mc-audio-el");

      const ds = root.dataset;
      const itemsDesktop = parseInt(ds.itemsDesktop || "3", 10);
      const itemsTablet  = parseInt(ds.itemsTablet  || "2", 10);
      const gap          = parseInt(ds.gap || "16", 10);
      this.track.style.setProperty("--mc-items-desktop", itemsDesktop);
      this.track.style.setProperty("--mc-items-tablet", itemsTablet);
      this.track.style.setProperty("--mc-gap", `${gap}px`);

      this._drag = { active:false, x:0, scroll:0 };

      this._bind();
      this._updateEdges();
      this._updateProgress();
      this._setupOnboarding();
    }

    _bind() {
      const pills = $all(this.root, ".mc-pill");
      pills.forEach(btn => {
        btn.addEventListener("click", () => {
          pills.forEach(b => { b.classList.remove("is-active"); b.setAttribute("aria-selected","false"); });
          btn.classList.add("is-active"); btn.setAttribute("aria-selected","true");
          this._applyPersona(btn.dataset.filter || "all");
        });
      });

      const onScroll = debounce(() => { this._updateEdges(); this._updateProgress(); this._pauseHiddenMedia(); }, 50);
      this.viewport.addEventListener("scroll", onScroll, { passive:true });
      window.addEventListener("resize", debounce(() => { this._updateEdges(); this._updateProgress(); }, 120));

      this.viewport.addEventListener("wheel", (e) => {
        if (Math.abs(e.deltaY) > Math.abs(e.deltaX)) {
          this.viewport.scrollLeft += e.deltaY;
          e.preventDefault();
        }
      }, { passive:false });

      this.viewport.addEventListener("pointerdown", (e) => {
        this._drag.active = true;
        this.viewport.setPointerCapture(e.pointerId);
        this._drag.x = e.clientX;
        this._drag.scroll = this.viewport.scrollLeft;
        this.root.classList.add("is-dragging");
      });
      this.viewport.addEventListener("pointermove", (e) => {
        if (!this._drag.active) return;
        const dx = e.clientX - this._drag.x;
        this.viewport.scrollLeft = this._drag.scroll - dx;
      });
      const endDrag = () => { this._drag.active = false; this.root.classList.remove("is-dragging"); };
      this.viewport.addEventListener("pointerup", endDrag);
      this.viewport.addEventListener("pointercancel", endDrag);
      this.viewport.addEventListener("pointerleave", endDrag);

      this.viewport.addEventListener("keydown", (e) => {
        if (e.key === "ArrowRight" || e.key === "PageDown") { this._scrollByViewport(1); e.preventDefault(); }
        if (e.key === "ArrowLeft"  || e.key === "PageUp")   { this._scrollByViewport(-1); e.preventDefault(); }
        if (e.key === "Home") { this.viewport.scrollTo({ left: 0, behavior: "smooth" }); e.preventDefault(); }
        if (e.key === "End")  { this.viewport.scrollTo({ left: this.viewport.scrollWidth, behavior: "smooth" }); e.preventDefault(); }
      });

      ["wheel","touchstart","pointerdown","keydown"].forEach(ev =>
        this.viewport.addEventListener(ev, () => this._hideLocalHint(), { passive:true })
      );

      this.media.forEach(m => {
        m.addEventListener("play", () => { this._pauseOthers(m); });
      });
    }

    _applyPersona(key) {
      $all(this.track, ".mc-slide").forEach(li => {
        const show = key === "all" || (li.dataset.persona || "all") === key;
        li.style.display = show ? "" : "none";
      });
      this.slides = $all(this.track, ".mc-slide").filter(el => el.style.display !== "none");
      this._updateEdges(); this._updateProgress();
    }

    _scrollByViewport(dir=1) {
      const delta = Math.max(1, Math.floor(this.viewport.clientWidth * 0.9));
      this.viewport.scrollBy({ left: delta * dir, behavior: "smooth" });
    }

    _updateEdges() {
      const vp = this.viewport;
      const canLeft  = vp.scrollLeft > 2;
      const canRight = (vp.scrollLeft + vp.clientWidth) < (vp.scrollWidth - 2);
      this.root.dataset.canLeft = canLeft ? "true" : "false";
      this.root.dataset.canRight = canRight ? "true" : "false";
    }

    _updateProgress() {
      if (!this.progress) return;
      const vp = this.viewport;
      const total = Math.max(1, vp.scrollWidth - vp.clientWidth);
      const pct = Math.min(1, Math.max(0, vp.scrollLeft / total));
      this.progress.style.width = `${pct * 100}%`;
    }

    _pauseHiddenMedia() {
      const vpRect = this.viewport.getBoundingClientRect();
      this.media.forEach(m => {
        const r = m.getBoundingClientRect();
        const visible = r.right > vpRect.left && r.left < vpRect.right;
        if (!visible && !m.paused) { try { m.pause(); } catch(_){} }
      });
    }

    _pauseOthers(current) {
      this.media.forEach(m => { if (m !== current && !m.paused) { try { m.pause(); } catch(_){} } });
    }

    _setupOnboarding() {
      const enabled = this.root.dataset.onboarding === "true";
      if (!enabled) return;

      const scope = this.root.dataset.onboardingScope || "session";
      const key   = `mc_onboard_${this.root.dataset.section || "carousel"}`;
      const storage = scope === "persistent" ? localStorage : sessionStorage;
      if (storage.getItem(key)) return;

      const io = new IntersectionObserver((entries) => {
        const e = entries[0];
        if (e && e.intersectionRatio >= 1) {
          this._startOnboarding(storage, key);
          io.disconnect();
        }
      }, { threshold: 1.0 });
      io.observe(this.root);
    }

    _startOnboarding(storage, key) {
      const y = window.scrollY;
      const title = this.root.dataset.stepTitle || "Parcourir les avis";
      const desc  = this.root.dataset.stepDesc  || "Faites défiler horizontalement pour tout voir.";

      if (window.Driver) {
        try {
          const driver = new window.Driver({
            opacity: 0.25, padding: 6, allowClose: true, animate: true, stageBackground: "rgba(0,0,0,.25)"
          });
          driver.defineSteps([{
            element: this.root,
            popover: { title, description: desc, position: "top", closeBtnText: "Fermer",
                       nextBtnText: "Suivant", prevBtnText: "Précédent", doneBtnText: "Compris" }
          }]);

          const restore = () => { try { window.scrollTo({ top:y, left:window.scrollX, behavior:"auto" }); } catch(_){} };
          if (typeof driver.on === "function") { driver.on('reset', restore); driver.on('destroyed', restore); }

          driver.start();
          storage.setItem(key, "1");
          return;
        } catch (_) {}
      }
      this._showLocalHint(storage, key);
    }

    _showLocalHint(storage, key) {
      if (!this.hint) return;
      this.hint.hidden = false;
      const close = this.hint.querySelector(".mc-hint-close");
      const end = () => { this._hideLocalHint(); storage.setItem(key, "1"); };
      close && close.addEventListener("click", end, { once:true });
      setTimeout(end, 5000);
    }
    _hideLocalHint(){ if (this.hint && !this.hint.hidden) this.hint.hidden = true; }
  }

  function boot(){ document.querySelectorAll(".mc-carousel").forEach(root => new MCCarousel(root)); }
  if (document.readyState !== "loading") boot();
  else document.addEventListener("DOMContentLoaded", boot);
})();
