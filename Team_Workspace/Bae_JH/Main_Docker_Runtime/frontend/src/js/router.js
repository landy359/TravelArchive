/**
 * router.js
 */

import { renderSettingsPage } from './settings.js';
import { renderAccountPage } from './account.js';
import { renderHelpPage } from './help.js';
import { BackendHooks, TokenManager } from './api.js';
import { HomeManager } from './home.js';
import { SidebarManager } from './sidebar.js';
import { CalendarManager } from './calendar.js';
import { showLoadingIndicator, removeLoadingIndicator, appendMessage, adjustTextareaHeight, renderFileInMsg } from './ui.js';
import { SessionManager } from './session.js';

const PAGES = {
  '#/settings': { type: 'page', renderer: renderSettingsPage },
  '#/account':  { type: 'page', renderer: renderAccountPage },
  '#/help':     { type: 'page', renderer: renderHelpPage },
  '#/':         { type: 'home' }
};


export function switchView(viewName, elements) {
  const {
    heroSection,
    chatHistory,
    chatWrap,
    pageSection,
    topBarActions,
    downloadChatBtn,
    shareChatBtn,
    mapToggleBtn,
    sessionInfoBtn,
  } = elements;

  heroSection.style.display = 'none';
  chatHistory.style.display = 'none';
  chatWrap.style.display = 'none';
  pageSection.style.display = 'none';

  topBarActions.style.display = 'flex';

  switch (viewName) {
    case 'home':
      heroSection.style.display = 'flex';
      chatWrap.style.display = 'block';
      if (sessionInfoBtn)  sessionInfoBtn.style.display = 'none';
      if (downloadChatBtn) downloadChatBtn.style.display = 'none';
      if (shareChatBtn)    shareChatBtn.style.display = 'none';
      if (mapToggleBtn)    mapToggleBtn.style.display = 'none';
      break;
    case 'chat':
      chatHistory.style.display = 'flex';
      chatWrap.style.display = 'block';
      if (sessionInfoBtn)  sessionInfoBtn.style.display = 'flex';
      if (downloadChatBtn) downloadChatBtn.style.display = 'flex';
      if (shareChatBtn)    shareChatBtn.style.display = 'flex';
      if (mapToggleBtn)    mapToggleBtn.style.display = 'flex';
      break;
    case 'page':
      pageSection.style.display = 'flex';
      if (sessionInfoBtn)  sessionInfoBtn.style.display = 'none';
      if (downloadChatBtn) downloadChatBtn.style.display = 'none';
      if (shareChatBtn)    shareChatBtn.style.display = 'none';
      if (mapToggleBtn)    mapToggleBtn.style.display = 'none';
      break;
  }
}

const HISTORY_PAGE = 40;

function _msgRole(msg, myId) {
  if (msg.sender_id && msg.sender_id === myId) return 'user';
  if (msg.sender_id) return 'bot';
  const raw = msg.role || msg.sender_type || '';
  return (raw === 'assistant' || raw === 'bot') ? 'bot' : (raw || 'bot');
}

function _renderMsgs(chatHistory, msgs, myId, isTeam, sessionId) {
  for (const msg of msgs) {
    const role = _msgRole(msg, myId);
    appendMessage(chatHistory, msg.content, role, {
      senderName: msg.sender_name || (role === 'bot' ? 'AI' : msg.sender_id || ''),
      senderId:   msg.sender_id || '',
      time:       msg.created_at || '',
      isTeam,
      sessionId,
      msgType:    msg.msg_type || null,
      files:      msg.files    || [],
    });
  }
}

