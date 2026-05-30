/**
 * mapOverlayControlsParent.js
 *
 * 부모(right sidebar) 컨텍스트에서 지도 오버레이 컨트롤 렌더링.
 * 실제 지도 조작은 #mapFrame 으로 postMessage 전송.
 *
 * 레이아웃: CSS(right_sidebar.css)가 제어.
 *   #oc-host            → 1행 (기본)
 *   #oc-host.oc-host--narrow → 2행 (좁을 때)
 */

import templateHtml from '../widgets/map-overlay-controls/map-overlay-controls.html?raw';
import '../widgets/map-overlay-controls/map-overlay-controls.css';
import { Icons } from './assets.js';

const LAYER_DEFS = [
  { id: 'traffic',   label: '교통량', icon: Icons.MapTraffic   },
  { id: 'satellite', label: '위성',   icon: Icons.MapSatellite },
  { id: 'bicycle',   label: '자전거', icon: Icons.MapBicycle   },
];

const MIN_LEVEL = 1;
const MAX_LEVEL = 14;
const BREAK_PX  = 300;

export function mountParentOverlayControls(host) {
  if (!host) return { destroy: () => {} };

  // ── 패널 빌드 ────────────────────────────────────────────────
  const tpl = document.createElement('template');
  tpl.innerHTML = templateHtml.trim();
  const panel = tpl.content.firstElementChild;

  panel.querySelector('[data-loc]').innerHTML      = Icons.MapLocation;
  panel.querySelector('[data-zoom-in]').innerHTML  = Icons.ZoomIn;
  panel.querySelector('[data-zoom-out]').innerHTML = Icons.ZoomOut;

  // 레이어 버튼 생성
  const layersBox    = panel.querySelector('[data-layers]');
  const layerState   = {};
  const layerButtons = {};
  LAYER_DEFS.forEach(({ id, label, icon }) => {
    const wrap = document.createElement('div');
    wrap.className = 'oc-btn-wrap';
    const btn = document.createElement('button');
    btn.className     = 'oc-btn';
    btn.dataset.layer = id;
    btn.title         = label;
    btn.innerHTML     = icon;
    const tip = document.createElement('span');
    tip.className   = 'oc-tooltip';
    tip.textContent = label;
    wrap.appendChild(btn);
    wrap.appendChild(tip);
    layersBox.appendChild(wrap);
    layerButtons[id] = btn;
    layerState[id]   = false;
  });

  const zoomWrap  = panel.querySelector('[data-zoom]');
  const levelDisp = panel.querySelector('[data-zoom-level]');
  const barFill   = panel.querySelector('[data-zoom-fill]');
  const barTrack  = panel.querySelector('.oc-bar-track');
  const locBtn    = panel.querySelector('[data-loc]');
  const zoomInBtn = panel.querySelector('[data-zoom-in]');
  const zoomOutBtn= panel.querySelector('[data-zoom-out]');

  // 줌 바: 가로 방향으로 고정 (CSS는 bottom/left 기준 세로 fill → 가로로 전환)
  if (barFill) {
    barFill.style.cssText = `
      position: absolute; bottom: 0; left: 0;
      height: 100%; width: 0%;
      border-radius: 2px;
      background: linear-gradient(to right, #38bdf8, #818cf8);
      transition: width .25s ease;
    `;
  }

  host.appendChild(panel);

  // ── postMessage 헬퍼 ─────────────────────────────────────────
  const send = data => document.getElementById('mapFrame')?.contentWindow?.postMessage(data, '*');

  // ── 줌 표시 업데이트 ─────────────────────────────────────────
  function updateZoom(level) {
    if (levelDisp) levelDisp.textContent = level;
    if (barFill) {
      const pct = ((level - MIN_LEVEL) / (MAX_LEVEL - MIN_LEVEL)) * 100;
      barFill.style.width = `${pct}%`;
    }
    zoomInBtn.disabled  = level <= MIN_LEVEL;
    zoomOutBtn.disabled = level >= MAX_LEVEL;
  }

  // ── iframe → parent 수신 ─────────────────────────────────────
  const onMessage = e => {
    if (e.data?.type === 'OC_ZOOM_CHANGED') updateZoom(e.data.level);
  };
  window.addEventListener('message', onMessage);

  // ── 버튼 → iframe ────────────────────────────────────────────
  locBtn.addEventListener('click',     () => send({ type: 'OC_LOCATION' }));
  zoomInBtn.addEventListener('click',  () => send({ type: 'OC_ZOOM_IN' }));
  zoomOutBtn.addEventListener('click', () => send({ type: 'OC_ZOOM_OUT' }));

  Object.entries(layerButtons).forEach(([id, btn]) => {
    btn.addEventListener('click', () => {
      layerState[id] = !layerState[id];
      btn.classList.toggle('oc-btn--active', layerState[id]);
      send({ type: 'OC_TOGGLE_LAYER', layer: id, active: layerState[id] });
    });
  });

  // ── 반응형: CSS 클래스 토글 ──────────────────────────────────
  const ro = new ResizeObserver(([entry]) => {
    host.classList.toggle('oc-host--narrow', entry.contentRect.width < BREAK_PX);
  });
  ro.observe(host);

  return {
    destroy() {
      ro.disconnect();
      window.removeEventListener('message', onMessage);
      panel.remove();
    },
  };
}
