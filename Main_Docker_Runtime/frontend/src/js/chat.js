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
import { attach as attachMentionDropdown } from '../widgets/mention-dropdown/index.js';

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
      const effectiveTripId = state.currentTripId === 'misc' ? null : (state.currentTripId || null);
      const session = await BackendHooks.createSession(text, effectiveTripId);
      const sid = session.id || session.session_id;
      state.currentSessionId = sid;
      // 새 세션은 혼자이므로 participant_count=1 기본값 적용
      session.participant_count = session.participant_count || 1;
      SessionManager.renderSidebarItem(session, elements, state, true);
      isNewSession = true;
    }

    if (isNewSession) {
      switchView('chat', elements);
      window.location.hash = `#/chat/${state.currentSessionId}`;
    }

    const myNickname = TokenManager.getNickname();
    const myId = TokenManager.getUserId();
    const isTeam = (state.currentParticipantCount || 1) > 1;
    appendMessage(chatHistory, text, 'user', {
      senderName: myNickname,
      senderId: myId,
      time: new Date().toISOString(),
      isTeam,
    });
    chatInput.value = '';
    adjustTextareaHeight(chatInput, chatBox);

    // 개인 세션이면 항상 bot 응답, 팀 세션이면 @BOT 명시 시만 bot 응답
    let botMsgDiv = null;
    const willCallBot = !isTeam || /^@BOT\s+/i.test(text);
    const loadingId = willCallBot ? showLoadingIndicator(chatHistory) : null;
    if (willCallBot) chatHistory.scrollTop = chatHistory.scrollHeight;
    let _loadingDone = false;
    const removeLoading = () => {
      if (_loadingDone || loadingId === null) return;
      _loadingDone = true;
      removeLoadingIndicator(loadingId);
    };

    try {
      await BackendHooks.sendTeamMessage(
        state.currentSessionId,
        text,
        (accumulated) => {
          if (!botMsgDiv) {
            removeLoading();
            state.isReceiving = true;
            appendMessage(chatHistory, accumulated, 'bot', {
              senderName: 'AI',
              senderId: 'bot',
              time: new Date().toISOString(),
              isTeam,
            });
            chatHistory.scrollTop = chatHistory.scrollHeight;
            botMsgDiv = chatHistory.lastElementChild?.querySelector('.message');
          } else {
            botMsgDiv.textContent = accumulated;
            chatHistory.scrollTop = chatHistory.scrollHeight;
          }
        },
        () => { removeLoading(); state.isReceiving = false; }
      );
    } catch (error) {
      removeLoading();
      console.error('Error in handleSend:', error);
      state.isReceiving = false;
    }
  },

  async _handleTempSend(state, elements) {
    const { chatInput, chatHistory, chatBox } = elements;
    const text = chatInput.value.trim();
    if (!text || state.isReceiving) return;

    if (!state.tempSessionId) {
      state.tempSessionId = 'tmp_' + Math.random().toString(36).slice(2, 10);
    }

    // 전용 안내 화면을 숨기고 채팅뷰로 전환
    if (elements.heroSection) elements.heroSection.style.display = 'none';
    chatHistory.style.display = 'flex';
    if (elements.chatWrap) elements.chatWrap.style.display = 'block';
    if (elements.downloadChatBtn) elements.downloadChatBtn.style.display = 'none';
    if (elements.shareChatBtn)    elements.shareChatBtn.style.display    = 'none';
    if (elements.mapToggleBtn)    elements.mapToggleBtn.style.display    = 'none';
    if (elements.sessionInfoBtn)  elements.sessionInfoBtn.style.display  = 'none';

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

    // @BOT 접두사 제거 후 항상 봇 응답
    const botQuery = text.replace(/^@BOT\s+/i, '').trim();
    state.isReceiving = true;

    const loadingId = showLoadingIndicator(chatHistory);
    chatHistory.scrollTop = chatHistory.scrollHeight;
    let _loadingDone = false;
    const removeLoading = () => { if (!_loadingDone) { _loadingDone = true; removeLoadingIndicator(loadingId); } };
    let botMsgDiv = null;

    try {
      await BackendHooks.sendTempMessage(
        state.tempSessionId,
        botQuery,
        (accumulated) => {
          if (!botMsgDiv) {
            removeLoading();
            appendMessage(chatHistory, accumulated, 'bot', {
              senderName: 'AI',
              senderId: 'ai',
              time: new Date().toISOString(),
              isTeam: false,
            });
            botMsgDiv = chatHistory.lastElementChild?.querySelector('.message');
          } else {
            botMsgDiv.textContent = accumulated;
          }
          chatHistory.scrollTop = chatHistory.scrollHeight;
        },
        () => { removeLoading(); state.isReceiving = false; }
      );
    } catch (e) {
      removeLoading();
      console.error('[tempChat]', e);
      appendMessage(chatHistory, '오류가 발생했습니다.', 'bot', {
        senderName: 'AI', senderId: 'ai',
        time: new Date().toISOString(), isTeam: false,
      });
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
    const isTeamMode = (state.currentParticipantCount || 1) > 1;

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
    return attachMentionDropdown(elements.chatInput, {
      getSessionId:  () => state.currentSessionId,
      getMyUserId:   () => TokenManager.getUserId(),
      fetchParticipants: async (sid) => {
        try {
          const res = await BackendHooks._authFetch(`/api/sessions/${sid}/info`);
          if (!res.ok) return [];
          const info = await res.json();
          return info.participants || [];
        } catch { return []; }
      },
    });
  }
};
