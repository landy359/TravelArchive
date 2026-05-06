/**
 * planner.js  —  메모 + 일정(plan) + 월간 표시(indicators) API
 */

import { authFetch } from './client.js';

export async function saveMemo(sessionId, memoContent, dateKey) {
  try {
    const res = await authFetch(`/api/sessions/${sessionId}/memo?date=${dateKey}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ memo: memoContent }),
    });
    return await res.json();
  } catch (error) {
    console.error('API Error (saveMemo):', error);
    throw error;
  }
}

export async function fetchMemo(sessionId, dateKey) {
  try {
    if (!sessionId || sessionId === 'default') return { memo: '' };
    const res = await authFetch(`/api/sessions/${sessionId}/memo?date=${dateKey}`);
    if (!res.ok) return { memo: '' };
    return await res.json();
  } catch {
    return { memo: '' };
  }
}

export async function updateSchedule(sessionId, planData, dateKey) {
  try {
    const res = await authFetch(`/api/sessions/${sessionId}/plan?date=${dateKey}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ plan: planData }),
    });
    return await res.json();
  } catch (error) {
    console.error('API Error (updateSchedule):', error);
    throw error;
  }
}

export async function fetchSchedule(sessionId, dateKey) {
  try {
    if (!sessionId || sessionId === 'default') return { plan: [] };
    const res = await authFetch(`/api/sessions/${sessionId}/plan?date=${dateKey}`);
    if (!res.ok) return { plan: [] };
    return await res.json();
  } catch {
    return { plan: [] };
  }
}

export async function fetchMonthDataIndicators(sessionId, year, month) {
  try {
    if (!sessionId || sessionId === 'default') return [];
    const res = await authFetch(`/api/sessions/${sessionId}/indicators?year=${year}&month=${month}`);
    if (!res.ok) return [];
    return await res.json();
  } catch {
    return [];
  }
}
