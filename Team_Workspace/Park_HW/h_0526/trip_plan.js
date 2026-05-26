/**
 * trip-plan widget
 * frontend/src/widgets/trip-plan/trip-plan.js
 *
 * 오른쪽 사이드바 rs-plan-box 내부에 위치하는 여행 일정 아코디언 위젯.
 * 백엔드 GET /api/sessions/{session_id}/trip_plan 에서 데이터를 받아
 * day 별 아코디언으로 렌더링한다.
 *
 * Usage:
 *   import { mount } from '@/widgets/trip-plan';
 *   const plan = mount({ planContentEl });
 *   plan.loadPlan(sessionId);
 *   plan.destroy();
 */

import { fetchTripPlan } from '../../core/api/sessions.js';

// ── 아이콘 ──────────────────────────────────────────────────
const ChevronIcon = `<svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="3" fill="none" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg>`;
const PinIcon     = `<svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>`;

// ── 빈 상태 렌더링 ──────────────────────────────────────────
function renderEmpty(container) {
  container.innerHTML = `
    <div style="padding: 16px 4px; text-align: center; color: rgba(255,255,255,0.35); font-size: 12px; line-height: 1.8;">
      아직 일정이 없습니다.<br>채팅에서 @plan 으로 일정을 만들어보세요.
    </div>
  `;
}

// ── day 아코디언 1개 생성 ───────────────────────────────────
function buildDayEl(dayObj) {
  const { day, date, items } = dayObj;

  // 날짜 표시 (YYMMDD → YY.MM.DD)
  const dateLabel = date
    ? `${date.slice(0, 2)}.${date.slice(2, 4)}.${date.slice(4, 6)}`
    : '';

  const wrap = document.createElement('div');
  wrap.className = 'tp-day-block';
  wrap.style.cssText = `
    margin-bottom: 6px;
    border-radius: 10px;
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.07);
    overflow: hidden;
  `;

  // 헤더
  const header = document.createElement('div');
  header.className = 'tp-day-header';
  header.style.cssText = `
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 9px 12px;
    cursor: pointer;
    user-select: none;
    gap: 8px;
  `;

  const title = document.createElement('div');
  title.style.cssText = `
    display: flex; align-items: center; gap: 8px;
    font-size: 12px; font-weight: 700;
    color: rgba(255,255,255,0.85);
    flex: 1; min-width: 0;
  `;
  title.innerHTML = `
    <span style="
      background: rgba(99,179,237,0.18);
      color: #63b3ed;
      border-radius: 5px;
      padding: 1px 7px;
      font-size: 11px;
      font-weight: 800;
      white-space: nowrap;
    ">${day}일차</span>
    <span style="
      color: rgba(255,255,255,0.4);
      font-size: 11px;
      font-weight: 400;
    ">${dateLabel}</span>
    <span style="
      color: rgba(255,255,255,0.3);
      font-size: 10px;
      margin-left: auto;
    ">${items.length}개</span>
  `;

  const chevron = document.createElement('span');
  chevron.innerHTML = ChevronIcon;
  chevron.style.cssText = `
    color: rgba(255,255,255,0.4);
    display: flex; align-items: center;
    transition: transform 0.25s ease;
    flex-shrink: 0;
  `;

  header.appendChild(title);
  header.appendChild(chevron);

  // 컨텐츠
  const content = document.createElement('div');
  content.className = 'tp-day-content';
  content.style.cssText = `
    display: none;
    padding: 0 12px 10px;
    flex-direction: column;
    gap: 4px;
  `;

  if (items.length === 0) {
    const empty = document.createElement('div');
    empty.style.cssText = `
      font-size: 11px; color: rgba(255,255,255,0.3);
      padding: 4px 0; text-align: center;
    `;
    empty.textContent = '일정 없음';
    content.appendChild(empty);
  } else {
    items.forEach(item => {
      const row = document.createElement('div');
      row.style.cssText = `
        display: flex; align-items: flex-start; gap: 8px;
        padding: 6px 0;
        border-bottom: 1px solid rgba(255,255,255,0.05);
      `;

      const orderEl = document.createElement('span');
      orderEl.style.cssText = `
        font-size: 10px; font-weight: 800;
        color: rgba(255,255,255,0.3);
        min-width: 16px; padding-top: 1px;
      `;
      orderEl.textContent = `${item.order}.`;

      const pinWrap = document.createElement('span');
      pinWrap.innerHTML = PinIcon;
      pinWrap.style.cssText = `
        color: #f6ad55; display: flex;
        align-items: center; flex-shrink: 0; padding-top: 1px;
      `;

      const info = document.createElement('div');
      info.style.cssText = `flex: 1; min-width: 0;`;

      const placeName = document.createElement('div');
      placeName.style.cssText = `
        font-size: 12px; font-weight: 600;
        color: rgba(255,255,255,0.85);
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
      `;
      placeName.textContent = item.place || '이름 없음';

      info.appendChild(placeName);

      // place_info 있으면 주소 표시
      const pi = item.place_info || {};
      if (pi.address_road || pi.name) {
        const addr = document.createElement('div');
        addr.style.cssText = `
          font-size: 10px; color: rgba(255,255,255,0.35);
          margin-top: 2px;
          white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        `;
        addr.textContent = pi.address_road || pi.name || '';
        info.appendChild(addr);
      }

      row.appendChild(orderEl);
      row.appendChild(pinWrap);
      row.appendChild(info);
      content.appendChild(row);
    });
  }

  // 토글
  let isOpen = false;
  const toggle = () => {
    isOpen = !isOpen;
    content.style.display = isOpen ? 'flex' : 'none';
    chevron.style.transform = isOpen ? 'rotate(180deg)' : 'rotate(0deg)';
  };
  header.addEventListener('click', toggle);

  wrap.appendChild(header);
  wrap.appendChild(content);
  return wrap;
}

// ── mount ───────────────────────────────────────────────────
/**
 * @param {{ planContentEl: HTMLElement }} options
 * @returns {{ loadPlan: Function, destroy: Function }}
 */
export function mount({ planContentEl }) {
  if (!planContentEl) return { loadPlan: () => {}, destroy: () => {} };

  let _currentSessionId = null;

  async function loadPlan(sessionId) {
    _currentSessionId = sessionId;
    planContentEl.innerHTML = '';

    if (!sessionId) {
      renderEmpty(planContentEl);
      return;
    }

    try {
      const data = await fetchTripPlan(sessionId);
      const plan = data?.plan || [];

      // 세션 전환 도중 응답이 왔으면 버림
      if (_currentSessionId !== sessionId) return;

      if (!plan || plan.length === 0 || plan.every(d => d.items.length === 0)) {
        renderEmpty(planContentEl);
        return;
      }

      plan.forEach(dayObj => {
        const el = buildDayEl(dayObj);
        planContentEl.appendChild(el);
      });

      // 첫 번째 day 자동 열기
      const firstHeader = planContentEl.querySelector('.tp-day-header');
      firstHeader?.click();

    } catch (e) {
      console.warn('[TripPlanWidget] loadPlan 실패:', e);
      if (_currentSessionId === sessionId) renderEmpty(planContentEl);
    }
  }

  function destroy() {
    planContentEl.innerHTML = '';
    _currentSessionId = null;
  }

  // 초기 렌더
  renderEmpty(planContentEl);

  return { loadPlan, destroy };
}
