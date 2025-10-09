(function () {
  const form = document.getElementById('form-stepper');
  if (!form) return;

  const messages = {
    required: 'Ce champ est obligatoire.',
    email: 'Veuillez saisir une adresse e-mail valide.',
  };

  function ensureFeedback(field) {
    const group = field.closest('.mb-3, .form-group, .form-floating') || field.parentElement;
    if (!group) return null;
    let feedback = group.querySelector('.invalid-feedback');
    if (!feedback) {
      feedback = document.createElement('div');
      feedback.className = 'invalid-feedback';
      group.appendChild(feedback);
    }
    return feedback;
  }

  function setValidity(field, message) {
    field.setCustomValidity(message || '');
    field.classList.toggle('is-invalid', Boolean(message));
    const feedback = ensureFeedback(field);
    if (feedback) {
      feedback.textContent = message || '';
    }
  }

  function isEmpty(value) {
    return value === null || String(value).trim() === '';
  }

  function validateField(field) {
    setValidity(field, '');

    if (field.hasAttribute('required') && isEmpty(field.value)) {
      setValidity(field, messages.required);
      return false;
    }

    if (field.type === 'email' && field.value) {
      const emailPattern = /\S+@\S+\.\S+/;
      if (!emailPattern.test(field.value)) {
        setValidity(field, messages.email);
        return false;
      }
    }

    if (!field.checkValidity()) {
      setValidity(field, field.validationMessage || messages.required);
      return false;
    }

    return true;
  }

  function validateStep(stepEl) {
    const controls = stepEl.querySelectorAll('input, select, textarea');
    let ok = true;
    controls.forEach((field) => {
      if (!validateField(field)) {
        ok = false;
      }
    });

    if (!ok) {
      const firstInvalid = stepEl.querySelector('.is-invalid');
      if (firstInvalid && typeof firstInvalid.reportValidity === 'function') {
        firstInvalid.reportValidity();
      }
    }

    return ok;
  }

  document.addEventListener('click', (event) => {
    const trigger = event.target.closest('[data-ff-next], [data-step-next], [data-action="next"]');
    if (!trigger) return;

    const step = trigger.closest('[data-ff-step], [data-step]');
    if (!step) return;

    if (!validateStep(step)) {
      event.preventDefault();
      event.stopPropagation();
    }
  }, true);

  form.addEventListener('input', (event) => {
    const field = event.target;
    if (!(field instanceof HTMLElement)) return;
    if (field.matches('input, select, textarea')) {
      setValidity(field, '');
    }
  });
})();
