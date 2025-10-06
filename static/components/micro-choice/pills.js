/* Composant: micro-choice/pills
   - Persist persona (localStorage 'll_persona')
   - Met à jour l’UI (aria-pressed)
   - Personnalise la page: [data-show-persona], [data-personas]
   - Analytics: dataLayer.push({event, persona})
*/
(function () {
  const KEY = "ll_persona";

  function qsa(sel, root = document) { return Array.prototype.slice.call(root.querySelectorAll(sel)); }
  function setPersona(persona) {
    if (!persona) return;
    // Persist
    try { localStorage.setItem(KEY, persona); } catch (e) {}
    // Attribute on <html> for CSS hooks if needed
    document.documentElement.setAttribute("data-persona", persona);
    // Toggle conditional content
    qsa("[data-show-persona]").forEach(el => {
      const list = (el.dataset.showPersona || "").split(",").map(s => s.trim());
      el.hidden = !list.includes(persona);
    });
    qsa("[data-personas]").forEach(el => {
      const list = (el.dataset.personas || "").split(",").map(s => s.trim());
      el.style.display = list.includes(persona) ? "" : "none";
    });
  }

  function push(evName, persona) {
    try {
      window.dataLayer = window.dataLayer || [];
      window.dataLayer.push({ event: evName, persona: persona || null });
    } catch (e) {}
  }

  function initChoiceSection(root) {
    const evView = root.getAttribute("data-ev-view") || "choice_view";
    const evClick = root.getAttribute("data-ev-click") || "choice_card_click";
    const anchorNext = root.getAttribute("data-anchor-next");
    const autoselect = root.getAttribute("data-autoselect") === "true";

    // View event
    push(evView, null);

    const pills = qsa(".ll-pill", root);
    const saved = (function () { try { return localStorage.getItem(KEY); } catch (e) { return null; } })();

    function updatePressed(p) {
      pills.forEach(b => b.setAttribute("aria-pressed", String(b.dataset.persona === p)));
    }

    // Restore selection (optional)
    if (autoselect && saved) {
      updatePressed(saved);
      setPersona(saved);
    }

    // Click handlers
    pills.forEach(btn => {
      btn.addEventListener("click", () => {
        const p = btn.dataset.persona;
        updatePressed(p);
        setPersona(p);
        push(evClick, p);
        // Smooth scroll to the next meaningful block
        if (anchorNext) {
          const t = document.querySelector(anchorNext);
          if (t) t.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      });

      // Keyboard support (Enter/Space)
      btn.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          btn.click();
        }
      });
    });
  }

  // Auto-boot all instances by alias
  qsa('[data-comp="micro-choice/pills"]').forEach(initChoiceSection);
})();
