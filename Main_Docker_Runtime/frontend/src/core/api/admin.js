/**
 * admin.js  —  관리자 전용 API
 */

import { authFetch } from './client.js';

export async function adminGetUsers() {
  const res = await authFetch('/api/admin/users');
  if (!res.ok) throw new Error(`Admin users fetch failed: ${res.status}`);
  return await res.json();
}

export async function adminGetSessions() {
  const res = await authFetch('/api/admin/sessions');
  if (!res.ok) throw new Error(`Admin sessions fetch failed: ${res.status}`);
  return await res.json();
}
