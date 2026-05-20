/**
 * marker-card widget
 *
 * 오른쪽 사이드바 드롭다운 안에서 마커 1개당 하나씩 보여지는 정보 카드.
 *
 * Lifecycle:
 *   loading → data | error
 *
 * Usage:
 *   import { mount } from '@/widgets/marker-card';
 *   const card = mount(container, {
 *     markerId,
 *     seq: 1,
 *     prepend: true,
 *     onClose: (id) => removeFromState(id),
 *   });
 *   card.setLoading();
 *   card.setData({ roadAddr, jibunAddr, regionText, lat, lng });
 *   card.setError();
 *   card.destroy();              // 애니메이션 제거 후 DOM 분리
 *   card.destroy({ animate:false }); // 즉시 제거
 */

import templateHtml from './marker-card.html?raw';
import './marker-card.css';
import { Icons } from '../../js/assets.js';

const REMOVE_ANIM_DURATION = 300;

const SVG_CHECK = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`;

function buildEl(markerId) {
  const tpl = document.createElement('template');
  tpl.innerHTML = templateHtml.trim();
  const el = tpl.content.firstElementChild;
  el.dataset.markerId = markerId;

  // 아이콘 주입
  el.querySelector('[data-close]').innerHTML = Icons.CardClose;
  el.querySelector('[data-copy]').innerHTML  = `${Icons.CardCopy} 복사`;
  el.querySelector('[data-naver]').innerHTML = `${Icons.CardMap} 지도`;
  return el;
}

/**
 * @param {HTMLElement} parent
 * @param {{ markerId: string, seq?: number, prepend?: boolean, onClose?: Function }} props
 */
export function mount(parent, { markerId, seq, prepend = false, onClose } = {}) {
  const el = buildEl(markerId);
  if (typeof seq === 'number') el.querySelector('.rs-card-seq').textContent = `#${seq}`;

  if (prepend) parent.prepend(el);
  else         parent.appendChild(el);

  // 캐시
  const $ = sel => el.querySelector(sel);
  const title  = $('.rs-card-title');
  const sk     = $('[data-sk]');
  const list   = $('[data-list]');
  const error  = $('[data-error]');
  const road   = $('[data-road]');
  const jibun  = $('[data-jibun]');
  const region = $('[data-region]');
  const coord  = $('[data-coord]');
  const copyBtn  = $('[data-copy]');
  const naverBtn = $('[data-naver]');
  const closeBtn = $('[data-close]');

  let _lat = null, _lng = null;

  closeBtn.addEventListener('click', () => onClose?.(markerId));

  copyBtn.addEventListener('click', () => {
    if (_lat == null) return;
    const text = `${_lat.toFixed(6)}, ${_lng.toFixed(6)}`;
    navigator.clipboard?.writeText(text).catch(() => {});
    const orig = copyBtn.innerHTML;
    copyBtn.innerHTML = `${SVG_CHECK} 복사됨`;
    setTimeout(() => { copyBtn.innerHTML = orig; }, 1800);
  });

  naverBtn.addEventListener('click', () => {
    if (_lat == null) return;
    window.open(`https://map.naver.com/v5/?c=${_lng},${_lat},15,0,0,0,dh`, '_blank');
  });

  return {
    el,
    setSeq(n) { el.querySelector('.rs-card-seq').textContent = `#${n}`; },

    setLoading() {
      title.textContent = '조회 중…';
      sk.hidden = false;
      list.hidden = true;
      error.hidden = true;
    },

    setData(payload) {
      _lat = payload.lat;
      _lng = payload.lng;
      title.textContent  = payload.roadAddr || payload.jibunAddr || '알 수 없는 위치';
      road.textContent   = payload.roadAddr   || '—';
      jibun.textContent  = payload.jibunAddr  || '—';
      region.textContent = payload.regionText || '—';
      coord.textContent  = `${payload.lat.toFixed(6)}, ${payload.lng.toFixed(6)}`;
      sk.hidden    = true;
      error.hidden = true;
      list.hidden  = false;
    },

    setError() {
      title.textContent = '오류';
      sk.hidden    = true;
      list.hidden  = true;
      error.hidden = false;
    },

    destroy({ animate = true } = {}) {
      if (animate) {
        el.classList.add('rs-card-removing');
        setTimeout(() => el.remove(), REMOVE_ANIM_DURATION);
      } else {
        el.remove();
      }
    },
  };
}

export const REMOVE_DURATION = REMOVE_ANIM_DURATION;
