# Raspberry Pi 4B+ 환경 구축 가이드

> 작성일: 2026-04-28 / 버전: 1.0

## 목차
- [전체 구성 요약](#전체-구성-요약)
- [STEP 1 — Raspberry Pi OS 설치](#step-1--raspberry-pi-os-설치)
- [STEP 2 — OS 기본 설정](#step-2--os-기본-설정)
- [STEP 3 — Docker 설치](#step-3--docker-설치)
- [STEP 4 — 포트 및 방화벽 설정](#step-4--포트-및-방화벽-설정)
- [STEP 5 — DuckDNS 도메인 설정](#step-5--duckdns-도메인-설정-lets-encrypt-ssl용)
- [STEP 6 — 프로젝트 클론](#step-6--프로젝트-클론)
- [STEP 7 — 환경변수 설정](#step-7--환경변수-설정-env)
- [STEP 8 — Nginx 도메인 설정](#step-8--nginx-도메인-설정)
- [STEP 9 — Docker 네트워크 생성](#step-9--docker-네트워크-생성)
- [STEP 10 — 서비스 기동 순서](#step-10--서비스-기동-순서)
- [STEP 11 — 정상 동작 확인](#step-11--정상-동작-확인)
- [STEP 12 — 재부팅 후 자동 기동 설정](#step-12--재부팅-후-자동-기동-설정)
- [전체 순서 요약 체크리스트](#전체-순서-요약-체크리스트)
- [주의 사항](#주의-사항)

---

## 전체 구성 요약

**대상 하드웨어**: Raspberry Pi 4B+ 8GB RAM

| 구성 요소 | 기술 |
|---|---|
| Backend | FastAPI (Python 3.10) |
| Frontend | Vite + Vanilla JS → Nginx |
| DB | PostgreSQL 18 + PostGIS |
| Cache | Redis 7 |
| Reverse Proxy | Nginx + Certbot (Let's Encrypt) |
| LLM | OpenAI / Gemini / Perplexity API |
| Network | Docker 외부 네트워크 (`TravelArchiveNetwork`) |

---

## STEP 1 — Raspberry Pi OS 설치

### 1-1. OS 이미지 다운로드 및 플래싱

```
Raspberry Pi Imager 사용 (공식 도구)
- OS 선택: Raspberry Pi OS (64-bit) — Bookworm 기반
  → "Lite" 버전 권장 (GUI 불필요, 메모리 절약)
  → 반드시 64-bit 선택 (ARM64 Docker 이미지 필수)
- MicroSD: 최소 32GB, Class 10 이상 권장
```

### 1-2. Imager 고급 설정 (플래싱 전 설정)

```
- 호스트명: raspberrypi (또는 원하는 이름)
- SSH 활성화: ON (패스워드 또는 공개키 방식)
- 사용자명/패스워드: pi / 원하는 비밀번호
- Wi-Fi 설정: SSID / 비밀번호 입력 (유선 권장)
- 로케일: Asia/Seoul, ko_KR
```

### 1-3. 부팅 및 초기 접속

```bash
# 같은 네트워크에서 SSH 접속
ssh pi@raspberrypi.local
# 또는 IP로 직접 접속
ssh pi@<라즈베리파이_IP>
```

---

## STEP 2 — OS 기본 설정

### 2-1. 시스템 업데이트

```bash
sudo apt update && sudo apt upgrade -y
sudo apt autoremove -y
```

### 2-2. 필수 패키지 설치

```bash
sudo apt install -y \
  git \
  curl \
  wget \
  nano \
  htop \
  ufw \
  net-tools \
  ca-certificates \
  gnupg \
  lsb-release \
  apt-transport-https \
  software-properties-common
```

### 2-3. 스왑 메모리 설정 (Docker 빌드 시 안정성 확보)

```bash
# 현재 스왑 확인
free -h

# 기존 스왑 비활성화 후 2GB로 설정
sudo dphys-swapfile swapoff
sudo nano /etc/dphys-swapfile
# → CONF_SWAPSIZE=2048 으로 수정

sudo dphys-swapfile setup
sudo dphys-swapfile swapon
```

### 2-4. 타임존 설정

```bash
sudo timedatectl set-timezone Asia/Seoul
timedatectl status  # 확인
```

### 2-5. 고정 IP 설정 (네트워크 안정성)

```bash
# 유선 랜 고정 IP 예시
sudo nano /etc/dhcpcd.conf

# 파일 끝에 추가:
interface eth0
static ip_address=192.168.1.XXX/24
static routers=192.168.1.1
static domain_name_servers=8.8.8.8 8.8.4.4
```

```bash
sudo systemctl restart dhcpcd
```

---

## STEP 3 — Docker 설치

### 3-1. Docker 공식 설치 (ARM64 대응)

```bash
# GPG 키 추가
curl -fsSL https://download.docker.com/linux/debian/gpg | \
  sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

# 저장소 추가 (ARM64)
echo \
  "deb [arch=arm64 signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] \
  https://download.docker.com/linux/debian \
  $(lsb_release -cs) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Docker 설치
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

### 3-2. pi 사용자 Docker 그룹 추가 (sudo 없이 사용)

```bash
sudo usermod -aG docker pi
newgrp docker  # 또는 재접속
```

### 3-3. Docker 서비스 자동 시작 등록

```bash
sudo systemctl enable docker
sudo systemctl start docker
docker --version        # 확인
docker compose version  # 확인
```

---

## STEP 4 — 포트 및 방화벽 설정

### 4-1. UFW 방화벽 설정

```bash
sudo ufw enable
sudo ufw allow ssh          # 22
sudo ufw allow 80/tcp       # HTTP (Certbot 인증 + 리다이렉트)
sudo ufw allow 443/tcp      # HTTPS (실제 서비스)
sudo ufw allow 6379/tcp     # Redis (내부 모니터링용, 필요시)
sudo ufw allow 5540/tcp     # RedisInsight (필요시)
sudo ufw status
```

### 4-2. 공유기 포트포워딩 (외부 HTTPS 접속용)

```
공유기 관리페이지 접속 → 포트포워딩 설정:
- 외부 80  → 내부 <라즈베리파이IP>:80
- 외부 443 → 내부 <라즈베리파이IP>:443
```

---

## STEP 5 — DuckDNS 도메인 설정 (Let's Encrypt SSL용)

### 5-1. DuckDNS 설정

```
1. https://www.duckdns.org 접속
2. 도메인 생성 (예: mytravelarchive.duckdns.org)
3. 현재 공인 IP 등록
```

### 5-2. DuckDNS 자동 IP 갱신 스크립트 설치

```bash
mkdir -p ~/duckdns
nano ~/duckdns/duck.sh
```

```bash
# duck.sh 내용
echo url="https://www.duckdns.org/update?domains=<YOUR_DOMAIN>&token=<YOUR_TOKEN>&ip=" \
  | curl -k -o ~/duckdns/duck.log -K -
```

```bash
chmod 700 ~/duckdns/duck.sh

# 크론 등록 (5분마다 갱신)
crontab -e
# 추가:
*/5 * * * * ~/duckdns/duck.sh >/dev/null 2>&1
```

---

## STEP 6 — 프로젝트 클론

### 6-1. 저장 위치 결정 및 클론

```bash
cd /home/pi

git clone https://github.com/<YOUR_ORG>/TravelArchive.git

cd TravelArchive/Team_Workspace/Bae_JH/Main_Docker_Runtime
```

### 6-2. 필요한 디렉토리 생성

```bash
# 프로젝트 루트에서 실행
mkdir -p db/data
mkdir -p db/redis_data
mkdir -p certbot/conf
mkdir -p certbot/www
mkdir -p uploads
```

---

## STEP 7 — 환경변수 설정 (.env)

```bash
cp setting/.env.sample setting/.env
nano setting/.env
```

### 입력해야 할 값 전체 목록

```bash
# ===== LLM API Keys =====
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=AIza...
PERPLEXITY_API_KEY=pplx-...

# ===== PostgreSQL =====
POSTGRES_USER=travel_user
POSTGRES_PASS=<강력한_비밀번호>
POSTGRES_DB=travel_archive

# ===== Database Connection =====
DB_HOST=TA_db          # Docker 서비스명 그대로
DB_PORT=5432
DATABASE_URL=postgresql://<POSTGRES_USER>:<POSTGRES_PASS>@TA_db:5432/<POSTGRES_DB>

# ===== Redis =====
REDIS_HOST=TA_redis    # Docker 서비스명 그대로
REDIS_PORT=6379
REDIS_PASSWORD=<강력한_비밀번호>
REDIS_DB_INDEX=0
REDIS_URL=redis://:<REDIS_PASSWORD>@TA_redis:6379/0

# ===== JWT =====
ACCESS_TOKEN_SECRET_KEY=<랜덤_긴_문자열>
REFRESH_TOKEN_SECRET_KEY=<랜덤_긴_문자열>
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# ===== Frontend =====
VITE_KAKAO_MAP_KEY=<카카오_지도_앱_키>

# ===== Admin (선택) =====
PGADMIN_DEFAULT_EMAIL=admin@example.com
PGADMIN_DEFAULT_PASSWORD=<비밀번호>
```

### JWT Secret 키 생성 방법

```bash
python3 -c "import secrets; print(secrets.token_hex(64))"
# 위 명령을 2번 실행해서 ACCESS / REFRESH 각각 사용
```

---

## STEP 8 — Nginx 도메인 설정

```bash
nano nginx/default.conf
```

```nginx
# 모든 도메인 값을 본인 DuckDNS 도메인으로 교체
server_name <YOUR_DOMAIN>.duckdns.org;

# SSL 인증서 경로도 도메인에 맞게 수정
ssl_certificate /etc/letsencrypt/live/<YOUR_DOMAIN>.duckdns.org/fullchain.pem;
ssl_certificate_key /etc/letsencrypt/live/<YOUR_DOMAIN>.duckdns.org/privkey.pem;
```

---

## STEP 9 — Docker 네트워크 생성

```bash
# 모든 서비스가 공유하는 외부 네트워크 (반드시 먼저 생성)
docker network create TravelArchiveNetwork
docker network ls  # 확인
```

---

## STEP 10 — 서비스 기동 순서

### 10-1. PostgreSQL DB 먼저 기동

```bash
docker compose -f docker-compose-db.yml up -d
docker logs TA_db -f  # 초기화 완료 확인 (PostGIS 익스텐션 설치 로그)
```

### 10-2. Redis 기동

```bash
docker compose -f docker-compose-redis.yml up -d
docker logs TA_redis  # 확인
```

### 10-3. Alembic 데이터베이스 마이그레이션

```bash
# Backend 이미지를 먼저 빌드 후 마이그레이션 실행
docker compose -f docker-compose-system.yml build

docker compose -f docker-compose-system.yml run --rm backend \
  python -m alembic upgrade head
```

### 10-4. Backend 기동

```bash
docker compose -f docker-compose-system.yml up -d
docker logs TA_backend -f  # FastAPI 시작 확인
```

### 10-5. SSL 인증서 최초 발급 (HTTP 임시 설정으로)

```bash
# Nginx를 HTTP 전용 설정으로 먼저 기동
cp nginx/certified.conf nginx/default.conf  # HTTPS 블록 제거된 설정으로 교체

docker compose -f docker-compose-nginx.yml build
docker compose -f docker-compose-nginx.yml up -d

# Certbot으로 인증서 발급
docker run --rm \
  -v $(pwd)/certbot/conf:/etc/letsencrypt \
  -v $(pwd)/certbot/www:/var/www/certbot \
  certbot/certbot certonly \
  --webroot \
  --webroot-path=/var/www/certbot \
  --email <YOUR_EMAIL> \
  --agree-tos \
  --no-eff-email \
  -d <YOUR_DOMAIN>.duckdns.org
```

### 10-6. HTTPS 설정으로 Nginx 재기동

```bash
# HTTPS 설정 파일로 복원 후 재빌드
docker compose -f docker-compose-nginx.yml down
docker compose -f docker-compose-nginx.yml build
docker compose -f docker-compose-nginx.yml up -d
```

---

## STEP 11 — 정상 동작 확인

```bash
# 전체 컨테이너 상태 확인
docker ps -a

# 예상 출력:
# TA_backend       Up
# TA_db            Up
# TA_redis         Up
# TA_redis_insight Up
# TA_nginx         Up
# TA_certbot       Up
```

```bash
# 브라우저에서 확인
https://<YOUR_DOMAIN>.duckdns.org       # 프론트엔드
https://<YOUR_DOMAIN>.duckdns.org/api/  # 백엔드 API
http://<라즈베리파이_IP>:5540           # RedisInsight
```

---

## STEP 12 — 재부팅 후 자동 기동 설정

```bash
# systemd 서비스 파일 생성
sudo nano /etc/systemd/system/travelarchive.service
```

```ini
[Unit]
Description=TravelArchive Docker Services
Requires=docker.service
After=docker.service network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/home/pi/TravelArchive/Team_Workspace/Bae_JH/Main_Docker_Runtime
ExecStart=/bin/bash -c '\
  docker compose -f docker-compose-db.yml up -d && \
  sleep 10 && \
  docker compose -f docker-compose-redis.yml up -d && \
  docker compose -f docker-compose-system.yml up -d && \
  docker compose -f docker-compose-nginx.yml up -d'
ExecStop=/bin/bash -c '\
  docker compose -f docker-compose-nginx.yml down && \
  docker compose -f docker-compose-system.yml down && \
  docker compose -f docker-compose-redis.yml down && \
  docker compose -f docker-compose-db.yml down'
User=pi

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable travelarchive
sudo systemctl start travelarchive
```

---

## 전체 순서 요약 체크리스트

```
[ ] 1.  Raspberry Pi OS 64-bit (Bookworm Lite) 설치 및 SSH 활성화
[ ] 2.  OS 업데이트 및 필수 패키지 설치
[ ] 3.  스왑 2GB 설정
[ ] 4.  고정 IP 설정
[ ] 5.  타임존 Asia/Seoul 설정
[ ] 6.  Docker (arm64) 설치 + pi 유저 그룹 추가
[ ] 7.  UFW 방화벽 설정 (22, 80, 443, 5540)
[ ] 8.  공유기 포트포워딩 (80, 443)
[ ] 9.  DuckDNS 도메인 등록 + 자동갱신 크론
[ ] 10. GitHub에서 프로젝트 클론
[ ] 11. 필요 디렉토리 생성 (db/data, certbot 등)
[ ] 12. setting/.env 작성 (API키, DB패스워드, JWT Secret 등)
[ ] 13. nginx/default.conf 도메인 교체
[ ] 14. docker network create TravelArchiveNetwork
[ ] 15. DB → Redis 순서로 컨테이너 기동
[ ] 16. Alembic 마이그레이션 실행
[ ] 17. Backend 컨테이너 기동
[ ] 18. Certbot SSL 인증서 최초 발급 (HTTP 임시 기동)
[ ] 19. HTTPS 설정으로 Nginx 재기동
[ ] 20. 전체 컨테이너 동작 확인
[ ] 21. systemd 자동 기동 서비스 등록
```

---

## 주의 사항

| 항목 | 내용 |
|---|---|
| **ARM64 필수** | OS를 반드시 64-bit로 설치해야 `kartoza/postgis`, `redis:7-alpine` 등 ARM64 이미지가 동작 |
| **DB 기동 대기** | PostgreSQL 초기화(PostGIS 설치)에 30~60초 소요 — 마이그레이션은 그 이후 실행 |
| **SSL 발급 순서** | 인증서 없이 HTTPS 설정으로 Nginx 기동하면 시작 실패 — HTTP 설정 먼저 |
| **certbot/conf 권한** | `sudo chown -R pi:pi certbot/` 로 권한 확인 |
| **.env는 절대 커밋 금지** | `.gitignore`에 `setting/.env` 포함 여부 반드시 확인 |
| **SD카드 수명** | DB 데이터는 외장 SSD/NAS로 마운트 권장 (현재 구조상 `./db/data` 경로 변경 필요 시) |

---

## 관련 문서

- [CONCEPT.md](CONCEPT.md) - 서비스 전체 콘셉트
- [ARCHITECTURE.md](ARCHITECTURE.md) - 프론트엔드/백엔드 구조
- [API_SPECIFICATION.md](API_SPECIFICATION.md) - API 엔드포인트 명세

---

**마지막 업데이트**: 2026-04-28
**담당**: Bae_JH
