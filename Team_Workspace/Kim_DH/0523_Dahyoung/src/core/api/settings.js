/**
 * settings.js  —  앱 컨텍스트 / 설정 / 테마 / 도움말 / 날씨 API
 */

import { authFetch, tryRefresh } from './client.js';
import { TokenManager } from './tokens.js';

export async function fetchAppContext() {
  try {
    // access token이 만료됐지만 refresh token이 있으면 먼저 갱신
    if (!TokenManager.isLoggedIn() && TokenManager.getRefreshToken()) {
      await tryRefresh();
    }
    const res = await authFetch('/api/context');
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
}

export async function fetchSettings() {
  try {
    const res = await authFetch('/api/settings');
    if (!res.ok) return {};
    return await res.json();
  } catch {
    return {};
  }
}

export async function saveUserSetting(key, value) {
  try {
    const res = await authFetch('/api/settings/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ [key]: value }),
    });
    return await res.json();
  } catch (error) {
    console.error('API Error (saveUserSetting):', error);
  }
}

export async function saveThemePreference(themeName) {
  try {
    const res = await authFetch('/api/theme', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ theme: themeName }),
    });
    return await res.json();
  } catch (error) {
    console.error('API Error (saveThemePreference):', error);
  }
}

export async function fetchHelpData() {
  try {
    const res = await fetch('/api/help');
    return await res.json();
  } catch {
    return { sections: [] };
  }
}

