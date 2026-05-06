/**
 * files.js  —  세션 파일 업로드 API
 */

import { TokenManager } from './tokens.js';

export async function uploadFiles(sessionId, files) {
  try {
    const formData = new FormData();
    Array.from(files).forEach(f => formData.append('files', f));

    const token = TokenManager.getAccessToken();
    const headers = token ? { 'Authorization': `Bearer ${token}` } : {};

    const res = await fetch(`/api/sessions/${sessionId}/files`, {
      method: 'POST',
      headers,
      body: formData,
    });
    return await res.json();
  } catch (error) {
    console.error('API Error (uploadFiles):', error);
    throw error;
  }
}
