# Frontend 구조 개편 계획

작성일: 2026-05-21  
작성자: Claude (코드 분석 기반)

---

## 1. 현재 상태 진단

### 1-1. 파일 수 및 크기

```
frontend/src/
  script.js            885줄   ← 앱 전체 오케스트레이션 (God File)
  main.js               13줄   ← script.js 하나만 import
  js/                  ~4575줄  ← 실제 로직이 사는 곳
  core/api/            ~1000줄  ← 잘 정리된 API 레이어
  views/                 ~5줄   ← 껍데기 (js/ 재export만)
  layouts/               ~5줄   ← 껍데기 (js/ 재export만)
  widgets/             ~1200줄  ← 실코드 존재, 단 index.js가 1줄 재export
```

### 1-2. 문제: 미완성 이중 구조

리팩터링이 중간에 멈춘 상태다. 새 레이어 구조(`views/`, `layouts/`)가 뼈대만 있고,
진짜 코드는 모두 구파일인 `js/`에 남아 있다.

```
views/home/index.js
  → export { HomeManager } from '../../js/home.js'   // 재export만. 실체 없음

layouts/app-shell/index.js
  → export { SidebarManager } from '../../js/sidebar.js'  // 동일

layouts/left-sidebar/index.js
  → export { SidebarManager } from '../../js/sidebar.js'  // app-shell과 완전 동일
```

결과: 파일 수는 늘었는데 코드 경로는 그대로. 혼란만 가중.

### 1-3. 문제: 지도 관련 파일 산재

같은 도메인의 코드가 세 군데에 흩어져 있다.

```
js/map.js                        ← 구 진입점
js/mapApiClient.js               ← 구 API 클라이언트
js/mapMarkerInfo.js              ← 구 마커 정보
js/mapOverlayControls.js         ← 구 오버레이
js/mapPolylineManager.js         ← 구 폴리라인
js/mapHeightResizer.js           ← 구 높이 조절
js/map/clickHandler.js           ← 신구조로 일부만 이동
js/map/locationHandler.js
js/map/markerManager.js
js/map/messageHandler.js
js/markerPanel/markerCard.js     ← 또 다른 위치
widgets/map-overlay-controls/    ← widget 버전 (별도 존재)
widgets/marker-card/
widgets/marker-panel/
```

### 1-4. 문제: 불필요한 중간 레이어

```
main.js → script.js import 1줄. main.js가 entry point여야 하는데 script.js가 실질 entry.
js/api.js → core/api/* 전체를 BackendHooks 하나로 재포장. 하위호환 목적이지만
            모든 신규 코드도 여전히 이걸 import해서 계속 살아남고 있음.
widgets/*/index.js → 각 위젯마다 1줄짜리 재export 파일. index.js가 없어도 동일하게 동작.
```

### 1-5. 문제: 번들 최적화 미적용

```
vite.config.js 현재:
  rollupOptions.input = { main, map }  // 2개 entry만 정의
  → manualChunks 없음 → 코드 스플리팅 없음
  → 지도, 캘린더, 채팅 모두 첫 로드 시 전부 번들링됨

폰트 패키지:
  @fontsource/gothic-a1       ← 실제로 쓰는지 확인 필요
  @fontsource/noto-sans-kr    ← 실제로 쓰는지 확인 필요
  @fontsource/pretendard      ← pretendard 패키지와 중복
  pretendard                  ← 동일 폰트 2개 설치
```

---

## 2. 목표 아키텍처

"밑에서부터 쌓는" 레이어 구조. 각 레이어는 자신보다 아래 레이어만 의존한다.

```
┌─────────────────────────────────────────────┐
│  Layer 5: script.js (진입점, 초기화)          │  ← 최소화 목표 (~100줄)
│  앱 부트스트랩, 이벤트 바인딩 최상위 조율       │
└────────────────────┬────────────────────────┘
                     │ depends on
┌────────────────────▼────────────────────────┐
│  Layer 4: views/                             │  ← 페이지/화면 단위
│  home, chat, settings, account, help         │
│  각 뷰는 자신의 DOM과 상태만 관리              │
└────────────────────┬────────────────────────┘
                     │ depends on
┌────────────────────▼────────────────────────┐
│  Layer 3: widgets/ + layouts/                │  ← 재사용 UI 컴포넌트
│  chat-message, marker-card, session-info     │  ← 위젯 (공통)
│  left-sidebar, right-sidebar, app-shell      │  ← 레이아웃 (뼈대)
└────────────────────┬────────────────────────┘
                     │ depends on
┌────────────────────▼────────────────────────┐
│  Layer 2: core/api/                          │  ← 서버 통신 (현재 가장 잘 정리됨)
│  auth, sessions, chat, trips, teams, markers │
│  tokens, client, files, notifications, users │
└────────────────────┬────────────────────────┘
                     │ depends on
┌────────────────────▼────────────────────────┐
│  Layer 1: js/utils.js, js/assets.js          │  ← 순수 유틸 (의존성 없음)
│  renderTemplate, debounce, Icons SVG 등       │
└─────────────────────────────────────────────┘
```

