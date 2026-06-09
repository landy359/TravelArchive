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

// ── 장소명 → stable ID slug ──────────────────────────────────
function _slug(place) {
  return (place || '').replace(/[^가-힣a-zA-Z0-9]/g, '_').slice(0, 40);
}

// ── 지도 마커 동기화 (플랜 전용 마커, 사용자 클릭 마커 불변) ──
function _syncPlanToMap(plan) {
  const iframe = document.querySelector('#kakaoMapContainer iframe');
  if (!iframe?.contentWindow) return;

  const post = (msg) => iframe.contentWindow.postMessage(msg, '*');

  const markers = [];
  plan.forEach((dayObj, dayIdx) => {
    (dayObj.items || []).forEach((item) => {
      const pi = item.place_info;
      if (pi?.lat && pi?.lng) {
        markers.push({
          lat:      pi.lat,
          lng:      pi.lng,
          title:    item.place || pi.name || '',
          markerId: `plan_d${dayIdx}_${_slug(item.place || pi.name || '')}`,
        });
      }
    });
  });

  // plan 마커만 교체 (click_ 사용자 마커는 건드리지 않음)
  post({ type: 'REMOVE_PLAN_MARKERS' });
  if (!markers.length) return;
  setTimeout(() => {
    markers.forEach(m => post({
      type: 'ADD_PLAN_MARKER', lat: m.lat, lng: m.lng, title: m.title, markerId: m.markerId,
    }));
    post({ type: 'FIT_BOUNDS', markers: markers.map(m => ({ lat: m.lat, lng: m.lng })) });
  }, 50);
}

// ── 아이콘 ──────────────────────────────────────────────────
const ChevronIcon = `<svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="3" fill="none" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg>`;
const PinIcon     = `<svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>`;

// ── 빈 상태 렌더링 ──────────────────────────────────────────
function renderEmpty(container) {
  container.innerHTML = `
    <div style="padding: 16px 4px; text-align: center; color: rgba(31,41,55,0.45); font-size: 12px; line-height: 1.8;">
      아직 일정이 없습니다.<br>채팅에서 @plan 으로 일정을 만들어보세요.
    </div>
  `;
}

