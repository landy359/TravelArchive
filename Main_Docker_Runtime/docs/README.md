# TravelArchive 공식 문서

## 📚 문서 네비게이션

### 🌍 프로젝트 개요
- **[CONCEPT.md](CONCEPT.md)** - 서비스 콘셉트 및 핵심 기능
  - 멀티패널 협업 플래닝 경험
  - 봇과 사용자 간 상호작용 흐름
  - 구현 현황

### 🏗️ 기술 아키텍처
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - 프론트엔드 모듈 구조 (업데이트: 2026-04-10)
  - 파일 구조 & 의존성 트리
  - 데이터 흐름 다이어그램
  - 모듈 책임 분배
  - 새 기능 추가 방법

### 🔌 API 명세
- **[API_SPECIFICATION.md](API_SPECIFICATION.md)** - 프론트엔드-백엔드 인터페이스
  - 모든 API 엔드포인트
  - 요청/응답 포맷
  - 인증, 세션, 채팅, 지도, 달력, 일정, 메모 등

- **[FRONTEND_API.md](FRONTEND_API.md)** - 프론트엔드 내부 API
  - BackendHooks (API 클라이언트)
  - UI 유틸리티
  - 유틸 함수

### 🔐 인증 시스템
- **[AUTH_SYSTEM_ROADMAP.md](AUTH_SYSTEM_ROADMAP.md)** - 인증 시스템 로드맵
  - 현재 구현 상태
  - 향후 계획

### 🚀 배포 & 인프라
- **[RASPBERRY_PI_SETUP.md](RASPBERRY_PI_SETUP.md)** - Raspberry Pi 4B+ 환경 구축 가이드
  - OS 설치부터 서비스 기동까지 전체 순서
  - Docker, DuckDNS, SSL 설정
  - 재부팅 자동 기동 설정

---

## 🚀 빠른 시작

### 프로젝트 구조 이해하기
```
1. CONCEPT.md 읽기          → 서비스 전체 아이디어 이해
2. ARCHITECTURE.md 읽기     → 프론트엔드 기술 구조 파악
3. API_SPECIFICATION.md 읽기 → 데이터 통신 방식 이해
```

### 새 기능 추가하기
```
1. ARCHITECTURE.md의 "새 기능 추가 시 연결점" 섹션 참고
2. 매니저 모듈 생성 (js/managers/*)
3. HTML 프래그먼트 추가 (html/fragments/*)
4. CSS 파일 추가 (css/*)
5. API 엔드포인트 필요시 API_SPECIFICATION.md에 문서화
```

---

## 📋 문서 유지보수 체크리스트

### 매월 첫 주
- [ ] 서비스 콘셉트 변경사항 반영
- [ ] API 엔드포인트 추가/삭제 확인

### 새 기능 추가 시
- [ ] CONCEPT.md의 "구현 현황" 테이블 업데이트
- [ ] API_SPECIFICATION.md에 새 엔드포인트 추가
- [ ] ARCHITECTURE.md의 의존성 트리 업데이트

### 매 분기마다
- [ ] 전체 문서 검토 및 정확성 확인
- [ ] 링크 유효성 확인
- [ ] 용어 일관성 확인

---

## 📝 문서 작성 가이드

### 제목 규칙
- 파일명: `UPPERCASE_WITH_UNDERSCORE.md` (영문)
- 문서 제목: `# 한국어 또는 영문`

### 구조
```markdown
# 제목

> 작성일: YYYY-MM-DD / 버전: X.X

## 목차
- [섹션 1](#섹션-1)
- [섹션 2](#섹션-2)

## 섹션 1
...

## 섹션 2
...

---

## 관련 문서
- [다른 문서](OTHER.md)
```

### 코드 블록
```python
# 코드는 언어 명시
def hello():
    print("Hello")
```

### 다이어그램
- 텍스트 기반 다이어그램 (ASCII art)
- 권장: Tree, Flow, Matrix 형식

---

## 🔗 외부 리소스

- **프론트엔드 소스**: `frontend/src/`
- **백엔드 소스**: `backend/`
- **배포**: Docker를 통한 컨테이너화

---

## 📞 문서 업데이트 요청

새로운 내용이나 수정사항이 있으면:
1. 해당 문서에 **작성일** 및 **변경 사항**을 기록
2. 버전 번호 업데이트 (최상단 참고)
3. 관련된 다른 문서의 링크 또는 참고사항 확인

---

**마지막 업데이트**: 2026-04-10  
**담당**: Bae_JH