function _attachScrollPager(chatHistory, ssid, myId, isTeam, state) {
  if (chatHistory._scrollPagerAttached) return;
  chatHistory._scrollPagerAttached = true;
  chatHistory._historyOffset = HISTORY_PAGE;
  chatHistory._historyExhausted = false;

  chatHistory.addEventListener('scroll', async () => {
    if (chatHistory.scrollTop > 60) return;
    if (chatHistory._historyExhausted || chatHistory._historyLoading) return;
    chatHistory._historyLoading = true;

    const prevHeight = chatHistory.scrollHeight;
    let loadedCount = 0;
    try {
      const result = await BackendHooks.fetchChatHistory(ssid, HISTORY_PAGE, chatHistory._historyOffset);
      const msgs = result.messages || [];
      loadedCount = msgs.length;
      if (msgs.length === 0) {
        chatHistory._historyExhausted = true;
        chatHistory._historyLoading = false;
        return;
      }
      chatHistory._historyOffset += msgs.length;
      const tempDiv = document.createElement('div');
      for (const msg of msgs) {
        const role = _msgRole(msg, myId);
        appendMessage(tempDiv, msg.content, role, {
          senderName: msg.sender_name || (role === 'bot' ? 'AI' : msg.sender_id || ''),
          senderId:   msg.sender_id || '',
          time:       msg.created_at || '',
          isTeam,
          sessionId:  ssid,
          msgType:    msg.msg_type || null,
          files:      msg.files    || [],
        });
      }
      const nodes = [...tempDiv.children];
      for (const n of nodes) chatHistory.insertBefore(n, chatHistory.firstChild);
      chatHistory.scrollTop = chatHistory.scrollHeight - prevHeight;
    } catch (e) {
      console.error('[pager]', e);
    }
    chatHistory._historyLoading = false;
    if (loadedCount < HISTORY_PAGE) chatHistory._historyExhausted = true;
  });
}

