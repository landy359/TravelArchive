/**
 * schedule.js
 * 여행 일정(trip_plan) 위젯 매니저.
 * widgets/trip-plan/ 을 왼쪽 사이드바의 plan 컨텐츠 영역에 마운트하고
 * 세션 전환 시 loadPlan 을 위임한다.
 */

import { mount } from '../widgets/trip-plan/index.js';
import { resetTripPlan } from '../core/api/trips.js';

let _ctrl = null;       // { loadPlan, destroy }
let _tripId = null;     // 현재 세션에 연결된 trip_id

export const ScheduleManager = {

  /**
   * 왼쪽 사이드바의 data-plan-content 에 위젯을 마운트한다.
   * script.js 초기화 시점에 한 번만 호출.
   *
   * @param {HTMLElement} planContentEl — [data-plan-content]
   */
  init(planContentEl) {
    if (_ctrl) _ctrl.destroy();
    _ctrl = mount({ planContentEl });
  },

  /**
   * 세션 전환 시 호출 — 해당 세션의 일정을 로드해 렌더링.
   * router.js 에서 CalendarManager.loadTripRange 와 함께 호출.
   *
   * @param {string|null} sessionId
   * @param {string|null} tripId
   */
  async loadPlan(sessionId, tripId = null) {
    _tripId = tripId;
    if (!_ctrl) return;
    await _ctrl.loadPlan(sessionId);
  },

  /**
   * 일정 전체 초기화. 리셋 버튼에서 호출.
   */
  async reset() {
    if (!_tripId) return;
    if (!confirm('이번 여행의 일정을 전체 초기화하시겠습니까?')) return;
    try {
      await resetTripPlan(_tripId);
      if (_ctrl) _ctrl.destroy();
    } catch (e) {
      console.error('[ScheduleManager] reset 실패:', e);
    }
  },

  setTripId(tripId) {
    _tripId = tripId;
  },
};
