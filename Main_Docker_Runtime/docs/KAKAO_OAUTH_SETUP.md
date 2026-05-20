# 카카오 OAuth 설정 가이드

## 개요

카카오 로그인을 사용하려면 `setting/.env` 파일에 아래 3개의 키를 설정해야 한다.

```
KAKAO_CLIENT_ID=
KAKAO_CLIENT_SECRET=
KAKAO_REDIRECT_URI=
```

---

## 1. KAKAO_CLIENT_ID (필수)

**REST API 키**다.

1. [developers.kakao.com](https://developers.kakao.com) → 로그인
2. **내 애플리케이션** → 앱 선택 (없으면 새로 추가)
3. **앱 키** 탭 → **REST API 키** 값 복사 → `KAKAO_CLIENT_ID`에 입력

---

## 2. KAKAO_CLIENT_SECRET (선택)

없어도 로그인은 동작한다. 보안 강화 시 사용.

1. 앱 선택 → **제품 설정** → **카카오 로그인** → **보안** 탭
2. **Client Secret 코드 생성** → 값 복사 → `KAKAO_CLIENT_SECRET`에 입력
3. 비워두면 백엔드가 자동으로 생략

---

## 3. KAKAO_REDIRECT_URI (필수)

백엔드가 카카오로부터 인증 코드를 받는 콜백 주소.  
**카카오 개발자 콘솔에 등록한 값과 `.env` 값이 반드시 일치해야 한다.**

### 콘솔에 등록하는 방법

1. 앱 선택 → **제품 설정** → **카카오 로그인** → 활성화 **ON**
2. **Redirect URI 등록** → 추가 → 아래 값 입력

| 환경 | URI |
|------|-----|
| 로컬 테스트 | `http://localhost:8000/api/auth/kakao/callback` |
| 실서버 | `https://your-domain.com/api/auth/kakao/callback` |

> 두 환경을 동시에 등록해두면 로컬/운영 전환 시 편리하다.

---

## 4. 동의항목 설정 (필수)

앱 선택 → **제품 설정** → **카카오 로그인** → **동의항목**

| 항목 | 설정 |
|------|------|
| 닉네임 | 필수 동의 |
| 카카오계정(이메일) | 선택 동의 이상 |

---

## 최종 .env 예시

```env
KAKAO_CLIENT_ID=abcdef1234567890abcdef1234567890
KAKAO_CLIENT_SECRET=                          # 비워도 됨
KAKAO_REDIRECT_URI=http://localhost:8000/api/auth/kakao/callback
```

---

## 설정 후 백엔드 재시작

```bash
docker compose -f docker-compose-system.yml restart
```

---

## 로그인 흐름 요약

```
프론트엔드 버튼 클릭
  → GET /api/auth/kakao
  → 카카오 인증 페이지로 리다이렉트
  → 사용자 카카오 로그인 승인
  → GET /api/auth/kakao/callback?code=...
  → 백엔드에서 토큰 발급 후 처리
  → GET /?access_token=...&refresh_token=...&user_id=...&nickname=...&email=...
  → 프론트엔드 script.js가 URL 파라미터 읽어 localStorage 저장
  → URL 클린업 후 홈 화면 표시
```
