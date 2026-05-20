/**
 * chat.js  —  채팅 메시지 API (히스토리 / 스트리밍 송신 / 타이핑)
 */

import { authFetch } from './client.js';
import { TokenManager } from './tokens.js';

export async function fetchChatHistory(sessionId, limit = 40, offset = 0) {
  try {
    const res = await authFetch(`/api/sessions/${sessionId}/history?limit=${limit}&offset=${offset}`);
    if (!res.ok) return { messages: [] };
    const data = await res.json();
    if (Array.isArray(data)) return { messages: data };
    return { messages: data.messages || [] };
  } catch (error) {
    console.error('API Error (fetchChatHistory):', error);
    return { messages: [] };
  }
}

/**
 * 팀 채팅 메시지 송신.
 * 백엔드가 @BOT 감지 시 LLM 응답을 스트리밍으로 회신.
 * @param onBotChunk(accumulatedText) - 봇 청크 도착 시
 * @param onBotDone() - 봇 응답 완료 시 (응답이 있었던 경우만)
 */
export async function sendTeamMessage(sessionId, message, onBotChunk, onBotDone) {
  try {
    const token = TokenManager.getAccessToken();
    const headers = { 'Content-Type': 'application/json' };
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const response = await fetch(`/api/sessions/${sessionId}/message`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ message }),
    });
    if (!response.body) return;
    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let botText = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const chunk = decoder.decode(value, { stream: true });
      if (!chunk) continue;
      botText += chunk;
      onBotChunk?.(botText);
    }
    onBotDone?.();
  } catch (error) {
    console.error('API Error (sendTeamMessage):', error);
    onBotDone?.();
  }
}

/**
 * 일반 메시지 송신 (스트리밍).
 */
export async function sendMessage(sessionId, message, onChunkReceived, onCompleted) {
  try {
    const token = TokenManager.getAccessToken();
    const headers = { 'Content-Type': 'application/json' };
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const response = await fetch(`/api/sessions/${sessionId}/message`, {
      method: 'POST',
      headers,
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
    console.error('API Error (sendMessage):', error);
    onCompleted();
  }
}

/**
 * 비로그인 임시 챗봇 메시지 송신 (스트리밍).
 */
export async function sendTempMessage(tempSessionId, message, onChunkReceived, onCompleted) {
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
}

export async function sendTypingEvent(sessionId) {
  try {
    await authFetch(`/api/sessions/${sessionId}/typing`, { method: 'POST' });
  } catch { /* silent */ }
}
