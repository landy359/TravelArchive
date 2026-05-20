/**
 * markers.js  —  지도 마커 CRUD API
 */

import { authFetch } from './client.js';

export async function saveMapMarkers(sessionId, markers) {
  try {
    const res = await authFetch(`/api/sessions/${sessionId}/map/markers`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ markers }),
    });
    return await res.json();
  } catch (error) {
    console.error('API Error (saveMapMarkers):', error);
  }
}

export async function fetchMapMarkers(sessionId) {
  try {
    const res = await authFetch(`/api/sessions/${sessionId}/map/markers`);
    if (!res.ok) return { markers: [] };
    return await res.json();
  } catch (error) {
    console.error('API Error (fetchMapMarkers):', error);
    return { markers: [] };
  }
}

export async function addMapMarker(sessionId, markerId, lat, lng, title = '') {
  try {
    const res = await authFetch(`/api/sessions/${sessionId}/map/markers/add`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ marker_id: markerId, lat, lng, title }),
    });
    return await res.json();
  } catch (error) {
    console.error('API Error (addMapMarker):', error);
  }
}

export async function removeMapMarker(sessionId, markerId) {
  try {
    const res = await authFetch(
      `/api/sessions/${sessionId}/map/markers/${encodeURIComponent(markerId)}`,
      { method: 'DELETE' }
    );
    return await res.json();
  } catch (error) {
    console.error('API Error (removeMapMarker):', error);
  }
}
