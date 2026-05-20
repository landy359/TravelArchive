# Frontend Architecture - Dependency & Data Flow

## 파일 구조 트리 (의존성 포함)

```
frontend/src/
│
├── script.js (앱 초기화 - 라우터)
│   │
│   ├──→ SessionManager (세션 목록)
│   │   ├──→ api.js (백엔드 API)
│   │   ├──→ assets.js (SVG 아이콘)
│   │   ├──→ utils.js (유틸)
│   │   └──→ ui.js (UI 유틸)
│   │
│   ├──→ CalendarManager (달력)
│   │   ├──→ api.js
│   │   ├──→ utils.js
│   │   └──→ event-bus.js ⬅️ EMITS: CALENDAR_DATE_SELECTED
│   │
│   ├──→ ScheduleManager (직접 렌더)
│   │   └──→ utils.js
│   │
│   ├──→ SidebarManager (파사드 - 모든 사이드바 기능)
│   │   │
│   │   ├──→ SidebarBase (sidebar-base.js)
│   │   │   └── open/close/mobile detection
│   │   │
│   │   ├──→ SidebarTabs (sidebar-tabs.js)
│   │   │   ├──→ CalendarManager.updateUI()
│   │   │   ├──→ event-bus (SIDEBAR_TAB_CHANGED)
│   │   │   └── 탭 전환 + memo 높이 조정
│   │   │
│   │   ├──→ SidebarResizer (sidebar-resizer.js)
│   │   │   ├──→ api.js (설정 저장)
│   │   │   └── 드래그 리사이징 로직
│   │   │
│   │   ├──→ SidebarFolding (sidebar-folding.js)
│   │   │   ├──→ SidebarTabs.adjustAllMemoHeights()
│   │   │   ├──→ MemoManager.init() ⬅️
│   │   │   ├──→ ScheduleManager.init() ⬅️
│   │   │   └── 접기/펴기 + 리사이저블 위젯
│   │   │
│   │   ├──→ MemoManager (memo-manager.js)
│   │   │   ├──→ api.js (메모 저장/로드)
│   │   │   ├──→ CalendarManager.getSelectedDate()
│   │   │   ├──→ CalendarManager.refreshDots()
│   │   │   ├──→ utils.js (debounce)
│   │   │   ├──→ event-bus (MEMO_UPDATED)
│   │   │   └── 메모 CRUD
│   │   │
│   │   └──→ ScheduleManager (schedule-manager.js)
│   │       ├──→ api.js (스케줄 저장/로드)
│   │       ├──→ CalendarManager.getSelectedDate()
│   │       ├──→ CalendarManager.refreshDots()
│   │       ├──→ utils.js (debounce)
│   │       ├──→ event-bus (SCHEDULE_UPDATED)
│   │       └── 스케줄 CRUD
│   │
│   ├──→ ChatManager (채팅)
│   │   ├──→ api.js
│   │   ├──→ ui.js
│   │   ├──→ router.js
│   │   └──→ SessionManager
│   │
│   ├──→ router.js (URL 라우팅)
│   │   ├──→ api.js
│   │   ├──→ SidebarManager
│   │   └──→ ui.js
│   │
│   ├──→ ThemeManager
│   │   ├──→ api.js
│   │   └──→ weatherManager.js
│   │
│   └── 기타: theme.js, help.js, account.js, settings.js
│
├── js/core/ (인프라)
│   ├── event-bus.js (pub-sub 시스템)
│   │   └─── eventBus.on(), .emit(), .once(), .off()
│   │
│   └── module-registry.js (모듈 생명주기)
│       └─── moduleRegistry.register(), .initAll(), .renderAll()
│
├── js/managers/ (기능별 매니저)
│   ├── sidebar-base.js → SidebarBase
│   ├── sidebar-tabs.js → SidebarTabs
│   ├── sidebar-resizer.js → SidebarResizer
│   ├── sidebar-folding.js → SidebarFolding ⭐ (memo/schedule 초기화)
│   ├── memo-manager.js → MemoManager
│   └── schedule-manager.js → ScheduleManager
│
├── js/
│   ├── sidebar.js (파사드)
│   │   └─── 모든 메서드를 위 매니저들로 위임
│   │
│   ├── calendar.js (달력 + 이벤트 발행)
│   │   └─── CALENDAR_DATE_SELECTED 이벤트 발행
│   │
│   ├── api.js (백엔드 API 클라이언트)
│   │   ├── fetchAppContext()
│   │   ├── saveMemo() / fetchMemo()
│   │   ├── updateSchedule() / fetchSchedule()
│   │   ├── fetchTripRange()
│   │   └── 40+ 기타 API 메서드
│   │
│   ├── ui.js (DOM 유틸)
│   │   ├── showToast()
│   │   ├── appendMessage()
│   │   └── adjustTextareaHeight()
│   │
│   ├── utils.js (공용 유틸)
│   │   ├── debounce()
│   │   ├── renderTemplate()
│   │   ├── createElementFromHTML()
│   │   └── getSessionIdFromHash()
│   │
│   ├── assets.js (SVG 아이콘 라이브러리)
│   ├── templates.js (HTML 프래그먼트 임포트)
│   ├── router.js (URL 해시 라우팅)
│   ├── theme.js (테마 관리)
│   ├── session.js (세션 목록)
│   ├── chat.js (채팅)
│   ├── help.js, account.js, settings.js (페이지 모듈)
│   └── weatherManager.js (날씨 데이터)
│
├── html/
│   ├── index.html (메인 페이지)
│   ├── map.html (지도 iframe)
│   └── fragments/
│       ├── calendar.html ← CalendarManager.render()에서 사용
│       ├── schedule.html ← ScheduleManager.render()에서 사용
│       ├── session_item.html
│       ├── message.html
│       ├── settings.html
│       ├── account.html
│       ├── help.html
│       ├── loading.html
│       └── user_search.html
│
└── css/
    ├── base.css (전역)
    ├── layout.css (그리드)
    ├── left_sidebar.css
    ├── right_sidebar.css
    ├── chat.css
    ├── pages.css
    ├── theme.css
    ├── responsive.css
    ├── map.css
    ├── assets/
    │   ├── buttons.css
    │   ├── cards.css
    │   └── forms.css
    └── styles.css (메인 import)
```

