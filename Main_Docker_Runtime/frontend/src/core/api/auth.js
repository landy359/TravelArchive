/**
 * auth.js  —  인증 / 계정 API
 */

import { authFetch } from './client.js';
import { TokenManager } from './tokens.js';

/** 자체 계정 로그인 — 성공 시 TokenManager 에 토큰/사용자정보 저장 */
export async function login(id, pw) {
  const res = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id, pw }),
  });
  const data = await res.json();
  if (!res.ok) throw { status: res.status, detail: data.detail || '로그인에 실패했습니다' };

  if (data.access_token && data.refresh_token) {
    TokenManager.setTokens(data.access_token, data.refresh_token);
    TokenManager.setUserInfo({
      userId:   data.user_id,
      userType: data.type || 'MEM',
      nickname: data.nickname,
      email:    data.email,
    });
  }
  return data;
}

/** 회원가입 */
export async function signUp(userData) {
  const res = await fetch('/api/auth/signup', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(userData),
  });
  const data = await res.json();
  if (!res.ok) throw { status: res.status, detail: data.detail || '회원가입에 실패했습니다' };
  return data;
}

/** 로그아웃 — 서버 측 refresh/access token 무효화 + 로컬 토큰 삭제 */
export async function logout() {
  const refreshToken = TokenManager.getRefreshToken();
  if (refreshToken) {
    try {
      const accessToken = TokenManager.getAccessToken();
      const headers = { 'Content-Type': 'application/json' };
      if (accessToken) headers['Authorization'] = `Bearer ${accessToken}`;
      await fetch('/api/auth/logout', {
        method: 'POST',
        headers,
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
    } catch { /* 네트워크 실패해도 로컬은 삭제 */ }
  }
  TokenManager.clearAll();
}

/** 카카오 OAuth 인가 페이지로 리다이렉트 */
export function kakaoLogin() {
  window.location.href = '/api/auth/kakao';
}

/** 계정 찾기 */
export async function findAccount() {
  const res = await fetch('/api/auth/find', { method: 'POST' });
  return await res.json();
}

/** 현재 사용자 프로필 조회 */
export async function getMyProfile() {
  try {
    const res = await authFetch('/api/auth/me');
    if (!res.ok) return null;
    return await res.json();
  } catch { return null; }
}

/** SNS 계정 연동 */
export async function linkSocialAccount(provider) {
  try {
    const res = await authFetch(`/api/auth/social/link/${provider}`, { method: 'POST' });
    return await res.json();
  } catch (error) {
    console.error(`API Error (linkSocialAccount:${provider}):`, error);
    throw error;
  }
}

/** 모든 기기 로그아웃 (refresh token 전체 무효화) */
export async function logoutAllDevices() {
  try {
    const res = await authFetch('/api/auth/logout/all', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: TokenManager.getRefreshToken() }),
    });
    TokenManager.clearAll();
    return await res.json();
  } catch (error) {
    console.error('API Error (logoutAllDevices):', error);
    TokenManager.clearAll();
    throw error;
  }
}

/** 계정 영구 삭제 */
export async function deleteAccount() {
  try {
    const res = await authFetch('/api/user/account', { method: 'DELETE' });
    if (!res.ok) throw { status: res.status, detail: (await res.json()).detail };
    return await res.json();
  } catch (error) {
    console.error('API Error (deleteAccount):', error);
    throw error;
  }
}
