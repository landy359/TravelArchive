/**
 * api.js
 * handles all backend API interactions including auth, sessions, messages, and theme preferences.
 */

/**
 * TokenManager: localStorage 기반 토큰 및 사용자 정보 관리
 */
export const TokenManager = {
  _keys: {
    access: 'ta_access_token',
    refresh: 'ta_refresh_token',
    userId: 'ta_user_id',
    userType: 'ta_user_type',
    nickname: 'ta_nickname',
    email: 'ta_email',
  },

  setTokens(accessToken, refreshToken) {
    localStorage.setItem(this._keys.access, accessToken);
    localStorage.setItem(this._keys.refresh, refreshToken);
  },

  setUserInfo({ userId, userType, nickname, email } = {}) {
    if (userId !== undefined) localStorage.setItem(this._keys.userId, userId);
    if (userType !== undefined) localStorage.setItem(this._keys.userType, userType);
    if (nickname !== undefined) localStorage.setItem(this._keys.nickname, nickname || '');
    if (email !== undefined) localStorage.setItem(this._keys.email, email || '');
  },

  getAccessToken() { return localStorage.getItem(this._keys.access); },
  getRefreshToken() { return localStorage.getItem(this._keys.refresh); },
  getUserId() { return localStorage.getItem(this._keys.userId); },
  getUserType() { return localStorage.getItem(this._keys.userType); },
  getNickname() { return localStorage.getItem(this._keys.nickname) || '사용자'; },
  getEmail() { return localStorage.getItem(this._keys.email) || ''; },

  /**
   * 로그인 여부 확인.
   * - 토큰 존재 + JWT exp 미만료인 경우만 true
   * - 만료된 경우 localStorage 자동 초기화
   */
  isLoggedIn() {
    const token = localStorage.getItem(this._keys.access);
    if (!token) return false;

    // JWT payload 디코딩 (서명 검증 없이 만료 시각만 확인)
    try {
      const payload = JSON.parse(atob(token.split('.')[1]));
      if (payload.exp && Date.now() / 1000 > payload.exp) {
        // 만료된 토큰 — 로컬 데이터 전체 삭제
        this.clearAll();
        return false;
      }
    } catch {
      // 디코딩 실패 (토큰 형식 이상) — 로그아웃 처리
      this.clearAll();
      return false;
    }
    return true;
  },
  isMember() {
    if (!this.isLoggedIn()) return false;
    const t = localStorage.getItem(this._keys.userType);
    return t === 'MEM';
  },

  clearAll() {
    Object.values(this._keys).forEach(k => localStorage.removeItem(k));
  },
};


