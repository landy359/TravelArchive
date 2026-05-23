/**
 * notification.js  —  하위 호환 facade
 *
 * 실제 위젯은 widgets/notification-panel/.
 * NotificationManager 의 init/startSSE/stopSSE/startPolling/stopPolling
 * 호출 시그니처는 그대로 유지된다.
 */

import { BackendHooks, TokenManager } from './api.js';
import { attach } from '../widgets/notification-panel/index.js';

export const NotificationManager = {
  _handle: null,

  init(elements, state) {
    if (!elements?.notifBtn || this._handle) return;

    this._handle = attach(elements.notifBtn, elements.notifBadge, {
      fetchNotifications:        () => BackendHooks.fetchNotifications(),
      acceptNotification:        (id) => BackendHooks.acceptNotification(id),
      dismissNotification:       (id) => BackendHooks.dismissNotification(id),
      clearViewedNotifications:  () => BackendHooks.clearViewedNotifications(),
      getAccessToken:            () => TokenManager.getAccessToken(),

      onMention: (sessionId, n) => {
        if (n?.type === 'mention') elements._switchToTeamMode?.();
        window.location.hash = `#/chat/${sessionId}`;
      },

      onAccept: (sessionId) => {
        elements._switchToTeamMode?.();
        elements._refreshSessions?.();
        window.location.hash = `#/chat/${sessionId}`;
      },

      onNewMessage: (sessionId) => {
        const wrapper = document.querySelector(`.sidebar-item-wrapper[data-session-id="${sessionId}"]`);
        const dot = wrapper?.querySelector('.trip-color-dot');
        if (dot) dot.classList.add('unread');
      },

      onSessionLeft: (sessionId) => {
        elements._refreshSessions?.();
        if (window.location.hash === `#/chat/${sessionId}`) {
          window.location.hash = '#/';
        }
      },
    });
  },

  startSSE()      { this._handle?.startSSE(); },
  stopSSE()       { this._handle?.stopSSE(); },
  startPolling(state, elements, intervalMs) {
    this._handle?.startPolling(intervalMs);
  },
  stopPolling()   { this._handle?.stopPolling(); },

  refresh(state, elements) { return this._handle?.refresh(); },
};