---

## 3. 이동 계획 (js/ → 각 레이어)

### 3-1. Layer 4: views/

| 현재 파일 | 이동 위치 | 비고 |
|---|---|---|
| `js/home.js` | `views/home/home.js` | HomeManager |
| `js/router.js` | `views/chat/router.js` | 라우팅 로직 |
| `js/chat.js` | `views/chat/chat.js` | ChatManager |
| `js/session.js` | `views/chat/session.js` | SessionManager |
| `js/settings.js` | `views/settings/settings.js` | 설정 페이지 |
| `js/account.js` | `views/account/account.js` | 계정 페이지 |
| `js/help.js` | `views/help/help.js` | 도움말 페이지 |

`views/*/index.js`는 진짜 코드를 담는 파일이 되어야 한다. 재export 파일이 되어선 안 된다.

### 3-2. Layer 3: layouts/

| 현재 파일 | 이동 위치 | 비고 |
|---|---|---|
| `js/sidebar.js` | `layouts/left-sidebar/sidebar.js` | 파사드 |
| `js/managers/sidebar-base.js` | `layouts/left-sidebar/sidebar-base.js` | |
| `js/managers/sidebar-folding.js` | `layouts/left-sidebar/sidebar-folding.js` | |
| `js/managers/sidebar-resizer.js` | `layouts/left-sidebar/sidebar-resizer.js` | |
| `js/managers/sidebar-tabs.js` | `layouts/left-sidebar/sidebar-tabs.js` | |
| `js/mapHeightResizer.js` | `layouts/right-sidebar/map-height-resizer.js` | |
| `js/theme.js` | `layouts/app-shell/theme.js` | |
| `js/notification.js` | `layouts/app-shell/notification.js` | |

### 3-3. Layer 3: widgets/ (지도 정리)

현재 지도 관련 파일이 `js/`, `js/map/`, `js/markerPanel/`, `widgets/` 네 곳에 분산.

| 현재 파일 | 이동 위치 | 비고 |
|---|---|---|
| `js/mapApiClient.js` | `core/api/map.js` | API 호출만 담당 |
| `js/map.js` | `widgets/map/map.js` | 지도 초기화/진입점 |
| `js/mapMarkerInfo.js` | `widgets/map/marker-info.js` | |
| `js/mapOverlayControls.js` | ← `widgets/map-overlay-controls/`로 통합 | 위젯 버전이 이미 존재 |
| `js/mapPolylineManager.js` | `widgets/map/polyline-manager.js` | |
| `js/map/clickHandler.js` | `widgets/map/click-handler.js` | |
| `js/map/locationHandler.js` | `widgets/map/location-handler.js` | |
| `js/map/markerManager.js` | `widgets/map/marker-manager.js` | |
| `js/map/messageHandler.js` | `widgets/map/message-handler.js` | |
| `js/markerPanel/markerCard.js` | ← `widgets/marker-card/`로 통합 | 위젯 버전이 이미 존재 |
| `js/rightSidebarMarkerPanel.js` | `widgets/marker-panel/right-sidebar.js` | |

### 3-4. 삭제 대상

```
main.js                        ← script.js를 직접 entry로 변경하면 불필요
js/api.js                      ← core/api/ 직접 import로 전환 후 삭제
views/*/index.js (재export만)   ← 실코드 이동 후 index.js로 통합하거나 삭제
layouts/*/index.js (재export만) ← 동일
widgets/*/index.js (1줄 재export) ← 불필요. 위젯 파일 직접 import
js/core/event-bus.js           ← core/event-bus.js 또는 core/infra/로 이동
js/core/module-registry.js     ← 동일
```

### 3-5. 이동하지 않는 것

```
js/utils.js     ← Layer 1. 현재 위치 유지 (또는 core/utils.js로 이동)
js/assets.js    ← Layer 1. 현재 위치 유지
js/templates.js ← 역할 확인 후 결정
js/ui.js        ← utils와 합치거나 현재 위치 유지
js/calendar.js  ← views/calendar/ 또는 widgets/calendar/로 이동
js/schedule.js  ← views/schedule/ 또는 widgets/calendar/ 하위로
core/api/       ← 현재 상태 유지 (가장 잘 정리됨)
widgets/chat-message/ ← 현재 상태 유지
css/            ← 현재 상태 유지
```

---

## 4. Vite 번들 최적화

### 4-1. manualChunks 추가

```js
// vite.config.js
build: {
  rollupOptions: {
    input: {
      main: resolve(__dirname, 'src/html/index.html'),
      map:  resolve(__dirname, 'src/html/map.html'),
    },
    output: {
      manualChunks: {
        'vendor-marked':    ['marked'],          // CDN으로 이미 로드 → 번들 제외 고려
        'chunk-map':        [                    // 지도: 첫 진입 불필요
          './src/widgets/map/map.js',
          './src/widgets/map-overlay-controls/map-overlay-controls.js',
          './src/widgets/marker-panel/marker-panel.js',
        ],
        'chunk-api':        ['./src/core/api/index.js'],
      },
    },
  },
},
```

