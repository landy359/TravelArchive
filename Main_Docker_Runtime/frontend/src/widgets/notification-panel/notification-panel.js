/**
 * notification-panel widget
 *
 * 벨 아이콘 클릭 시 열리는 알림 드롭다운.
 * SSE 실시간 + 폴링 폴백 + 초대 수락/거절 + 멘션 클릭 이동까지 일체 책임.
 *
 * 모든 백엔드 호출과 부수효과(콜백) 는 의존성 주입(DI) 로 받아
 * 위젯 자체는 BackendHooks 에 종속되지 않는다.
 *
 * Usage:
 *   import { attach } from '@/widgets/notification-panel';
 *   const panel = attach(triggerBtnEl, badgeEl, {
 *     fetchNotifications, acceptNotification,
 *     dismissNotification, clearViewedNotifications,
 *     getAccessToken,
 *     onMention:    (sessionId) => { ... },
 *     onAccept:     (sessionId) => { ... },
 *     onNewMessage: (sessionId) => { ... },
 *   });
 *   panel.startSSE();
 *   panel.startPolling();
 *   panel.refresh();
 *   panel.destroy();
 */

import templateHtml from './notification-panel.html?raw';
import './notification-panel.css';

/**
 * @param {HTMLElement} triggerBtn  벨 버튼
 * @param {HTMLElement} badgeEl     뱃지 카운트 요소
 * @param {object} deps  외부 의존성
 */
