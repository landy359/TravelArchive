/**
 * schedule.js
 */

import { renderTemplate } from './utils.js';

export const ScheduleManager = {
  render(container) {
    if (!container) return;
    container.innerHTML = renderTemplate('schedule');
  }
};
