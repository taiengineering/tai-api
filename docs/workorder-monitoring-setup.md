# TAI 모니터링 4단계 구축 작업지시서

**작성일**: 2026-04-19
**규칙 문서**: `docs/monitoring-rules.md`
**첫 적용 대상**: Fix Chat (로직 확정, API 동작 확인 완료)

---

## 작업 순서

### STEP 1: Sentry 연동 (30분)

#### 1-1. Sentry 가입 + 프로젝트 생성
- https://sentry.io 가입 (GitHub 계정 연동)
- 새 프로젝트 생성: Platform = Python, Project Name = `tai-api`
- DSN 복사 (예: `https://xxx@o123.ingest.sentry.io/456`)

#### 1-2. Fly.io에 DSN 등록
```bash
fly secrets set SENTRY_DSN="https://xxx@o123.ingest.sentry.io/456" -a tai-api-prod
```

#### 1-3. requirements.txt 추가
```
sentry-sdk[fastapi]
```

#### 1-4. main.py 수정 (상단에 추가)
```python
import sentry_sdk
import os

sentry_dsn = os.getenv("SENTRY_DSN", "")
if sentry_dsn:
    sentry_sdk.init(
        dsn=sentry_dsn,
        traces_sample_rate=0.1,  # 성능 영향 최소화
        environment="production",
    )
```

#### 1-5. Sentry Alert 설정
- Sentry 대시보드 → Alerts → Create Alert
- 조건: `When an event is seen` (every new error)
- 알림: Email (hetto@kakao.com)
- 향후 Webhook → MessageMi SMS 연동 가능

#### 1-6. 테스트
```python
# Sentry 동작 확인용 (배포 후 1회 실행, 삭제)
sentry_sdk.capture_message("TAI Sentry 연동 테스트")
```

---

### STEP 2: /health 엔드포인트 + UptimeRobot (1시간)

#### 2-1. main.py에 /health 엔드포인트 추가
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

#### 2-2. UptimeRobot 모니터 추가
- https://uptimerobot.com 로그인
- New Monitor → Monitor Type: Keyword
- URL: `https://api.taieng.co.kr/health`
- Keyword: `healthy`
- Keyword Type: Exists
- Monitoring Interval: 5 minutes
- Alert Contact: 기존 SMS 설정 사용

#### 2-3. 테스트
```bash
curl https://api.taieng.co.kr/health
# 예상: {"status":"healthy","checks":{"db":"ok","law_engine":"ok","fix_chat":"ok"}}
```

---

### STEP 3: API Smoke Test — GitHub Actions (2시간)

#### 3-1. 테스트 계정 준비
- Supabase에 테스트용 사용자 레코드 확인 (또는 생성)
- 테스트 이메일/비밀번호 확보

#### 3-2. GitHub Secrets 등록
- tai-api 리포 → Settings → Secrets and variables → Actions
- 추가:
  - `SMOKE_API_URL` = `https://api.taieng.co.kr`
  - `SMOKE_TEST_EMAIL` = 테스트 계정 이메일
  - `SMOKE_TEST_PASSWORD` = 테스트 계정 비밀번호
  - `MESSAGEMI_API_KEY` = MessageMi API 키
  - `ALERT_PHONE` = 대표님 전화번호

#### 3-3. 파일 생성: `.github/workflows/smoke-test.yml`
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

#### 3-4. 파일 생성: `scripts/smoke_test.py`
```python
import os
import sys
import httpx

API = os.environ["API_URL"]
failures = []

def check(name, fn):
    try:
        fn()
        print(f"  ✓ {name}")
    except Exception as e:
        msg = f"{name}: {e}"
        print(f"  ✗ {msg}")
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
        return  # 테스트 계정 없으면 skip
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

print(f"\n결과: {4 - len(failures)}/4 성공")

if failures:
    alert_msg = f"[TAI Smoke] {len(failures)}건 실패: {failures[0][:60]}"
    send_alert(alert_msg)
    sys.exit(1)
```

#### 3-5. 테스트
- GitHub Actions → Actions 탭 → "API Smoke Test" → Run workflow
- 4/4 성공 확인

---

### STEP 4: pg_cron 비즈니스 점검 (2시간)

#### 4-1. Supabase Edge Function 생성: `daily-health-check`

