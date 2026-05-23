/**
 * event-bus.js
 * Simple pub-sub event system for inter-module communication.
 * Enables loose coupling between sidebar, calendar, memo, schedule, etc.
 */

class EventBus {
  constructor() {
    this.events = {};
  }

  /**
   * Subscribe to an event
   * @param {string} eventName - Event name to listen for
   * @param {Function} callback - Handler function
   * @returns {Function} Unsubscribe function
   */
  on(eventName, callback) {
    if (!this.events[eventName]) {
      this.events[eventName] = [];
    }
    this.events[eventName].push(callback);

    // Return unsubscribe function
    return () => {
      this.events[eventName] = this.events[eventName].filter(cb => cb !== callback);
    };
  }

  /**
   * Subscribe to an event once, then auto-unsubscribe
   * @param {string} eventName - Event name to listen for
   * @param {Function} callback - Handler function
   */
  once(eventName, callback) {
    const unsubscribe = this.on(eventName, (data) => {
      callback(data);
      unsubscribe();
    });
  }

  /**
   * Emit an event
   * @param {string} eventName - Event name to emit
   * @param {*} data - Data to pass to listeners
   */
  emit(eventName, data) {
    if (!this.events[eventName]) return;
    this.events[eventName].forEach(callback => {
      try {
        callback(data);
      } catch (e) {
        console.error(`Error in event handler for ${eventName}:`, e);
      }
    });
  }

  /**
   * Remove all listeners for an event
   * @param {string} eventName - Event name to clear
   */
  off(eventName) {
    if (eventName) {
      delete this.events[eventName];
    } else {
      this.events = {};
    }
  }
}

// Export singleton instance
export const eventBus = new EventBus();

// Common event names used throughout the app
export const EVENTS = {
  CALENDAR_DATE_SELECTED: 'calendar:dateSelected',
  SIDEBAR_TAB_CHANGED: 'sidebar:tabChanged',
  SIDEBAR_OPENED: 'sidebar:opened',
  SIDEBAR_CLOSED: 'sidebar:closed',
};
