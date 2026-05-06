/**
 * core/api/index.js  —  단일 진입점 (barrel export)
 *
 * 새 코드는 이 파일에서 필요한 도메인만 import 하면 된다.
 *   import { Sessions, Markers } from '@/core/api';
 *
 * 또는 namespace 형태:
 *   import * as Api from '@/core/api';
 *   Api.Sessions.createSession(...);
 */

export { TokenManager } from './tokens.js';
export { authFetch, tryRefresh } from './client.js';

export * as Auth          from './auth.js';
export * as Sessions      from './sessions.js';
export * as Chat          from './chat.js';
export * as Trips         from './trips.js';
export * as Teams         from './teams.js';
export * as Markers       from './markers.js';
export * as Planner       from './planner.js';
export * as Files         from './files.js';
export * as Notifications from './notifications.js';
export * as Users         from './users.js';
export * as Settings      from './settings.js';
export * as Admin         from './admin.js';
