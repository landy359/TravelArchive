/**
 * schedule.js
 * 여행 일정(trip_plan) 위젯 매니저. //frontend/src/js/schedule.js
 * widgets/trip-plan/ 을 rs-plan-content 에 마운트하고
 * 세션 전환 시 loadPlan 을 위임한다.
 */

import { mount } from '../widgets/trip-plan/index.js';

let _ctrl = null;  // { loadPlan, destroy }

export const ScheduleManager = {

  /**
   * 오른쪽 사이드바의 data-plan-content 에 위젯을 마운트한다.
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
   */
  async loadPlan(sessionId) {
    if (!_ctrl) return;
    await _ctrl.loadPlan(sessionId);
  },
};
