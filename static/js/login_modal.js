(function () {
  // Autofocus sur username à l'ouverture
  document.addEventListener("shown.bs.modal", function (ev) {
    var el = ev.target;
    var input = el.querySelector('input[name="username"]');
    if (input) { try { input.focus(); } catch (e) {} }
  });

  // Ouverture automatique si data-autoshow="1"
  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll('.modal[data-autoshow="1"]').forEach(function (el) {
      if (window.bootstrap && el.id) new bootstrap.Modal(el).show();
    });
  });

  // Option: ouverture via attribut data-open-login-modal="modalId"
  document.addEventListener("click", function (e) {
    var t = e.target.closest("[data-open-login-modal]");
    if (!t) return;
    e.preventDefault();
    var id = t.getAttribute("data-open-login-modal") || "loginModal";
    var el = document.getElementById(id);
    if (window.bootstrap && el) new bootstrap.Modal(el).show();
  });
})();
