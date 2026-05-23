/**
 * trip-card widget
 *
 * 홈 대시보드의 여행 카드.
 *
 * Usage:
 *   import { mount } from '@/widgets/trip-card';
 *   const card = mount(track, {
 *     trip: { trip_id, title, destination, start_date, color },
 *     idx: 0,
 *     onSelect: (tripId) => ...,
 *     onDelete: (tripId) => ...,
 *   });
 *   card.destroy();
 */

import templateHtml from './trip-card.html?raw';
import './trip-card.css';

const PALETTE = [
  { bg: 'rgba(254, 243, 199, 0.72)', accent: '#d97706', icon: '#f59e0b' },
  { bg: 'rgba(243, 232, 255, 0.72)', accent: '#7c3aed', icon: '#a78bfa' },
  { bg: 'rgba(255, 228, 230, 0.72)', accent: '#e11d48', icon: '#fb7185' },
  { bg: 'rgba(224, 242, 254, 0.72)', accent: '#0284c7', icon: '#38bdf8' },
];

const MAP_ICON = `<svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6"></polygon><line x1="8" y1="2" x2="8" y2="18"></line><line x1="16" y1="6" x2="16" y2="22"></line></svg>`;

function buildEl(trip, idx) {
  const tpl = document.createElement('template');
  tpl.innerHTML = templateHtml.trim();
  const el = tpl.content.firstElementChild;

  const p   = PALETTE[idx % PALETTE.length];
  const bg  = trip.color ? `${trip.color}33` : p.bg;
  const acc = trip.color || p.accent;
  el.dataset.tripId = trip.trip_id;
  el.style.setProperty('--i', idx);
  el.style.setProperty('--card-bg', bg);
  el.style.setProperty('--card-accent', acc);
  el.style.setProperty('--card-icon', acc);

  el.querySelector('[data-icon]').innerHTML = MAP_ICON;
  el.querySelector('[data-title]').textContent = trip.title || '이름 없는 여행';

  if (trip.destination) {
    const badge = el.querySelector('[data-badge]');
    badge.textContent = trip.destination;
    badge.hidden = false;
  }

  const dateLabel = (trip.start_date || '').slice(0, 7).replace(/-/g, '.');
  if (dateLabel) {
    const dateEl = el.querySelector('[data-date]');
    dateEl.textContent = dateLabel;
    dateEl.hidden = false;
  }

  const deleteBtn = el.querySelector('[data-delete]');
  deleteBtn.dataset.deleteTripId = trip.trip_id;

  return el;
}

/**
 * @param {HTMLElement} parent  마운트 대상 (.trip-card-track 등)
 * @param {{ trip: object, idx: number, onSelect?: Function, onDelete?: Function }} props
 */
export function mount(parent, { trip, idx = 0, onSelect, onDelete } = {}) {
  const el = buildEl(trip, idx);
  parent.appendChild(el);

  const deleteBtn = el.querySelector('[data-delete]');
  deleteBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    onDelete?.(trip.trip_id, trip);
  });

  el.addEventListener('click', (e) => {
    if (e.target.closest('[data-delete]')) return;
    onSelect?.(trip.trip_id, trip);
  });

  return {
    el,
    destroy() { el.remove(); },
  };
}

/** 외부에서 카드 마크업만 필요한 경우 (예: innerHTML join) */
export function renderHTML(trip, idx) {
  return buildEl(trip, idx).outerHTML;
}
