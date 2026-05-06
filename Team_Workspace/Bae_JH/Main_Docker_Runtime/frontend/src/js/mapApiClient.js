/**
 * mapApiClient.js
 *
 * Travel Archive 백엔드 API 연결 함수들.
 * 마커 추가/삭제/조회 등을 담당합니다.
 *
 * @module mapApiClient
 */

// ─────────────────────────────────────────────────────────────────
//  기본 설정
// ─────────────────────────────────────────────────────────────────

const API_BASE = '/api/sessions';

/**
 * 현재 세션 ID 가져오기
 */
function getSessionId() {
  return window.parent?.currentSessionId || window.currentSessionId || '';
}

/**
 * API 에러 처리
 */
function handleError(error, context = '') {
  console.error(`[Map API Error] ${context}:`, error);
  return null;
}

// ─────────────────────────────────────────────────────────────────
//  마커 API
// ─────────────────────────────────────────────────────────────────

/**
 * 마커 추가 API
 * @param {string} markerId - 마커 ID
 * @param {number} lat - 위도
 * @param {number} lng - 경도
 * @param {object} metadata - 추가 메타데이터 (도로명, 지번 등)
 * @returns {Promise<object>} API 응답
 */
export async function addMarker(markerId, lat, lng, metadata = {}) {
  try {
    const sid = getSessionId();
    if (!sid) throw new Error('Session ID not found');

    const response = await fetch(`${API_BASE}/${encodeURIComponent(sid)}/map/markers/add`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        marker_id: markerId,
        lat,
        lng,
        ...metadata,
      }),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    return handleError(error, 'addMarker');
  }
}

/**
 * 마커 삭제 API
 * @param {string} markerId - 마커 ID
 * @returns {Promise<object>} API 응답
 */
export async function deleteMarker(markerId) {
  try {
    const sid = getSessionId();
    if (!sid) throw new Error('Session ID not found');

    const response = await fetch(
      `${API_BASE}/${encodeURIComponent(sid)}/map/markers/${encodeURIComponent(markerId)}`,
      { method: 'DELETE' }
    );

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    return handleError(error, 'deleteMarker');
  }
}

/**
 * 마커 목록 조회 API
 * @returns {Promise<array>} 마커 배열
 */
export async function getMarkers() {
  try {
    const sid = getSessionId();
    if (!sid) throw new Error('Session ID not found');

    const response = await fetch(`${API_BASE}/${encodeURIComponent(sid)}/map/markers`);

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    return data.markers || [];
  } catch (error) {
    return handleError(error, 'getMarkers') || [];
  }
}

/**
 * 마커 정보 조회 API
 * @param {string} markerId - 마커 ID
 * @returns {Promise<object>} 마커 정보
 */
export async function getMarker(markerId) {
  try {
    const sid = getSessionId();
    if (!sid) throw new Error('Session ID not found');

    const response = await fetch(
      `${API_BASE}/${encodeURIComponent(sid)}/map/markers/${encodeURIComponent(markerId)}`
    );

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    return handleError(error, 'getMarker');
  }
}

/**
 * 마커 정보 업데이트 API
 * @param {string} markerId - 마커 ID
 * @param {object} data - 업데이트할 데이터
 * @returns {Promise<object>} API 응답
 */
export async function updateMarker(markerId, data) {
  try {
    const sid = getSessionId();
    if (!sid) throw new Error('Session ID not found');

    const response = await fetch(
      `${API_BASE}/${encodeURIComponent(sid)}/map/markers/${encodeURIComponent(markerId)}`,
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      }
    );

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    return handleError(error, 'updateMarker');
  }
}

/**
 * 모든 마커 삭제 API
 * @returns {Promise<object>} API 응답
 */
export async function deleteAllMarkers() {
  try {
    const sid = getSessionId();
    if (!sid) throw new Error('Session ID not found');

    const response = await fetch(
      `${API_BASE}/${encodeURIComponent(sid)}/map/markers/all`,
      { method: 'DELETE' }
    );

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    return handleError(error, 'deleteAllMarkers');
  }
}

// ─────────────────────────────────────────────────────────────────
//  경로 API
// ─────────────────────────────────────────────────────────────────

/**
 * 경로 저장 API
 * @param {array} markerIds - 마커 ID 배열 (순서)
 * @returns {Promise<object>} API 응답
 */
export async function saveRoute(markerIds) {
  try {
    const sid = getSessionId();
    if (!sid) throw new Error('Session ID not found');

    const response = await fetch(`${API_BASE}/${encodeURIComponent(sid)}/map/routes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ marker_ids: markerIds }),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    return handleError(error, 'saveRoute');
  }
}

/**
 * 경로 조회 API
 * @returns {Promise<object>} 경로 정보
 */
export async function getRoute() {
  try {
    const sid = getSessionId();
    if (!sid) throw new Error('Session ID not found');

    const response = await fetch(`${API_BASE}/${encodeURIComponent(sid)}/map/routes`);

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    return handleError(error, 'getRoute');
  }
}

// ─────────────────────────────────────────────────────────────────
//  유틸리티
// ─────────────────────────────────────────────────────────────────

/**
 * 일괄 마커 업로드
 * @param {array} markers - [{markerId, lat, lng, ...metadata}, ...]
 * @returns {Promise<array>} 결과 배열
 */
export async function bulkUploadMarkers(markers) {
  try {
    const results = await Promise.all(
      markers.map(m => addMarker(m.markerId, m.lat, m.lng, m))
    );
    return results.filter(r => r !== null);
  } catch (error) {
    return handleError(error, 'bulkUploadMarkers') || [];
  }
}

/**
 * 마커와 경로 한 번에 저장
 * @param {array} markers - 마커 배열
 * @returns {Promise<object>} API 응답
 */
export async function saveMapSession(markers) {
  try {
    const sid = getSessionId();
    if (!sid) throw new Error('Session ID not found');

    // 마커 업로드
    const uploadResults = await bulkUploadMarkers(markers);

    // 경로 저장
    const markerIds = markers.map(m => m.markerId);
    const routeResult = await saveRoute(markerIds);

    return {
      markers: uploadResults,
      route: routeResult,
      success: uploadResults.length === markers.length,
    };
  } catch (error) {
    return handleError(error, 'saveMapSession');
  }
}
