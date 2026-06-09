/**
 * chat-message widget
 *
 * 채팅 1턴(메시지 1개) 버블. 사용자/봇/시스템 + 텍스트/파일/미디어 모두 처리.
 *
 * Usage:
 *   import { mount } from '@/widgets/chat-message';
 *   const m = mount(chatHistory, {
 *     text:   '안녕',
 *     sender: 'user' | 'bot' | 'system',
 *     meta:   { senderName, senderId, time, isTeam, mediaFile?, msgType?, files?, sessionId? },
 *   });
 *   // 스트리밍 중 텍스트만 갱신:
 *   m.setText(accumulated);
 *
 * 기존 ui.js appendMessage(chatHistory, text, sender, meta) 호환을 위해
 * mount 가 row element 를 반환 (ui.js facade 가 이를 그대로 리턴).
 */

import templateHtml from './chat-message.html?raw';
import './chat-message.css';
import { Icons } from '../../js/assets.js';
import { renderTemplate, createElementFromHTML } from '../../js/utils.js';

const IMAGE_EXTS = new Set(['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg']);
const VIDEO_EXTS = new Set(['mp4', 'webm', 'ogg', 'mov']);

/**
 * 메시지 div 안에 파일/미디어 미리보기를 그린다.
 */
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

function _formatMessageTime(isoOrDate) {
  try {
    const d = isoOrDate instanceof Date ? isoOrDate : new Date(isoOrDate);
    if (isNaN(d.getTime())) return '';
    return d.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', hour12: false });
  } catch {
    return '';
  }
}

/**
 * 메시지 1개를 chatHistory 에 추가.
 *
 * @param {HTMLElement} chatHistory
 * @param {{ text:string, sender:'user'|'bot'|'system', meta?:object,
 *           onCopySuccess?:Function, onCopyError?:Function }} props
 * @returns {{ el:HTMLElement, msgEl:HTMLElement, setText:Function, destroy:Function }}
 */
export function mount(chatHistory, { text = '', sender, meta = {}, onCopySuccess, onCopyError } = {}) {
  const {
    senderName = '', senderId = '', time = '', isTeam = false,
    mediaFile = null, msgType = null, files = [], sessionId = '',
  } = meta;

  const isFileMsg = msgType === 'file' || mediaFile != null;

  let processedText = text;
  if (sender === 'bot' && text && !isFileMsg && typeof marked !== 'undefined') {
    const raw = marked.parse(text);
    processedText = typeof DOMPurify !== 'undefined' ? DOMPurify.sanitize(raw) : raw;
  }

  const avatarChar = senderName
    ? senderName.charAt(0).toUpperCase()
    : (sender === 'user' ? 'U' : 'B');

  const displayTime = time
    ? _formatMessageTime(time)
    : _formatMessageTime(new Date().toISOString());

  // 기존 templates.js 'message' 와 본 widget 의 chat-message.html 둘 다 가능 — 일관성을 위해 widget 내부 템플릿 사용.
  // renderTemplate 가 message key 기준 [[Copy]] 등 아이콘 보간을 처리하므로 그것을 활용.
  // 봇은 항상 정체성(아바타+이름) 표시. 유저는 팀 세션일 때만.
  const showIdentity = isTeam || sender === 'bot';

  const html = renderTemplate('message', {
    sender,
    text: isFileMsg ? '' : processedText,
    senderId,
    senderName: showIdentity ? senderName : '',
    avatarChar: showIdentity ? avatarChar : '',
    time: displayTime,
  }, Icons);

  const rowDiv = createElementFromHTML(html);
  const msgDiv = rowDiv.querySelector('.message');
  const copyBtn = rowDiv.querySelector('.copy-btn');

  if (!showIdentity) {
    const avatar = rowDiv.querySelector('.message-avatar');
    const nameEl = rowDiv.querySelector('.message-sender-name');
    if (avatar) avatar.style.display = 'none';
    if (nameEl) nameEl.style.display = 'none';
  }

  // 파일/미디어
  if (mediaFile) {
    const url = URL.createObjectURL(mediaFile);
    renderFileInMsg(msgDiv, url, mediaFile.name);
  } else if (msgType === 'file' && files.length > 0) {
    for (const fname of files) {
      const fileUrl = `/api/files/${sessionId}/${senderId}/${fname}`;
      renderFileInMsg(msgDiv, fileUrl, fname);
    }
  } else if (!(sender === 'bot' && text && typeof marked !== 'undefined')) {
    msgDiv.textContent = text;
  }

  // 복사 버튼
  copyBtn?.addEventListener('click', async () => {
    const currentText = msgDiv.innerText || msgDiv.textContent;
    try {
      await navigator.clipboard.writeText(currentText);
      const originalIcon = copyBtn.innerHTML;
      copyBtn.innerHTML = Icons.Check;
      const svg = copyBtn.querySelector('svg');
      if (svg) svg.style.stroke = '#10B981';
      setTimeout(() => { copyBtn.innerHTML = originalIcon; }, 2000);
      onCopySuccess?.();
    } catch (err) {
      console.error(err);
      onCopyError?.(err);
    }
  });

  chatHistory.appendChild(rowDiv);
  chatHistory.scrollTop = chatHistory.scrollHeight;

  return {
    el: rowDiv,
    msgEl: msgDiv,
    setText(newText) {
      if (sender === 'bot' && newText && typeof marked !== 'undefined') {
        const raw = marked.parse(newText);
        msgDiv.innerHTML = typeof DOMPurify !== 'undefined' ? DOMPurify.sanitize(raw) : raw;
      } else {
        msgDiv.textContent = newText;
      }
    },
    destroy() { rowDiv.remove(); },
  };
}
