/**
 * mapOverlayControls.js  —  하위 호환 facade
 * 실제 위젯: widgets/map-overlay-controls/
 */

import { mount } from '../widgets/map-overlay-controls/index.js';

/**
 * @param {kakao.maps.Map} map
 * @param {HTMLElement}    container
 * @param {Function}       [onLocationClick]
 * @returns {{ destroy: Function, locationBtn: HTMLElement }}
 */
export function initOverlayControls(map, container, onLocationClick) {
  return mount(map, container, onLocationClick);
}
