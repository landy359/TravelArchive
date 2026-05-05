/**
 * help.js
 */

import { renderTemplate } from './utils.js';
import { BackendHooks, TokenManager } from './api.js';

function _renderAdminTable(container, cols, rows) {
  if (!rows.length) {
    container.innerHTML = '<div style="color:var(--text-secondary);padding:8px;">데이터 없음</div>';
    return;
  }
  const table = document.createElement('table');
  table.style.cssText = 'width:100%;border-collapse:collapse;font-size:12px;';
  const thead = document.createElement('thead');
  thead.innerHTML = '<tr>' + cols.map(c =>
    `<th style="text-align:left;padding:4px 8px;border-bottom:1px solid var(--border,#ddd);color:var(--text-secondary);">${c.label}</th>`
  ).join('') + '</tr>';
  table.appendChild(thead);
  const tbody = document.createElement('tbody');
  for (const row of rows) {
    const tr = document.createElement('tr');
    tr.innerHTML = cols.map(c =>
      `<td style="padding:4px 8px;border-bottom:1px solid var(--border-light,rgba(0,0,0,.06));word-break:break-all;">${row[c.key] ?? ''}</td>`
    ).join('');
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  container.innerHTML = '';
  container.appendChild(table);
}

async function _loadUsers(container) {
  container.innerHTML = '<div style="padding:8px;color:var(--text-secondary);">로딩 중...</div>';
  try {
    const data = await BackendHooks.adminGetUsers();
    _renderAdminTable(container, [
      { key: 'user_id',    label: 'ID' },
      { key: 'nickname',   label: '닉네임' },
      { key: 'email',      label: '이메일' },
      { key: 'created_at', label: '가입일' },
    ], data.users || []);
  } catch (e) {
    container.innerHTML = `<div style="color:red;padding:8px;">${e.message}</div>`;
  }
}

async function _loadSessions(container) {
  container.innerHTML = '<div style="padding:8px;color:var(--text-secondary);">로딩 중...</div>';
  try {
    const data = await BackendHooks.adminGetSessions();
    _renderAdminTable(container, [
      { key: 'session_id',     label: 'Session ID' },
      { key: 'sse_subscribers', label: 'SSE' },
    ], data.active_sessions || []);
  } catch (e) {
    container.innerHTML = `<div style="color:red;padding:8px;">${e.message}</div>`;
  }
}

export function renderHelpPage(container) {
  const uid   = TokenManager.getUserId() || '';
  const email = TokenManager.getEmail()  || '';
  const isAdmin = TokenManager.isLoggedIn() &&
    (uid.endsWith(':admin') || uid === 'admin' || email === 'test@test.com');

  if (isAdmin) {
    container.innerHTML = `
      <div class="page-view-content">
        <h2 class="title-main">Admin Panel</h2>
        <div class="item-card" style="margin-bottom:16px;">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;">
            <strong>사용자 목록</strong>
            <button id="adminRefreshUsers" style="padding:3px 10px;border-radius:6px;border:1px solid var(--border,#ccc);background:var(--bg-secondary);cursor:pointer;font-size:12px;">↻ 새로고침</button>
          </div>
          <div id="adminUsersTable" style="max-height:260px;overflow-y:auto;"></div>
        </div>
        <div class="item-card">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;">
            <strong>활성 세션</strong>
            <button id="adminRefreshSessions" style="padding:3px 10px;border-radius:6px;border:1px solid var(--border,#ccc);background:var(--bg-secondary);cursor:pointer;font-size:12px;">↻ 새로고침</button>
          </div>
          <div id="adminSessionsTable" style="max-height:200px;overflow-y:auto;"></div>
        </div>
      </div>`;

    const usersEl    = container.querySelector('#adminUsersTable');
    const sessionsEl = container.querySelector('#adminSessionsTable');
    _loadUsers(usersEl);
    _loadSessions(sessionsEl);
    container.querySelector('#adminRefreshUsers').addEventListener('click',    () => _loadUsers(usersEl));
    container.querySelector('#adminRefreshSessions').addEventListener('click', () => _loadSessions(sessionsEl));
  } else {
    container.innerHTML = renderTemplate('help');
  }
}
