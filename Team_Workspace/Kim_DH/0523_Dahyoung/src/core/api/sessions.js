/**
 * sessions.js  —  세션 라이프사이클 / 메타 / 공유 API
 */

import { authFetch } from './client.js';
import { TokenManager } from './tokens.js';

export async function fetchSessionList(tripId = null) {
  try {
    const params = new URLSearchParams();
    if (tripId) params.set('trip_id', tripId);
    const query = params.toString();
    const res = await authFetch(`/api/sessions${query ? '?' + query : ''}`);
    if (!res.ok) return [];
    const data = await res.json();
    return Array.isArray(data) ? data : (data.sessions || []);
  } catch (error) {
    console.error('API Error (fetchSessionList):', error);
    return [];
  }
}

export async function createSession(firstMessage, tripId = null) {
  try {
    const body = { first_message: firstMessage };
    if (tripId) body.trip_id = tripId;
    const res = await authFetch('/api/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    return await res.json();
  } catch (error) {
    console.error('API Error (createSession):', error);
    throw error;
  }
}

export async function deleteSession(sessionId) {
  try {
    const res = await authFetch(`/api/sessions/${sessionId}`, { method: 'DELETE' });
    return await res.json();
  } catch (error) {
    console.error('API Error (deleteSession):', error);
    throw error;
  }
}

export async function leaveSession(sessionId) {
  try {
    const res = await authFetch(`/api/sessions/${sessionId}/leave`, { method: 'POST' });
    return await res.json();
  } catch (error) {
    console.error('API Error (leaveSession):', error);
    throw error;
  }
}

export async function convertToPersonal(sessionId) {
  try {
    const res = await authFetch(`/api/sessions/${sessionId}/convert-personal`, { method: 'POST' });
    return await res.json();
  } catch (error) {
    console.error('API Error (convertToPersonal):', error);
    throw error;
  }
}

export async function updateSessionColor(sessionId, color) {
  try {
    const res = await authFetch(`/api/sessions/${sessionId}/color`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ color }),
    });
    return await res.json();
  } catch (error) {
    console.error('API Error (updateSessionColor):', error);
    throw error;
  }
}

export async function updateSessionTitle(sessionId, newTitle) {
  try {
    const res = await authFetch(`/api/sessions/${sessionId}/title`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: newTitle }),
    });
    return await res.json();
  } catch (error) {
    console.error('API Error (updateSessionTitle):', error);
    throw error;
  }
}

export async function moveSessionToTrip(sessionId, tripId) {
  try {
    const res = await authFetch(`/api/sessions/${sessionId}/trip`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ trip_id: tripId || null }),
    });
    return await res.json();
  } catch (error) {
    console.error('API Error (moveSessionToTrip):', error);
    throw error;
  }
}

export async function inviteUserToSession(sessionId, searchInput) {
  try {
    const res = await authFetch(`/api/sessions/${sessionId}/invite`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user: searchInput }),
    });
    return await res.json();
  } catch (error) {
    console.error('API Error (inviteUserToSession):', error);
    throw error;
  }
}

export async function markSessionRead(sessionId) {
  try {
    await authFetch(`/api/sessions/${sessionId}/read`, { method: 'POST' });
  } catch { /* silent */ }
}

/** 페이지 언로드 시 세션 메모리 → DB 플러시 */
export function flushSessions() {
  const token = TokenManager.getAccessToken();
  if (!token) return;
  // sendBeacon은 Authorization 헤더를 보낼 수 없어 401 실패 → fetch keepalive 사용
  fetch('/api/sessions/flush', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
    body: JSON.stringify({}),
    keepalive: true,
  }).catch(() => {});
}

/**
 * 팀 채팅 SSE 구독 — 자동 재연결 포함.
 * @returns {{ close: Function }}
 */
export function subscribeToSessionEvents(sessionId, onEvent, onError) {
  let closed = false;
  let retryDelay = 2000;
  let _currentAbort = null;

  const connect = async () => {
    while (!closed) {
      const controller = new AbortController();
      _currentAbort = controller;
      try {
        const token = TokenManager.getAccessToken();
        const res = await fetch(`/api/sessions/${sessionId}/events`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
          signal: controller.signal,
        });
        if (!res.ok) throw new Error(`SSE ${res.status}`);
        retryDelay = 2000;
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buf = '';
        while (!closed) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          const parts = buf.split('\n\n');
          buf = parts.pop() ?? '';
          for (const part of parts) {
            const m = part.match(/^data: (.+)$/m);
            if (m) { try { onEvent(JSON.parse(m[1])); } catch {} }
          }
        }
      } catch (e) {
        if (e.name === 'AbortError' || closed) return;
        onError?.(e);
      }
      if (!closed) {
        await new Promise(r => setTimeout(r, retryDelay));
        retryDelay = Math.min(retryDelay * 1.5, 30000);
      }
    }
  };

  connect();
  return {
    close: () => { closed = true; _currentAbort?.abort(); },
  };
}

export async function shareChat(sessionId) {
  try {
    const res = await authFetch(`/api/sessions/${sessionId}/share`, { method: 'POST' });
    return await res.json();
  } catch (error) {
    console.error('API Error (shareChat):', error);
    throw error;
  }
}

export function blurSession(sessionId) {
  authFetch(`/api/sessions/${sessionId}/blur`, { method: 'POST' }).catch(() => {});
}

export async function openSession(sessionId) {
  try {
    await authFetch(`/api/sessions/${sessionId}/open`, { method: 'POST' });
  } catch {}
}

export async function downloadChat(sessionId) {
  try {
    const res = await authFetch(`/api/sessions/${sessionId}/download`);
    if (!res.ok) throw new Error(`다운로드 실패: ${res.status}`);
    const blob = await res.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url;
    a.download = `chat_${sessionId}.txt`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch (error) {
    console.error('API Error (downloadChat):', error);
    throw error;
  }
}
