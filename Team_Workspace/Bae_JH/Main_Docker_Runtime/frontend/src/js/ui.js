/**
 * ui.js
 */

import { Icons } from './assets.js';
import { renderTemplate, createElementFromHTML } from './utils.js';

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

export function showLoadingIndicator(chatHistory) {
  const loadingId = 'loading-' + Date.now();
  const html = renderTemplate('loading');
  const rowDiv = createElementFromHTML(html);
  rowDiv.id = loadingId;
  chatHistory.appendChild(rowDiv);
  chatHistory.scrollTop = chatHistory.scrollHeight;
  return loadingId;
}

export function removeLoadingIndicator(id) {
  document.getElementById(id)?.remove();
}

/**
 * @param {HTMLElement} chatHistory
 * @param {string} text
 * @param {'user'|'bot'|'system'} sender
 * @param {object} [meta] - { senderName, senderId, time, isTeam }
 */
const IMAGE_EXTS = new Set(['jpg','jpeg','png','gif','webp','bmp','svg']);
const VIDEO_EXTS = new Set(['mp4','webm','ogg','mov']);

export function renderFileInMsg(msgDiv, fileUrl, fname) {
  const ext = (fname.split('.').pop() || '').toLowerCase();
  if (IMAGE_EXTS.has(ext)) {
    const img = document.createElement('img');
    img.src = fileUrl;
    img.className = 'chat-media-preview';
    img.alt = fname;
    img.style.cssText = 'max-width:280px;max-height:220px;border-radius:12px;cursor:pointer;display:block;margin-bottom:4px;';
    img.addEventListener('click', () => window.open(fileUrl, '_blank'));
    msgDiv.appendChild(img);
  } else if (VIDEO_EXTS.has(ext)) {
    const video = document.createElement('video');
    video.src = fileUrl;
    video.controls = true;
    video.style.cssText = 'max-width:280px;max-height:220px;border-radius:12px;display:block;margin-bottom:4px;';
    msgDiv.appendChild(video);
  } else {
    const wrap = document.createElement('a');
    wrap.href = fileUrl;
    wrap.download = fname;
    wrap.style.cssText = 'display:flex;align-items:center;gap:8px;padding:8px 12px;border-radius:10px;background:var(--bg-secondary,rgba(0,0,0,.07));text-decoration:none;margin-bottom:4px;max-width:260px;';
    const icon = document.createElement('span');
    icon.textContent = '📎';
    const nameSpan = document.createElement('span');
    nameSpan.textContent = fname;
    nameSpan.style.cssText = 'color:var(--accent,#6366f1);font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;';
    wrap.appendChild(icon);
    wrap.appendChild(nameSpan);
    msgDiv.appendChild(wrap);
  }
}

export function appendMessage(chatHistory, text, sender, meta = {}) {
  const {
    senderName = '', senderId = '', time = '', isTeam = false,
    mediaFile = null, msgType = null, files = [], sessionId = '',
  } = meta;

  const isFileMsg = msgType === 'file' || mediaFile != null;

  let processedText = text;
  if (sender === 'bot' && text && !isFileMsg && typeof marked !== 'undefined') {
    processedText = marked.parse(text);
  }

  const avatarChar = senderName
    ? senderName.charAt(0).toUpperCase()
    : (sender === 'user' ? 'U' : 'B');

  const displayTime = time
    ? _formatMessageTime(time)
    : _formatMessageTime(new Date().toISOString());

  const html = renderTemplate('message', {
    sender,
    text: isFileMsg ? '' : processedText,
    senderId,
    senderName: isTeam ? senderName : '',
    avatarChar: isTeam ? avatarChar : '',
    time: displayTime,
  }, Icons);

  const rowDiv = createElementFromHTML(html);
  const msgDiv = rowDiv.querySelector('.message');
  const copyBtn = rowDiv.querySelector('.copy-btn');

  if (!isTeam) {
    const avatar = rowDiv.querySelector('.message-avatar');
    const nameEl = rowDiv.querySelector('.message-sender-name');
    if (avatar) avatar.style.display = 'none';
    if (nameEl) nameEl.style.display = 'none';
  }

  // 파일 메시지 렌더링 (발신: blob URL / 수신: /uploads/ 경로)
  if (mediaFile) {
    const url = URL.createObjectURL(mediaFile);
    renderFileInMsg(msgDiv, url, mediaFile.name);
  } else if (msgType === 'file' && files.length > 0) {
    for (const fname of files) {
      const fileUrl = `/uploads/${sessionId}/${senderId}/${fname}`;
      renderFileInMsg(msgDiv, fileUrl, fname);
    }
  } else if (!(sender === 'bot' && text && typeof marked !== 'undefined')) {
    msgDiv.textContent = text;
  }

  copyBtn.addEventListener('click', async () => {
    const currentText = msgDiv.innerText || msgDiv.textContent;
    try {
      await navigator.clipboard.writeText(currentText);
      const originalIcon = copyBtn.innerHTML;
      copyBtn.innerHTML = Icons.Check;
      if (copyBtn.querySelector('svg')) copyBtn.querySelector('svg').style.stroke = '#10B981';
      setTimeout(() => copyBtn.innerHTML = originalIcon, 2000);
      showToast('메시지가 복사되었습니다.');
    } catch (err) { console.error(err); }
  });

  chatHistory.appendChild(rowDiv);
  chatHistory.scrollTop = chatHistory.scrollHeight;
  return rowDiv;
}

function _formatMessageTime(isoOrDate) {
  try {
    const d = isoOrDate instanceof Date ? isoOrDate : new Date(isoOrDate);
    if (isNaN(d.getTime())) return '';
    return d.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', hour12: false });
  } catch {
    return '';
  }
}
