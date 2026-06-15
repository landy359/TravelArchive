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

// ── 강제 로그아웃 카운트다운 모달 ───────────────────────────────
function _showForceLogoutModal() {
  // 이미 표시 중이면 중복 방지
  if (document.getElementById('ta-force-logout-modal')) return;

  const overlay = document.createElement('div');
  overlay.id = 'ta-force-logout-modal';
  overlay.style.cssText = [
    'position:fixed', 'inset:0', 'z-index:99999',
    'display:flex', 'align-items:center', 'justify-content:center',
    'background:rgba(0,0,0,0.55)', 'backdrop-filter:blur(4px)',
  ].join(';');

  const box = document.createElement('div');
  box.style.cssText = [
    'background:#fff', 'border-radius:16px', 'padding:32px 28px 24px',
    'max-width:360px', 'width:90%', 'text-align:center',
    'box-shadow:0 8px 40px rgba(0,0,0,0.18)',
    'animation:ta-modal-in .25s cubic-bezier(.22,1,.36,1)',
  ].join(';');

  const style = document.createElement('style');
  style.textContent = '@keyframes ta-modal-in{from{opacity:0;transform:scale(.93)}to{opacity:1;transform:scale(1)}}';
  document.head.appendChild(style);

  let sec = 5;
  box.innerHTML = `
    <div style="font-size:36px;margin-bottom:12px">⚠️</div>
    <div style="font-size:15px;font-weight:700;color:#111;margin-bottom:8px">다른 기기에서 로그인되었습니다</div>
    <div style="font-size:13px;color:#666;line-height:1.6;margin-bottom:20px">
      보안을 위해 현재 기기는 자동으로 로그아웃됩니다.
    </div>
    <div id="ta-flo-count" style="font-size:28px;font-weight:800;color:#ef4444;margin-bottom:20px">${sec}</div>
    <button id="ta-flo-btn" style="
      width:100%;padding:10px;border-radius:9px;border:none;
      background:#ef4444;color:#fff;font-size:14px;font-weight:700;cursor:pointer;
    ">지금 로그아웃</button>
  `;
  overlay.appendChild(box);
  document.body.appendChild(overlay);

  const countEl = document.getElementById('ta-flo-count');
  const btn     = document.getElementById('ta-flo-btn');

  const doLogout = () => {
    overlay.remove();
    document.dispatchEvent(new CustomEvent('ta:force-logout'));
  };

  btn.addEventListener('click', doLogout);

  const timer = setInterval(() => {
    sec--;
    if (countEl) countEl.textContent = sec;
    if (sec <= 0) { clearInterval(timer); doLogout(); }
  }, 1000);
}

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

  // ── 데스크탑 알림 (창 백그라운드 시) ──
  const _maybeDesktopNotify = (message, sessionId) => {
    try {
      if (!('Notification' in window)) return;
      if (Notification.permission !== 'granted') return;
      if (!document.hidden) return; // 보고 있으면 굳이 안 띄움
      const n = new Notification('TravelArchive', { body: message, tag: 'ta-response' });
      n.onclick = () => {
        window.focus();
        if (sessionId) window.location.hash = `#/chat/${sessionId}`;
        n.close();
      };
    } catch { /* 무음 */ }
  };

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
                if (ev.type === 'force_logout') {
                  _showForceLogoutModal();
                  continue;
                }
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
                  // 초대·응답완료·날씨변동 등 일반 알림 — 뱃지 증가
                  const cur = parseInt(badgeEl?.textContent) || 0;
                  updateBadge(cur + 1);
                  if (isOpen()) refresh();
                  // 창이 백그라운드(최소화·다른 탭)일 때 데스크탑 알림
                  if (ev.sub_type === 'response_complete') {
                    _maybeDesktopNotify(ev.message || 'AI 응답이 완료되었습니다.', ev.session_id);
                  }
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