---

## 데이터 흐름 (Data Flow Diagram)

### 1️⃣ 앱 초기화 흐름

```
script.js DOMContentLoaded
    ↓
BackendHooks.fetchAppContext()
    ↓ (elements 수집, state 초기화)
    ├──→ SessionManager.init(elements, state) ✅ 세션 목록 로드
    ├──→ CalendarManager.init(todayDate) ✅ 달력 초기화
    ├──→ CalendarManager.render(container) ✅ 달력 HTML 렌더
    ├──→ ScheduleManager.render(container) ✅ 스케줄 초기화
    │
    └──→ SidebarManager 초기화 (순서 중요)
        ├──→ initTabs(elements)
        │   └─ CalendarManager.onDateSelect = (date) => { 
        │      eventBus.emit(CALENDAR_DATE_SELECTED, {date}) }
        │
        ├──→ initResizers(elements, config)
        │   └─ 좌/우 사이드바 리사이징 설정
        │
        └──→ initFolding(elements)
            ├─ 접기/펴기 토글 설정
            └─ MemoManager.init(elements) ⭐ (버튼 바인딩)
            └─ ScheduleManager.init(elements) ⭐ (버튼 바인딩)
                ├──→ 메모 행 바인딩 완료
                └──→ 스케줄 행 바인딩 완료

    ↓
router(state, elements) ✅ 초기 라우팅
    ↓
window.addEventListener('hashchange', router) ✅ 라우팅 리스너
```

### 2️⃣ 사용자가 달력 날짜 선택

```
사용자 클릭 → CalendarManager.setSelectedDate(date)
    ↓
calendar.js 내부:
    1. selectedDate = new Date(date)
    2. CalendarManager.updateUI() (달력 UI 업데이트)
    3. eventBus.emit(CALENDAR_DATE_SELECTED, {date, sessionId}) ⭐ 이벤트 발행
    4. CalendarManager.onDateSelect(date) (콜백 - 하위호환성)
    ↓
sidebar-tabs.js 리스너:
    CalendarManager.onDateSelect = (date) => {
        eventBus.emit(CALENDAR_DATE_SELECTED, {date})
    }
    ↓
memo-manager.js 리스너 (onDateSelect 콜백):
    await MemoManager.initMemoRows(elements)
        ├──→ BackendHooks.fetchMemo(sessionId, dateKey)
        ├──→ API에서 메모 데이터 로드
        └──→ UI 업데이트
    ↓
schedule-manager.js 리스너 (onDateSelect 콜백):
    await ScheduleManager.initScheduleRows(elements)
        ├──→ BackendHooks.fetchSchedule(sessionId, dateKey)
        ├──→ API에서 스케줄 데이터 로드
        └──→ UI 업데이트

결과: 메모/스케줄 UI가 선택된 날짜의 데이터로 업데이트됨 ✅
```

### 3️⃣ 사용자가 메모 입력

