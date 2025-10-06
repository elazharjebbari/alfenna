(function () {

    const cfg = window.__CHECKOUT__ || {};
    if (!cfg.stripePK) {
        console.error("Stripe publishable key manquante");
        return;
    }

    function trackEvent(name, detail) {
        if (typeof window === "undefined") return;
        const payload = Object.assign({event: name}, detail || {});
        if (Array.isArray(window.dataLayer)) {
            window.dataLayer.push(payload);
        }
        window.dispatchEvent(new CustomEvent(`checkout:${name}`, {detail: detail || {}}));
    }

    const stripe = Stripe(cfg.stripePK);
    const elements = stripe.elements();

    function buildThankYouUrl(orderId) {
        const base = (cfg.thankYouUrl && String(cfg.thankYouUrl)) || (cfg.planSlug ? `/billing/thank-you/plan/${cfg.planSlug}/` : '/billing/thank-you/');
        const query = orderId ? `?order=${encodeURIComponent(orderId)}` : '';
        return base + query;
    }

    function getCookie(name) {
        const match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
        if (match) {
            return decodeURIComponent(match[2]);
        }
    }

    // ---------------- Email helpers (guest)
    const emailField = document.getElementById("guest-email");
    const confirmField = document.getElementById("confirm-guest-email");
    const emailMsg = document.getElementById("email-error");

    function isValidEmail(v) {
        return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(v).toLowerCase());
    }

    function setFieldValidity(field, valid) {
        if (!field) return;
        field.setAttribute("aria-invalid", valid ? "false" : "true");
        field.classList.toggle("is-invalid", !valid);
    }

    function showMsg(text, ok) {
        if (!emailMsg) return;
        emailMsg.hidden = false;
        emailMsg.classList.toggle("text-success", !!ok);
        emailMsg.classList.toggle("text-danger", !ok);
        emailMsg.textContent = text || "";
    }

    function hideMsg() {
        if (!emailMsg) return;
        emailMsg.hidden = true;
        emailMsg.textContent = "";
        emailMsg.classList.remove("text-success", "text-danger");
    }

    function validateFirst() {
        if (!emailField) return true;
        const v = emailField.value.trim();
        const ok = v && isValidEmail(v);
        setFieldValidity(emailField, ok);
        if (!ok) {
            showMsg("Le format de l’adresse e-mail est invalide.", false);
            if (confirmField) {
                confirmField.value = "";
                confirmField.disabled = true;
                setFieldValidity(confirmField, true);
            }
            return false;
        }
        hideMsg();
        if (confirmField) confirmField.disabled = false;
        return true;
    }

    function validateSecond() {
        if (!emailField || !confirmField) return true;
        const v1 = emailField.value.trim();
        const v2 = confirmField.value.trim();
        const validFormat = !!v2 && isValidEmail(v2);
        if (!validFormat) {
            setFieldValidity(confirmField, false);
            showMsg("Le format de confirmation est invalide.", false);
            return false;
        }
        const matches = v1 === v2;
        setFieldValidity(confirmField, matches);
        if (!matches) {
            showMsg("Les adresses e-mail ne correspondent pas.", false);
            return false;
        }
        setFieldValidity(emailField, true);
        showMsg("Les adresses e-mail correspondent.", true);
        return true;
    }

    let addPaymentInfoTracked = false;
    function maybeTrackAddPayment() {
        if (!addPaymentInfoTracked) {
            addPaymentInfoTracked = true;
            trackEvent("add_payment_info", {planSlug: cfg.planSlug || "", currency: cfg.currency || ""});
        }
    }

    if (emailField) {
        emailField.addEventListener("blur", validateFirst);
        emailField.addEventListener("input", () => {
            hideMsg();
            if (confirmField) confirmField.disabled = true;
            setFieldValidity(emailField, true);
            if (confirmField) setFieldValidity(confirmField, true);
        });
        emailField.addEventListener("focus", maybeTrackAddPayment, {once: true});
    }
    if (confirmField) {
        confirmField.addEventListener("blur", validateSecond);
        confirmField.addEventListener("input", hideMsg);
        confirmField.addEventListener("focus", maybeTrackAddPayment, {once: true});
    }

    // ---------------- Payment Element (carte)
    const cardElement = elements.create('card', {
        style: {
            base: {fontSize: '16px', color: '#32325d', '::placeholder': {color: '#a0aec0'}},
            invalid: {color: '#fa755a'}
        }
    });
    const cardContainer = document.getElementById('card-element');
    if (cardContainer) cardElement.mount(cardContainer);

    // ---------------- Bouton principal
    const payBtn = document.getElementById("payment-button");
    const payBtnLabel = payBtn ? payBtn.querySelector(".checkout-submit-label") : null;
    const payBtnAmount = payBtn ? payBtn.querySelector(".checkout-submit-amount") : null;
    const payBtnSpinner = payBtn ? payBtn.querySelector(".checkout-submit-spinner") : null;
    const errors = document.getElementById("card-errors");
    const payFeedback = document.getElementById("payment-feedback");
    const originalLabel = payBtnLabel ? payBtnLabel.textContent : "";

    function showPaymentError(message) {
        if (errors) {
            errors.textContent = message || "";
        }
        if (payFeedback) {
            payFeedback.textContent = message || "";
        }
    }

    function setButtonLoading(loading, label) {
        if (!payBtn) return;
        payBtn.disabled = !!loading;
        payBtn.classList.toggle("is-loading", !!loading);
        if (payBtnLabel) {
            if (loading) {
                payBtnLabel.dataset.original = originalLabel;
                payBtnLabel.textContent = label || payBtn.dataset.loadingLabel || "…";
            } else {
                const origin = payBtnLabel.dataset.original || originalLabel;
                payBtnLabel.textContent = origin;
            }
        }
        if (payBtnAmount) {
            payBtnAmount.style.display = loading ? "none" : "";
        }
        if (payBtnSpinner) {
            if (loading) {
                payBtnSpinner.hidden = false;
                payBtnSpinner.setAttribute("aria-hidden", "false");
            } else {
                payBtnSpinner.hidden = true;
                payBtnSpinner.setAttribute("aria-hidden", "true");
            }
        }
    }

    if (payBtn) {
        trackEvent("begin_checkout", {
            planSlug: cfg.planSlug || "",
            currency: cfg.currency || "",
            amount: payBtn.dataset.amount || "",
        });
    }

    async function postCreateIntent(payload) {
        const headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'X-CSRFToken': getCookie('csrftoken') || '',
        };
        const resp = await fetch(cfg.endpoints.createIntent, {
            method: 'POST',
            headers,
            body: JSON.stringify(payload),
        });
        if (!resp.ok) {
            const txt = await resp.text();
            throw new Error(txt || 'Erreur lors de la création du paiement');
        }
        return resp.json();
    }

    // ---------------- Payment Request Button (Express)
    const prbHost = document.getElementById('payment-request-button');
    if (prbHost) {
        prbHost.style.display = 'none';
        const currencyUpper = (cfg.currency || "EUR").toUpperCase();
        let countryCode = currencyUpper === "USD" ? "US" : "FR";
        if (cfg.country) {
            countryCode = String(cfg.country).toUpperCase();
        }

        const amountCentsRaw = cfg.amountCents != null ? cfg.amountCents : (payBtn ? payBtn.dataset.amountCents : null);
        const amountCents = Number.parseInt(amountCentsRaw, 10);
        if (!Number.isFinite(amountCents) || amountCents <= 0) {
            console.debug('Payment Request hidden: amount cents invalid', amountCentsRaw);
            prbHost.style.display = 'none';
        } else {
            const paymentRequest = stripe.paymentRequest({
                country: countryCode,
                currency: (cfg.currency || "EUR").toLowerCase(),
                total: {label: 'Total', amount: amountCents},
                requestPayerName: true,
                requestPayerEmail: true,
            });

            const prb = elements.create('paymentRequestButton', {
                paymentRequest,
                style: {paymentRequestButton: {type: 'default', theme: 'light', height: '40px'}}
            });

            paymentRequest.canMakePayment().then(function (result) {
                console.debug('Payment Request canMakePayment result:', result);
                if (result) {
                    prb.mount('#payment-request-button');
                    prbHost.style.display = 'block';
                } else {
                    prbHost.style.display = 'none';
                }
            }).catch(function (err) {
                console.warn('Payment Request canMakePayment failed:', err);
                prbHost.style.display = 'none';
            });

            paymentRequest.on('paymentmethod', async function (ev) {
                try {
                    showPaymentError('');
                    const email = ev.payerEmail || (ev.paymentMethod && ev.paymentMethod.billing_details && ev.paymentMethod.billing_details.email) || '';
                    if (!email) {
                        ev.complete('fail');
                        showPaymentError('Email requis pour confirmer le paiement.');
                        return;
                    }

                    const payload = {
                        plan_slug: cfg.planSlug,
                        email,
                        currency: cfg.currency,
                    };
                    if (cfg.courseId) payload.course_id = cfg.courseId;
                    if (cfg.courseSlug) payload.course_slug = cfg.courseSlug;

                    const paymentMethodId = ev.paymentMethod && ev.paymentMethod.id;
                    if (!paymentMethodId) {
                        ev.complete('fail');
                        showPaymentError('Mode de paiement indisponible pour ce portefeuille.');
                        return;
                    }

                    const intent = await postCreateIntent(payload);
                    const confirmResult = await stripe.confirmCardPayment(intent.clientSecret, {
                        payment_method: paymentMethodId,
                    }, {
                        handleActions: false,
                    });

                    if (confirmResult.error) {
                        ev.complete('fail');
                        showPaymentError(confirmResult.error.message || 'Erreur de confirmation du portefeuille.');
                        return;
                    }

                    ev.complete('success');

                    const orderId = (intent.orderId || intent.orderID || cfg.orderId || '');
                    const thankYouUrl = buildThankYouUrl(orderId);

                    if (confirmResult.paymentIntent && confirmResult.paymentIntent.status === 'requires_action') {
                        const actionResult = await stripe.confirmCardPayment(
                            intent.clientSecret,
                            undefined,
                            {return_url: thankYouUrl}
                        );
                        if (actionResult.error) {
                            showPaymentError(actionResult.error.message || 'Authentification requise pour finaliser le paiement.');
                            return;
                        }
                        if (!actionResult.paymentIntent || actionResult.paymentIntent.status !== 'succeeded') {
                            showPaymentError('Paiement en attente de confirmation.');
                            return;
                        }
                    }

                    window.location.href = thankYouUrl;
                } catch (error) {
                    ev.complete('fail');
                    const message = (error && error.message) ? error.message : 'Erreur inattendue lors du paiement.';
                    showPaymentError(message);
                }
            });

            prbHost.addEventListener('click', function () {
                trackEvent('express_click', {planSlug: cfg.planSlug || ''});
            }, {capture: true});
        }
    }

    async function createIntentIfNeeded() {
        // Si la vue a déjà donné un client_secret (user loggé), on le réutilise.
        if (cfg.initialClientSecret) return {clientSecret: cfg.initialClientSecret};

        // Sinon, guest : validons l'e-mail et créons l'intent via l’endpoint JSON.
        if (!validateFirst() || !validateSecond()) {
            throw new Error("Veuillez vérifier que vos adresses e-mail sont correctes et identiques.");
        }
        const email = emailField.value.trim();

        const payload = {plan_slug: cfg.planSlug, email, currency: cfg.currency};
        if (cfg.courseId) {
            payload.course_id = cfg.courseId;
        }
        if (cfg.courseSlug) {
            payload.course_slug = cfg.courseSlug;
        }

        return postCreateIntent(payload);
    }

    async function pay() {
        if (!payBtn) return;
        setButtonLoading(true);
        showPaymentError("");

        try {
            const intent = await createIntentIfNeeded();

            const {error, paymentIntent} = await stripe.confirmCardPayment(intent.clientSecret, {
                payment_method: {
                    card: cardElement,
                    billing_details: {name: (window.CURRENT_USER_NAME || "Guest")}
                }
            });

            if (error) {
                showPaymentError(error.message || "Erreur de paiement");
                setButtonLoading(false);
                return;
            }

            if (paymentIntent && paymentIntent.status === "succeeded") {
                // Redirection : page Thank You (on passe l'orderId si on l'a)
                const orderId = (intent && (intent.orderId || intent.orderID)) || cfg.orderId || "";
                window.location.href = buildThankYouUrl(orderId);
            } else {
                showPaymentError("Paiement en cours…");
                setButtonLoading(false);
            }
        } catch (e) {
            const message = (e && e.message) ? e.message : "Erreur";
            showPaymentError(message);
            setButtonLoading(false);
        }
    }

    if (payBtn) {
        payBtn.addEventListener("click", function (ev) {
            ev.preventDefault();
            pay();
        });
    }

    // ---------------- Coupon reveal tracking
    const couponToggle = document.getElementById("checkout-coupon-toggle");
    const couponField = document.getElementById("checkout-coupon-field");
    if (couponToggle && couponField) {
        couponToggle.addEventListener("click", function () {
            const isHidden = couponField.hasAttribute("hidden");
            if (isHidden) {
                couponField.removeAttribute("hidden");
                couponToggle.setAttribute("aria-expanded", "true");
                const input = couponField.querySelector("input");
                if (input) input.focus();
                trackEvent("coupon_reveal", {planSlug: cfg.planSlug || ""});
            } else {
                couponField.setAttribute("hidden", "hidden");
                couponToggle.setAttribute("aria-expanded", "false");
            }
        });
    }

    const faqDetails = document.querySelectorAll('details[data-track-faq]');
    faqDetails.forEach((detail) => {
        detail.addEventListener('toggle', () => {
            if (detail.open) {
                trackEvent('faq_open_checkout', {
                    planSlug: cfg.planSlug || '',
                    faqId: detail.dataset.faqId || '',
                });
            }
        });
    });
})();
