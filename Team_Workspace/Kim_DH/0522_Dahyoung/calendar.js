/**
 * calendar.js
 * Manages the interactive calendar component with original styling.
 */

import { renderTemplate, getSessionIdFromHash } from './utils.js';
import { BackendHooks } from './api.js';
import { eventBus, EVENTS } from './core/event-bus.js';

let currentViewDate = new Date(); 
let selectedDate = new Date(); // Focus date (Left Click)
let tripRanges = []; // Array of {start: Date, end: Date}
let rangeSelectionStart = null; // Temporary start for right-click range selection
let referenceTodayDate = new Date();

const isSameDay = (d1, d2) => 
  d1 && d2 &&
  d1.getFullYear() === d2.getFullYear() && 
  d1.getMonth() === d2.getMonth() && 
  d1.getDate() === d2.getDate();

const formatDate = (date) => `${date.getFullYear()}-${date.getMonth()+1}-${date.getDate()}`;

const makeLocalDate = (year, month, day) => {
  const parsed = new Date(year, month - 1, day);
  parsed.setHours(0, 0, 0, 0);
  if (
    parsed.getFullYear() !== year ||
    parsed.getMonth() !== month - 1 ||
    parsed.getDate() !== day
  ) {
    return null;
  }
  return parsed;
};

const parseTripDate = (value) => {
  if (value instanceof Date) {
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return null;
    parsed.setHours(0, 0, 0, 0);
    return parsed;
  }

  if (typeof value !== 'string') return null;

  const text = value.trim();
  let match = text.match(/^(\d{2})(\d{2})(\d{2})$/);
  if (match) {
    return makeLocalDate(2000 + Number(match[1]), Number(match[2]), Number(match[3]));
  }

  match = text.match(/^(\d{4})(\d{2})(\d{2})$/);
  if (match) {
    return makeLocalDate(Number(match[1]), Number(match[2]), Number(match[3]));
  }

  match = text.match(/^(\d{4})[-./](\d{1,2})[-./](\d{1,2})$/);
  if (match) {
    return makeLocalDate(Number(match[1]), Number(match[2]), Number(match[3]));
  }

  return null;
};

const normalizeTripRanges = (ranges) => {
  if (!Array.isArray(ranges) || ranges.length === 0) return [];

  const normalized = [];
  const addRange = (startValue, endValue = startValue) => {
    const startDate = parseTripDate(startValue);
    const endDate = parseTripDate(endValue);
    if (!startDate || !endDate) return;

    const start = new Date(Math.min(startDate, endDate));
    const end = new Date(Math.max(startDate, endDate));
    normalized.push({ start, end });
  };

  if (!Array.isArray(ranges[0]) && typeof ranges[0] !== 'object') {
    addRange(ranges[0], ranges[1] || ranges[0]);
    return normalized;
  }

  ranges.forEach((range) => {
    if (Array.isArray(range)) {
      addRange(range[0], range[1] || range[0]);
      return;
    }

    if (range && typeof range === 'object') {
      addRange(range.start, range.end || range.start);
    }
  });

  return normalized;
};