### 4-2. 지도 lazy load

지도는 우측 사이드바를 열 때만 필요하다. 초기 로드 대상이 아니다.

```js
// layouts/right-sidebar/index.js
async function openMap() {
  const { initMap } = await import('../../widgets/map/map.js');  // 최초 열 때만 로드
  initMap();
}
```

### 4-3. 폰트 정리

`package.json` 현재 폰트 패키지 4개 → 실제 사용 확인 후 1개로 축소.
한국어 앱이므로 Pretendard 단일 사용 권장.

```json
"dependencies": {
  "pretendard": "^1.3.9"
}
```

---

## 5. 마이그레이션 순서 (안전한 순서)

단계별로 진행하고, 각 단계 후 앱이 정상 동작하는지 확인한다.

### Phase 0: 기준선 확보
- 현재 앱 동작 상태 스냅샷
- 주요 기능 동작 목록 작성 (로그인, 채팅, 지도, 세션 생성 등)

### Phase 1: 저위험 정리
- `widgets/*/index.js` 1줄짜리 삭제 → import 경로 직접 파일로 수정
- `main.js` 삭제 → `vite.config.js`에서 `script.js` 직접 entry 등록
- `layouts/left-sidebar/index.js` (app-shell과 중복) 삭제
- 폰트 패키지 정리

### Phase 2: API 레이어 정리
- `js/api.js`의 BackendHooks import를 하나씩 core/api/ 직접 import로 교체
- 모든 호출처 수정 완료 후 `js/api.js` 삭제

### Phase 3: 지도 도메인 통합
- `js/map*.js` + `js/map/` → `widgets/map/`으로 이동
- `js/markerPanel/` → `widgets/marker-card/`로 통합
- 중복되는 `widgets/map-overlay-controls/` vs `js/mapOverlayControls.js` 중 하나로 통합
- 이동 후 import 경로 일괄 수정

### Phase 4: views/ 실체화
- `js/home.js` → `views/home/home.js` 이동 (재export 제거)
- `js/settings.js` → `views/settings/settings.js`
- `js/account.js` → `views/account/account.js`
- `js/help.js` → `views/help/help.js`
- 각 이동 후 `views/*/index.js`를 실체 코드로 교체

### Phase 5: layouts/ 실체화
- `js/sidebar.js` + `js/managers/*` → `layouts/left-sidebar/`
- `js/theme.js` → `layouts/app-shell/`
- `js/notification.js` → `layouts/app-shell/`
- `js/mapHeightResizer.js` → `layouts/right-sidebar/`

### Phase 6: script.js 분해
- 가장 마지막, 가장 리스크 높음
- `script.js` 885줄을 각 view 초기화 코드로 분산
- 완료 후 script.js는 ~100줄의 부트스트랩만 남김

### Phase 7: js/ 폴더 정리
- `utils.js`, `assets.js`, `ui.js` → `core/utils.js`, `core/assets.js` 등으로 이동
- `js/` 폴더 삭제

---

## 6. 리스크 분석

| 작업 | 리스크 | 이유 |
|---|---|---|
| Phase 1 | 낮음 | 실코드 변경 없음, import 경로만 변경 |
| Phase 2 | 낮음 | BackendHooks → core/api 직접 호환됨 |
| Phase 3 | 중간 | iframe 통신 포함, map postMessage 경로 주의 |
| Phase 4 | 중간 | 파일 이동 + import 경로 수정 |
| Phase 5 | 중간 | 사이드바 매니저 4개 협력 구조, 순서 의존성 있음 |
| Phase 6 | 높음 | script.js 885줄이 state 공유, 클로저 의존성 많음 |
| Phase 7 | 낮음 | Phase 6 완료 후 단순 삭제 |

---

## 7. 완료 기준

- `js/` 폴더 없음 (utils/assets/ui 제외 또는 core/로 이동)
- `views/*/index.js` 모두 실체 코드 보유 (1줄 재export 없음)
- `layouts/*/index.js` 모두 실체 코드 보유
- `main.js` 없음 (또는 진짜 entry point 역할)
- `js/api.js` (BackendHooks) 없음
- `script.js` 100줄 이하 (부트스트랩만)
- Vite manualChunks로 map 청크 분리 확인
- 폰트 패키지 1개

---

## 8. 현재 건드리지 말 것

다음은 이미 잘 정리되어 있으므로 이번 리팩터링에서 제외:

- `core/api/` — 구조 완성됨
- `widgets/chat-message/` — 독립적, 잘 동작
- `widgets/invite-modal/` — 독립적
- `widgets/session-info-modal/` — 독립적
- `widgets/notification-panel/` — 독립적
- `css/` — 별도 논의 필요 시 독립 진행
- 백엔드 전체 — 프론트 리팩터링과 무관
