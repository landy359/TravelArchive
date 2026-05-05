/**
 * notification.js
 * 알림 패널 — 벨 아이콘 클릭 시 드롭다운, 세션 초대 수락/거절 처리.
 */

import { BackendHooks } from './api.js';

export const NotificationManager = {
  _panel: null,
  _badge: null,
  _btn: null,
  _pollTimer: null,

  _sseConn: null,

  init(elements, state) {
    this._btn   = elements.notifBtn;
    this._badge = elements.notifBadge;
    if (!this._btn) return;

    this._panel = this._createPanel();
    document.body.appendChild(this._panel);

    this._btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const open = this._panel.classList.toggle('notif-panel-open');
      if (open) this._render(state, elements);
    });

    document.addEventListener('click', (e) => {
      if (!this._panel.contains(e.target) && e.target !== this._btn) {
        this._panel.classList.remove('notif-panel-open');
      }
    });
  },

  startSSE(state, elements) {
    if (this._sseConn) return; // 이미 연결 중
    let closed = false;
    let retryDelay = 3000;
    const connect = async () => {
      while (!closed) {
        try {
          const token = (await import('./api.js')).TokenManager.getAccessToken();
          const res = await fetch('/api/notifications/stream', {
            headers: token ? { Authorization: `Bearer ${token}` } : {},
          });
          if (!res.ok) throw new Error(`Notif SSE ${res.status}`);
          retryDelay = 3000;
          const reader = res.body.getReader();
          const decoder = new TextDecoder();
          let buf = '';
          while (!closed) {
            const { done, value } = await reader.read();
            if (done) break;
            buf += decoder.decode(value, { stream: true });
            const parts = buf.split('\n\n');
            buf = parts.pop() ?? '';
            for (const part of parts) {
              const m = part.match(/^data: (.+)$/m);
              if (m) {
                try {
                  const ev = JSON.parse(m[1]);
                  if (ev.type === 'notification') {
                    if (ev.sub_type === 'new_message') {
                      // 해당 세션 아이템의 dot만 파란색으로 켬 (전체 목록 재렌더 불필요)
                      const sid = ev.session_id;
                      if (sid) {
                        const wrapper = document.querySelector(`.sidebar-item-wrapper[data-session-id="${sid}"]`);
                        const dot = wrapper?.querySelector('.trip-color-dot');
                        if (dot) dot.classList.add('unread');
                      }
                    } else {
                      // 초대 등 일반 알림: 뱃지 증가
                      const cur = parseInt(this._badge?.textContent) || 0;
                      const next = cur + 1;
                      if (this._badge) {
                        this._badge.textContent = next > 99 ? '99+' : next;
                        this._badge.style.display = '';
                      }
                      // 패널 열려있으면 갱신
                      if (this._panel?.classList.contains('notif-panel-open')) {
                        this._render(state, elements);
                      }
                    }
                  }
                } catch {}
              }
            }
          }
        } catch (e) {
          if (closed) return;
        }
        if (!closed) await new Promise(r => setTimeout(r, retryDelay));
        retryDelay = Math.min(retryDelay * 1.5, 30000);
      }
    };
    this._sseConn = { close: () => { closed = true; } };
    connect();
  },

  stopSSE() {
    this._sseConn?.close();
    this._sseConn = null;
  },

  _createPanel() {
    const el = document.createElement('div');
    el.className = 'notif-panel';
    el.innerHTML = `
      <div class="notif-panel-header">
        <span>알림</span>
        <button class="notif-clear-btn" title="알림 목록 지우기">&#8722;</button>
      </div>
      <div class="notif-panel-body"></div>`;
    el.querySelector('.notif-clear-btn').addEventListener('click', async () => {
      try {
        await BackendHooks.clearViewedNotifications();
        // 패널 UI에서 즉시 제거 (DB는 유지)
        const body = el.querySelector('.notif-panel-body');
        if (body) body.innerHTML = '<div class="notif-empty">알림이 없습니다</div>';
        this._updateBadge(0);
      } catch (e) {
        console.error('[Notification] clear failed:', e);
      }
    });
    return el;
  },

  async refresh(state, elements) {
    if (!BackendHooks.fetchNotifications) return;
    try {
      const notifs = await BackendHooks.fetchNotifications();
      const unread = notifs.filter(n => !n.is_read).length;
      this._updateBadge(unread);
      if (this._panel?.classList.contains('notif-panel-open')) {
        this._renderItems(notifs, state, elements);
      }
    } catch (e) {
      console.error('[Notification] refresh failed:', e);
    }
  },

  _updateBadge(count) {
    if (!this._badge) return;
    if (count > 0) {
      this._badge.textContent = count > 99 ? '99+' : count;
      this._badge.style.display = '';
    } else {
      this._badge.style.display = 'none';
    }
  },

  async _render(state, elements) {
    const body = this._panel.querySelector('.notif-panel-body');
    body.innerHTML = '<div class="notif-loading">불러오는 중...</div>';
    try {
      const notifs = await BackendHooks.fetchNotifications();
      this._updateBadge(notifs.filter(n => !n.is_read).length);
      this._renderItems(notifs, state, elements);
    } catch {
      body.innerHTML = '<div class="notif-empty">알림을 불러올 수 없습니다</div>';
    }
  },

  _renderItems(notifs, state, elements) {
    const body = this._panel.querySelector('.notif-panel-body');
    if (!notifs.length) {
      body.innerHTML = '<div class="notif-empty">알림이 없습니다</div>';
      return;
    }

    body.innerHTML = '';
    for (const n of notifs) {
      const item = document.createElement('div');
      item.className = 'notif-item' + (n.is_read ? ' notif-read' : '');
      item.dataset.id = n.notification_id;

      // 출처 표시 (세션 멘션, 초대 등)
      const sourceSessionId = n.reference_type === 'session' ? n.reference_id : null;

      const msgWrap = document.createElement('div');
      msgWrap.className = 'notif-msg-wrap';

      const msg = document.createElement('p');
      msg.className = 'notif-msg';
      msg.textContent = n.message;
      msgWrap.appendChild(msg);

      // 클릭 시 source 세션으로 이동 (멘션, 초대 수락 후 읽음 처리된 경우 등)
      if (sourceSessionId && n.type !== 'session_invite') {
        item.style.cursor = 'pointer';
        item.title = '해당 대화로 이동';
        item.addEventListener('click', async () => {
          this._panel.classList.remove('notif-panel-open');
          if (!n.is_read) {
            try {
              await BackendHooks.dismissNotification(n.notification_id);
              item.classList.add('notif-read');
              const unreadCount = this._panel.querySelectorAll('.notif-item:not(.notif-read)').length;
              this._updateBadge(unreadCount);
            } catch (e) {
              console.error('[Notification] mark read failed:', e);
            }
          }
          if (n.type === 'mention') elements._switchToTeamMode?.();
          window.location.hash = `#/chat/${sourceSessionId}`;
        });
      }

      item.appendChild(msgWrap);

      if (!n.is_read && n.type === 'session_invite') {
        const actions = document.createElement('div');
        actions.className = 'notif-actions';

        const acceptBtn = document.createElement('button');
        acceptBtn.className = 'notif-accept-btn';
        acceptBtn.textContent = '수락';
        acceptBtn.addEventListener('click', async (e) => {
          e.stopPropagation();
          acceptBtn.disabled = true;
          rejectBtn.disabled = true;
          try {
            const result = await BackendHooks.acceptNotification(n.notification_id);
            item.remove();
            this._updateBadge(
              this._panel.querySelectorAll('.notif-item:not(.notif-read)').length
            );
            this._panel.classList.remove('notif-panel-open');

            if (result.session_id) {
              // 팀 플래너 탭으로 전환 후 해당 세션으로 이동
              elements._switchToTeamMode?.();
              // 사이드바 즉시 갱신
              elements._refreshSessions?.();
              window.location.hash = `#/chat/${result.session_id}`;
            }
          } catch {
            acceptBtn.disabled = false;
            rejectBtn.disabled = false;
          }
        });

        const rejectBtn = document.createElement('button');
        rejectBtn.className = 'notif-reject-btn';
        rejectBtn.textContent = '거절';
        rejectBtn.addEventListener('click', async (e) => {
          e.stopPropagation();
          acceptBtn.disabled = true;
          rejectBtn.disabled = true;
          try {
            await BackendHooks.dismissNotification(n.notification_id);
            item.remove();
            this._updateBadge(
              this._panel.querySelectorAll('.notif-item:not(.notif-read)').length
            );
          } catch {
            acceptBtn.disabled = false;
            rejectBtn.disabled = false;
          }
        });

        actions.appendChild(acceptBtn);
        actions.appendChild(rejectBtn);
        item.appendChild(actions);
      }
      body.appendChild(item);
    }
  },

  startPolling(state, elements, intervalMs = 30000) {
    this.stopPolling();
    this.refresh(state, elements);
    this._pollTimer = setInterval(() => this.refresh(state, elements), intervalMs);
  },

  stopPolling() {
    if (this._pollTimer) {
      clearInterval(this._pollTimer);
      this._pollTimer = null;
    }
    this._updateBadge(0);
    if (this._panel) this._panel.classList.remove('notif-panel-open');
  },
};