```typescript
// supabase/functions/daily-health-check/index.ts
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const supabase = createClient(
  Deno.env.get('SUPABASE_URL')!,
  Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!
)

Deno.serve(async () => {
  const alerts: string[] = []

  // 1) fix_chat: 24시간 내 세션 중 current_turn=0 비율
  const { data: sessions } = await supabase
    .from('fix_chat_sessions')
    .select('id, current_turn')
    .gte('created_at', new Date(Date.now() - 86400000).toISOString())
  
  if (sessions && sessions.length > 0) {
    const abandoned = sessions.filter(s => s.current_turn === 0).length
    const rate = abandoned / sessions.length
    if (rate > 0.8) {
      alerts.push(`채팅 이탈율 ${Math.round(rate*100)}% (${abandoned}/${sessions.length})`)
    }
  }

  // 2) 법령진단 빈 결과
  const { data: emptyDiag } = await supabase
    .from('diagnosis_results')
    .select('id')
    .eq('rules_count', 0)
    .gte('created_at', new Date(Date.now() - 86400000).toISOString())
  
  if (emptyDiag && emptyDiag.length > 0) {
    alerts.push(`법령진단 빈결과 ${emptyDiag.length}건`)
  }

  // 3) D-3 알림 미발송 (향후 work_assignments 테이블 활성화 후)
  // 현재는 skip

  // 알림 발송
  if (alerts.length > 0) {
    const msg = `[TAI Daily] ${alerts.join(' / ')}`
    const MESSAGEMI_KEY = Deno.env.get('MESSAGEMI_API_KEY')
    const ALERT_PHONE = Deno.env.get('ALERT_PHONE')
    
    if (MESSAGEMI_KEY && ALERT_PHONE) {
      await fetch('https://api.messagemi.com/v1/send', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${MESSAGEMI_KEY}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ to: ALERT_PHONE, content: msg.slice(0, 90) })
      })
    }
    return new Response(JSON.stringify({ alerts }), { status: 200 })
  }

  return new Response(JSON.stringify({ status: 'all_clear' }), { status: 200 })
})
```

#### 4-2. pg_cron 설정
```sql
-- Supabase SQL Editor에서 실행
SELECT cron.schedule(
  'daily-health-check',
  '0 0 * * *',  -- 매일 UTC 00:00 = KST 09:00
  $$
  SELECT net.http_post(
    url := 'https://xntdkrjhgcscmqctdzyo.supabase.co/functions/v1/daily-health-check',
    headers := jsonb_build_object(
      'Authorization', 'Bearer ' || current_setting('app.settings.service_role_key')
    )
  );
  $$
);
```

#### 4-3. Edge Function 배포
```bash
supabase functions deploy daily-health-check --project-ref xntdkrjhgcscmqctdzyo
```

#### 4-4. Edge Function Secrets 등록
```bash
supabase secrets set MESSAGEMI_API_KEY="xxx" ALERT_PHONE="01012345678" --project-ref xntdkrjhgcscmqctdzyo
```

#### 4-5. 테스트
```bash
curl -X POST https://xntdkrjhgcscmqctdzyo.supabase.co/functions/v1/daily-health-check \
  -H "Authorization: Bearer {service_role_key}"
# 예상: {"status":"all_clear"} 또는 {"alerts":[...]}
```

---

## 완료 기준

| 단계 | 확인 방법 | 완료 |
|------|----------|------|
| 1 | Sentry 대시보드에 테스트 메시지 표시 | ☐ |
| 2 | `curl /health` → `{"status":"healthy"}` + UptimeRobot 모니터 추가 | ☐ |
| 3 | GitHub Actions 수동 실행 → 4/4 성공 | ☐ |
| 4 | Edge Function 수동 호출 → `all_clear` 응답 | ☐ |

## 절대 규칙

- 🔒 알림은 MessageMi SMS만 (카카오 알림톡 금지)
- 🔒 Smoke Test에서 실제 사용자 데이터 건드리지 않음 (테스트 전용 계정 사용)
- 🔒 pg_cron 점검은 SELECT만 (INSERT/UPDATE/DELETE 금지)
- 🔒 모니터링 자체가 서비스에 부하를 주지 않도록 (매시간 5건 이내 API 호출)
- 🔒 기존 main.py, fix_chat.py 로직 변경 금지 (추가만)

## 향후 확장

로직 확정되는 기능이 생길 때마다:
1. smoke_test.py에 해당 API 검증 항목 추가 (S5, S6, ...)
2. daily-health-check Edge Function에 비즈니스 쿼리 추가
3. /health 엔드포인트에 해당 테이블 체크 추가
