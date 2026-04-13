# Fly.io TAI API 이전 가이드
# 작성일: 2026-04-13

## 사전 준비

### 1. flyctl 설치 (Mac/Linux)
```bash
curl -L https://fly.io/install.sh | sh
export PATH="$HOME/.fly/bin:$PATH"  # 또는 ~/.zshrc에 추가
```

### 2. Fly.io 로그인
```bash
fly auth login  # 브라우저 열림 → 가입/로그인
```

---

## STEP 1: 앱 생성 (처음 한 번만)

```bash
# 레포 루트에서 실행
cd ~/path/to/tai-api

# 앱 생성 (fly.toml의 app 이름으로)
fly apps create tai-api-prod --org personal
```

---

## STEP 2: 환경변수 등록

Railway에서 사용하던 환경변수를 Fly.io에 등록합니다.

```bash
# 한 번에 여러 개 등록 (Railway Variables 탭에서 복사)
fly secrets set \
  SUPABASE_URL="https://xntdkrjhgcscmqctdzyo.supabase.co" \
  SUPABASE_KEY="your_supabase_key" \
  SECRET_KEY="your_secret_key" \
  OPENAI_API_KEY="your_openai_key" \
  RESEND_API_KEY="your_resend_key" \
  FIREBASE_SERVICE_ACCOUNT="your_firebase_json" \
  --app tai-api-prod

# 등록 확인
fly secrets list --app tai-api-prod
```

> **주의**: FIREBASE_SERVICE_ACCOUNT가 JSON이면 따옴표 처리 주의
> ```bash
> fly secrets set FIREBASE_SERVICE_ACCOUNT="$(cat firebase-service-account.json)" --app tai-api-prod
> ```

---

## STEP 3: 첫 배포

```bash
# 레포 루트에서 실행
fly deploy --app tai-api-prod --region nrt

# 배포 상태 확인
fly status --app tai-api-prod

# 로그 확인
fly logs --app tai-api-prod
```

---

## STEP 4: 커스텀 도메인 연결 (api.taieng.co.kr)

### 4-1. Fly.io 인증서 발급
```bash
fly certs create api.taieng.co.kr --app tai-api-prod
fly certs show api.taieng.co.kr --app tai-api-prod
```

### 4-2. Cloudflare DNS 변경
Cloudflare Dashboard → taieng.co.kr → DNS

| 타입 | 이름 | 값 | 프록시 |
|------|------|-----|--------|
| CNAME | api | `tai-api-prod.fly.dev` | ❌ OFF (DNS only) |

> Fly.io SSL 인증서가 활성화된 후 프록시 ON으로 변경 가능

### 4-3. DNS 전파 확인
```bash
dig api.taieng.co.kr
# 또는
curl https://api.taieng.co.kr/health
```

---

## STEP 5: 전환 전 검증

```bash
# Fly.io 앱 직접 URL로 테스트
curl https://tai-api-prod.fly.dev/health

# 응답 예: {"status": "ok", ...}
```

---

## GitHub Actions 자동 배포 (선택)

### FLY_API_TOKEN 등록
```bash
# 토큰 발급
fly tokens create deploy -x 999999h --app tai-api-prod
# 출력된 토큰을 복사
```

GitHub → tai-api repo → Settings → Secrets and variables → Actions
- 이름: `FLY_API_TOKEN`
- 값: 위에서 복사한 토큰

`.github/workflows/fly-deploy.yml` 파일이 자동 배포를 처리합니다.

---

## Railway 종료 (전환 완료 후)

```bash
# Fly.io 정상 확인 후
# Railway 대시보드에서 서비스 삭제 또는 일시정지
# (바로 삭제 금지 — 최소 1주일 동시 운영 권장)
```

---

## 비용 예상

| 조건 | 비용 |
|------|------|
| 트래픽 없을 때 정지 (현재 설정) | 실사용량만 과금, ~$1~3/월 |
| 항상 켜놓기 (min_machines=1) | ~$5~7/월 |
| Railway 현재 | ~$5/월 |

---

## 문제 해결

```bash
# 로그 실시간 보기
fly logs --app tai-api-prod -f

# 머신 상태
fly machine list --app tai-api-prod

# SSH 접속 (디버깅)
fly ssh console --app tai-api-prod

# 재배포
fly deploy --app tai-api-prod

# 환경변수 수정
fly secrets set KEY=VALUE --app tai-api-prod
```
