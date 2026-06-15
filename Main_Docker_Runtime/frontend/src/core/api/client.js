/**
 * client.js  —  API 통신 기반 (auth fetch + token refresh)
 *
 * 모든 도메인 모듈이 이 파일의 authFetch 만 사용한다.
 * - 401 시 자동으로 refresh token 으로 access token 재발급
 * - 재발급 실패 시 TokenManager.clearAll() 후 401 결과 반환
 */

import { TokenManager } from './tokens.js';

/**
 * 인증 헤더 포함 fetch.
 * 401 시 refresh 시도 후 한 번 재요청.
 */
export async function authFetch(url, options = {}) {
  const token = TokenManager.getAccessToken();
  const headers = {
    ...options.headers,
    ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
  };

  let res = await fetch(url, { ...options, headers });

  if (res.status === 401 && TokenManager.getRefreshToken()) {
    const refreshed = await tryRefresh();
    if (refreshed) {
      headers['Authorization'] = `Bearer ${TokenManager.getAccessToken()}`;
      res = await fetch(url, { ...options, headers });
    }
  }
  return res;
}

/**
 * Refresh token 으로 access token 재발급.
 * 실패 시 TokenManager 초기화.
 */
export async function tryRefresh() {
  try {
    const res = await fetch('/api/auth/refresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: TokenManager.getRefreshToken() }),
    });
    if (!res.ok) { _expireSession(); return false; }
    const data = await res.json();
    if (data.access_token) {
      TokenManager.setTokens(data.access_token, TokenManager.getRefreshToken());
      return true;
    }
    _expireSession();
    return false;
  } catch {
    return false;
  }
}

/**
 * refresh 토큰이 만료/무효 → 세션 종료.
 * 토큰 정리 후 UI가 로그아웃 상태로 전환되도록 ta:logout 이벤트 발행.
 * (이게 없으면 토큰만 비고 화면은 로그인 상태로 남아 "자동 로그아웃 안 됨")
 */
function _expireSession() {
  TokenManager.clearAll();
  try {
    document.dispatchEvent(new CustomEvent('ta:logout'));
  } catch { /* document 없는 환경 무시 */ }
}
