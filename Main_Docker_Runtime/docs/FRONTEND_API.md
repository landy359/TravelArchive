# 🌐 Frontend API Documentation

이 문서는 `frontend/src/js/api.js`에 정의된 모든 백엔드 통신 인터페이스(BackendHooks)를 정리한 문서입니다.

## 1. 인증 및 사용자 관리 (`/api/auth`)

| 함수명 | HTTP 메소드 | 엔드포인트 | 매개변수 | 설명 |
| :--- | :---: | :--- | :--- | :--- |
| `login` | POST | `/api/auth/login` | `id`, `pw` | 일반 로그인 시도 |
| `guestLogin` | POST | `/api/auth/guest` | - | 게스트 모드 로그인 |
| `socialLogin` | POST | `/api/auth/social/${provider}` | `provider` | SNS 소셜 로그인 (Google, Kakao 등) |
| `signUp` | POST | `/api/auth/signup` | `userData` | 신규 사용자 회원가입 |
| `findAccount` | POST | `/api/auth/find` | - | 계정 찾기 프로세스 시작 |

## 2. 세션 및 채팅 관리 (`/api/sessions`)

| 함수명 | HTTP 메소드 | 엔드포인트 | 매개변수 | 설명 |
| :--- | :---: | :--- | :--- | :--- |
| `fetchSessionList` | GET | `/api/sessions?mode=${mode}` | `mode` ('personal'/'team') | 필터링된 세션 목록 조회 |
| `createSession` | POST | `/api/sessions` | `first_message`, `mode` | 새 채팅 세션 생성 (첫 메시지 포함) |
| `updateSessionMode` | PUT | `/api/sessions/${sessionId}/mode` | `mode` | 세션의 모드 변경 (개인 <-> 팀) |
| `inviteUserToSession`| POST | `/api/sessions/${sessionId}/invite`| `user` (ID/이름) | 팀 플래너에 다른 사용자 초대 |
| `fetchChatHistory` | GET | `/api/sessions/${sessionId}/history` | - | 특정 세션의 과거 대화 내역 조회 |
| `sendMessage` | POST | `/api/sessions/${sessionId}/message` | `message` | 메시지 전송 및 스트리밍 응답(Chunk) 수신 |
| `updateSessionTitle` | PUT | `/api/sessions/${sessionId}/title` | `title` | 세션의 제목(이름) 변경 |
| `deleteSession` | DELETE | `/api/sessions/${sessionId}` | - | 채팅 세션 및 관련 데이터 완전 삭제 |
| `shareChat` | POST | `/api/sessions/${sessionId}/share` | - | 세션 공유 활성화 및 링크 정보 요청 |
| `downloadChat` | GET | `/api/sessions/${sessionId}/download` | - | 대화 내역 TXT 파일 다운로드 (브라우저 이동 방식) |
| `uploadFiles` | POST | `/api/sessions/${sessionId}/files` | `files` (FormData) | 세션 내 파일 업로드 (멀티파트) |

## 3. 달력, 일정 및 메모 (`/api/sessions/...`)

| 함수명 | HTTP 메소드 | 엔드포인트 | 매개변수 | 설명 |
| :--- | :---: | :--- | :--- | :--- |
| `fetchMonthDataIndicators`| GET | `/api/sessions/${id}/indicators` | `year`, `month` | 특정 월의 데이터 존재 여부(점) 조회 |
| `fetchMemo` | GET | `/api/sessions/${id}/memo` | `date` (dateKey) | 특정 날짜의 메모 내용 조회 |
| `saveMemo` | PUT | `/api/sessions/${id}/memo` | `memo`, `date` | 특정 날짜의 메모 내용 저장 |
| `fetchSchedule` | GET | `/api/sessions/${id}/plan` | `date` (dateKey) | 특정 날짜의 일정(Plan) 목록 조회 |
| `updateSchedule` | PUT | `/api/sessions/${id}/plan` | `plan`, `date` | 특정 날짜의 일정(Plan) 목록 저장 |
| `fetchTripRange` | GET | `/api/sessions/${id}/trip_range`| - | 세션의 여행 기간들 설정 조회 |
| `saveTripRange` | PUT | `/api/sessions/${id}/trip_range`| `ranges` ([{start, end}]) | 세션의 여행 기간들 설정 저장 |

## 4. 지도 데이터 관리 (`/api/sessions/.../map`)

> 지도 마커는 두 방향으로 흐릅니다.  
> **프론트→백**: 사용자 클릭 시 `map.js`가 직접 API 호출 (`window.parent.currentSessionId` 사용).  
> **백→프론트**: 부모 창이 `fetchMapMarkers`로 폴링 후 iframe에 `postMessage { type: 'ADD_MARKER' }`.

| 함수명 | HTTP 메소드 | 엔드포인트 | 매개변수 | 설명 |
| :--- | :---: | :--- | :--- | :--- |
| `addMapMarker` | POST | `/api/sessions/${id}/map/markers/add` | `markerId`, `lat`, `lng`, `title?` | 마커 단건 추가. `map.js` 또는 부모 창에서 직접 호출 가능 |
| `removeMapMarker` | DELETE | `/api/sessions/${id}/map/markers/${markerId}` | `markerId` | 마커 단건 삭제. 우클릭 제거 시 `map.js`가 자동 호출 |
| `fetchMapMarkers` | GET | `/api/sessions/${id}/map/markers` | - | 세션 전체 마커 조회. 백엔드→지도 push 기준 소스 |
| `saveMapMarkers` | POST | `/api/sessions/${id}/map/markers` | `markers` (Array) | 마커 목록 일괄(bulk) upsert |

## 5. 앱 설정 및 사용자 환경 (`/api/...`)

| 함수명 | HTTP 메소드 | 엔드포인트 | 매개변수 | 설명 |
| :--- | :---: | :--- | :--- | :--- |
| `fetchAppContext` | GET | `/api/context` | - | 앱 초기화 데이터 (오늘 날짜, 기본 UI 설정 등) |
| `fetchSettings` | GET | `/api/settings` | - | 저장된 사용자 UI 설정값 조회 |
| `saveUserSetting` | POST | `/api/settings/update` | `key`, `value` | 개별 설정값(투명도, 사이드바 너비 등) 저장 |
| `fetchAccountInfo` | GET | `/api/account` | - | 현재 로그인된 사용자 정보 조회 |
| `fetchHelpData` | GET | `/api/help` | - | 도움말 및 가이드 문서 데이터 조회 |
| `saveThemePreference`| POST | `/api/theme` | `theme` (이름) | 사용자 선택 테마 취향 저장 |
| `fetchCurrentWeather` | GET | `/api/weather` | - | 현재 날씨 상태 및 물리 효과 파라미터 조회 |

---
*Last Updated: 2026-04-10*
