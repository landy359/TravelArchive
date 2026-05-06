/**
 * api.js  —  하위 호환 facade
 *
 * 모든 API 로직은 core/api/* 도메인 모듈에 있다.
 * 이 파일은 기존 `BackendHooks` / `TokenManager` import 를 유지하기 위한 얇은 재export.
 *
 * 새 코드는 가능한 직접 import 하라:
 *   import { Sessions, Markers } from '../core/api';
 */

import { TokenManager, authFetch } from '../core/api/index.js';
import * as Auth          from '../core/api/auth.js';
import * as Sessions      from '../core/api/sessions.js';
import * as Chat          from '../core/api/chat.js';
import * as Trips         from '../core/api/trips.js';
import * as Teams         from '../core/api/teams.js';
import * as Markers       from '../core/api/markers.js';
import * as Planner       from '../core/api/planner.js';
import * as Files         from '../core/api/files.js';
import * as Notifications from '../core/api/notifications.js';
import * as Users         from '../core/api/users.js';
import * as Settings      from '../core/api/settings.js';
import * as Admin         from '../core/api/admin.js';

export { TokenManager };

/**
 * BackendHooks  —  기존 코드와 호환되는 단일 객체.
 * 새 코드는 도메인 모듈을 직접 import 하는 것을 권장.
 */
export const BackendHooks = {
  // 내부 헬퍼 (일부 소비자가 직접 호출)
  _authFetch: (url, options) => authFetch(url, options),

  // Auth
  ...Auth,

  // Sessions
  ...Sessions,

  // Chat
  ...Chat,

  // Trips
  ...Trips,

  // Teams
  ...Teams,

  // Markers
  ...Markers,

  // Planner (memo + schedule)
  ...Planner,

  // Files
  ...Files,

  // Notifications
  ...Notifications,

  // Users
  ...Users,

  // Settings
  ...Settings,

  // Admin
  ...Admin,
};
