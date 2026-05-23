/**
 * session-info-modal widget
 *
 * 세션 정보(이름/모드/여행/생성일/참여자) + 마스터 전용 소속계획 변경 UI.
 * 외부 API 호출은 DI 로 받음.
 *
 * Usage:
 *   import { mount } from '@/widgets/session-info-modal';
 *   await mount({
 *     info,             // 세션 info JSON
 *     myUserId,         // 현재 로그인 유저 id
 *     fetchTrips,       // 마스터일 때 trip 목록 조회
 *     onSaveTrip,       // (newTripId) => Promise — 저장 콜백
 *     onTripSaved,      // 저장 성공 후 콜백 (예: 사이드바 갱신)
 *     onSaveFailToast,  // (msg) => void
 *     onSaveSuccessToast,
 *   });
 */

import templateHtml from './session-info-modal.html?raw';
import './session-info-modal.css';

export async function mount({
  info = {},
  myUserId = null,
  fetchTrips = async () => [],
  onSaveTrip = async () => {},
  onTripSaved = () => {},
  onSaveFailToast = () => {},
  onSaveSuccessToast = () => {},
} = {}) {
  // 기존 모달 제거
  document.getElementById('session-info-modal')?.remove();

  const tpl = document.createElement('template');
  tpl.innerHTML = templateHtml.trim();
  const modal = tpl.content.firstElementChild;
  modal.classList.add('show');

  const body = modal.querySelector('[data-body]');

  const isMaster = (info.participants || []).some(p => p.user_id === myUserId && p.role === 'master');

  const participantsHtml = (info.participants || []).map(p => `
    <div class="session-info-participant">
      <div class="session-info-avatar">${(p.nickname || p.user_id || '?').charAt(0).toUpperCase()}</div>
      <div class="session-info-pname">${p.nickname || p.user_id}${p.role === 'master' ? ' <span class="session-info-master-badge">마스터</span>' : ''}</div>
    </div>`).join('');

  const tripDot = info.trip_color
    ? `<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${info.trip_color};margin-right:6px;vertical-align:middle;"></span>`
    : '';
  const tripDisplay = info.trip_title
    ? `${tripDot}${info.trip_title}`
    : '<span style="color:var(--text-secondary,#9ca3af)">기타</span>';

  // 소속 계획 변경 (마스터만)
  let tripChangeHtml = '';
  if (isMaster) {
    let trips = [];
    try { trips = (await fetchTrips()).filter(t => !t.is_misc); } catch {}
    const opts = trips.map(t =>
      `<option value="${t.trip_id}" ${info.trip_id === t.trip_id ? 'selected' : ''}>${t.title || '이름 없는 여행'}</option>`
    ).join('');
    tripChangeHtml = `
      <div class="session-info-row" style="margin-top:8px;align-items:center;">
        <span class="session-info-label">계획 변경</span>
        <select id="sessionTripSelect" style="flex:1;padding:4px 8px;border-radius:6px;border:1px solid var(--border-color,#e2e8f0);background:var(--bg-secondary,#f8fafc);color:var(--text-primary,#222);font-size:13px;">
          <option value="">기타 (미분류)</option>
          ${opts}
        </select>
        <button id="sessionTripSaveBtn" style="margin-left:6px;padding:4px 10px;border-radius:6px;background:var(--accent,#2563eb);color:#fff;border:none;cursor:pointer;font-size:12px;">저장</button>
      </div>`;
  }

  body.innerHTML = `
    <div class="session-info-row"><span class="session-info-label">이름</span><span>${info.title || '-'}</span></div>
    <div class="session-info-row"><span class="session-info-label">모드</span><span>${(info.participants || []).length > 1 ? '팀 대화' : '개인 플래너'}</span></div>
    <div class="session-info-row"><span class="session-info-label">여행</span><span>${tripDisplay}</span></div>
    <div class="session-info-row"><span class="session-info-label">생성일</span><span>${info.created_at ? info.created_at.substring(0, 10) : '-'}</span></div>
    ${tripChangeHtml}
    <div class="session-info-section-title" style="margin-top:12px;">참여자 (${(info.participants || []).length}명)</div>
    <div class="session-info-participants">${participantsHtml || '<span style="color:var(--text-secondary,#9ca3af)">없음</span>'}</div>
  `;

  document.body.appendChild(modal);

  const close = () => modal.remove();
  modal.querySelector('[data-close]').addEventListener('click', close);
  modal.addEventListener('click', e => { if (e.target === modal) close(); });

  if (isMaster) {
    modal.querySelector('#sessionTripSaveBtn')?.addEventListener('click', async () => {
      const sel = modal.querySelector('#sessionTripSelect');
      const newTripId = sel?.value || null;
      try {
        await onSaveTrip(newTripId);
        onSaveSuccessToast('소속 계획이 변경되었습니다.');
        close();
        onTripSaved();
      } catch {
        onSaveFailToast('변경에 실패했습니다.');
      }
    });
  }

  return { el: modal, close };
}
