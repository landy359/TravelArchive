/**
 * notifications.js  —  알림 API
 */

import { authFetch } from './client.js';

export async function fetchNotifications() {
  try {
    const res = await authFetch('/api/notifications');
    if (!res.ok) return [];
    const data = await res.json();
    return data.notifications || [];
  } catch (error) {
    console.error('API Error (fetchNotifications):', error);
    return [];
  }
}

export async function acceptNotification(notificationId) {
  try {
    const res = await authFetch(`/api/notifications/${notificationId}/accept`, { method: 'POST' });
    return await res.json();
  } catch (error) {
    console.error('API Error (acceptNotification):', error);
    throw error;
  }
}

export async function dismissNotification(notificationId) {
  try {
    const res = await authFetch(`/api/notifications/${notificationId}/dismiss`, { method: 'POST' });
    return await res.json();
  } catch (error) {
    console.error('API Error (dismissNotification):', error);
    throw error;
  }
}

export async function clearViewedNotifications() {
  try {
    const res = await authFetch('/api/notifications/clear-viewed', { method: 'POST' });
    return await res.json();
  } catch (error) {
    console.error('API Error (clearViewedNotifications):', error);
    throw error;
  }
}
