/**
 * mention-dropdown widget
 *
 * 채팅 입력창에서 `@` 입력 시 참여자/봇 자동완성 드롭다운.
 *
 * 호스트(chat.js)는 이 위젯을 input 에 attach 하기만 하면 됨.
 * 참여자 fetch / 캐시 / @BOT 항상 노출 / 입력 자리 교체까지 위젯 책임.
 *
 * Usage:
 *   import { attach } from '@/widgets/mention-dropdown';
 *   const handle = attach(chatInputEl, {
 *     getSessionId:    () => state.currentSessionId,
 *     getMyUserId:     () => TokenManager.getUserId(),
 *     fetchParticipants: async (sid) => {
 *       const res = await BackendHooks._authFetch(`/api/sessions/${sid}/info`);
 *       if (!res.ok) return [];
 *       const info = await res.json();
 *       return info.participants || [];
 *     },
 *   });
 *   // 정리:
 *   handle.destroy();
 */

import './mention-dropdown.css';

const CACHE_TTL_MS = 30 * 1000;
const MAX_ITEMS    = 6;

const BOT_ENTRY = { user_id: 'bot', nickname: 'BOT' };

/**
 * @param {HTMLInputElement|HTMLTextAreaElement} inputEl
 * @param {{
 *   getSessionId: () => string|null,
 *   getMyUserId:  () => string|null,
 *   fetchParticipants: (sessionId:string) => Promise<Array<{user_id, nickname}>>,
 * }} options
 * @returns {{ destroy: Function }}
 */
export function attach(inputEl, { getSessionId, getMyUserId, fetchParticipants }) {
  let dropdown = null;
  let cache    = []; // 추가속성: ._sid, ._ts

  const closeDropdown = () => { dropdown?.remove(); dropdown = null; };

  const onInput = async () => {
    const val      = inputEl.value;
    const cursor   = inputEl.selectionStart;
    const before   = val.slice(0, cursor);
    const match    = before.match(/@(\S*)$/);
    if (!match) { closeDropdown(); return; }

    const query = match[1];
    const sid   = getSessionId();
    const now   = Date.now();

    // 캐시 갱신
    if (sid && (cache._sid !== sid || (now - (cache._ts || 0)) > CACHE_TTL_MS)) {
      try {
        cache = await fetchParticipants(sid) || [];
        cache._sid = sid;
        cache._ts  = now;
      } catch { /* 무음 실패 — 빈 캐시 유지 */ }
    }

    const myId = getMyUserId();
    const q    = query.toLowerCase();
    const humans = cache.filter(p =>
      p.user_id !== myId &&
      (p.nickname || p.user_id).toLowerCase().includes(q)
    );

    // BOT 은 항상 후보에 (조건: 빈쿼리 또는 'bot' 시작)
    const showBot = q === '' || 'bot'.startsWith(q);
    const items = showBot ? [BOT_ENTRY, ...humans] : humans;

    closeDropdown();
    if (!items.length) return;

    dropdown = document.createElement('div');
    dropdown.className = 'mention-dropdown';
    const rect = inputEl.getBoundingClientRect();
    dropdown.style.cssText =
      `position:fixed;bottom:${window.innerHeight - rect.top + 4}px;` +
      `left:${rect.left}px;z-index:999;`;

    items.slice(0, MAX_ITEMS).forEach(p => {
      const item = document.createElement('div');
      item.className = 'mention-item';
      item.textContent = p.nickname || p.user_id;
      item.addEventListener('mousedown', (e) => {
        e.preventDefault();
        const nick = p.nickname || p.user_id;
        inputEl.value = val.slice(0, cursor - match[0].length) + `@${nick} ` + val.slice(cursor);
        inputEl.focus();
        closeDropdown();
      });
      dropdown.appendChild(item);
    });

    document.body.appendChild(dropdown);
  };

  const onKeyDown = (e) => { if (e.key === 'Escape') closeDropdown(); };
  const onDocClick = (e) => { if (e.target !== inputEl) closeDropdown(); };

  inputEl.addEventListener('input', onInput);
  inputEl.addEventListener('keydown', onKeyDown);
  document.addEventListener('click', onDocClick);

  return {
    destroy() {
      closeDropdown();
      inputEl.removeEventListener('input', onInput);
      inputEl.removeEventListener('keydown', onKeyDown);
      document.removeEventListener('click', onDocClick);
    },
  };
}
