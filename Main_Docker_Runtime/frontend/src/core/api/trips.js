/**
 * trips.js  —  여행(Trip) CRUD + 여행 기간(trip_range)
 */

import { authFetch } from './client.js';

export async function fetchTripList() {
  try {
    const res = await authFetch('/api/trips');
    if (!res.ok) return [];
    const data = await res.json();
    return data.trips || [];
  } catch (error) {
    console.error('API Error (fetchTripList):', error);
    return [];
  }
}

export async function createTrip(data) {
  try {
    const res = await authFetch('/api/trips', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return await res.json();
  } catch (error) {
    console.error('API Error (createTrip):', error);
    throw error;
  }
}

export async function updateTrip(tripId, data) {
  try {
    const res = await authFetch(`/api/trips/${tripId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return await res.json();
  } catch (error) {
    console.error('API Error (updateTrip):', error);
    throw error;
  }
}

export async function deleteTrip(tripId) {
  try {
    const res = await authFetch(`/api/trips/${tripId}`, { method: 'DELETE' });
    return await res.json();
  } catch (error) {
    console.error('API Error (deleteTrip):', error);
    throw error;
  }
}

/** 하위 호환 별칭 */
export async function fetchPlanList() {
  return fetchTripList();
}

/** 여행 기간 (날짜 범위) 저장 */
export async function saveTripRange(sessionId, ranges) {
  try {
    const res = await authFetch(`/api/sessions/${sessionId}/trip_range`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ranges }),
    });
    return await res.json();
  } catch (error) {
    console.error('API Error (saveTripRange):', error);
  }
}

export async function resetTripPlan(tripId) {
  const res = await authFetch(`/api/trips/${tripId}/reset`, { method: 'POST' });
  if (!res.ok) throw new Error('reset 실패');
  return res.json();
}

export async function fetchTripRange(sessionId) {
  try {
    if (!sessionId || sessionId === 'default') return { ranges: [] };
    // 시나리오4: 임시 세션은 인증 없이 전용 엔드포인트 사용
    if (sessionId.startsWith('tmp_')) {
      const res = await fetch(`/api/temp/${encodeURIComponent(sessionId)}/trip_range`);
      if (!res.ok) return { ranges: [] };
      return await res.json();
    }
    const res = await authFetch(`/api/sessions/${sessionId}/trip_range`);
    if (!res.ok) return { ranges: [] };
    return await res.json();
  } catch {
    return { ranges: [] };
  }
}

export async function saveCalendarDate(sessionId, dateStr) {
  try {
    await authFetch(`/api/sessions/${sessionId}/calendar_date`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ date: dateStr }),
    });
  } catch { /* silent */ }
}