```
사용자 타입 → memo-manager.js의 input 이벤트 핸들러
    ↓
textarea.addEventListener('input', () => {
    adjustHeight(textarea)
    saveMemos(tableBody, getInfo) ⭐ debounce(500ms)
})
    ↓
500ms 후 (debounce):
    1. 모든 메모 textarea 값 수집
    2. BackendHooks.saveMemo(sessionId, allMemos, dateKey)
    3. API 호출 → 백엔드 저장
    4. CalendarManager.refreshDots() (달력 점 업데이트)
    5. eventBus.emit(MEMO_UPDATED, {sessionId, dateKey, content})
    ↓
다른 모듈 (필요시):
    eventBus.on(EVENTS.MEMO_UPDATED, (data) => {
        // 메모 업데이트 감지 → 반응
    })

결과: 메모 저장 + 달력 인디케이터 업데이트 ✅
```

### 4️⃣ 탭 전환 (세션 ↔ 달력)

```
사용자 클릭 → "달력" 탭 버튼
    ↓
sidebar-tabs.js의 tabCalendar 클릭 핸들러
    ↓
switchTab(tabCalendar, tabSessions, calendarView, sessionView, ...)
    1. 탭 활성화 클래스 토글
    2. 뷰 display 토글 (flex ↔ none)
    3. setTimeout(() => {
        SidebarTabs.adjustAllMemoHeights()
        CalendarManager.updateUI()
        eventBus.emit(SIDEBAR_TAB_CHANGED, {tab: 'calendar'})
    }, 0)
    ↓
결과: 달력 탭이 활성화되고, 메모 높이 조정됨 ✅
```

### 5️⃣ 사이드바 리사이징

```
사용자 드래그 → 리사이저 핸들
    ↓
sidebar-resizer.js의 mousedown → mousemove → mouseup
    ↓
mousemove 중:
    1. 마우스 이동거리 계산 (delta)
    2. 새 너비 계산 (MIN/MAX 제약 적용)
    3. sidebar.style.width = newWidth + 'px'
    4. config.currentLeftWidth = newWidth (메모리에 저장)
    5. window.updatePlaceholder() (채팅 입력창 placeholder 업데이트)
    6. 우측 사이드바(맵)이면: mapFrame.contentWindow.postMessage({type: 'relayout'})
    ↓
mouseup 후:
    1. 리사이저 활성화 제거 (UI 피드백)
    2. BackendHooks.saveUserSetting(key, newWidth)
    3. API 호출 → 백엔드에 설정 저장
    ↓
다음 앱 로드시:
    script.js의 state 초기화에서 저장된 너비 로드 ✅
```

### 6️⃣ 섹션 접기/펴기 (메모, 스케줄, 달력)

```
사용자 클릭 → 접기 버튼
    ↓
sidebar-folding.js의 setupFolding 핸들러
    ↓
toggle(true) // 접기
    1. content.classList.add('section-content-collapsed')
    2. btn.classList.add('collapsed')
    3. 행 버튼들 비활성화
    ↓
사용자 클릭 → 펴기 버튼
    ↓
toggle(false) // 펴기
    1. content.classList.remove('section-content-collapsed')
    2. btn.classList.remove('collapsed')
    3. 행 버튼들 활성화
    4. if (isMemoContent):
        setTimeout(() => SidebarTabs.adjustAllMemoHeights(), 10)
    ↓
결과: 메모 높이 재계산으로 모든 텍스트 표시 ✅
```

---

## 이벤트 흐름 (Event Flow)

```
┌─────────────────────────────────────────────────────┐
│               Event Bus (eventBus.js)                │
│                                                      │
│  Singleton pub-sub Event System                     │
│                                                      │
│  eventBus.on(EVENTS.X, callback)                   │
│  eventBus.emit(EVENTS.X, data)                     │
└─────────────────────────────────────────────────────┘
         ↑              ↑              ↑
         │              │              │
    [발행처]         [발행처]       [발행처]
         │              │              │
         ▼              ▼              ▼

CALENDAR_DATE_SELECTED          MEMO_UPDATED              SCHEDULE_UPDATED
  ← calendar.js                  ← memo-manager.js         ← schedule-manager.js
  ← sidebar-tabs.js              
         │                              │                          │
         ├────────[구독처]────────┐     ├──[구독처]──┐             │
         │                        │     │           │             │
         ▼                        ▼     ▼           ▼             ▼
   memo-manager.js          [미래 모듈들]    [미래 모듈들]   [미래 모듈들]
   schedule-manager.js
         │
    메모/스케줄
    새로고침
```

---

