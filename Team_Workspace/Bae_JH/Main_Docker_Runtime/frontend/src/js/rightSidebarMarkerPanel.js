import {
  buildCard,
  createCardCtrl,
  removeCardAnimated,
  SVG_TRASH,
} from './markerPanel/markerCard.js';

const SVG_CHEVRON = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg>`;
const SVG_PIN = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>`;

function el(tag, cls = '', attrs = {}) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  Object.entries(attrs).forEach(([k, v]) => e.setAttribute(k, v));
  return e;
}

function buildDropdown() {
  const wrapper = el('div', '', { id: 'rs-marker-dropdown' });
  wrapper.innerHTML = `
    <div class="rs-dropdown-header" id="rs-dropdown-header">
      <div class="rs-header-content">
        <span class="rs-header-icon">${SVG_PIN}</span>
        <div class="rs-header-info">
          <span class="rs-header-title">마커 정보</span>
          <span class="rs-header-count" id="rs-header-count">0개</span>
        </div>
      </div>
      <div class="rs-header-actions">
        <button class="rs-header-btn rs-clear-all-btn" id="rs-clear-all" title="전체 지우기">
          ${SVG_TRASH}
        </button>
        <button class="rs-header-btn rs-toggle-btn" id="rs-toggle-btn">
          ${SVG_CHEVRON}
        </button>
      </div>
    </div>

    <div class="rs-dropdown-content" id="rs-dropdown-content">
      <div class="rs-cards-container" id="rs-cards-container"></div>
    </div>
  `;
  return wrapper;
}

/**
 * @param {{ mapContainerEl: HTMLElement }} options
 * @returns {{ destroy: Function }}
 */
export function initRightSidebarMarkerPanel({ mapContainerEl }) {
  const dropdown   = buildDropdown();
  const header     = dropdown.querySelector('#rs-dropdown-header');
  const container  = dropdown.querySelector('#rs-cards-container');
  const headerCount = dropdown.querySelector('#rs-header-count');
  const clearBtn   = dropdown.querySelector('#rs-clear-all');
  const toggleBtn  = dropdown.querySelector('#rs-toggle-btn');

  mapContainerEl.insertAdjacentElement('afterend', dropdown);

  let isOpen = true;
  dropdown.classList.add('rs-open');

  function toggleDropdown() {
    isOpen = !isOpen;
    dropdown.classList.toggle('rs-open', isOpen);
    toggleBtn.classList.toggle('rs-chevron-rotated', isOpen);
  }

  header.addEventListener('click', e => {
    if (e.target.closest('.rs-header-btn')) return;
    toggleDropdown();
  });

  toggleBtn.addEventListener('click', e => {
    e.stopPropagation();
    toggleDropdown();
  });

  const cards = new Map();
  let seq = 0;

  function updateHeader() {
    const n = cards.size;
    headerCount.textContent = `${n}개`;
    clearBtn.style.display = n > 0 ? '' : 'none';
    dropdown.classList.toggle('rs-has-markers', n > 0);
  }

  function removeCard(markerId) {
    const entry = cards.get(markerId);
    if (!entry) return;
    cards.delete(markerId);
    removeCardAnimated(entry.card, updateHeader);
    updateHeader();
  }

  clearBtn.addEventListener('click', e => {
    e.stopPropagation();
    const mapIframe = document.querySelector('iframe');
    if (mapIframe) {
      mapIframe.contentWindow.postMessage({ type: 'DELETE_ALL_MARKERS' }, '*');
    }
    [...cards.keys()].forEach(id => removeCard(id));
  });

  function onMessage(e) {
    const { type, markerId, payload } = e.data ?? {};
    if (!type?.startsWith('MI_') || !markerId) return;

    if (type === 'MI_LOADING') {
      if (cards.has(markerId)) {
        cards.get(markerId).ctrl.loading();
        return;
      }
      seq++;
      const card = buildCard(markerId);
      const ctrl = createCardCtrl(card);

      card.querySelector('.rs-card-seq').textContent = `#${seq}`;
      card.querySelector('.rs-card-close-btn').addEventListener('click', () => removeCard(markerId));

      cards.set(markerId, { card, ctrl });
      container.prepend(card);
      ctrl.loading();
      updateHeader();
      container.scrollTop = 0;

    } else if (type === 'MI_DATA') {
      cards.get(markerId)?.ctrl.data(payload);
    } else if (type === 'MI_ERROR') {
      cards.get(markerId)?.ctrl.error();
    } else if (type === 'MI_REMOVE') {
      removeCard(markerId);
    }
  }

  window.addEventListener('message', onMessage);
  updateHeader();

  return {
    destroy() {
      window.removeEventListener('message', onMessage);
      dropdown.remove();
    },
  };
}
