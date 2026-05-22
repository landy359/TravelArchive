/**
 * invite-modal widget
 *
 * 이메일 검색 → 스테이징 목록 → 일괄 초대 모달.
 * 외부 호출(검색/초대) 은 DI.
 *
 * Usage:
 *   import { mount } from '@/widgets/invite-modal';
 *   mount({
 *     sessionId,
 *     searchUsers,        // (email) => Promise<users[]>
 *     inviteUserToSession,// (sid, userId) => Promise
 *     toast,              // (msg) => void
 *   });
 */

import templateHtml from './invite-modal.html?raw';
import './invite-modal.css';

export function mount({
  sessionId,
  searchUsers,
  inviteUserToSession,
  toast = () => {},
} = {}) {
  const tpl = document.createElement('template');
  tpl.innerHTML = templateHtml.trim();
  const modal = tpl.content.firstElementChild;
  document.body.appendChild(modal);
  setTimeout(() => modal.classList.add('show'), 10);

  const $ = sel => modal.querySelector(sel);
  const emailInput   = $('[data-input]');
  const searchBtn    = $('[data-search]');
  const resultDiv    = $('[data-result]');
  const stagingLabel = $('[data-staging-label]');
  const stagingList  = $('[data-staging-list]');
  const sendBtn      = $('[data-send]');

  const close = () => { modal.classList.remove('show'); setTimeout(() => modal.remove(), 300); };
  $('[data-close]').addEventListener('click', close);
  modal.addEventListener('click', e => { if (e.target === modal) close(); });

  const staged = new Map(); // user_id → {nickname, email}

  const refreshStaging = () => {
    stagingList.innerHTML = '';
    if (staged.size === 0) {
      stagingLabel.style.display = 'none';
      sendBtn.disabled = true;
      sendBtn.style.opacity = '0.45';
      sendBtn.style.cursor = 'not-allowed';
      return;
    }
    stagingLabel.style.display = '';
    sendBtn.disabled = false;
    sendBtn.style.opacity = '1';
    sendBtn.style.cursor = 'pointer';
    staged.forEach((u, uid) => {
      const row = document.createElement('div');
      row.style.cssText = 'display:flex;align-items:center;justify-content:space-between;padding:5px 8px;border-radius:6px;background:var(--bg-secondary,#f1f5f9);';
      const nameSpan = document.createElement('span');
      nameSpan.style.cssText = 'font-size:13px;color:var(--text-primary,#222);';
      nameSpan.textContent = `${u.nickname || uid} (${u.email || ''})`;
      const removeBtn = document.createElement('button');
      removeBtn.textContent = '−';
      removeBtn.style.cssText = 'background:none;border:none;cursor:pointer;font-size:16px;color:#ef4444;padding:0 4px;line-height:1;';
      removeBtn.addEventListener('click', () => { staged.delete(uid); refreshStaging(); });
      row.appendChild(nameSpan);
      row.appendChild(removeBtn);
      stagingList.appendChild(row);
    });
  };

  const doSearch = async () => {
    const q = emailInput.value.trim();
    if (!q) return;
    resultDiv.textContent = '검색 중...';
    try {
      const users = await searchUsers(q);
      if (!users.length) { resultDiv.textContent = '해당 이메일로 가입된 사용자가 없습니다.'; return; }
      const user = users[0];
      if (staged.has(user.user_id)) { resultDiv.textContent = '이미 목록에 추가된 사용자입니다.'; return; }
      staged.set(user.user_id, { nickname: user.nickname, email: user.email || q });
      refreshStaging();
      resultDiv.textContent = `${user.nickname || user.user_id} 추가됨`;
      emailInput.value = '';
    } catch { resultDiv.textContent = '검색에 실패했습니다.'; }
  };

  searchBtn.addEventListener('click', doSearch);
  emailInput.addEventListener('keydown', ev => { if (ev.key === 'Enter') doSearch(); });

  sendBtn.addEventListener('click', async () => {
    if (!staged.size) return;
    sendBtn.disabled = true;
    sendBtn.textContent = '초대 중...';
    let ok = 0, fail = 0;
    for (const uid of staged.keys()) {
      try { await inviteUserToSession(sessionId, uid); ok++; }
      catch { fail++; }
    }
    if (ok) toast(`${ok}명 초대 완료${fail ? `, ${fail}명 실패` : ''}`);
    else    toast('초대에 실패했습니다.');
    close();
  });

  emailInput.focus();
  return { el: modal, close };
}
