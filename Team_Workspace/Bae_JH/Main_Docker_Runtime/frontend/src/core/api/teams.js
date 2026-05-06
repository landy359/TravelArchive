/**
 * teams.js  —  팀(Team) 조회 API
 */

import { authFetch } from './client.js';

export async function fetchTeamList() {
  try {
    const res = await authFetch('/api/teams');
    if (!res.ok) return [];
    const data = await res.json();
    return data.teams || [];
  } catch (error) {
    console.error('API Error (fetchTeamList):', error);
    return [];
  }
}

export async function fetchTeamSessions(teamId) {
  try {
    const res = await authFetch(`/api/teams/${teamId}/sessions`);
    if (!res.ok) return [];
    const data = await res.json();
    return data.sessions || [];
  } catch (error) {
    console.error('API Error (fetchTeamSessions):', error);
    return [];
  }
}
