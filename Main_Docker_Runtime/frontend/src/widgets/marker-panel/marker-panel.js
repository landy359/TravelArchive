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
  const cards = new Map();  // markerId → cardCtrl

  const _getMapIframe = () => document.querySelector('#kakaoMapContainer iframe');

  // 현재 DOM 순서 기준으로 #1, #2, #3... 재부여
  const renumber = () => {
    let n = 0;
    cards.forEach(ctrl => ctrl.setSeq(++n));
  };

  const updateHeader = () => {
    const n = cards.size;
    countEl.textContent = `${n}개`;
    clearBtn.style.display = n > 0 ? '' : 'none';
    dropdown.classList.toggle('rs-has-markers', n > 0);
  };

  // notifyMap=true: 카드 X 버튼 → 지도 마커도 제거
  // notifyMap=false: MI_REMOVE(지도에서 이미 제거됨) → 카드만 제거
  const removeCard = (markerId, notifyMap = true) => {
    const ctrl = cards.get(markerId);
    if (!ctrl) return;
    cards.delete(markerId);
    ctrl.destroy({ animate: true });
    renumber();
    updateHeader();
    if (notifyMap) {
      _getMapIframe()?.contentWindow?.postMessage({ type: 'REMOVE_MARKER', markerId }, '*');
    }
    if (markerId.startsWith('plan_')) {
      window.dispatchEvent(new CustomEvent('ta:plan-marker-removed', { detail: { markerId } }));
    }
  };

  // 플랜 위젯에서 아이템 제거 → 카드만 제거 (마커는 플랜 위젯이 처리)
  const onPlanItemRemoved = (e) => removeCard(e.detail.markerId, false);
  window.addEventListener('ta:plan-item-removed', onPlanItemRemoved);

  clearBtn.addEventListener('click', e => {
    e.stopPropagation();
    // 1) 지도 전체 마커 삭제
    _getMapIframe()?.contentWindow?.postMessage({ type: 'DELETE_ALL_MARKERS' }, '*');
    // 2) 카드만 제거 (이벤트 연쇄 없이 직접 DOM 정리)
    cards.forEach(ctrl => ctrl.destroy({ animate: false }));
    cards.clear();
    updateHeader();
  });

  // iframe → 부모 메시지 핸들러
  const onMessage = (e) => {
    const { type, markerId, payload } = e.data ?? {};
    if (!type) return;

    // 전체 삭제 완료 응답 (markerId 없음)
    if (type === 'DELETE_ALL_RESPONSE') {
      [...cards.keys()].forEach(id => cards.get(id)?.destroy({ animate: false }));
      cards.clear();
      updateHeader();
      return;
    }

    if (!markerId) return;

    if (type === 'MI_LOADING') {
      if (cards.has(markerId)) {
        cards.get(markerId).setLoading();
        return;
      }
      const ctrl = mountCard(cardsBox, {
        markerId,
        seq: cards.size + 1,
        prepend: true,
        onClose: removeCard,
      });
      ctrl.setLoading();
      cards.set(markerId, ctrl);
      renumber();
      updateHeader();
      cardsBox.scrollTop = 0;

    } else if (type === 'MI_DATA') {
      const _applyData = async () => {
        const enriched = { ...payload };
        if (!enriched.name && enriched.lat != null && enriched.lng != null) {
          try {
            const r = await fetch(`/api/places/nearest?lat=${enriched.lat}&lng=${enriched.lng}&radius=100`);
            if (r.ok) {
              const place = await r.json();
              if (place.found) {
                enriched.name = place.name;
                enriched.description = [place.main_category, place.sub_category, place.kakao_category]
                  .filter(Boolean).join(' / ');
              }
            }
          } catch {}
        }
        cards.get(markerId)?.setData(enriched);
      };
      _applyData();

    } else if (type === 'MI_ERROR') {
      cards.get(markerId)?.setError();

    } else if (type === 'MI_REMOVE') {
      removeCard(markerId, false);
    }
  };

  window.addEventListener('message', onMessage);
  updateHeader();

  return {
    el: dropdown,
    destroy() {
      window.removeEventListener('message', onMessage);
      window.removeEventListener('ta:plan-item-removed', onPlanItemRemoved);
      dropdown.remove();
    },
  };
}
