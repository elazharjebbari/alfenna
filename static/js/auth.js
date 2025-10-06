(function () {
  function ready(fn) {
    if (document.readyState !== 'loading') {
      fn();
    } else {
      document.addEventListener('DOMContentLoaded', fn, { once: true });
    }
  }

  function createSpinner() {
    var spin = document.createElement('span');
    spin.className = 'spinner';
    spin.setAttribute('aria-hidden', 'true');
    return spin;
  }

  function setupPasswordToggle(form) {
    form.querySelectorAll('.pw-toggle').forEach(function (btn) {
      var targetId = btn.getAttribute('aria-controls') || btn.getAttribute('data-toggle-target');
      if (!targetId) {
        return;
      }
      var selector = '#' + CSS.escape(targetId);
      var input = form.querySelector(selector);
      if (!input) {
        return;
      }

      var showLabel = btn.getAttribute('data-label-show') || btn.getAttribute('aria-label') || 'Afficher le mot de passe';
      var hideLabel = btn.getAttribute('data-label-hide') || 'Masquer le mot de passe';

      btn.addEventListener('click', function (event) {
        event.preventDefault();
        var showing = input.getAttribute('type') === 'password';
        input.setAttribute('type', showing ? 'text' : 'password');
        btn.setAttribute('aria-label', showing ? hideLabel : showLabel);
        btn.classList.toggle('is-active', showing);
        btn.innerText = showing ? '🙈' : '👁';
        input.focus({ preventScroll: false });
      });
    });
  }

  function setupDisableOnSubmit(form) {
    var button = form.querySelector('[type="submit"]');
    if (!button) {
      return;
    }

    form.addEventListener('submit', function () {
      if (button.disabled) {
        return;
      }
      button.disabled = true;
      button.setAttribute('aria-busy', 'true');
      if (!button.querySelector('.spinner')) {
        button.insertBefore(createSpinner(), button.firstChild);
      }
    });
  }

  function focusFirstError(form) {
    var invalid = form.querySelector('[aria-invalid="true"]');
    if (invalid) {
      invalid.focus({ preventScroll: false });
    }
  }

  function setupCapsHint(form) {
    form.querySelectorAll('input[type="password"]').forEach(function (input) {
      var parent = input.closest('.password-field') || input.closest('.field');
      if (!parent) {
        return;
      }
      var hint = parent.querySelector('.caps-hint');
      if (!hint) {
        return;
      }

      function update(event) {
        if (!event.getModifierState) {
          return;
        }
        var caps = event.getModifierState('CapsLock');
        hint.classList.toggle('is-visible', Boolean(caps));
      }

      input.addEventListener('keydown', update);
      input.addEventListener('keyup', update);
      input.addEventListener('focus', update);
      input.addEventListener('blur', function () {
        hint.classList.remove('is-visible');
      });
    });
  }

  ready(function () {
    document.querySelectorAll('.auth-form').forEach(function (form) {
      setupPasswordToggle(form);
      setupDisableOnSubmit(form);
      focusFirstError(form);
      setupCapsHint(form);
    });
  });
})();
