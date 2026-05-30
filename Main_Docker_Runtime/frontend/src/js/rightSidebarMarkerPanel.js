/**
 * rightSidebarMarkerPanel.js  —  하위 호환 facade
 * 실제 위젯: widgets/marker-panel/
 */

import { mount } from '../widgets/marker-panel/index.js';

/**
 * @param {{ mapContainerEl: HTMLElement }} options
 * @returns {{ destroy: Function }}
 */
export function initRightSidebarMarkerPanel({ mapContainerEl }) {
  // 오버레이 컨트롤 위젯(#oc-host) 이 있으면 그 뒤에, 없으면 지도 뒤에 삽입
  const insertAfterEl = document.getElementById('oc-host') || mapContainerEl;
  return mount({ mapContainerEl: insertAfterEl });
}