export async function router(state, elements) {
  const path = window.location.hash || '#/';
  const { chatHistory, chatInput, chatBox, pageSection } = elements;

  if (path.startsWith('#/chat/')) {
    const ssid = path.replace('#/chat/', '');

    if (state.isTempMode) {
      state.isTempMode = false;
      if (elements.planFilter) elements.planFilter.style.display = '';
    }

    if (state._sseConnection) {
      state._sseConnection.close();
      state._sseConnection = null;
    }

    let actualSessionMode = state.currentMode;

    if (state.currentSessionId !== ssid) {
      switchView('chat', elements);
      chatHistory.innerHTML = '';
      chatHistory._scrollPagerAttached = false;
      const loadingId = showLoadingIndicator(chatHistory);
      state.currentSessionId = ssid;

      CalendarManager.loadTripRange(ssid);
      SidebarManager.initMemoRows(elements);
      SidebarManager.initScheduleRows(elements);
      BackendHooks.markSessionRead(ssid).catch(() => {});
      SessionManager.clearUnreadDot(ssid);

      try {
        const result = await BackendHooks.fetchChatHistory(ssid, HISTORY_PAGE, 0);
        actualSessionMode = result.mode || state.currentMode;
        state.currentSessionMode = actualSessionMode;
        removeLoadingIndicator(loadingId);
        const myId = TokenManager.getUserId();
        const isTeam = actualSessionMode === 'team';
        _renderMsgs(chatHistory, result.messages, myId, isTeam, ssid);
        chatHistory.scrollTop = chatHistory.scrollHeight;
        _attachScrollPager(chatHistory, ssid, myId, isTeam, state);
      } catch (e) {
        console.error(e);
        removeLoadingIndicator(loadingId);
      }
    } else {
      switchView('chat', elements);
      if (state.currentSessionMode) actualSessionMode = state.currentSessionMode;
      if (actualSessionMode !== 'team' && chatHistory.children.length === 0) {
        const loadingId2 = showLoadingIndicator(chatHistory);
        try {
          const result2 = await BackendHooks.fetchChatHistory(ssid, HISTORY_PAGE, 0);
          removeLoadingIndicator(loadingId2);
          const myId2 = TokenManager.getUserId();
          _renderMsgs(chatHistory, result2.messages, myId2, false, ssid);
          chatHistory.scrollTop = chatHistory.scrollHeight;
          _attachScrollPager(chatHistory, ssid, myId2, false, state);
        } catch (e) {
          removeLoadingIndicator(loadingId2);
        }
      }
    }

    // SSE는 실제 세션 모드 기준으로 시작 (사이드바 탭 무관)
    if (actualSessionMode === 'team') {
      const myId = TokenManager.getUserId();
      state._sseConnection = BackendHooks.subscribeToSessionEvents(
        ssid,
        (event) => {
          if (event.type === 'message') {
            if (event.sender_id !== myId) {
              appendMessage(chatHistory, event.content, 'bot', {
                senderName: event.sender_name || event.sender_id || '',
                senderId:   event.sender_id || '',
                time:       event.ts || '',
                isTeam:     true,
                sessionId:  ssid,
                msgType:    event.msg_type || null,
                files:      event.files    || [],
              });
              chatHistory.scrollTop = chatHistory.scrollHeight;
              if (document.visibilityState === 'visible') {
                BackendHooks.markSessionRead(ssid).catch(() => {});
              }
            }
          } else if (event.type === 'kicked') {
            // 마스터가 개인 전환 → 즉시 세션에서 퇴출
            if (state._sseConnection) {
              state._sseConnection.close();
              state._sseConnection = null;
            }
            state.currentSessionId = null;
            state.currentSessionMode = null;
            window.location.hash = '#/';
            import('./ui.js').then(({ showToast }) =>
              showToast('마스터가 개인 플래너로 전환하여 세션에서 나왔습니다.')
            );
          } else if (event.type === 'title_updated') {
            // 세션 제목 실시간 반영
            import('./ui.js').then(({ updateSidebarSessionTitle }) =>
              updateSidebarSessionTitle(event.session_id, event.title)
            );
          } else if (event.type === 'notification') {
            // 알림 실시간 뱃지 갱신
            const badge = document.getElementById('notifBadge');
            if (badge) {
              const cur = parseInt(badge.textContent) || 0;
              const next = cur + 1;
              badge.textContent = next > 99 ? '99+' : next;
              badge.style.display = '';
            }
          }
        },
        (err) => console.error('[SSE]', err)
      );

      // 탭/창 복귀 시 즉시 읽음 처리
      const _onVisible = () => {
        if (document.visibilityState === 'visible' && state.currentSessionId === ssid) {
          BackendHooks.markSessionRead(ssid).catch(() => {});
        }
      };
      document.addEventListener('visibilitychange', _onVisible);
      // SSE 종료 시 이벤트 해제 (기존 _sseConnection 래핑)
      const _origClose = state._sseConnection?.close?.bind(state._sseConnection);
      if (state._sseConnection) {
        state._sseConnection.close = () => {
          document.removeEventListener('visibilitychange', _onVisible);
          _origClose?.();
        };
      }
    }

    return;
  }

  const page = PAGES[path] || PAGES['#/'];

  // Close SSE when navigating away from chat
  if (state._sseConnection) {
    state._sseConnection.close();
    state._sseConnection = null;
  }

  state.currentSessionId = null;
  state.currentSessionMode = null;

  // page 경로 이탈 시 임시채팅 모드 해제 (종료버튼 외 다른 방법으로 나갈 때)
  if (page.type === 'page' && state.isTempMode) {
    state.isTempMode = false;
    if (elements.planFilter) elements.planFilter.style.display = '';
  }

  CalendarManager.loadTripRange(null);
  SidebarManager.initMemoRows(elements);
  SidebarManager.initScheduleRows(elements);

  if (page.type === 'home') {
    chatHistory.innerHTML = '';
    chatInput.value = '';
    adjustTextareaHeight(chatInput, chatBox);
    switchView('home', elements);

    if (state.isTempMode) {
      // 임시 채팅 모드: hereTempChat 헤더 + chatHistory 동시 표시
      document.getElementById('heroNormal')?.setAttribute('style', 'display:none');
      document.getElementById('hereTempChat')?.removeAttribute('style');
      if (elements.homeDashboard) {
        elements.homeDashboard.style.display = 'none';
        elements.heroSection?.classList.remove('dashboard-active');
      }
      // switchView('home')이 chatHistory를 숨기므로 다시 열어줌
      chatHistory.style.display = 'flex';
      const exitBtn = document.getElementById('exitTempChatBtn');
      if (exitBtn) {
        exitBtn.onclick = () => { elements._exitTempMode?.(); };
      }
      return;
    }

    // 일반 홈 — heroNormal 보장
    document.getElementById('heroNormal')?.removeAttribute('style');
    document.getElementById('hereTempChat')?.setAttribute('style', 'display:none');

    if (elements.homeDashboard) {
      if (TokenManager.isLoggedIn()) {
        elements.homeDashboard.style.display = 'block';
        elements.heroSection?.classList.add('dashboard-active');
        HomeManager.render(elements.homeDashboard, elements._onNewSession || (() => {}), elements._onTripSelect);
        elements._refreshSessions?.();
      } else {
        elements.homeDashboard.style.display = 'none';
        elements.heroSection?.classList.remove('dashboard-active');
      }
    }
  } else if (page.type === 'page') {
    switchView('page', elements);
    pageSection.innerHTML = '';
    page.renderer(pageSection);
  }
}
