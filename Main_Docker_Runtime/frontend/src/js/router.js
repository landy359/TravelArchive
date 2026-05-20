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
  const raw = (msg.role || msg.sender_type || '').toLowerCase();
  if (raw === 'assistant' || raw === 'bot' || raw === 'ai') return 'bot';
  if (raw === 'user') return 'user';
  return 'bot';
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

    if (state.currentSessionId !== ssid) {
      // 이전 세션 blur → dirty 위젯 PG flush (fire-and-forget)
      if (state.currentSessionId) {
        BackendHooks.blurSession(state.currentSessionId);
      }

      switchView('chat', elements);
      chatHistory.innerHTML = '';
      chatHistory._scrollPagerAttached = false;
      const loadingId = showLoadingIndicator(chatHistory);
      state.currentSessionId = ssid;

      // 새 세션 open → PG→Redis 로드 (캐시 miss 시)
      BackendHooks.openSession(ssid).catch(() => {});

      CalendarManager.loadTripRange(ssid);
      BackendHooks.markSessionRead(ssid).catch(() => {});
      SessionManager.clearUnreadDot(ssid);

      try {
        // 히스토리와 세션 정보를 병렬로 조회
        const [result, infoRes] = await Promise.all([
          BackendHooks.fetchChatHistory(ssid, HISTORY_PAGE, 0),
          BackendHooks._authFetch(`/api/sessions/${ssid}/info`).then(r => r.ok ? r.json() : null).catch(() => null),
        ]);
        const participantCount = infoRes?.participants?.length || 1;
        state.currentParticipantCount = participantCount;
        removeLoadingIndicator(loadingId);
        const myId = TokenManager.getUserId();
        const isTeam = participantCount > 1;
        _renderMsgs(chatHistory, result.messages, myId, isTeam, ssid);
        chatHistory.scrollTop = chatHistory.scrollHeight;
        _attachScrollPager(chatHistory, ssid, myId, isTeam, state);
      } catch (e) {
        console.error(e);
        removeLoadingIndicator(loadingId);
      }
    } else {
      switchView('chat', elements);
      if (chatHistory.children.length === 0) {
        const loadingId2 = showLoadingIndicator(chatHistory);
        try {
          const result2 = await BackendHooks.fetchChatHistory(ssid, HISTORY_PAGE, 0);
          removeLoadingIndicator(loadingId2);
          const myId2 = TokenManager.getUserId();
          const isTeam2 = (state.currentParticipantCount || 1) > 1;
          _renderMsgs(chatHistory, result2.messages, myId2, isTeam2, ssid);
          chatHistory.scrollTop = chatHistory.scrollHeight;
          _attachScrollPager(chatHistory, ssid, myId2, isTeam2, state);
        } catch (e) {
          removeLoadingIndicator(loadingId2);
        }
      }
    }

    // SSE: 팀/개인 모두 구독 (팀=실시간 메시지, 개인=title_updated 수신)
    const isTeamSession = (state.currentParticipantCount || 1) > 1;
    if (true) {
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
            if (state._sseConnection) {
              state._sseConnection.close();
              state._sseConnection = null;
            }
            state.currentSessionId = null;
            state.currentParticipantCount = null;
            window.location.hash = '#/';
            SessionManager.init(elements, state);
            const kickMsg = event.reason === 'session_deleted' ? '세션이 삭제되었습니다.' : '세션에서 퇴출되었습니다.';
            import('./ui.js').then(({ showToast }) => showToast(kickMsg));
          } else if (event.type === 'new_master') {
            // 마스터 승계: 내가 새 마스터가 됐으면 UI 새로고침
            const myId = TokenManager.getUserId();
            if (event.user_id === myId) {
              state.currentParticipantCount = null;
              import('./ui.js').then(({ showToast }) =>
                showToast('마스터 권한이 위임되었습니다.')
              );
              // 세션 목록 새로고침
              import('./session.js').then(({ SessionManager }) =>
                SessionManager.init(elements, state)
              );
            }
          } else if (event.type === 'title_updated') {
            import('./ui.js').then(({ updateSidebarSessionTitle }) =>
              updateSidebarSessionTitle(event.session_id, event.title)
            );
          } else if (event.type === 'color_updated') {
            const wrapper = document.querySelector(`.sidebar-item-wrapper[data-session-id="${event.session_id}"]`);
            const bar = wrapper?.querySelector('.session-color-bar');
            if (bar) bar.style.background = event.color;
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
  state.currentParticipantCount = null;

  // page 경로 이탈 시 임시채팅 모드 해제 (종료버튼 외 다른 방법으로 나갈 때)
  if (page.type === 'page' && state.isTempMode) {
    state.isTempMode = false;
    if (elements.planFilter) elements.planFilter.style.display = '';
  }

  CalendarManager.loadTripRange(null);

  if (page.type === 'home') {
    chatHistory.innerHTML = '';
    chatInput.value = '';
    adjustTextareaHeight(chatInput, chatBox);
    switchView('home', elements);

    if (state.isTempMode) {
      // 임시 채팅 모드: 전용 안내 화면만 표시, chatHistory는 숨김
      // 대화 시작 시 _handleTempSend 에서 heroSection 숨기고 chatHistory 표시함
      document.getElementById('heroNormal')?.setAttribute('style', 'display:none');
      document.getElementById('hereTempChat')?.removeAttribute('style');
      if (elements.homeDashboard) {
        elements.homeDashboard.style.display = 'none';
        elements.heroSection?.classList.remove('dashboard-active');
      }
      // chatHistory는 숨긴 채 유지 (대화 시작 전에는 안내 화면만 보임)
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
        HomeManager.render(elements.homeDashboard, elements._onNewSession || (() => {}), elements._onTripSelect, elements._onTripCreated);
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