## API 호출 흐름 (BackendHooks)

```
script.js
    ↓
BackendHooks.fetchAppContext()
    → GET /api/context (테마, 너비, 날짜 설정)
    ↓
CalendarManager.setSelectedDate()
    ↓
MemoManager 또는 ScheduleManager
    │
    ├──→ BackendHooks.fetchMemo(sessionId, dateKey)
    │   → GET /api/memo/{sessionId}?date={dateKey}
    │   ← 메모 텍스트 반환
    │
    ├──→ BackendHooks.saveMemo(sessionId, memo, dateKey)
    │   → POST /api/memo/{sessionId} ({memo, dateKey})
    │   ← 저장 완료
    │
    ├──→ BackendHooks.fetchSchedule(sessionId, dateKey)
    │   → GET /api/schedule/{sessionId}?date={dateKey}
    │   ← [{time, activity}, ...] 반환
    │
    └──→ BackendHooks.updateSchedule(sessionId, plan, dateKey)
        → POST /api/schedule/{sessionId} ({plan, dateKey})
        ← 저장 완료

CalendarManager.refreshDots()
    ↓
BackendHooks.fetchTripRange(sessionId)
    → GET /api/trip-range/{sessionId}
    ← 여행 기간 범위 반환 (달력에 표시)
```

---

## 모듈 책임 분배 (Responsibility Matrix)

```
┌──────────────────┬──────────┬──────────┬──────────┬────────────┐
│ 기능              │ 열기/닫기 │ 탭 전환  │ 리사이즈 │ 접기/펴기  │
├──────────────────┼──────────┼──────────┼──────────┼────────────┤
│ SidebarBase      │    ✅    │          │          │            │
│ SidebarTabs      │          │    ✅    │          │            │
│ SidebarResizer   │          │          │    ✅    │            │
│ SidebarFolding   │          │          │          │     ✅     │
│ MemoManager      │          │          │          │            │
│ ScheduleManager  │          │          │          │            │
└──────────────────┴──────────┴──────────┴──────────┴────────────┘

┌──────────────────┬──────────┬──────────┬──────────┬────────────┐
│ 기능              │ 메모 CRUD│ 스케줄   │ 버튼     │ 데이터     │
│                  │ 작업     │ CRUD     │ 바인딩   │ 로드       │
├──────────────────┼──────────┼──────────┼──────────┼────────────┤
│ MemoManager      │    ✅    │          │    ✅    │     ✅     │
│ ScheduleManager  │          │    ✅    │    ✅    │     ✅     │
│ SidebarFolding   │          │          │          │            │
└──────────────────┴──────────┴──────────┴──────────┴────────────┘
```

---

## 새 기능 추가 시 연결점

```
새로운 "여행지 메모" 기능 추가 예시
│
├─ 1. Destination Manager 만들기
│   └─ js/managers/destination-manager.js
│      ├── CalendarManager.getSelectedDate() 사용
│      ├── BackendHooks.saveDestination() 호출
│      └── eventBus.emit(DESTINATION_UPDATED) 발행
│
├─ 2. HTML Fragment 추가
│   └─ html/fragments/destination.html
│
├─ 3. CSS 추가
│   └─ css/destination.css
│
└─ 4. script.js에서 초기화
    └─ DestinationManager.init(elements)

연결 완료! ✅
```

---

## 하위 호환성 보장 구조

```
기존 코드 (script.js)
│
└──→ SidebarManager.initTabs(elements)
     └──→ sidebar.js (파사드)
          └──→ SidebarTabs.initTabs() (새로운 구현)
                └──→ 동일한 결과 반환

기존 코드
│
└──→ CalendarManager.onDateSelect = (date) => { ... }
     └──→ calendar.js에서 여전히 호출됨
          └──→ 기존 콜백 실행 ✅
          └──→ + 새로운 이벤트 발행 (추가 기능)

결론: 기존 코드는 변경 없음, 새 기능 추가됨 🎯
```

---

## 성능 최적화 포인트

```
✅ debounce 사용
   - saveMemos(500ms)
   - saveSchedules(500ms)
   → 빠른 타이핑 중 불필요한 API 호출 방지

✅ 조건부 렌더링
   - CalendarManager.updateUI()만 필요할 때 호출
   - initFolding() 토글 시에만 높이 재계산

✅ 이벤트 위임
   - 매니저 간 직접 호출 대신 이벤트 발행
   → 느슨한 결합으로 메모리 누수 방지

✅ CSS 클래스 토글
   - display 토글 (display: none으로 DOM 제거 안 함)
   → DOM 재생성 비용 절감
```