export const CalendarManager = {
  onDateSelect: null,

  init(todayDate) {
    referenceTodayDate = new Date(todayDate);
    currentViewDate = new Date(todayDate);
    selectedDate = new Date(todayDate);
    selectedDate.setHours(0, 0, 0, 0);
  },

  async render(container) {
    if (!container) return;
    this.container = container;
    this.container.innerHTML = renderTemplate('calendar');

    // 버튼 바인딩은 render() 시 한 번만 수행 — updateUI() 매 호출마다 재바인딩하지 않음
    const prevBtn = document.getElementById('prevMonthBtn');
    const nextBtn = document.getElementById('nextMonthBtn');
    const todayBtn = document.getElementById('todayBtn');
    if (prevBtn) prevBtn.onclick = (e) => { e.stopPropagation(); currentViewDate.setMonth(currentViewDate.getMonth() - 1); this.updateUI(); };
    if (nextBtn) nextBtn.onclick = (e) => { e.stopPropagation(); currentViewDate.setMonth(currentViewDate.getMonth() + 1); this.updateUI(); };
    if (todayBtn) todayBtn.onclick = async (e) => { e.stopPropagation(); await this.setSelectedDate(new Date(referenceTodayDate)); };

    await this.updateUI(true);
  },

  async setSelectedDate(date) {
    selectedDate = new Date(date);
    selectedDate.setHours(0, 0, 0, 0);
    currentViewDate = new Date(date);
    await this.updateUI();
    // Emit event for other modules (memo, schedule managers)
    eventBus.emit(EVENTS.CALENDAR_DATE_SELECTED, { date: selectedDate, sessionId: getSessionIdFromHash() });
    // Keep backwards-compatible callback for existing code
    if (this.onDateSelect) this.onDateSelect(selectedDate);
  },

  getSelectedDate() {
    return selectedDate;
  },

  async refreshDots() {
    await this.updateUI();
  },

  async loadTripRange(sessionId) {
    if (!sessionId || sessionId === 'default') {
        tripRanges = [];
        rangeSelectionStart = null;
        await this.updateUI();
        return;
    }
    const data = await BackendHooks.fetchTripRange(sessionId);
    tripRanges = normalizeTripRanges(data.ranges || []);
    rangeSelectionStart = null;
    await this.updateUI();
  },

  async saveRanges() {
    const sessionId = getSessionIdFromHash();
    if (sessionId === 'default') return;
    const rangesToSave = tripRanges.map(r => ({
        start: formatDate(r.start),
        end: formatDate(r.end)
    }));
    await BackendHooks.saveTripRange(sessionId, rangesToSave);
  },

  async updateUI(forceFullUpdate = false) {
    const titleEl = document.getElementById('calendarTitle');
    const daysContainer = document.getElementById('calendarDays');

    if (!titleEl || !daysContainer) {
        if (this.container) {
            return this.render(this.container);
        }
        return;
    }

    const year = currentViewDate.getFullYear();
    const month = currentViewDate.getMonth();
    titleEl.textContent = `${year}년 ${month + 1}월`;
    
    const fragment = document.createDocumentFragment();
    const firstDayOfMonth = new Date(year, month, 1).getDay();
    const lastDateOfMonth = new Date(year, month + 1, 0).getDate();
    const lastDateOfPrevMonth = new Date(year, month, 0).getDate();

    const createDaySpan = (date, isCurrentMonth, opacity = '1') => {
        const span = document.createElement('span');
        span.textContent = date;
        span.style.opacity = opacity;
        span.style.position = 'relative';
        span.style.cursor = 'pointer';

        let dYear = year, dMonth = month;
        if (!isCurrentMonth) {
            const d = date > 15 ? new Date(year, month, 0) : new Date(year, month + 1, 1);
            dYear = d.getFullYear(); dMonth = d.getMonth();
        }
        
        const targetDate = new Date(dYear, dMonth, date);
        targetDate.setHours(0, 0, 0, 0);

        // Check if in any range
        const isInTripRange = tripRanges.some(r => targetDate >= r.start && targetDate <= r.end);
        const isSelectionStart = rangeSelectionStart && isSameDay(targetDate, rangeSelectionStart);
        const isSelectedFocus = isSameDay(targetDate, selectedDate);

        if (isSelectedFocus) {
            span.classList.add('active'); // Dark Blue
        } else if (isInTripRange || isSelectionStart) {
            span.classList.add('range-mid'); // Light Blue
        }
        
        // Left Click: Focus & Edit
        span.onclick = async (e) => {
            e.preventDefault();
            selectedDate = new Date(targetDate);
            
            // Smart Jump: If clicking adjacent month day, move the view
            if (!isCurrentMonth) {
                currentViewDate = new Date(targetDate.getFullYear(), targetDate.getMonth(), 1);
            }
            
            await this.updateUI();
            if (this.onDateSelect) this.onDateSelect(selectedDate);
        };

        // Right Click: Range Management
        span.oncontextmenu = async (e) => {
            e.preventDefault();
            
            if (!rangeSelectionStart) {
                // Not in selection mode: Delete or Start
                const existingRangeIdx = tripRanges.findIndex(r => targetDate >= r.start && targetDate <= r.end);
                if (existingRangeIdx !== -1) {
                    tripRanges.splice(existingRangeIdx, 1);
                    await this.saveRanges();
                } else {
                    rangeSelectionStart = new Date(targetDate);
                }
            } else {
                // In selection mode: Cancel or Finish
                if (isSameDay(targetDate, rangeSelectionStart)) {
                    rangeSelectionStart = null; // Cancel if same day
                } else {
                    const start = new Date(Math.min(rangeSelectionStart, targetDate));
                    const end = new Date(Math.max(rangeSelectionStart, targetDate));
                    tripRanges.push({ start, end });
                    rangeSelectionStart = null;
                    await this.saveRanges();
                }
            }

            // Smart Jump for right click too
            if (!isCurrentMonth) {
                currentViewDate = new Date(targetDate.getFullYear(), targetDate.getMonth(), 1);
            }
            
            await this.updateUI();
        };

        return span;
    };

    for (let i = firstDayOfMonth; i > 0; i--) fragment.appendChild(createDaySpan(lastDateOfPrevMonth - i + 1, false, '0.3'));
    for (let i = 1; i <= lastDateOfMonth; i++) fragment.appendChild(createDaySpan(i, true));
    const dayCount = firstDayOfMonth + lastDateOfMonth;
    const finalSlots = dayCount > 35 ? 42 : 35;
    for (let i = 1; i <= (finalSlots - dayCount); i++) fragment.appendChild(createDaySpan(i, false, '0.3'));

    daysContainer.innerHTML = '';
    daysContainer.appendChild(fragment);
  }
};
