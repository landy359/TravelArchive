/**
 * users.js  —  사용자 검색 / 프로필 / 스타일 / 계정정보 API
 */

import { authFetch } from './client.js';

export async function searchUsers(q) {
  try {
    const res = await authFetch(`/api/users/search?q=${encodeURIComponent(q)}`);
    if (!res.ok) return [];
    const data = await res.json();
    return data.users || [];
  } catch (error) {
    console.error('API Error (searchUsers):', error);
    return [];
  }
}

export async function fetchAccountInfo() {
  try {
    const res = await authFetch('/api/account');
    return await res.json();
  } catch {
    return { status: 'guest', user_id: null };
  }
}

export async function getMyProfile() {
  try {
    const res = await authFetch('/api/auth/me');
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

/** 사용자 프로필 저장 (닉네임, 소개, 이메일, 추가 연락수단) */
export async function saveUserProfile(data) {
  try {
    const res = await authFetch('/api/user/profile', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!res.ok) throw { status: res.status, detail: (await res.json()).detail };
    return await res.json();
  } catch (error) {
    console.error('API Error (saveUserProfile):', error);
    throw error;
  }
}

/** AI 스타일/말투 설정 저장 */
export async function saveUserStyle(data) {
  try {
    const res = await authFetch('/api/user/style', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!res.ok) throw { status: res.status, detail: (await res.json()).detail };
    return await res.json();
  } catch (error) {
    console.error('API Error (saveUserStyle):', error);
    throw error;
  }
}

/** 여행 스타일 설정 저장 */
export async function saveTravelPreferences(data) {
  try {
    const res = await authFetch('/api/user/travel', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!res.ok) throw { status: res.status, detail: (await res.json()).detail };
    return await res.json();
  } catch (error) {
    console.error('API Error (saveTravelPreferences):', error);
    throw error;
  }
}
