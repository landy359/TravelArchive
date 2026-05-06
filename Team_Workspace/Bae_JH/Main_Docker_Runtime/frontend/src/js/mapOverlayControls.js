import { bindLayerLogic } from './overlay/layerLogic.js';
import { bindZoomLogic }  from './overlay/zoomLogic.js';
import { bindResponsive } from './overlay/layoutLogic.js';

const ICONS = {
  traffic: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
      stroke-width="2" stroke-linecap="round">
    <rect x="9" y="1" width="6" height="22" rx="3"/>
    <circle cx="12" cy="6"  r="1.6" fill="#ef4444" stroke="none"/>
    <circle cx="12" cy="12" r="1.6" fill="#f59e0b" stroke="none"/>
    <circle cx="12" cy="18" r="1.6" fill="#22c55e" stroke="none"/>
  </svg>`,

  satellite: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
      stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
    <path d="M3.5 20.5l4-4"/>
    <path d="M7.5 16.5L4 13l3-3 3.5 3.5"/>
    <path d="M13 7.5L9.5 4l3-3 3.5 3.5"/>
    <path d="M20.5 3.5l-4 4"/>
    <path d="M16.5 7.5l3.5 3.5-3 3-3.5-3.5"/>
    <circle cx="12" cy="12" r="2"/>
    <path d="M7.5 7.5l9 9" stroke-dasharray="2 2"/>
  </svg>`,

  bicycle: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
      stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
    <circle cx="5.5"  cy="17.5" r="3.5"/>
    <circle cx="18.5" cy="17.5" r="3.5"/>
    <path d="M15 6h-5l-1.5 5.5 5 3 2-8.5z"/>
    <path d="M5.5 17.5l4-5.5"/>
    <path d="M18.5 17.5L15 9l-4.5 3"/>
    <circle cx="15" cy="5" r="1"/>
  </svg>`,

  location: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
      stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
    <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/>
    <circle cx="12" cy="10" r="3"/>
  </svg>`,

  zoomIn: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
      stroke-width="2.5" stroke-linecap="round">
    <line x1="12" y1="5"  x2="12" y2="19"/>
    <line x1="5"  y1="12" x2="19" y2="12"/>
  </svg>`,

  zoomOut: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
      stroke-width="2.5" stroke-linecap="round">
    <line x1="5" y1="12" x2="19" y2="12"/>
  </svg>`,
};

function el(tag, cls = '', attrs = {}) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  Object.entries(attrs).forEach(([k, v]) => e.setAttribute(k, v));
  return e;
}

function buildPanel() {
  const panel = el('div', 'oc-panel', { id: 'overlay-panel' });

  const locationBtn = el('button', 'oc-btn oc-location-btn', { id: 'location-btn', title: '내 위치 보기' });
  locationBtn.innerHTML = ICONS.location;
  panel.appendChild(locationBtn);

  panel.appendChild(el('div', 'oc-sep'));

  const layerLabel = el('span', 'oc-section-label');
  layerLabel.textContent = '레이어';
  panel.appendChild(layerLabel);

  const layerButtons = {};
  const LAYER_DEFS = [
    { id: 'traffic',   label: '교통량', icon: ICONS.traffic   },
    { id: 'satellite', label: '위성',   icon: ICONS.satellite },
    { id: 'bicycle',   label: '자전거', icon: ICONS.bicycle   },
  ];

  LAYER_DEFS.forEach(({ id, label, icon }) => {
    const wrap = el('div', 'oc-btn-wrap');
    const btn  = el('button', 'oc-btn', { 'data-layer': id, title: label });
    btn.innerHTML = icon;
    const tip = el('span', 'oc-tooltip');
    tip.textContent = label;
    wrap.appendChild(btn);
    wrap.appendChild(tip);
    panel.appendChild(wrap);
    layerButtons[id] = btn;
  });

  panel.appendChild(el('div', 'oc-sep'));

  const zoomLabel = el('span', 'oc-section-label');
  zoomLabel.textContent = '줌';
  panel.appendChild(zoomLabel);

  const zoomWrap   = el('div', 'oc-zoom-wrap');
  const zoomInBtn  = el('button', 'oc-btn oc-zoom-btn', { title: '확대' });
  const levelDisp  = el('div', 'oc-zoom-level');
  const barTrack   = el('div', 'oc-bar-track');
  const barFill    = el('div', 'oc-bar-fill');
  const zoomOutBtn = el('button', 'oc-btn oc-zoom-btn', { title: '축소' });

  zoomInBtn.innerHTML   = ICONS.zoomIn;
  zoomOutBtn.innerHTML  = ICONS.zoomOut;
  levelDisp.textContent = '8';
  barTrack.appendChild(barFill);
  [zoomInBtn, levelDisp, barTrack, zoomOutBtn].forEach(c => zoomWrap.appendChild(c));
  panel.appendChild(zoomWrap);

  return { panel, locationBtn, layerButtons, zoomInBtn, zoomOutBtn, levelDisp, barFill, zoomWrap };
}

/**
 * @param {kakao.maps.Map} map
 * @param {HTMLElement}    container
 * @param {Function}       onLocationClick
 * @returns {{ destroy: Function, locationBtn: HTMLElement }}
 */
export function initOverlayControls(map, container, onLocationClick) {
  if (getComputedStyle(container).position === 'static') {
    container.style.position = 'relative';
  }

  const { panel, locationBtn, layerButtons, zoomInBtn, zoomOutBtn, levelDisp, barFill, zoomWrap } = buildPanel();

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
