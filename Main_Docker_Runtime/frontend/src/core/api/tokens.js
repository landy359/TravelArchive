/**
 * tokens.js  —  TokenManager (localStorage 기반 인증 토큰/사용자 정보)
 *
 * 클라이언트 측 인증 상태 단일 진실 공급원.
 * JWT exp 검사로 만료된 토큰 자동 정리.
 */

export const TokenManager = {
  _keys: {
    access:   'ta_access_token',
    refresh:  'ta_refresh_token',
    userId:   'ta_user_id',
    userType: 'ta_user_type',
    nickname: 'ta_nickname',
    email:    'ta_email',
  },

  setTokens(accessToken, refreshToken) {
    localStorage.setItem(this._keys.access, accessToken);
    localStorage.setItem(this._keys.refresh, refreshToken);
  },

  setUserInfo({ userId, userType, nickname, email } = {}) {
    if (userId   !== undefined) localStorage.setItem(this._keys.userId,   userId);
    if (userType !== undefined) localStorage.setItem(this._keys.userType, userType);
    if (nickname !== undefined) localStorage.setItem(this._keys.nickname, nickname || '');
    if (email    !== undefined) localStorage.setItem(this._keys.email,    email || '');
  },

  getAccessToken()  { return localStorage.getItem(this._keys.access); },
  getRefreshToken() { return localStorage.getItem(this._keys.refresh); },
  getUserId()       { return localStorage.getItem(this._keys.userId); },
  getUserType()     { return localStorage.getItem(this._keys.userType); },
  getNickname()     { return localStorage.getItem(this._keys.nickname) || '사용자'; },
  getEmail()        { return localStorage.getItem(this._keys.email) || ''; },

  /**
   * 토큰 존재 + JWT exp 미만료인 경우만 true.
   * 만료 시 localStorage 자동 초기화.
   */
  isLoggedIn() {
    const token = localStorage.getItem(this._keys.access);
    if (!token) return false;
    try {
      const payload = JSON.parse(atob(token.split('.')[1]));
      if (payload.exp && Date.now() / 1000 > payload.exp) {
        this.clearAll();
        return false;
      }
    } catch {
      this.clearAll();
      return false;
    }
    return true;
  },

  isMember() {
    if (!this.isLoggedIn()) return false;
    return localStorage.getItem(this._keys.userType) === 'MEM';
  },

  clearAll() {
    Object.values(this._keys).forEach(k => localStorage.removeItem(k));
  },
};
