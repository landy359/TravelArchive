/**
 * rightSidebarMarkerPanel.js  —  하위 호환 facade
 * 실제 위젯: widgets/marker-panel/
 */

import { mount } from '../widgets/marker-panel/index.js';

/**
 * @param {{ mapContainerEl: HTMLElement }} options
 * @returns {{ destroy: Function }}
 */
export function initRightSidebarMarkerPanel(options) {
  return mount(options);
}