export const BackendHooks = {

  // --------------------------------------------------
  // 내부 헬퍼: 인증 헤더 포함 fetch + 401 자동 재발급
  // --------------------------------------------------

  async _authFetch(url, options = {}) {
    const token = TokenManager.getAccessToken();
    const headers = {
      ...options.headers,
      ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
    };

    let res = await fetch(url, { ...options, headers });

    // 401: 자동 토큰 재발급 시도
    if (res.status === 401 && TokenManager.getRefreshToken()) {
      const refreshed = await this._tryRefresh();
      if (refreshed) {
        const newToken = TokenManager.getAccessToken();
        headers['Authorization'] = `Bearer ${newToken}`;
        res = await fetch(url, { ...options, headers });
      }
    }

    return res;
  },

  async _tryRefresh() {
    try {
      const res = await fetch('/api/auth/refresh', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: TokenManager.getRefreshToken() }),
      });
      if (!res.ok) { TokenManager.clearAll(); return false; }
      const data = await res.json();
      if (data.access_token) {
        // refresh token은 그대로 유지, access token만 갱신
        TokenManager.setTokens(data.access_token, TokenManager.getRefreshToken());
        return true;
      }
      TokenManager.clearAll();
      return false;
    } catch {
      return false;
    }
  },

  // --------------------------------------------------
  // 인증 API
  // --------------------------------------------------

  /**
   * 자체 계정 로그인.
   * 성공 시 TokenManager에 토큰 및 사용자 정보 저장.
   */
  async login(id, pw) {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id, pw }),
    });
    const data = await res.json();

    if (!res.ok) {
      throw { status: res.status, detail: data.detail || '로그인에 실패했습니다' };
    }

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
  },

  /**
   * 회원가입.
   */
  async signUp(userData) {
    const res = await fetch('/api/auth/signup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(userData),
    });
    const data = await res.json();

    if (!res.ok) {
      throw { status: res.status, detail: data.detail || '회원가입에 실패했습니다' };
    }
    return data;
  },

  /**
   * 로그아웃: 서버에서 refresh token 무효화 후 로컬 토큰 삭제.
   */
  async logout() {
    const refreshToken = TokenManager.getRefreshToken();
    if (refreshToken) {
      try {
        await fetch('/api/auth/logout', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: refreshToken }),
        });
      } catch {
        // 네트워크 오류여도 로컬 토큰은 삭제
      }
    }
    TokenManager.clearAll();
  },

  /**
   * 현재 사용자 프로필 조회.
   */
  async getMyProfile() {
    try {
      const res = await this._authFetch('/api/auth/me');
      if (!res.ok) return null;
      return await res.json();
    } catch {
      return null;
    }
  },

  /**
   * 카카오 로그인 — 백엔드 OAuth 인가 URL로 리다이렉트.
   */
  kakaoLogin() {
    window.location.href = '/api/auth/kakao';
  },

  /**
   * 비로그인 임시 챗봇 메시지 전송 (스트리밍).
   * temp_session_id 는 호출자가 sessionStorage 등에서 관리.
   */
  async sendTempMessage(tempSessionId, message, onChunkReceived, onCompleted) {
    try {
      const response = await fetch(`/api/temp/${encodeURIComponent(tempSessionId)}/message`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message }),
      });
      if (!response.body) throw new Error('Streaming not supported');
      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let currentText = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        currentText += decoder.decode(value, { stream: true });
        onChunkReceived(currentText);
      }
      onCompleted();
    } catch (error) {
      console.error('API Error (sendTempMessage):', error);
      onCompleted();
    }
  },

  /**
   * 계정 찾기 (Phase 7).
   */
  async findAccount() {
    const res = await fetch('/api/auth/find', { method: 'POST' });
    return await res.json();
  },

  // --------------------------------------------------
  // 세션 API
  // --------------------------------------------------

  // --------------------------------------------------
  // 여행(Trip) API
  // --------------------------------------------------

  async fetchTripList() {
    try {
      const res = await this._authFetch('/api/trips');
      if (!res.ok) return [];
      const data = await res.json();
      return data.trips || [];
    } catch (error) {
      console.error('API Error (fetchTripList):', error);
      return [];
    }
  },

  async createTrip(data) {
    try {
      const res = await this._authFetch('/api/trips', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      return await res.json();
    } catch (error) {
      console.error('API Error (createTrip):', error);
      throw error;
    }
  },

  async updateTrip(tripId, data) {
    try {
      const res = await this._authFetch(`/api/trips/${tripId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      return await res.json();
    } catch (error) {
      console.error('API Error (updateTrip):', error);
      throw error;
    }
  },

  async deleteTrip(tripId) {
    try {
      const res = await this._authFetch(`/api/trips/${tripId}`, { method: 'DELETE' });
      return await res.json();
    } catch (error) {
      console.error('API Error (deleteTrip):', error);
      throw error;
    }
  },

  // 하위 호환 별칭
  async fetchPlanList() {
    return this.fetchTripList();
  },

  // --------------------------------------------------
  // 팀(Team) API
  // --------------------------------------------------

  async fetchTeamList() {
    try {
      const res = await this._authFetch('/api/teams');
      if (!res.ok) return [];
      const data = await res.json();
      return data.teams || [];
    } catch (error) {
      console.error('API Error (fetchTeamList):', error);
      return [];
    }
  },

  async fetchTeamSessions(teamId) {
    try {
      const res = await this._authFetch(`/api/teams/${teamId}/sessions`);
      if (!res.ok) return [];
      const data = await res.json();
      return data.sessions || [];
    } catch (error) {
      console.error('API Error (fetchTeamSessions):', error);
      return [];
    }
  },

  // --------------------------------------------------
  // 세션 플러시 (창 닫기 전 저장)
  // --------------------------------------------------

  flushSessions() {
    // sendBeacon을 사용해 페이지 언로드 중에도 전송
    const token = TokenManager.getAccessToken();
    if (!token) return;
    const data = JSON.stringify({});
    navigator.sendBeacon
      ? navigator.sendBeacon('/api/sessions/flush', new Blob([data], { type: 'application/json' }))
      : fetch('/api/sessions/flush', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
          body: data,
          keepalive: true,
        }).catch(() => {});
  },

  // --------------------------------------------------
  // 세션 API
  // --------------------------------------------------

  async fetchSessionList(tripId = null) {
    try {
      const params = new URLSearchParams();
      if (tripId) params.set('trip_id', tripId);
      const query = params.toString();
      const res = await this._authFetch(`/api/sessions${query ? '?' + query : ''}`);
      if (!res.ok) return [];
      const data = await res.json();
      return Array.isArray(data) ? data : (data.sessions || []);
    } catch (error) {
      console.error("API Error (fetchSessionList):", error);
      return [];
    }
  },

  async createSession(firstMessage, mode = 'personal', tripId = null) {
    try {
      const body = { first_message: firstMessage, mode };
      if (tripId) body.trip_id = tripId;
      const res = await this._authFetch('/api/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      return await res.json();
    } catch (error) {
      console.error("API Error (createSession):", error);
      throw error;
    }
  },

  async updateSessionMode(sessionId, mode) {
    try {
      const res = await this._authFetch(`/api/sessions/${sessionId}/mode`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode }),
      });
      return await res.json();
    } catch (error) {
      console.error("API Error (updateSessionMode):", error);
      throw error;
    }
  },

  async updateSessionColor(sessionId, color) {
    try {
      const res = await this._authFetch(`/api/sessions/${sessionId}/color`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ color }),
      });
      return await res.json();
    } catch (error) {
      console.error("API Error (updateSessionColor):", error);
      throw error;
    }
  },

  async searchUsers(q) {
    try {
      const res = await this._authFetch(`/api/users/search?q=${encodeURIComponent(q)}`);
      if (!res.ok) return [];
      const data = await res.json();
      return data.users || [];
    } catch (error) {
      console.error('API Error (searchUsers):', error);
      return [];
    }
  },

  // 팀 채팅 SSE 구독 — 자동 재연결 포함, {close()} 반환
  subscribeToSessionEvents(sessionId, onEvent, onError) {
    let closed = false;
    let retryDelay = 2000;

    const connect = async () => {
      while (!closed) {
        const controller = new AbortController();
        // close() 호출 시 현재 연결도 즉시 중단
        _currentAbort = controller;
        try {
          const token = TokenManager.getAccessToken();
          const res = await fetch(`/api/sessions/${sessionId}/events`, {
            headers: token ? { Authorization: `Bearer ${token}` } : {},
            signal: controller.signal,
          });
          if (!res.ok) throw new Error(`SSE ${res.status}`);
          retryDelay = 2000; // 연결 성공 시 재연결 딜레이 초기화
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
          retryDelay = Math.min(retryDelay * 1.5, 30000); // 최대 30초
        }
      }
    };

    let _currentAbort = null;
    connect();
    return {
      close: () => {
        closed = true;
        _currentAbort?.abort();
      }
    };
  },

  async inviteUserToSession(sessionId, searchInput) {
    try {
      const res = await this._authFetch(`/api/sessions/${sessionId}/invite`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user: searchInput }),
      });
      return await res.json();
    } catch (error) {
      console.error("API Error (inviteUserToSession):", error);
      throw error;
    }
  },

  // --------------------------------------------------
  // 컨텍스트 및 설정 API
  // --------------------------------------------------

  async fetchAppContext() {
    try {
      const res = await fetch('/api/context');
      if (!res.ok) throw new Error('Not Found');
      return await res.json();
    } catch {
      return {
        today: new Date().toISOString().split('T')[0],
        settings: {
          appGlassOpacity: '20',
          leftSidebarCustomWidth: 300,
          rightSidebarCustomWidth: 300,
          theme: 'default',
        },
      };
    }
  },

  async fetchSettings() {
    try {
      const res = await this._authFetch('/api/settings');
      if (!res.ok) return {};
      return await res.json();
    } catch {
      return {};
    }
  },

  async saveUserSetting(key, value) {
    try {
      const res = await this._authFetch('/api/settings/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [key]: value }),
      });
      return await res.json();
    } catch (error) {
      console.error("API Error (saveUserSetting):", error);
    }
  },

  // --------------------------------------------------
  // 채팅 API
  // --------------------------------------------------

  async fetchChatHistory(sessionId, limit = 40, offset = 0) {
    try {
      const res = await this._authFetch(
        `/api/sessions/${sessionId}/history?limit=${limit}&offset=${offset}`
      );
      if (!res.ok) return { messages: [], mode: 'personal' };
      const data = await res.json();
      if (Array.isArray(data)) return { messages: data, mode: 'personal' };
      return { messages: data.messages || [], mode: data.mode || 'personal' };
    } catch (error) {
      console.error("API Error (fetchChatHistory):", error);
      return { messages: [], mode: 'personal' };
    }
  },

  async sendTeamMessage(sessionId, message) {
    try {
      const token = TokenManager.getAccessToken();
      const headers = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = `Bearer ${token}`;
      await fetch(`/api/sessions/${sessionId}/team-message`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ message }),
      });
    } catch (error) {
      console.error('API Error (sendTeamMessage):', error);
    }
  },

  async markSessionRead(sessionId) {
    try {
      await this._authFetch(`/api/sessions/${sessionId}/read`, { method: 'POST' });
    } catch { /* 실패해도 무시 */ }
  },

  async sendTypingEvent(sessionId) {
    try {
      await this._authFetch(`/api/sessions/${sessionId}/typing`, { method: 'POST' });
    } catch {
      // typing 이벤트는 실패해도 무시
    }
  },

  async sendMessage(sessionId, message, onChunkReceived, onCompleted) {
    try {
      const token = TokenManager.getAccessToken();
      const headers = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = `Bearer ${token}`;

      const response = await fetch(`/api/sessions/${sessionId}/message`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ message }),
      });

      if (!response.body) throw new Error("Streaming not supported");

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let currentText = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        currentText += decoder.decode(value, { stream: true });
        onChunkReceived(currentText);
      }
      onCompleted();
    } catch (error) {
      console.error("API Error (sendMessage):", error);
      onCompleted();
    }
  },

  // --------------------------------------------------
  // 계정 정보 API
  // --------------------------------------------------

  async fetchAccountInfo() {
    try {
      const res = await this._authFetch('/api/account');
      return await res.json();
    } catch {
      return { status: 'guest', user_id: null };
    }
  },

  // --------------------------------------------------
  // 기타 API
  // --------------------------------------------------

  async fetchHelpData() {
    try {
      const res = await fetch('/api/help');
      return await res.json();
    } catch {
      return { sections: [] };
    }
  },

  async saveThemePreference(themeName) {
    try {
      const res = await this._authFetch('/api/theme', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ theme: themeName }),
      });
      return await res.json();
    } catch (error) {
      console.error("API Error (saveThemePreference):", error);
    }
  },

  async fetchCurrentWeather() {
    try {
      const res = await fetch('/api/weather');
      if (!res.ok) throw new Error();
      return await res.json();
    } catch {
      return { condition: 'clear', params: {} };
    }
  },

  async updateSessionTitle(sessionId, newTitle) {
    try {
      const res = await this._authFetch(`/api/sessions/${sessionId}/title`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: newTitle }),
      });
      return await res.json();
    } catch (error) {
      console.error("API Error (updateSessionTitle):", error);
      throw error;
    }
  },

  async deleteSession(sessionId) {
    try {
      const res = await this._authFetch(`/api/sessions/${sessionId}`, {
        method: 'DELETE',
      });
      return await res.json();
    } catch (error) {
      console.error("API Error (deleteSession):", error);
      throw error;
    }
  },

  async shareChat(sessionId) {
    try {
      const res = await this._authFetch(`/api/sessions/${sessionId}/share`, {
        method: 'POST',
      });
      return await res.json();
    } catch (error) {
      console.error("API Error (shareChat):", error);
      throw error;
    }
  },

  async downloadChat(sessionId) {
    try {
      const res = await this._authFetch(`/api/sessions/${sessionId}/download`);
      if (!res.ok) throw new Error(`다운로드 실패: ${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `chat_${sessionId}.txt`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (error) {
      console.error('API Error (downloadChat):', error);
      throw error;
    }
  },

  // --------------------------------------------------
  // 지도 API
  // --------------------------------------------------

  async saveMapMarkers(sessionId, markers) {
    try {
      const res = await this._authFetch(`/api/sessions/${sessionId}/map/markers`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ markers }),
      });
      return await res.json();
    } catch (error) {
      console.error("API Error (saveMapMarkers):", error);
    }
  },

  async fetchMapMarkers(sessionId) {
    try {
      const res = await this._authFetch(`/api/sessions/${sessionId}/map/markers`);
      if (!res.ok) return { markers: [] };
      return await res.json();
    } catch (error) {
      console.error("API Error (fetchMapMarkers):", error);
      return { markers: [] };
    }
  },

  async addMapMarker(sessionId, markerId, lat, lng, title = '') {
    try {
      const res = await this._authFetch(`/api/sessions/${sessionId}/map/markers/add`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ marker_id: markerId, lat, lng, title }),
      });
      return await res.json();
    } catch (error) {
      console.error("API Error (addMapMarker):", error);
    }
  },

  async removeMapMarker(sessionId, markerId) {
    try {
      const res = await this._authFetch(
        `/api/sessions/${sessionId}/map/markers/${encodeURIComponent(markerId)}`,
        { method: 'DELETE' }
      );
      return await res.json();
    } catch (error) {
      console.error("API Error (removeMapMarker):", error);
    }
  },

  // --------------------------------------------------
  // 여행 일정 API
  // --------------------------------------------------

  async saveTripRange(sessionId, ranges) {
    try {
      const res = await this._authFetch(`/api/sessions/${sessionId}/trip_range`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ranges }),
      });
      return await res.json();
    } catch (error) {
      console.error("API Error (saveTripRange):", error);
    }
  },

  async fetchTripRange(sessionId) {
    try {
      if (!sessionId || sessionId === 'default') return { ranges: [] };
      const res = await this._authFetch(`/api/sessions/${sessionId}/trip_range`);
      if (!res.ok) return { ranges: [] };
      return await res.json();
    } catch {
      return { ranges: [] };
    }
  },

  async uploadFiles(sessionId, files) {
    try {
      const formData = new FormData();
      Array.from(files).forEach(file => formData.append('files', file));

      const token = TokenManager.getAccessToken();
      const headers = token ? { 'Authorization': `Bearer ${token}` } : {};

      const res = await fetch(`/api/sessions/${sessionId}/files`, {
        method: 'POST',
        headers,
        body: formData,
      });
      return await res.json();
    } catch (error) {
      console.error("API Error (uploadFiles):", error);
      throw error;
    }
  },

  // --------------------------------------------------
  // 메모 / 플래너 API
  // --------------------------------------------------

  async saveMemo(sessionId, memoContent, dateKey) {
    try {
      const res = await this._authFetch(
        `/api/sessions/${sessionId}/memo?date=${dateKey}`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ memo: memoContent }),
        }
      );
      return await res.json();
    } catch (error) {
      console.error("API Error (saveMemo):", error);
      throw error;
    }
  },

  async fetchMemo(sessionId, dateKey) {
    try {
      if (!sessionId || sessionId === 'default') return { memo: '' };
      const res = await this._authFetch(`/api/sessions/${sessionId}/memo?date=${dateKey}`);
      if (!res.ok) return { memo: '' };
      return await res.json();
    } catch {
      return { memo: '' };
    }
  },

  async updateSchedule(sessionId, planData, dateKey) {
    try {
      const res = await this._authFetch(
        `/api/sessions/${sessionId}/plan?date=${dateKey}`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ plan: planData }),
        }
      );
      return await res.json();
    } catch (error) {
      console.error("API Error (updateSchedule):", error);
      throw error;
    }
  },

  async fetchSchedule(sessionId, dateKey) {
    try {
      if (!sessionId || sessionId === 'default') return { plan: [] };
      const res = await this._authFetch(`/api/sessions/${sessionId}/plan?date=${dateKey}`);
      if (!res.ok) return { plan: [] };
      return await res.json();
    } catch {
      return { plan: [] };
    }
  },

  async fetchMonthDataIndicators(sessionId, year, month) {
    try {
      if (!sessionId || sessionId === 'default') return [];
      const res = await this._authFetch(
        `/api/sessions/${sessionId}/indicators?year=${year}&month=${month}`
      );
      if (!res.ok) return [];
      return await res.json();
    } catch {
      return [];
    }
  },

  // --------------------------------------------------
  // 사용자 프로필 API
  // --------------------------------------------------

  /**
   * 사용자 프로필 저장 (닉네임, 소개, 이메일, 추가 연락수단).
   */
  async saveUserProfile(data) {
    try {
      const res = await this._authFetch('/api/user/profile', {
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
  },

  /**
   * AI 스타일/말투 설정 저장 (특성, 이모지, 헤더, 지침, 추가 정보).
   */
  async saveUserStyle(data) {
    try {
      const res = await this._authFetch('/api/user/style', {
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
  },

  /**
   * 여행 스타일 설정 저장.
   */
  async saveTravelPreferences(data) {
    try {
      const res = await this._authFetch('/api/user/travel', {
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
  },

  /**
   * SNS 계정 연동.
   */
  async linkSocialAccount(provider) {
    try {
      const res = await this._authFetch(`/api/auth/social/link/${provider}`, {
        method: 'POST',
      });
      return await res.json();
    } catch (error) {
      console.error(`API Error (linkSocialAccount:${provider}):`, error);
      throw error;
    }
  },

  /**
   * 모든 기기에서 로그아웃 (refresh token 전체 무효화).
   */
  async logoutAllDevices() {
    try {
      const res = await this._authFetch('/api/auth/logout/all', {
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
  },

  /**
   * 계정 영구 삭제.
   */
  async deleteAccount() {
    try {
      const res = await this._authFetch('/api/user/account', {
        method: 'DELETE',
      });
      if (!res.ok) throw { status: res.status, detail: (await res.json()).detail };
      return await res.json();
    } catch (error) {
      console.error('API Error (deleteAccount):', error);
      throw error;
    }
  },

  // --------------------------------------------------
  // 알림 API
  // --------------------------------------------------

  async fetchNotifications() {
    try {
      const res = await this._authFetch('/api/notifications');
      if (!res.ok) return [];
      const data = await res.json();
      return data.notifications || [];
    } catch (error) {
      console.error('API Error (fetchNotifications):', error);
      return [];
    }
  },

  async acceptNotification(notificationId) {
    try {
      const res = await this._authFetch(`/api/notifications/${notificationId}/accept`, {
        method: 'POST',
      });
      return await res.json();
    } catch (error) {
      console.error('API Error (acceptNotification):', error);
      throw error;
    }
  },

  async dismissNotification(notificationId) {
    try {
      const res = await this._authFetch(`/api/notifications/${notificationId}/dismiss`, {
        method: 'POST',
      });
      return await res.json();
    } catch (error) {
      console.error('API Error (dismissNotification):', error);
      throw error;
    }
  },

  async clearViewedNotifications() {
    try {
      const res = await this._authFetch('/api/notifications/clear-viewed', { method: 'POST' });
      return await res.json();
    } catch (error) {
      console.error('API Error (clearViewedNotifications):', error);
      throw error;
    }
  },

  async adminGetUsers() {
    const res = await this._authFetch('/api/admin/users');
    if (!res.ok) throw new Error(`Admin users fetch failed: ${res.status}`);
    return await res.json();
  },

  async adminGetSessions() {
    const res = await this._authFetch('/api/admin/sessions');
    if (!res.ok) throw new Error(`Admin sessions fetch failed: ${res.status}`);
    return await res.json();
  },
};
