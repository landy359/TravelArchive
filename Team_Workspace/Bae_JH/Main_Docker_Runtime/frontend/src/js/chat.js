/**
 * chat.js
 * handles chat interactions, messaging, and file uploads.
 */

import { BackendHooks, TokenManager } from './api.js';
import {
  showLoadingIndicator,
  removeLoadingIndicator,
  appendMessage,
  adjustTextareaHeight,
  updateSidebarSessionTitle
} from './ui.js';
import { switchView } from './router.js';
import { SessionManager } from './session.js';

export const ChatManager = {
  async handleSend(state, elements) {
    if (state.isTempMode) {
      await this._handleTempSend(state, elements);
      return;
    }

    const { chatInput, chatHistory, sendBtn, chatBox } = elements;
    const text = chatInput.value.trim();
    if (!text || state.isReceiving) return;

    let isNewSession = false;
    if (!state.currentSessionId) {
      const effectiveTripId = state.currentTripId === 'none' ? null : (state.currentTripId || null);
      const session = await BackendHooks.createSession(text, 'personal', effectiveTripId);
      const sid = session.id || session.session_id;
      state.currentSessionId = sid;
      state.currentSessionMode = 'personal';
      SessionManager.renderSidebarItem(session, elements, state, true);
      isNewSession = true;
    }

    if (isNewSession) {
      switchView('chat', elements);
      window.location.hash = `#/chat/${state.currentSessionId}`;
    }

    const myNickname = TokenManager.getNickname();
    const myId = TokenManager.getUserId();
    const isTeam = (state.currentSessionMode === 'team');
    appendMessage(chatHistory, text, 'user', {
      senderName: myNickname,
      senderId: myId,
      time: new Date().toISOString(),
      isTeam,
    });
    chatInput.value = '';
    adjustTextareaHeight(chatInput, chatBox);

    // 모든 일반 세션은 AI 없이 즉시 DB 저장
    try {
      await BackendHooks.sendTeamMessage(state.currentSessionId, text);
    } catch (error) {
      console.error('Error in handleSend:', error);
    }
  },

  async _handleTempSend(state, elements) {
    const { chatInput, chatHistory, chatBox } = elements;
    const text = chatInput.value.trim();
    if (!text || state.isReceiving) return;

    if (!state.tempSessionId) {
      state.tempSessionId = 'tmp_' + Math.random().toString(36).slice(2, 10);
    }

    // 첫 메시지 → hero 숨기고 일반 채팅뷰로 전환 (임시채팅 전용 버튼은 숨김 유지)
    if (chatHistory.children.length === 0) {
      switchView('chat', elements);
      if (elements.downloadChatBtn) elements.downloadChatBtn.style.display = 'none';
      if (elements.shareChatBtn)    elements.shareChatBtn.style.display    = 'none';
      if (elements.mapToggleBtn)    elements.mapToggleBtn.style.display    = 'none';
      if (elements.sessionInfoBtn)  elements.sessionInfoBtn.style.display  = 'none';
    }

    const myNickname = TokenManager.getNickname() || 'Me';
    appendMessage(chatHistory, text, 'user', {
      senderName: myNickname,
      senderId: TokenManager.getUserId() || '',
      time: new Date().toISOString(),
      isTeam: false,
    });
    chatInput.value = '';
    adjustTextareaHeight(chatInput, chatBox);
    chatHistory.scrollTop = chatHistory.scrollHeight;

    state.isReceiving = true;

    // 봇 메시지 자리 확보 (빈 메시지로 먼저 append)
    appendMessage(chatHistory, '...', 'bot', {
      senderName: 'AI',
      senderId: 'ai',
      time: new Date().toISOString(),
      isTeam: false,
    });
    chatHistory.scrollTop = chatHistory.scrollHeight;
    const botRow = chatHistory.lastElementChild;
    const botMsgDiv = botRow?.querySelector('.message');

    try {
      await BackendHooks.sendTempMessage(
        state.tempSessionId,
        text,
        (accumulated) => {
          if (botMsgDiv) botMsgDiv.textContent = accumulated;
          chatHistory.scrollTop = chatHistory.scrollHeight;
        },
        () => { state.isReceiving = false; }
      );
    } catch (e) {
      console.error('[tempChat]', e);
      if (botMsgDiv) botMsgDiv.textContent = '오류가 발생했습니다.';
      state.isReceiving = false;
    }
  },

  handleFileUpload(files, state, elements) {
    const { chatHistory, fileInput } = elements;

    if (!state.currentSessionId) {
      alert("먼저 대화를 시작해주세요.");
      return;
    }

    const myNickname = TokenManager.getNickname();
    const myId = TokenManager.getUserId();
    const isTeamMode = (state.currentSessionMode || state.currentMode) === 'team';

    Array.from(files).forEach(file => {
      if (file.type.startsWith('image/') || file.type.startsWith('video/')) {
        // 미디어 미리보기 버블
        appendMessage(chatHistory, '', 'user', {
          senderName: myNickname,
          senderId: myId,
          time: new Date().toISOString(),
          isTeam: isTeamMode,
          mediaFile: file,
        });
      } else {
        appendMessage(chatHistory, `[파일 첨부] ${file.name}`, 'user', {
          senderName: myNickname,
          senderId: myId,
          time: new Date().toISOString(),
          isTeam: isTeamMode,
        });
      }
    });

    BackendHooks.uploadFiles(state.currentSessionId, files);
    if (fileInput) fileInput.value = "";
  },

  setupPasteHandler(state, elements) {
    const { chatInput } = elements;
    chatInput.addEventListener('paste', (e) => {
      const items = e.clipboardData?.items;
      if (!items) return;
      const imageItems = Array.from(items).filter(i => i.type.startsWith('image/'));
      if (!imageItems.length) return;
      e.preventDefault();
      const files = imageItems.map(i => i.getAsFile()).filter(Boolean);
      if (files.length) this.handleFileUpload(files, state, elements);
    });
  },

  setupMentionAutocomplete(state, elements) {
    const { chatInput } = elements;
    let _dropdown = null;
    let _sessionParticipants = [];

    const closeDropdown = () => { _dropdown?.remove(); _dropdown = null; };

    chatInput.addEventListener('input', async () => {
      const val = chatInput.value;
      const cursor = chatInput.selectionStart;
      const textBefore = val.slice(0, cursor);
      const match = textBefore.match(/@(\S*)$/);

      if (!match || state.currentSessionMode !== 'team') {
        closeDropdown();
        return;
      }

      const query = match[1];

      // 세션 참여자 목록 캐시 (세션 변경 또는 30초 경과 시 재조회)
      const _now = Date.now();
      if (
        !_sessionParticipants._sid ||
        _sessionParticipants._sid !== state.currentSessionId ||
        (_now - (_sessionParticipants._ts || 0)) > 30000
      ) {
        try {
          const res = await BackendHooks._authFetch(`/api/sessions/${state.currentSessionId}/info`);
          if (res.ok) {
            const info = await res.json();
            _sessionParticipants = info.participants || [];
            _sessionParticipants._sid = state.currentSessionId;
            _sessionParticipants._ts = _now;
          }
        } catch {}
      }

      const myId = TokenManager.getUserId();
      const filtered = _sessionParticipants.filter(p =>
        p.user_id !== myId &&
        (p.nickname || p.user_id).toLowerCase().includes(query.toLowerCase())
      );

      closeDropdown();
      if (!filtered.length) return;

      _dropdown = document.createElement('div');
      _dropdown.className = 'mention-dropdown';
      const rect = chatInput.getBoundingClientRect();
      _dropdown.style.cssText = `position:fixed;bottom:${window.innerHeight - rect.top + 4}px;left:${rect.left}px;z-index:999;`;

      filtered.slice(0, 6).forEach(p => {
        const item = document.createElement('div');
        item.className = 'mention-item';
        item.textContent = p.nickname || p.user_id;
        item.addEventListener('mousedown', (e) => {
          e.preventDefault();
          const nick = p.nickname || p.user_id;
          const newVal = val.slice(0, cursor - match[0].length) + `@${nick} ` + val.slice(cursor);
          chatInput.value = newVal;
          chatInput.focus();
          closeDropdown();
        });
        _dropdown.appendChild(item);
      });

      document.body.appendChild(_dropdown);
    });

    chatInput.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') closeDropdown();
    });

    document.addEventListener('click', (e) => {
      if (e.target !== chatInput) closeDropdown();
    });
  }
};
