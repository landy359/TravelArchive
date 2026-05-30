/**
 * ui.js
 */

import { Icons } from './assets.js';
import { renderTemplate, createElementFromHTML } from './utils.js';
import { mount as mountLoadingIndicator } from '../widgets/loading-indicator/index.js';
import {
  mount as mountChatMessage,
  renderFileInMsg as _renderFileInMsg,
} from '../widgets/chat-message/index.js';
import { mount as mountTripSelect } from '../widgets/trip-select/index.js';

export function updateSidebarSessionTitle(sessionId, newTitle) {
  const itemBtn = document.querySelector(`.sidebar-item[data-session-id="${sessionId}"]`);
  if (itemBtn) itemBtn.innerHTML = `<span class="dot"></span>${newTitle}`;
  const wrapper = itemBtn?.closest('.sidebar-item-wrapper');
  if (wrapper) {
    const editInput = wrapper.querySelector('.sidebar-item-edit-input');
    if (editInput) editInput.value = newTitle;
  }
}

export function showToast(message) {
  let toast = document.getElementById('global-toast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'global-toast';
    toast.className = 'toast-notification';
    document.body.appendChild(toast);
  }
  toast.textContent = message;
  toast.classList.add('show');
  if (toast.hideTimeout) clearTimeout(toast.hideTimeout);
  toast.hideTimeout = setTimeout(() => toast.classList.remove('show'), 3000);
}

export function adjustTextareaHeight(chatInput, chatBox) {
  if (!chatInput) return;
  const style = window.getComputedStyle(chatInput);
  const lineHeight = parseFloat(style.lineHeight) || 21;
  const padding = parseFloat(style.paddingTop) + parseFloat(style.paddingBottom);
  const borders = parseFloat(style.borderTopWidth) + parseFloat(style.borderBottomWidth);
  const baseHeight = lineHeight + padding + borders;

  // 확장 모드: 최소 136px, 일반 모드: 최소 32px (한 줄)
  const isExpanded = chatBox.classList.contains('expanded');
  const minHeight = isExpanded ? Math.max(136, Math.ceil(baseHeight)) : Math.max(32, Math.ceil(baseHeight));
  const maxHeight = isExpanded ? 360 : 180;

  chatInput.style.height = 'auto';
  const nextHeight = Math.min(Math.max(chatInput.scrollHeight, minHeight), maxHeight);
  chatInput.style.height = `${nextHeight}px`;
  chatInput.style.overflowY = nextHeight >= maxHeight ? 'auto' : 'hidden';
}

// 위젯 인스턴스 추적용 (id-기반 API 하위 호환)
const _liInstances = new Map();

export function showLoadingIndicator(chatHistory) {
  const id = 'loading-' + Date.now() + '-' + Math.random().toString(36).slice(2, 6);
  const li = mountLoadingIndicator(chatHistory);
  li.el.id = id;
  _liInstances.set(id, li);
  return id;
}

export function removeLoadingIndicator(id) {
  const li = _liInstances.get(id);
  if (li) {
    li.destroy();
    _liInstances.delete(id);
  } else {
    // fallback: id 로 직접 검색
    document.getElementById(id)?.remove();
  }
}

/**
 * @param {HTMLElement} chatHistory
 * @param {string} text
 * @param {'user'|'bot'|'system'} sender
 * @param {object} [meta] - { senderName, senderId, time, isTeam }
 */
// renderFileInMsg / appendMessage / _formatMessageTime → widgets/chat-message/
export const renderFileInMsg = _renderFileInMsg;

export function appendMessage(chatHistory, text, sender, meta = {}) {
  const m = mountChatMessage(chatHistory, {
    text, sender, meta,
    onCopySuccess: () => showToast('메시지가 복사되었습니다.'),
  });
  return m.el; // 기존 호출자가 row element 를 받으므로 그대로 반환
}

export function appendTripSelect(chatHistory, data, handlers = {}) {
  chatHistory.querySelectorAll('.trip-select-row').forEach((el) => el.remove());
  if (!data?.visible || !Array.isArray(data.options) || data.options.length < 2) {
    return null;
  }
  const m = mountTripSelect(chatHistory, {
    data,
    onSelect: handlers.onSelect,
  });
  return m.el;
}