// ── day 아코디언 1개 생성 ───────────────────────────────────
function buildDayEl(dayObj, onRemoveItem) {
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
    background: rgba(255,255,255,0.40);
    border: 1px solid rgba(255,255,255,0.25);
    box-shadow: 0 1px 6px rgba(0,0,0,0.08);
    overflow: hidden;
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
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
    color: rgba(17,24,39,0.90);
    flex: 1; min-width: 0;
  `;
  title.innerHTML = `
    <span style="
      background: rgba(59,130,246,0.12);
      color: #1d4ed8;
      border-radius: 5px;
      padding: 1px 7px;
      font-size: 11px;
      font-weight: 800;
      white-space: nowrap;
    ">${day}일차</span>
    <span style="
      color: rgba(31,41,55,0.50);
      font-size: 11px;
      font-weight: 400;
    ">${dateLabel}</span>
    <span style="
      color: rgba(31,41,55,0.40);
      font-size: 10px;
      margin-left: auto;
    ">${items.length}개</span>
  `;

  const chevron = document.createElement('span');
  chevron.innerHTML = ChevronIcon;
  chevron.style.cssText = `
    color: rgba(31,41,55,0.50);
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
      font-size: 11px; color: rgba(31,41,55,0.40);
      padding: 4px 0; text-align: center;
    `;
    empty.textContent = '일정 없음';
    content.appendChild(empty);
  } else {
    items.forEach((item, itemIdx) => {
      const row = document.createElement('div');
      row.style.cssText = `
        display: flex; align-items: flex-start; gap: 8px;
        padding: 6px 0;
        border-bottom: 1px solid rgba(0,0,0,0.05);
        position: relative;
      `;

      const orderEl = document.createElement('span');
      orderEl.style.cssText = `
        font-size: 10px; font-weight: 800;
        color: rgba(31,41,55,0.40);
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
        color: rgba(17,24,39,0.85);
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
      `;
      placeName.textContent = item.place || '이름 없음';

      info.appendChild(placeName);

      // place_info 있으면 주소 표시
      const pi = item.place_info || {};
      if (pi.address_road || pi.name) {
        const addr = document.createElement('div');
        addr.style.cssText = `
          font-size: 10px; color: rgba(31,41,55,0.50);
          margin-top: 2px;
          white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        `;
        addr.textContent = pi.address_road || pi.name || '';
        info.appendChild(addr);
      }

      // X 버튼 (아이템 개별 제거)
      if (onRemoveItem) {
        const removeBtn = document.createElement('button');
        removeBtn.style.cssText = `
          background: none; border: none; padding: 0 2px;
          cursor: pointer; color: rgba(31,41,55,0.30);
          font-size: 13px; line-height: 1; flex-shrink: 0;
          display: flex; align-items: center;
          transition: color 0.15s;
        `;
        removeBtn.textContent = '×';
        removeBtn.title = '일정에서 제거';
        removeBtn.addEventListener('mouseenter', () => { removeBtn.style.color = 'rgba(239,68,68,0.8)'; });
        removeBtn.addEventListener('mouseleave', () => { removeBtn.style.color = 'rgba(31,41,55,0.30)'; });
        removeBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          onRemoveItem(day - 1, itemIdx);  // dayIdx는 day(1-indexed) - 1
        });
        row.appendChild(removeBtn);
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
  let _currentPlan = [];   // 현재 플랜 상태 (mutable)

  function _renderPlan(plan) {
    planContentEl.innerHTML = '';
    if (!plan || plan.length === 0 || plan.every(d => d.items.length === 0)) {
      renderEmpty(planContentEl);
      return;
    }
    plan.forEach(dayObj => {
      const el = buildDayEl(dayObj, _onRemoveItem);
      planContentEl.appendChild(el);
    });
    const firstHeader = planContentEl.querySelector('.tp-day-header');
    firstHeader?.click();
  }

  async function _onRemoveItem(dayIdx, itemIdx) {
    if (!_currentPlan[dayIdx]) return;

    _currentPlan[dayIdx].items.splice(itemIdx, 1);
    _currentPlan[dayIdx].items.forEach((it, i) => { it.order = i + 1; });

    // 플랜 마커 전체 재동기화 (stable ID 사용 — index drift 없음)
    _syncPlanToMap(_currentPlan);

    if (_currentSessionId) {
      try {
        const { saveTripPlan } = await import('../../core/api/sessions.js');
        const raw = _currentPlan.map(d => d.items.map(it => ({
          date:       d.date || '',
          order:      it.order,
          place:      it.place || '',
          place_info: it.place_info || {},
        })));
        await saveTripPlan(_currentSessionId, raw);
      } catch (e) { console.warn('[TripPlan] 저장 실패:', e); }
    }

    _renderPlan(_currentPlan);
  }

  async function loadPlan(sessionId) {
    _currentSessionId = sessionId;
    planContentEl.innerHTML = '';

    if (!sessionId) {
      _currentPlan = [];
      renderEmpty(planContentEl);
      return;
    }

    try {
      const data = await fetchTripPlan(sessionId);
      const plan = data?.plan || [];

      if (_currentSessionId !== sessionId) return;

      _currentPlan = plan;
      _renderPlan(plan);
      _syncPlanToMap(plan);

    } catch (e) {
      console.warn('[TripPlanWidget] loadPlan 실패:', e);
      if (_currentSessionId === sessionId) renderEmpty(planContentEl);
    }
  }

  // plan 마커는 addPlan()으로 생성 — rightclick 없으므로 ta:plan-marker-removed 발생 안 함
  // 이 핸들러는 안전 장치용으로만 유지
  const _onMarkerRemoved = (e) => {
    const { markerId } = e.detail;
    if (!markerId?.startsWith('plan_')) return;
    const m = markerId.match(/^plan_d(\d+)_(.+)$/);
    if (!m) return;
    const dayIdx = parseInt(m[1], 10);
    const slug   = m[2];
    if (!_currentPlan[dayIdx]) return;
    const itemIdx = _currentPlan[dayIdx].items.findIndex(it => _slug(it.place) === slug);
    if (itemIdx < 0) return;
    _currentPlan[dayIdx].items.splice(itemIdx, 1);
    _currentPlan[dayIdx].items.forEach((it, i) => { it.order = i + 1; });
    _syncPlanToMap(_currentPlan);
    _renderPlan(_currentPlan);
    if (_currentSessionId) {
      import('../../core/api/sessions.js').then(({ saveTripPlan }) => {
        const raw = _currentPlan.map(d => d.items.map(it => ({
          date: d.date || '', order: it.order, place: it.place || '', place_info: it.place_info || {},
        })));
        saveTripPlan(_currentSessionId, raw).catch(() => {});
      });
    }
  };
  window.addEventListener('ta:plan-marker-removed', _onMarkerRemoved);

  // 시나리오9: API 호출 없이 plan 데이터를 직접 주입 (공유 뷰 등)
  function setPlan(plan) {
    _currentPlan = plan || [];
    _renderPlan(_currentPlan);
    if (_currentPlan.length) _syncPlanToMap(_currentPlan);
  }

  function destroy() {
    planContentEl.innerHTML = '';
    _currentSessionId = null;
    _currentPlan = [];
    window.removeEventListener('ta:plan-marker-removed', _onMarkerRemoved);
  }

  renderEmpty(planContentEl);

  return { loadPlan, setPlan, destroy };
}
