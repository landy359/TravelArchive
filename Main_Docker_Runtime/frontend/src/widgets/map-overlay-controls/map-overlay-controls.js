/**
 * map-overlay-controls widget  (iframe 내부용)
 *
 * 카카오 지도 오버레이 컨트롤 패널.
 *  - 위치 버튼 (현위치 이동)
 *  - 레이어 토글 (교통량/위성/자전거)
 *  - 줌 +/- + 레벨 표시 + 진행바
 *  - 반응형 레이아웃 (가로/세로/ultra-compact)
 *
 * Usage (iframe 내 map.js 에서):
 *   import { mount } from '@/widgets/map-overlay-controls';
 *   const oc = mount(map, container, onLocationClick);
 *   oc.destroy();
 */

import templateHtml from './map-overlay-controls.html?raw';
import './map-overlay-controls.css';

import { Icons } from '../../js/assets.js';
import { bindLayerLogic } from './layer-logic.js';
import { bindZoomLogic }  from './zoom-logic.js';
import { bindResponsive } from './layout-logic.js';

const LAYER_DEFS = [
  { id: 'traffic',   label: '교통량', icon: Icons.MapTraffic   },
  { id: 'satellite', label: '위성',   icon: Icons.MapSatellite },
  { id: 'bicycle',   label: '자전거', icon: Icons.MapBicycle   },
];

function buildEl() {
  const tpl = document.createElement('template');
  tpl.innerHTML = templateHtml.trim();
  const panel = tpl.content.firstElementChild;

  panel.querySelector('[data-loc]').innerHTML       = Icons.MapLocation;
  panel.querySelector('[data-zoom-in]').innerHTML   = Icons.ZoomIn;
  panel.querySelector('[data-zoom-out]').innerHTML  = Icons.ZoomOut;

  // 레이어 버튼 + 툴팁 동적 생성
  const layersBox = panel.querySelector('[data-layers]');
  const layerButtons = {};
  LAYER_DEFS.forEach(({ id, label, icon }) => {
    const wrap = document.createElement('div');
    wrap.className = 'oc-btn-wrap';
    const btn = document.createElement('button');
    btn.className = 'oc-btn';
    btn.dataset.layer = id;
    btn.title = label;
    btn.innerHTML = icon;
    const tip = document.createElement('span');
    tip.className = 'oc-tooltip';
    tip.textContent = label;
    wrap.appendChild(btn);
    wrap.appendChild(tip);
    layersBox.appendChild(wrap);
    layerButtons[id] = btn;
  });

  return {
    panel,
    locationBtn: panel.querySelector('[data-loc]'),
    layerButtons,
    zoomInBtn:   panel.querySelector('[data-zoom-in]'),
    zoomOutBtn:  panel.querySelector('[data-zoom-out]'),
    levelDisp:   panel.querySelector('[data-zoom-level]'),
    barFill:     panel.querySelector('[data-zoom-fill]'),
    zoomWrap:    panel.querySelector('[data-zoom]'),
  };
}

/**
 * @param {kakao.maps.Map}  map
 * @param {HTMLElement}     container  지도 div
 * @param {Function}        [onLocationClick]
 * @returns {{ destroy: Function, locationBtn: HTMLElement }}
 */
export function mount(map, container, onLocationClick) {
  if (getComputedStyle(container).position === 'static') {
    container.style.position = 'relative';
  }

  const { panel, locationBtn, layerButtons, zoomInBtn, zoomOutBtn, levelDisp, barFill, zoomWrap } = buildEl();

  bindLayerLogic(map, layerButtons);
  const zoomCtrl = bindZoomLogic(map, { zoomInBtn, zoomOutBtn, levelDisp, barFill });

  container.appendChild(panel);

  if (typeof onLocationClick === 'function') {
    locationBtn.addEventListener('click', e => {
      e.stopPropagation();
      onLocationClick();
    });
  }

  const disconnect = bindResponsive(container, panel, zoomWrap, zoomCtrl, map);
  zoomCtrl.update();

  return {
    destroy() {
      disconnect();
      panel.remove();
    },
    locationBtn,
  };
}
