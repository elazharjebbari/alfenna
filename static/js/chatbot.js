(function () {
  'use strict';

  if (window.__chatInit) {
    return;
  }
  window.__chatInit = true;

  const API = {
    consent: '/api/chat/consent/',
    start: '/api/chat/start/',
    send: '/api/chat/send/',
    history: '/api/chat/history/',
    stream: '/api/chat/stream/',
  };

  const STORAGE_KEYS = {
    session: 'll.chatbot.session',
    unread: 'll.chatbot.unread',
  };

  const FOCUSABLE_SELECTOR = 'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

const cssEscape = (value) => {
    if (window.CSS && typeof window.CSS.escape === 'function') {
      return window.CSS.escape(String(value));
    }
    return String(value).replace(/[^a-zA-Z0-9_-]/g, '_');
  };

  function getCookie(name) {
    const value = document.cookie
      .split(';')
      .map((segment) => segment.trim())
      .find((segment) => segment.startsWith(name + '='));
    if (!value) {
      return null;
    }
    return decodeURIComponent(value.split('=').slice(1).join('='));
  }

  function safeParseJSON(payload) {
    try {
      return JSON.parse(payload);
    } catch (error) {
      console.warn('chatbot: unable to parse JSON payload', error);
      return null;
    }
  }

  async function requestJSON(url, options) {
    const opts = options || {};
    const method = (opts.method || 'GET').toUpperCase();
    const headers = new Headers(opts.headers || {});

    if (method !== 'GET' && method !== 'HEAD') {
      headers.set('Content-Type', 'application/json');
      const csrfName = 'csrftoken';
      const csrfToken = getCookie(csrfName);
      if (csrfToken) {
        headers.set('X-CSRFToken', csrfToken);
      }
    }

    const fetchOpts = {
      method,
      headers,
      credentials: 'same-origin',
    };

    if (opts.body !== undefined) {
      fetchOpts.body = typeof opts.body === 'string' ? opts.body : JSON.stringify(opts.body);
    }

    const response = await fetch(url, fetchOpts);
    const retryAfterHeader = response.headers.get('Retry-After');
    if (!response.ok) {
      const text = await response.text();
      const err = new Error(`chatbot request failed (${response.status})`);
      err.status = response.status;
      err.payload = text;
      err.retryAfter = retryAfterHeader;
      throw err;
    }

    if (response.status === 204) {
      return null;
    }

    const contentType = response.headers.get('Content-Type') || '';
    if (!contentType.includes('application/json')) {
      return null;
    }
    return response.json();
  }

  function setHidden(el, hidden) {
    if (!el) {
      return;
    }
    if (hidden) {
      el.setAttribute('hidden', '');
    } else {
      el.removeAttribute('hidden');
    }
  }

  function sanitizeText(value) {
    return (value || '').replace(/\s+/g, ' ').trim();
  }

  class ChatbotController {
    constructor(root) {
      this.root = root;
      this.trigger = root.querySelector('[data-chatbot-trigger]');
      this.panel = root.querySelector('[data-chatbot-panel]');
      this.surface = this.panel ? this.panel.querySelector('[data-chatbot-surface]') : null;
      this.closeButton = this.panel ? this.panel.querySelector('[data-chatbot-close]') : null;
      this.messagesViewport = this.panel ? this.panel.querySelector('[data-chatbot-messages]') : null;
      this.scrollContainer =
        (this.panel && this.panel.querySelector('.chatbot-panel__messages')) ||
        (this.messagesViewport ? this.messagesViewport.parentElement : null);
      this.typingIndicator = this.panel ? this.panel.querySelector('[data-chatbot-typing]') : null;
      this.form = root.querySelector('[data-chatbot-input]');
      this.textarea = this.form ? this.form.querySelector('[data-chatbot-textarea]') : null;
      this.submitButton = this.form ? this.form.querySelector('[data-chatbot-submit]') : null;
      this.badge = root.querySelector('[data-chatbot-badge]');
      this.consentButton = null;
      this.consentPortal = null;
      this.consentCard = null;
      this.handleConsentAccept = (event) => this._grantConsent(event);

      this.state = {
        enabled: root.dataset.chatbotEnabled === 'true',
        open: false,
        consent: this._hasConsent(),
        sessionId: window.sessionStorage.getItem(STORAGE_KEYS.session) || null,
        unread: parseInt(window.sessionStorage.getItem(STORAGE_KEYS.unread) || '0', 10) || 0,
        connecting: false,
        typing: false,
        streamReady: false,
        streaming: false,
        busy: false,
        streamingBlock: false,
        message: '',
        backoffUntil: 0,
        historyLoaded: false,
      };

      this.pollTimer = null;
      this.pollInterval = 4000;
      this.isPolling = false;
      this.focusTrapHandler = this._handleFocusTrap.bind(this);
      this.handleKeyDown = this._handleKeyDown.bind(this);
      this.pendingBuffers = new Map();
      this.lastMessageId = this._readLastMessageId();
      this.historyLoading = false;
      this.backoffTimer = null;
      this.pendingUserMessages = new Map();
      this.streamController = null;
      this.statusLabels = {
        pending: 'Envoi…',
        failed: 'Non délivré',
      };
    }

    init() {
      if (!this.state.enabled || !this.trigger || !this.panel) {
        return;
      }

      if (this.state.unread > 0) {
        this._updateBadge(this.state.unread);
      }

      this.trigger.addEventListener('click', () => this.toggle());
      if (this.closeButton) {
        this.closeButton.addEventListener('click', () => this.close());
      }
      document.addEventListener('keydown', this.handleKeyDown);

      if (this.form) {
        this.form.addEventListener('submit', (event) => this._handleSubmit(event));
      }
      if (this.textarea) {
        this.textarea.addEventListener('input', () => {
          this._setMessage(this.textarea.value || '');
        });
        this._setMessage(this.textarea.value || '');
      } else {
        this.state.message = '';
      }

      if (!this.state.consent) {
        this._disableInput();
      } else {
        this._unlockInput();
      }

      this._setupConsentGate();
      this._syncSendState();
      this._scrollToBottom();
    }

    toggle() {
      if (this.state.open) {
        this.close();
      } else {
        this.open();
      }
    }

    open() {
      if (this.state.open) {
        return;
      }
      this.state.open = true;
      this.root.classList.add('chatbot-shell--open');
      this.trigger.setAttribute('aria-expanded', 'true');
      if (this.panel) {
        this.panel.setAttribute('aria-hidden', 'false');
      }
      if (this.surface) {
        this.surface.addEventListener('keydown', this.focusTrapHandler);
      }
      this._markRead();
      this._focusFirstInteractive();
      if (!this.state.historyLoaded) {
        this._loadHistory();
      }
      this._scrollToBottom();
      if (!this.state.consent) {
        this._setupConsentGate();
      }
      if (this.state.consent) {
        this._ensureSession().then(() => this._startPolling(true));
      }
    }

    close() {
      if (!this.state.open) {
        return;
      }
      this.state.open = false;
      this.root.classList.remove('chatbot-shell--open');
      this.trigger.setAttribute('aria-expanded', 'false');
      if (this.panel) {
        this.panel.setAttribute('aria-hidden', 'true');
      }
      if (this.surface) {
        this.surface.removeEventListener('keydown', this.focusTrapHandler);
      }
      this.trigger.focus({ preventScroll: true });
      this._cancelStream('panel-closed');
      this._stopPolling();
    }

    _hasConsent() {
      const cookieName = document.body ? document.body.dataset.llConsentCookie : null;
      if (!cookieName) {
        return true;
      }
      const value = (getCookie(cookieName) || '').toLowerCase();
      return ['yes', 'true', 'accept', '1'].includes(value);
    }

    _grantConsent(event) {
      if (event) {
        event.preventDefault();
      }

      const cookieName = document.body ? document.body.dataset.llConsentCookie : null;
      const name = (cookieName && cookieName.trim()) || 'cookie_consent_marketing';
      const maxAge = 15552000; // 180 days
      document.cookie = `${name}=accept; path=/; Max-Age=${maxAge}; SameSite=Lax`;

      const dataLayer = (window.dataLayer = window.dataLayer || []);
      if (typeof window.gtag !== 'function') {
        window.gtag = function gtag() {
          dataLayer.push(arguments);
        };
      }
      window.gtag('consent', 'update', {
        ad_user_data: 'granted',
        ad_personalization: 'granted',
        ad_storage: 'granted',
        analytics_storage: 'granted',
      });

      requestJSON(API.consent, { method: 'POST' }).catch((error) => {
        console.error('chatbot: consent request failed', error);
      });

      this.state.consent = true;
      this._teardownConsentGate();
      this._unlockInput();
      this._syncSendState();
      this._ensureSession();
      window.requestAnimationFrame(() => {
        if (this.textarea) {
          this.textarea.focus({ preventScroll: false });
        }
      });
      if (this.state.open) {
        if (!this.state.historyLoaded) {
          this._loadHistory();
        }
        this._startPolling(true);
      }
    }

    async _ensureSession() {
      if (this.state.sessionId || this.state.connecting) {
        return this.state.sessionId;
      }
      this.state.connecting = true;
      try {
        const payload = await requestJSON(API.start, { method: 'POST', body: {} });
        if (payload && payload.session_id) {
          this.state.sessionId = String(payload.session_id);
          window.sessionStorage.setItem(STORAGE_KEYS.session, this.state.sessionId);
        }
      } catch (error) {
        console.error('chatbot: unable to start session', error);
      } finally {
        this.state.connecting = false;
      }
      return this.state.sessionId;
    }

    _renderMessage(payload, options) {
      if (!this.messagesViewport) {
        return;
      }
      const message = payload || {};
      const role = message.role || 'assistant';
      const messageId = message.id != null ? String(message.id) : null;
      const clientId = message.client_id ? String(message.client_id) : null;
      const key = clientId || messageId || 'pending';
      const delta = typeof message.delta === 'string' ? message.delta : null;
      const content = typeof message.content === 'string' ? message.content : '';
      const isFinal = message.final === true || message.is_final === true;
      const appendMode = !!(options && options.append);
      const list = this._ensureMessageList();
      if (!list) {
        return;
      }

      let item = null;
      if (clientId) {
        item = list.querySelector(`[data-client-id="${cssEscape(clientId)}"]`);
      }
      if (!item && messageId) {
        item = list.querySelector(`[data-message-id="${cssEscape(messageId)}"]`);
      }

      if (!item) {
        item = document.createElement('li');
        item.className = `chatbot-messages__item chatbot-messages__item--${role}`;
        if (clientId) {
          item.dataset.clientId = clientId;
        }
        item.dataset.messageId = messageId || key;
        const bubble = document.createElement('div');
        bubble.className = 'chatbot-messages__bubble';
        bubble.dataset.role = role;
        item.appendChild(bubble);
        list.appendChild(item);
      } else {
        if (clientId) {
          item.dataset.clientId = clientId;
        }
        if (messageId) {
          item.dataset.messageId = messageId;
        }
        item.className = `chatbot-messages__item chatbot-messages__item--${role}`;
      }

      const bubble = item.querySelector('.chatbot-messages__bubble');
      if (bubble.dataset.role !== role) {
        bubble.dataset.role = role;
      }
      const buffer = this._bufferForMessage(clientId, messageId);
      if (delta) {
        buffer.content += delta;
      } else if (!appendMode || isFinal) {
        buffer.content = content;
      }
      bubble.innerHTML = this._formatContent(buffer.content);

      if (role === 'user') {
        if (message.pending) {
          this._updateMessageStatus(item, 'pending');
        } else if (message.failed) {
          this._updateMessageStatus(item, 'failed');
        } else if (message.final || message.sent || message.pending === false) {
          this._updateMessageStatus(item, 'sent');
        }
      }

      if (isFinal) {
        if (clientId) {
          this.pendingBuffers.delete(clientId);
        }
        if (messageId) {
          this.pendingBuffers.delete(messageId);
        }
        this.pendingBuffers.delete(key);
      } else {
        this.pendingBuffers.set(key, buffer);
      }

      const numericMessageId = messageId != null ? Number(messageId) : NaN;
      if (Number.isFinite(numericMessageId)) {
        this.lastMessageId = Math.max(this.lastMessageId || 0, numericMessageId);
      }

      if (role === 'assistant' && !this.state.open) {
        this._incrementUnread();
      }

      this._scrollToBottom();
    }

    _bufferForMessage(clientId, messageId) {
      const primaryKey = clientId || messageId || 'pending';
      let buffer = this.pendingBuffers.get(primaryKey);
      if (!buffer && clientId) {
        buffer = this.pendingBuffers.get(clientId);
      }
      if (!buffer && messageId) {
        buffer = this.pendingBuffers.get(messageId);
      }
      if (!buffer) {
        buffer = { content: '' };
      }
      if (clientId) {
        this.pendingBuffers.set(clientId, buffer);
      }
      if (messageId) {
        this.pendingBuffers.set(messageId, buffer);
      }
      this.pendingBuffers.set(primaryKey, buffer);
      return buffer;
    }

    _formatContent(text) {
      if (!text) {
        return '';
      }
      const escaped = text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
      return escaped.replace(/\n+/g, '<br />');
    }

    _ensureMessageList() {
      if (!this.messagesViewport) {
        return null;
      }
      if (!this.scrollContainer) {
        this.scrollContainer = this.messagesViewport.parentElement || this.messagesViewport;
      }
      let list = this.messagesViewport.querySelector('.chatbot-messages__list');
      if (list) {
        return list;
      }
      list = document.createElement('ul');
      list.className = 'chatbot-messages__list';
      const emptyState = this.messagesViewport.querySelector('.chatbot-messages__empty');
      if (emptyState) {
        emptyState.remove();
      }
      this.messagesViewport.appendChild(list);
      return list;
    }

    _handleSubmit(event) {
      event.preventDefault();
      if (!this.submitButton || !this.textarea) {
        return;
      }
      if (!this.state.consent) {
        this.open();
        this._syncSendState();
        return;
      }
      if (!this._computeCanSend()) {
        this._syncSendState();
        return;
      }
      const text = sanitizeText(this.state.message);
      this._setBusy(true);
      const clientId = this._queueOutgoingMessage(text);
      this._setMessage('');
      this.textarea.value = '';
      this._sendUserMessage(text, clientId);
    }

    async _sendUserMessage(text, clientId) {
      const sessionId = await this._ensureSession();
      if (!sessionId) {
        this._markMessageFailed(clientId);
        this._setBusy(false);
        return;
      }
      this._setTyping(true);
      try {
        const responsePayload = await requestJSON(API.send, {
          method: 'POST',
          body: { session_id: sessionId, message: text },
        });
        this._markMessageDelivered(clientId);
        if (responsePayload && responsePayload.assistant) {
          this._renderMessage(responsePayload.assistant, { append: true });
        }
        this._beginAssistantStream(sessionId);
      } catch (error) {
        if (error && error.status === 429) {
          this._applyBackoff(error.retryAfter);
          this._markMessageFailed(clientId, { reason: 'throttle' });
          this._pushAlert("Trop de requêtes. Réessayez dans un instant.");
        } else if (error && error.status === 403) {
          this._markMessageFailed(clientId);
          this._pushAlert('Autorisation requise pour envoyer le message. Rafraîchissez la page.');
        } else {
          console.error('chatbot: send failed', error);
          this._markMessageFailed(clientId);
          this._pushAlert("L'envoi du message a échoué. Réessayez.");
          this._renderMessage({ id: `error-${Date.now()}`, role: 'assistant', content: "Je rencontre un souci pour répondre. Réessayez dans un instant." }, { append: true });
        }
      } finally {
        this._setTyping(false);
        this._setBusy(false);
        this._syncSendState();
        if (!this.state.streaming && this.state.open && this.state.consent) {
          this._startPolling(true);
        }
      }
    }

    _queueOutgoingMessage(text) {
      const clientId = `client-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      this.pendingUserMessages.set(clientId, { text });
      this._renderMessage({ id: clientId, client_id: clientId, role: 'user', content: text, pending: true }, { append: true });
      const item = this._findMessageElementByClientId(clientId);
      this._updateMessageStatus(item, 'pending');
      this._scrollToBottom();
      if (this.lastMessageId == null) {
        this.lastMessageId = 0;
      }
      return clientId;
    }

    _setBusy(isBusy) {
      const nextValue = Boolean(isBusy);
      if (this.state.busy === nextValue) {
        return;
      }
      this.state.busy = nextValue;
      this._syncSendState();
    }

    _markMessageDelivered(clientId) {
      const item = this._findMessageElementByClientId(clientId);
      if (item) {
        this._updateMessageStatus(item, 'sent');
        item.removeAttribute('data-client-id');
      }
      this.pendingUserMessages.delete(clientId);
    }

    _markMessageFailed(clientId, options) {
      const item = this._findMessageElementByClientId(clientId);
      if (item) {
        this._updateMessageStatus(item, 'failed');
      }
      if (options && options.reason === 'throttle') {
        this.pendingUserMessages.set(clientId, {
          ...(this.pendingUserMessages.get(clientId) || {}),
          throttled: true,
        });
      }
      this._syncSendState();
    }

    _setMessage(value) {
      const nextValue = typeof value === 'string' ? value : '';
      if (this.state.message === nextValue) {
        this._syncSendState();
        return;
      }
      this.state.message = nextValue;
      this._syncSendState();
    }

    _findMessageElementByClientId(clientId) {
      if (!clientId || !this.messagesViewport) {
        return null;
      }
      return this.messagesViewport.querySelector(`[data-client-id="${cssEscape(clientId)}"]`);
    }

    _updateMessageStatus(item, status) {
      if (!item) {
        return;
      }
      item.classList.remove('chatbot-messages__item--pending', 'chatbot-messages__item--failed');
      if (status === 'pending') {
        item.classList.add('chatbot-messages__item--pending');
      } else if (status === 'failed') {
        item.classList.add('chatbot-messages__item--failed');
      }
      item.dataset.messageState = status;
      const bubble = item.querySelector('.chatbot-messages__bubble');
      if (!bubble) {
        return;
      }
      let statusEl = bubble.querySelector('.chatbot-messages__status');
      if (status === 'sent') {
        if (statusEl) {
          statusEl.remove();
        }
        return;
      }
      if (!statusEl) {
        statusEl = document.createElement('span');
        statusEl.className = 'chatbot-messages__status';
        bubble.appendChild(statusEl);
      }
      statusEl.textContent = status === 'pending' ? this.statusLabels.pending : this.statusLabels.failed;
    }

    _computeCanSend() {
      const trimmed = (this.state.message || '').trim();
      const backoffActive = this.state.backoffUntil && Date.now() < this.state.backoffUntil;
      return Boolean(
        this.state.consent &&
        !this.state.busy &&
        !this.state.streamingBlock &&
        !backoffActive &&
        trimmed.length > 0
      );
    }

    _syncSendState() {
      if (!this.submitButton) {
        return;
      }
      const canSend = this._computeCanSend();
      if (canSend) {
        this.submitButton.removeAttribute('disabled');
      } else {
        this.submitButton.setAttribute('disabled', 'disabled');
      }
    }

    _applyBackoff(retryAfterHeader) {
      const retrySeconds = Number(retryAfterHeader);
      const minDelay = 4000;
      const maxDelay = 10000;
      let delay = Number.isFinite(retrySeconds) && retrySeconds > 0 ? retrySeconds * 1000 : minDelay;
      delay = Math.min(Math.max(delay, minDelay), maxDelay);
      this.state.backoffUntil = Date.now() + delay;
      if (this.backoffTimer) {
        clearTimeout(this.backoffTimer);
      }
      this.backoffTimer = window.setTimeout(() => {
        this.backoffTimer = null;
        this.state.backoffUntil = 0;
        this._syncSendState();
      }, delay);
      this._syncSendState();
    }

    _setStreaming(isStreaming, options = {}) {
      const next = Boolean(isStreaming);
      const block = options.block;
      if (this.state.streaming === next && block === undefined) {
        return;
      }
      this.state.streaming = next;
      if (typeof block === 'boolean') {
        this.state.streamingBlock = block;
      }
      if (!next && block === undefined) {
        this.state.streamingBlock = false;
      }
      this._syncSendState();
    }

    _cancelStream(reason) {
      if (this.streamController) {
        this.streamController.abort(reason || 'cancelled');
        this.streamController = null;
      }
      this._setStreaming(false);
    }

    _beginAssistantStream(sessionId) {
      if (!sessionId || this.state.streamingBlock) {
        return;
      }
      this._cancelStream('restart');

      const params = new URLSearchParams({ session: sessionId });
      if (this.lastMessageId != null) {
        params.append('cursor', String(this.lastMessageId));
      }

      const controller = new AbortController();
      this.streamController = controller;
      this._setStreaming(true);

      const decoder = new TextDecoder();
      let buffer = '';

      const processLine = (rawLine) => {
        const line = (rawLine || '').trim();
        if (!line) {
          return;
        }
        if (line.startsWith(':')) {
          return;
        }
        if (line === '[DONE]') {
          this._finalizeStream();
          return;
        }
        let payloadText = line;
        if (payloadText.startsWith('data:')) {
          payloadText = payloadText.replace(/^data:\s*/, '');
          if (payloadText === '[DONE]') {
            this._finalizeStream();
            return;
          }
        }
        try {
          const payload = JSON.parse(payloadText);
          this._handleStreamPayload(payload);
        } catch (error) {
          console.warn('chatbot: unable to parse stream payload', error, payloadText);
        }
      };

      const flushBuffer = () => {
        let newlineIndex = buffer.indexOf('\n');
        while (newlineIndex >= 0) {
          const line = buffer.slice(0, newlineIndex);
          buffer = buffer.slice(newlineIndex + 1);
          processLine(line.replace(/\r$/, ''));
          newlineIndex = buffer.indexOf('\n');
        }
      };

      fetch(`${API.stream}?${params.toString()}`, {
        signal: controller.signal,
        headers: {
          Accept: 'text/event-stream, application/x-ndjson, application/json',
        },
        credentials: 'same-origin',
      })
        .then((response) => {
          if (!response.ok) {
            const error = new Error(`chatbot stream failed (${response.status})`);
            error.status = response.status;
            throw error;
          }
          return response.body;
        })
        .then(async (body) => {
          if (!body) {
            return;
          }
          const reader = body.getReader();
          while (true) {
            const { value, done } = await reader.read();
            if (done) {
              break;
            }
            if (value) {
              buffer += decoder.decode(value, { stream: true });
              flushBuffer();
            }
          }
          const tail = decoder.decode();
          if (tail) {
            buffer += tail;
            flushBuffer();
          }
          if (buffer.trim()) {
            processLine(buffer.trim());
            buffer = '';
          }
        })
        .catch((error) => {
          if (controller.signal.aborted) {
            return;
          }
          console.error('chatbot: stream error', error);
          if (error && error.status === 429) {
            this._applyBackoff(error.retryAfter);
            this._pushAlert("Trop de requêtes. Le flux de réponse est interrompu.");
          } else {
            this._pushAlert("La réponse ne peut pas être diffusée pour le moment.");
          }
        })
        .finally(() => {
          if (this.streamController === controller) {
            this.streamController = null;
          }
          this._finalizeStream();
        });
    }

    _handleStreamPayload(payload) {
      if (!payload) {
        return;
      }
      if (payload.error) {
        this._pushAlert(payload.error.message || 'Une erreur est survenue pendant la diffusion.');
        return;
      }
      if (payload.done === true || payload.event === 'done' || payload.type === 'done') {
        this._finalizeStream();
        return;
      }
      const message = payload.message || payload;
      if (!message) {
        return;
      }
      this._renderMessage(message, { append: true });
      if (message.final === true || message.is_final === true) {
        this._finalizeStream();
      }
    }

    _finalizeStream() {
      this._setStreaming(false, { block: false });
      if (this.state.open && this.state.consent) {
        this._startPolling(true);
      }
    }

    _pushAlert(message) {
      const text = sanitizeText(message);
      if (!text) {
        return;
      }
      this._renderMessage({ id: `alert-${Date.now()}`, role: 'system', content: text, final: true }, { append: true });
      this._scrollToBottom();
    }

    _loadHistory() {
      if (this.historyLoading || this.state.historyLoaded) {
        return;
      }

      const existingSession = this.state.sessionId;
      this.historyLoading = true;

      const sessionPromise = existingSession
        ? Promise.resolve(existingSession)
        : this._ensureSession();

      let resolvedSessionId = null;

      Promise.resolve(sessionPromise)
        .then((sessionId) => {
          resolvedSessionId = sessionId;
          if (!sessionId) {
            return null;
          }
          const params = new URLSearchParams({ session: sessionId, limit: '50' });
          return requestJSON(`${API.history}?${params.toString()}`, {
            headers: { Accept: 'application/json' },
          });
        })
        .then((payload) => {
          if (!resolvedSessionId) {
            return;
          }
          const messages = Array.isArray(payload?.messages) ? payload.messages : [];
          if (messages.length) {
            this._replaceMessages(messages);
            this._scrollToBottom();
          }
          this.state.historyLoaded = true;
        })
        .catch((error) => {
          console.error('chatbot: history request failed', error);
          this.state.historyLoaded = false;
        })
        .finally(() => {
          this.historyLoading = false;
        });
    }

    _setTyping(isTyping) {
      this.state.typing = isTyping;
      setHidden(this.typingIndicator, !isTyping);
    }

    _scrollToBottom() {
      const scrollTarget = this.scrollContainer || this.messagesViewport;
      if (!scrollTarget) {
        return;
      }
      window.requestAnimationFrame(() => {
        scrollTarget.scrollTop = scrollTarget.scrollHeight;
      });
    }

    _focusFirstInteractive() {
      if (!this.surface) {
        return;
      }
      const candidates = this.surface.querySelectorAll('[data-chatbot-consent-accept], textarea, button:not([disabled]), a[href]');
      const focusable = Array.from(candidates).find((element) => element.offsetParent !== null && !element.hasAttribute('disabled'));
      if (focusable) {
        focusable.focus({ preventScroll: true });
      }
    }

    _handleFocusTrap(event) {
      if (!this.state.open || event.key !== 'Tab') {
        return;
      }
      const focusable = this._getFocusableElements();
      if (focusable.length === 0) {
        event.preventDefault();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey) {
        if (document.activeElement === first) {
          event.preventDefault();
          last.focus();
        }
      } else if (document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    _getFocusableElements() {
      if (!this.surface) {
        return [];
      }
      return Array.from(this.surface.querySelectorAll(FOCUSABLE_SELECTOR)).filter((element) => element.offsetParent !== null);
    }

    _handleKeyDown(event) {
      if (!this.state.open) {
        return;
      }
      if (event.key === 'Escape') {
        event.preventDefault();
        this.close();
      }
    }

    _markRead() {
      this.state.unread = 0;
      window.sessionStorage.removeItem(STORAGE_KEYS.unread);
      this._updateBadge(0);
    }

    _incrementUnread() {
      this.state.unread += 1;
      window.sessionStorage.setItem(STORAGE_KEYS.unread, String(this.state.unread));
      this._updateBadge(this.state.unread);
    }

    _updateBadge(count) {
      if (!this.badge) {
        return;
      }
      if (count > 0) {
        this.badge.textContent = String(count);
        this.badge.removeAttribute('hidden');
      } else {
        this.badge.textContent = '0';
        this.badge.setAttribute('hidden', '');
      }
    }

    _readLastMessageId() {
      const lastItem = this.messagesViewport
        ? this.messagesViewport.querySelector('.chatbot-messages__item:last-of-type')
        : null;
      if (!lastItem) {
        return null;
      }
      const value = lastItem.getAttribute('data-message-id');
      const numeric = value != null ? Number(value) : NaN;
      return Number.isFinite(numeric) ? numeric : null;
    }

    _startPolling(immediate = false) {
      if (!this.state.consent || !this.state.open || this.state.streaming) {
        return;
      }
      if (this.isPolling) {
        return;
      }
      if (this.pollTimer) {
        clearTimeout(this.pollTimer);
        this.pollTimer = null;
      }
      if (immediate) {
        this._pollMessages();
      } else {
        this._scheduleNextPoll(this.pollInterval);
      }
    }

    _stopPolling() {
      if (this.pollTimer) {
        clearTimeout(this.pollTimer);
        this.pollTimer = null;
      }
      this.isPolling = false;
    }

    _scheduleNextPoll(delay) {
      if (!this.state.open || !this.state.consent) {
        this._stopPolling();
        return;
      }
      const safeDelay = Math.max(0, Number(delay) || this.pollInterval);
      if (this.pollTimer) {
        clearTimeout(this.pollTimer);
      }
      this.pollTimer = window.setTimeout(() => {
        this.pollTimer = null;
        this._pollMessages();
      }, safeDelay);
    }

    _pollMessages() {
      if (!this.state.open || !this.state.consent || this.isPolling) {
        return;
      }

      if (this.pollTimer) {
        clearTimeout(this.pollTimer);
        this.pollTimer = null;
      }

      this.isPolling = true;
      let nextDelay = this.pollInterval;

      Promise.resolve(this._ensureSession())
        .then((sessionId) => {
          if (!sessionId) {
            return null;
          }
          const params = new URLSearchParams({ session: sessionId, limit: '50' });
          if (this.lastMessageId != null) {
            params.append('cursor', String(this.lastMessageId));
          }
          return requestJSON(`${API.stream}?${params.toString()}`, {
            headers: { Accept: 'application/json' },
          })
            .then((data) => {
              const messages = Array.isArray(data?.messages) ? data.messages : [];
              if (this.lastMessageId == null) {
                this._replaceMessages(messages);
              } else {
                messages.forEach((message) => this._renderMessage(message, { append: true }));
              }
              if (messages.length) {
                const last = messages[messages.length - 1];
                const numericId = last && last.id != null ? Number(last.id) : NaN;
                if (Number.isFinite(numericId)) {
                  this.lastMessageId = Math.max(this.lastMessageId || 0, numericId);
                }
              }
              this._setTyping(false);
              nextDelay = this.pollInterval;
            })
            .catch((error) => {
              if (error && error.status === 429) {
                const retryAfter = error.retryAfter ? Number(error.retryAfter) : NaN;
                if (Number.isFinite(retryAfter) && retryAfter > 0) {
                  nextDelay = Math.max(retryAfter * 1000, 10000);
                } else {
                  nextDelay = 10000;
                }
              } else {
                console.error('chatbot: poll failed', error);
                nextDelay = Math.min(this.pollInterval * 2, 15000);
              }
            });
        })
        .catch((error) => {
          console.error('chatbot: poll setup failed', error);
          nextDelay = Math.min(this.pollInterval * 2, 15000);
        })
        .finally(() => {
          this.isPolling = false;
          if (!this.state.open || !this.state.consent) {
            this._stopPolling();
            return;
          }
          this._scheduleNextPoll(nextDelay);
        });
    }

    _replaceMessages(messages) {
      if (!this.messagesViewport) {
        return;
      }
      const list = this._ensureMessageList();
      if (!list) {
        return;
      }
      const pendingFragment = document.createDocumentFragment();
      const pendingNodes = Array.from(list.querySelectorAll('[data-client-id]'));
      pendingNodes.forEach((node) => {
        pendingFragment.appendChild(node);
      });

      list.innerHTML = '';
      messages.forEach((message) => {
        this._renderMessage(message, { append: true });
      });
      if (pendingFragment.childNodes.length) {
        list.appendChild(pendingFragment);
      }
      if (messages.length) {
        const last = messages[messages.length - 1];
        const numericId = last && last.id != null ? Number(last.id) : NaN;
        if (Number.isFinite(numericId)) {
          this.lastMessageId = Math.max(this.lastMessageId || 0, numericId);
        }
      } else {
        this.lastMessageId = null;
      }
    }

    _setupConsentGate() {
      if (!this.panel) {
        return;
      }

      const gateInPanel = this.panel.querySelector('[data-chatbot-consent]');
      if (this.state.consent) {
        if (gateInPanel) {
          gateInPanel.remove();
        }
        this._teardownConsentGate();
        return;
      }

      let portal = this.consentPortal;
      if (!portal) {
        portal = document.createElement('div');
        portal.className = 'chat-consent-portal';
        portal.dataset.chatbotConsentPortal = 'true';
      }

      document.querySelectorAll('[data-chatbot-consent-portal]').forEach((node) => {
        if (node !== portal) {
          node.remove();
        }
      });

      let gate = gateInPanel || this.consentCard;
      if (!gate && portal) {
        gate = portal.querySelector('[data-chatbot-consent]');
      }
      if (!gate) {
        return;
      }

      if (!portal.contains(gate)) {
        portal.appendChild(gate);
      }

      if (portal.parentElement !== document.body) {
        document.body.appendChild(portal);
      } else {
        document.body.appendChild(portal);
      }

      if (this.consentButton) {
        this.consentButton.removeEventListener('click', this.handleConsentAccept);
      }

      this.consentPortal = portal;
      this.consentCard = gate;
      this.consentButton = gate.querySelector('[data-chatbot-consent-accept]');
      if (this.consentButton) {
        this.consentButton.addEventListener('click', this.handleConsentAccept);
      }
    }

    _teardownConsentGate() {
      if (this.consentButton) {
        this.consentButton.removeEventListener('click', this.handleConsentAccept);
        this.consentButton = null;
      }
      if (this.consentPortal) {
        this.consentPortal.remove();
        this.consentPortal = null;
      }
      if (this.consentCard) {
        this.consentCard.remove();
        this.consentCard = null;
      }
    }

    _disableInput() {
      if (this.form) {
        this.form.setAttribute('aria-disabled', 'true');
      }
      if (this.textarea) {
        this.textarea.removeAttribute('disabled');
      }
      this._syncSendState();
      this._stopPolling();
    }

    _unlockInput() {
      if (this.form) {
        this.form.removeAttribute('aria-disabled');
      }
      if (this.textarea) {
        this.textarea.removeAttribute('disabled');
      }
      this._syncSendState();
    }
  }

  function bootstrap() {
    const root = document.querySelector('[data-chatbot]');
    if (!root) {
      return;
    }
    const controller = new ChatbotController(root);
    controller.init();
    window.__chat = controller;
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bootstrap);
  } else {
    bootstrap();
  }
})();
