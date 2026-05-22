/**
 * marker-panel widget
 *
 * 오른쪽 사이드바, 지도 컨테이너 바로 아래에 위치하는 마커 정보 드롭다운.
 * 지도 iframe 으로부터 MI_LOADING / MI_DATA / MI_ERROR / MI_REMOVE 메시지를 받아
 * marker-card 위젯을 카드 컨테이너에 누적 표시한다.
 *
 * Usage:
 *   import { mount } from '@/widgets/marker-panel';
 *   const panel = mount({ mapContainerEl });
 *   panel.destroy();
 */

import templateHtml from './marker-panel.html?raw';
import './marker-panel.css';
import { Icons } from '../../js/assets.js';
import { mount as mountCard } from '../marker-card/index.js';

function buildEl() {
  const tpl = document.createElement('template');
  tpl.innerHTML = templateHtml.trim();
  const el = tpl.content.firstElementChild;
  el.querySelector('[data-icon]').innerHTML      = Icons.Pin;
  el.querySelector('[data-clear-all]').innerHTML = Icons.CardTrash;
  el.querySelector('[data-toggle]').innerHTML    = Icons.Chevron;
  return el;
}

/**
 * @param {{ mapContainerEl: HTMLElement }} options
 * @returns {{ el: HTMLElement, destroy: Function }}
 */
export function mount({ mapContainerEl }) {
  const dropdown = buildEl();
  const header   = dropdown.querySelector('[data-header]');
  const cardsBox = dropdown.querySelector('[data-cards]');
  const countEl  = dropdown.querySelector('[data-count]');
  const clearBtn = dropdown.querySelector('[data-clear-all]');
  const toggleBtn = dropdown.querySelector('[data-toggle]');

  mapContainerEl.insertAdjacentElement('afterend', dropdown);

  // 기본 접힘 상태
  let isOpen = false;

  const toggleDropdown = () => {
    isOpen = !isOpen;
    dropdown.classList.toggle('rs-open', isOpen);
    toggleBtn.classList.toggle('rs-chevron-rotated', isOpen);
  };

  header.addEventListener('click', e => {
    if (e.target.closest('.rs-header-btn')) return;
    toggleDropdown();
  });
  toggleBtn.addEventListener('click', e => {
    e.stopPropagation();
    toggleDropdown();
  });

  // 카드 관리
  const cards = new Map();   // markerId → cardCtrl
  let seq = 0;

  const updateHeader = () => {
    const n = cards.size;
    countEl.textContent = `${n}개`;
    clearBtn.style.display = n > 0 ? '' : 'none';
    dropdown.classList.toggle('rs-has-markers', n > 0);
  };

  const removeCard = (markerId) => {
    const ctrl = cards.get(markerId);
    if (!ctrl) return;
    cards.delete(markerId);
    ctrl.destroy({ animate: true });
    updateHeader();
  };

  clearBtn.addEventListener('click', e => {
    e.stopPropagation();
    const mapIframe = document.querySelector('iframe');
    if (mapIframe) {
      mapIframe.contentWindow.postMessage({ type: 'DELETE_ALL_MARKERS' }, '*');
    }
    [...cards.keys()].forEach(removeCard);
  });

  // iframe → 부모 메시지 핸들러
  const onMessage = (e) => {
    const { type, markerId, payload } = e.data ?? {};
    if (!type?.startsWith('MI_') || !markerId) return;

    if (type === 'MI_LOADING') {
      if (cards.has(markerId)) {
        cards.get(markerId).setLoading();
        return;
      }
      seq++;
      const ctrl = mountCard(cardsBox, {
        markerId,
        seq,
        prepend: true,
        onClose: removeCard,
      });
      ctrl.setLoading();
      cards.set(markerId, ctrl);
      updateHeader();
      cardsBox.scrollTop = 0;

    } else if (type === 'MI_DATA') {
      cards.get(markerId)?.setData(payload);
    } else if (type === 'MI_ERROR') {
      cards.get(markerId)?.setError();
    } else if (type === 'MI_REMOVE') {
      removeCard(markerId);
    }
  };

  window.addEventListener('message', onMessage);
  updateHeader();

  return {
    el: dropdown,
    destroy() {
      window.removeEventListener('message', onMessage);
      dropdown.remove();
    },
  };
}