export function attach(triggerBtn, badgeEl, {
  fetchNotifications,
  acceptNotification,
  dismissNotification,
  clearViewedNotifications,
  getAccessToken,
  onMention      = () => {},
  onAccept       = () => {},
  onNewMessage   = () => {},
  onSessionLeft  = () => {},
  pollIntervalMs = 30000,
} = {}) {
  if (!triggerBtn) {
    return { refresh:()=>{}, open:()=>{}, close:()=>{}, startSSE:()=>{}, stopSSE:()=>{}, startPolling:()=>{}, stopPolling:()=>{}, destroy:()=>{} };
  }

  // 패널 DOM
  const tpl = document.createElement('template');
  tpl.innerHTML = templateHtml.trim();
  const panel = tpl.content.firstElementChild;
  document.body.appendChild(panel);

  const body     = panel.querySelector('[data-body]');
  const clearBtn = panel.querySelector('[data-clear]');

  // 상태
  let pollTimer = null;
  let sseConn   = null;

  // ── 뱃지 ──
  const updateBadge = (count) => {
    if (!badgeEl) return;
    if (count > 0) {
      badgeEl.textContent = count > 99 ? '99+' : count;
      badgeEl.style.display = '';
    } else {
      badgeEl.style.display = 'none';
    }
  };

  // ── 항목 렌더 ──
  const renderItems = (notifs) => {
    if (!notifs.length) {
      body.innerHTML = '<div class="notif-empty">알림이 없습니다</div>';
      return;
    }
    body.innerHTML = '';
    for (const n of notifs) {
      body.appendChild(buildItem(n));
    }
  };

  const buildItem = (n) => {
    const item = document.createElement('div');
    item.className = 'notif-item' + (n.is_read ? ' notif-read' : '');
    item.dataset.id = n.notification_id;

    const sourceSessionId = n.reference_type === 'session' ? n.reference_id : null;

    const msgWrap = document.createElement('div');
    msgWrap.className = 'notif-msg-wrap';
    const msg = document.createElement('p');
    msg.className = 'notif-msg';
    msg.textContent = n.message;
    msgWrap.appendChild(msg);
    item.appendChild(msgWrap);

    // 멘션 등 — 클릭 시 해당 세션으로
    if (sourceSessionId && n.type !== 'session_invite') {
      item.style.cursor = 'pointer';
      item.title = '해당 대화로 이동';
      item.addEventListener('click', async () => {
        close();
        if (!n.is_read) {
          try {
            await dismissNotification(n.notification_id);
            item.classList.add('notif-read');
            updateBadge(panel.querySelectorAll('.notif-item:not(.notif-read)').length);
          } catch (e) {
            console.error('[Notification] mark read failed:', e);
          }
        }
        onMention(sourceSessionId, n);
      });
    }

    // 세션 초대 — 수락/거절 버튼
    if (!n.is_read && n.type === 'session_invite') {
      const actions = document.createElement('div');
      actions.className = 'notif-actions';

      const acceptBtn = document.createElement('button');
      acceptBtn.className = 'notif-accept-btn';
      acceptBtn.textContent = '수락';

      const rejectBtn = document.createElement('button');
      rejectBtn.className = 'notif-reject-btn';
      rejectBtn.textContent = '거절';

      acceptBtn.addEventListener('click', async (e) => {
        e.stopPropagation();
        acceptBtn.disabled = true;
        rejectBtn.disabled = true;
        try {
          const result = await acceptNotification(n.notification_id);
          item.remove();
          updateBadge(panel.querySelectorAll('.notif-item:not(.notif-read)').length);
          close();
          if (result?.session_id) onAccept(result.session_id, result);
        } catch {
          acceptBtn.disabled = false;
          rejectBtn.disabled = false;
        }
      });

      rejectBtn.addEventListener('click', async (e) => {
        e.stopPropagation();
        acceptBtn.disabled = true;
        rejectBtn.disabled = true;
        try {
          await dismissNotification(n.notification_id);
          item.remove();
          updateBadge(panel.querySelectorAll('.notif-item:not(.notif-read)').length);
        } catch {
          acceptBtn.disabled = false;
          rejectBtn.disabled = false;
        }
      });

      actions.appendChild(acceptBtn);
      actions.appendChild(rejectBtn);
      item.appendChild(actions);
    }

    return item;
  };

  // ── 패널 열기/닫기 ──
  const open = () => panel.classList.add('notif-panel-open');
  const close = () => panel.classList.remove('notif-panel-open');
  const isOpen = () => panel.classList.contains('notif-panel-open');

  const refresh = async () => {
    if (!fetchNotifications) return;
    try {
      const notifs = await fetchNotifications();
      const unread = notifs.filter(n => !n.is_read).length;
      updateBadge(unread);
      if (isOpen()) renderItems(notifs);
    } catch (e) {
      console.error('[Notification] refresh failed:', e);
    }
  };

  const renderOnOpen = async () => {
    body.innerHTML = '<div class="notif-loading">불러오는 중...</div>';
    try {
      const notifs = await fetchNotifications();
      updateBadge(notifs.filter(n => !n.is_read).length);
      renderItems(notifs);
    } catch {
      body.innerHTML = '<div class="notif-empty">알림을 불러올 수 없습니다</div>';
    }
  };

  // ── 이벤트 ──
  const onTriggerClick = (e) => {
    e.stopPropagation();
    const willOpen = !isOpen();
    panel.classList.toggle('notif-panel-open', willOpen);
    if (willOpen) renderOnOpen();
  };
  const onDocClick = (e) => {
    if (!panel.contains(e.target) && e.target !== triggerBtn) close();
  };

  triggerBtn.addEventListener('click', onTriggerClick);
  document.addEventListener('click', onDocClick);

  clearBtn.addEventListener('click', async () => {
    try {
      await clearViewedNotifications();
      body.innerHTML = '<div class="notif-empty">알림이 없습니다</div>';
      updateBadge(0);
    } catch (e) {
      console.error('[Notification] clear failed:', e);
    }
  });

  // ── SSE ──
  const startSSE = () => {
    if (sseConn) return;
    let closed = false;
    let retryDelay = 3000;
    const connect = async () => {
      while (!closed) {
        try {
          const token = getAccessToken?.();
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
              if (!m) continue;
              try {
                const ev = JSON.parse(m[1]);
                if (ev.type === 'session_left') {
                  onSessionLeft(ev.session_id);
                  continue;
                }
                if (ev.type === 'analysis_update') {
                  document.dispatchEvent(new CustomEvent('ta:analysis-update', { detail: ev.analysis }));
                  continue;
                }
                if (ev.type !== 'notification') continue;
                if (ev.sub_type === 'new_message') {
                  if (ev.session_id) onNewMessage(ev.session_id, ev);
                } else {
                  // 초대 등 일반 알림 — 뱃지 증가
                  const cur = parseInt(badgeEl?.textContent) || 0;
                  updateBadge(cur + 1);
                  if (isOpen()) refresh();
                }
              } catch {}
            }
          }
        } catch {
          if (closed) return;
        }
        if (!closed) await new Promise(r => setTimeout(r, retryDelay));
        retryDelay = Math.min(retryDelay * 1.5, 30000);
      }
    };
    sseConn = { close: () => { closed = true; } };
    connect();
  };

  const stopSSE = () => {
    sseConn?.close();
    sseConn = null;
  };

  // ── 폴링 ──
  const startPolling = (interval = pollIntervalMs) => {
    stopPolling();
    refresh();
    pollTimer = setInterval(refresh, interval);
  };

  const stopPolling = () => {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
    updateBadge(0);
    close();
  };

  return {
    refresh,
    open,
    close,
    isOpen,
    startSSE,
    stopSSE,
    startPolling,
    stopPolling,
    destroy() {
      stopSSE();
      stopPolling();
      triggerBtn.removeEventListener('click', onTriggerClick);
      document.removeEventListener('click', onDocClick);
      panel.remove();
    },
  };
}
