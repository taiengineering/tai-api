# TAI 모니터링 4단계 구축 작업지시서

**작성일**: 2026-04-19
**규칙 문서**: `docs/monitoring-rules.md`
**첫 적용 대상**: Fix Chat (로직 확정, API 동작 확인 완료)

---

## 작업 순서

### STEP 1: Sentry 연동 — ✅ 완료

- Sentry 가입, DSN 발급, Fly.io secrets 등록, main.py v5.33.0 연동 완료
- 에러 자동 수집 확인 완료 (APIError: invalid input syntax for type uuid)

---

### STEP 2: /health 엔드포인트 개선 + UptimeRobot (1시간)

#### 2-1. main.py의 기존 /health 엔드포인트를 아래로 교체

```python
from fastapi.responses import JSONResponse

@app.get("/health")
def health_check():
    checks = {}
    try:
        sb = get_supabase()
        sb.table("system_codes").select("code").limit(1).execute()
        checks["db"] = "ok"
    except Exception as e:
        checks["db"] = f"fail: {str(e)[:100]}"
    
    try:
        res = sb.table("law_rules").select("id").eq("is_active", True).limit(1).execute()
        checks["law_engine"] = "ok" if res.data else "empty"
    except Exception as e:
        checks["law_engine"] = f"fail: {str(e)[:100]}"
    
    try:
        res = sb.table("fix_chat_sessions").select("id").limit(1).execute()
        checks["fix_chat"] = "ok"
    except Exception as e:
        checks["fix_chat"] = f"fail: {str(e)[:100]}"
    
    all_ok = all(v == "ok" for v in checks.values())
    return JSONResponse(
        status_code=200 if all_ok else 503,
        content={"status": "healthy" if all_ok else "unhealthy", "checks": checks}
    )
```

🔒 기존 /health 함수를 위 코드로 교체. 기존 root() 함수는 건드리지 않음.

#### 2-2. UptimeRobot 모니터 추가 (수동)
- https://uptimerobot.com 로그인
- New Monitor → Monitor Type: Keyword
- URL: `https://api.taieng.co.kr/health`
- Keyword: `healthy`
- Keyword Type: Exists
- Monitoring Interval: 5 minutes

#### 2-3. 테스트
```bash
curl https://api.taieng.co.kr/health
# 예상: {"status":"healthy","checks":{"db":"ok","law_engine":"ok","fix_chat":"ok"}}
```

---

### STEP 3: API Smoke Test — GitHub Actions (2시간)

#### 3-1. GitHub Secrets 등록 (수동)
- tai-api 리포 → Settings → Secrets and variables → Actions
- 추가:
  - `SMOKE_API_URL` = `https://api.taieng.co.kr`
  - `SMOKE_TEST_EMAIL` = 테스트 계정 이메일
  - `SMOKE_TEST_PASSWORD` = 테스트 계정 비밀번호
  - `MESSAGEMI_API_KEY` = MessageMi API 키
  - `ALERT_PHONE` = 대표님 전화번호

#### 3-2. 파일 생성: `.github/workflows/smoke-test.yml`
```yaml
name: API Smoke Test
on:
  schedule:
    - cron: '0 * * * *'
  workflow_dispatch:

jobs:
  smoke:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install httpx
      - run: python scripts/smoke_test.py
        env:
          API_URL: ${{ secrets.SMOKE_API_URL }}
          TEST_EMAIL: ${{ secrets.SMOKE_TEST_EMAIL }}
          TEST_PASSWORD: ${{ secrets.SMOKE_TEST_PASSWORD }}
          MESSAGEMI_KEY: ${{ secrets.MESSAGEMI_API_KEY }}
          ALERT_PHONE: ${{ secrets.ALERT_PHONE }}
```

#### 3-3. 파일 생성: `scripts/smoke_test.py`
```python
import os
import sys
import httpx

API = os.environ["API_URL"]
failures = []

def check(name, fn):
    try:
        fn()
        print(f"  \u2713 {name}")
    except Exception as e:
        msg = f"{name}: {e}"
        print(f"  \u2717 {msg}")
        failures.append(msg)

def send_alert(text):
    key = os.environ.get("MESSAGEMI_KEY")
    phone = os.environ.get("ALERT_PHONE")
    if not key or not phone:
        print(f"[ALERT] {text}")
        return
    httpx.post(
        "https://api.messagemi.com/v1/send",
        headers={"Authorization": f"Bearer {key}"},
        json={"to": phone, "content": text[:90]}
    )

# S1: Health
def s1():
    r = httpx.get(f"{API}/health", timeout=10)
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"
check("S1 /health", s1)

# S2: Fix Chat 세션 생성
def s2():
    r = httpx.post(f"{API}/fix/chat/start",
        json={"user_type": "GUEST"}, timeout=10)
    assert r.status_code == 200
    assert r.json().get("session_id")
check("S2 fix/chat/start", s2)

# S3: 로그인
def s3():
    email = os.environ.get("TEST_EMAIL")
    pw = os.environ.get("TEST_PASSWORD")
    if not email:
        return
    r = httpx.post(f"{API}/auth/login",
        json={"email": email, "password": pw}, timeout=10)
    assert r.status_code == 200
check("S3 auth/login", s3)

# S4: 법령진단 (최소 입력)
def s4():
    r = httpx.post(f"{API}/diagnosis/free",
        json={"sector": "BUILDING", "area": 500,
              "building_use": "OFFICE", "completion_year": 2010},
        timeout=30)
    assert r.status_code == 200
check("S4 diagnosis/free", s4)

print(f"\n\uacb0\uacfc: {4 - len(failures)}/4 \uc131\uacf5")

if failures:
    alert_msg = f"[TAI Smoke] {len(failures)}\uac74 \uc2e4\ud328: {failures[0][:60]}"
    send_alert(alert_msg)
    sys.exit(1)
```

#### 3-4. 테스트
- GitHub Actions → Actions 탭 → "API Smoke Test" → Run workflow
- 4/4 성공 확인

---

### STEP 4: pg_cron 비즈니스 점검 — 별도 안내 예정

Supabase Edge Function + pg_cron 설정이 필요하여 STEP 2~3 완료 후 별도 진행.

---

## 절대 규칙

- 🔒 기존 main.py의 Sentry 초기화 코드 건드리지 않음 (STEP 1 완료)
- 🔒 기존 root() 함수 건드리지 않음
- 🔒 기존 fix_chat.py 로직 변경 금지
- 🔒 모든 커밋은 dev 브랜치에
- 🔒 파일 생성 후 python3 -m py_compile로 검증
- 🔒 의문이 있으면 구현하지 말고 질문
