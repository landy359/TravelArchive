/**
 * sidebar-tabs.js
 * Handles tab switching between sessions and calendar views.
 */

import { CalendarManager } from '../calendar.js';
import { eventBus, EVENTS } from '../core/event-bus.js';

export const SidebarTabs = {
  initTabs(elements) {
    const { tabSessions, tabCalendar, sessionView, calendarView, sessionHeaderControls, calendarHeaderControls } = elements;
    if (!tabSessions || !tabCalendar) return;

    const switchTab = (activeTab, inactiveTab, showView, hideView, showHeader, hideHeader) => {
      activeTab.classList.add('active');
      inactiveTab.classList.remove('active');
      showView.style.display = 'flex';
      hideView.style.display = 'none';
      showHeader.style.display = 'block';
      hideHeader.style.display = 'none';

      if (activeTab === tabCalendar) {
        setTimeout(() => {
          if (CalendarManager && CalendarManager.updateUI) {
            CalendarManager.updateUI();
          }
          eventBus.emit(EVENTS.SIDEBAR_TAB_CHANGED, { tab: 'calendar' });
        }, 0);
      } else {
        eventBus.emit(EVENTS.SIDEBAR_TAB_CHANGED, { tab: 'sessions' });
      }
    };

    tabSessions.addEventListener('click', () => switchTab(tabSessions, tabCalendar, sessionView, calendarView, sessionHeaderControls, calendarHeaderControls));
    tabCalendar.addEventListener('click', () => switchTab(tabCalendar, tabSessions, calendarView, sessionView, calendarHeaderControls, sessionHeaderControls));

    CalendarManager.onDateSelect = (date) => {
        eventBus.emit(EVENTS.CALENDAR_DATE_SELECTED, { date });
    };

    if (tabSessions.classList.contains('active')) {
      sessionView.style.display = 'flex';
      calendarView.style.display = 'none';
      sessionHeaderControls.style.display = 'block';
      calendarHeaderControls.style.display = 'none';
    } else {
      calendarView.style.display = 'flex';
      sessionView.style.display = 'none';
      calendarHeaderControls.style.display = 'block';
      sessionHeaderControls.style.display = 'none';
      setTimeout(() => {
          if (CalendarManager && CalendarManager.updateUI) {
            CalendarManager.updateUI();
          }
      }, 0);
    }
  },
};
