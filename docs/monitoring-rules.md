# TAI 서비스 모니터링 규칙 (4단계)

**확정일**: 2026-04-19
**원칙**: SMS가 안 오면 정상. SMS가 오면 그때 확인.
**알림 채널**: MessageMi SMS → 대표 (향후 팀 확장 시 Slack 전환)

---

## 구조

```
Sentry (에러 발생)     ─┐
UptimeRobot (서버 다운) ─┼──→ MessageMi SMS → 대표님 폰
Smoke Test (기능 이상)  ─┤
pg_cron (데이터 이상)   ─┘
```

평소에 대시보드를 보러 갈 필요 없음.
SMS가 오면 해당 도구(Sentry/UptimeRobot 등)에서 상세 확인.

---

## 1단계: Sentry 에러 자동 수집

**목적**: 코드에서 에러 발생 시 자동 수집 + SMS 알림
**비용**: 무료 (월 5,000건)

### 적용 방법

```python
# main.py 상단에 2줄 추가
import sentry_sdk
sentry_sdk.init(dsn="https://xxx@sentry.io/xxx")
```

### 알림 설정
- Sentry Alert → Webhook → MessageMi SMS 발송
- 또는 Sentry Alert → Email → 확인

### 감지 대상
- 모든 500 에러
- 예외(Exception)
- 타임아웃
- Claude API 호출 실패

---

## 2단계: /health 엔드포인트 + UptimeRobot

**목적**: 서버·DB·엔진 상태를 종합 감시
**비용**: 무료 (UptimeRobot 이미 사용 중)

### /health 엔드포인트 구현

```python
@app.get("/health")
def health_check():
    checks = {}
    
    # 1) DB 연결
    try:
        sb = get_supabase()
        sb.table("system_codes").select("code").limit(1).execute()
        checks["db"] = "ok"
    except:
        checks["db"] = "fail"
    
    # 2) 법령 엔진 (rules 테이블 존재 확인)
    try:
        res = sb.table("law_rules").select("id").limit(1).execute()
        checks["law_engine"] = "ok" if res.data else "empty"
    except:
        checks["law_engine"] = "fail"
    
    # 3) 전체 판정
    all_ok = all(v == "ok" for v in checks.values())
    status_code = 200 if all_ok else 503
    
    return JSONResponse(
        status_code=status_code,
        content={"status": "healthy" if all_ok else "unhealthy", "checks": checks}
    )
```

### UptimeRobot 설정
- 기존 4개 모니터 유지
- 추가: `api.taieng.co.kr/health` (키워드 모니터, "healthy" 포함 확인)
- 간격: 5분
- 알림: MessageMi SMS

---

## 3단계: API Smoke Test (매시간 자동 검증)

**목적**: 핵심 API가 정상 동작하는지 매시간 자동 확인
**비용**: 무료 (GitHub Actions 월 2,000분)
**구현**: GitHub Actions Cron

### 테스트 시나리오

```yaml
# .github/workflows/smoke-test.yml
name: API Smoke Test
on:
  schedule:
    - cron: '0 * * * *'  # 매시간
  workflow_dispatch:       # 수동 실행 가능

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
          API_URL: https://api.taieng.co.kr
          MESSAGEMI_KEY: ${{ secrets.MESSAGEMI_KEY }}
          ALERT_PHONE: ${{ secrets.ALERT_PHONE }}
```

### 검증 항목

| # | API | 성공 조건 |
|---|-----|----------|
| S1 | `GET /health` | status=200, "healthy" |
| S2 | `POST /fix/chat/start` | session_id 존재 |
| S3 | `POST /diagnosis/free` (최소 입력) | result 존재 |
| S4 | `POST /auth/login` (테스트 계정) | token 발급 |
| S5 | `GET /inspection-sets?size=1` (인증) | 200 응답 |

### 실패 시
- MessageMi SMS: "[TAI Smoke] S3 법령진단 API 실패 — {에러 내용}"
- GitHub Actions 화면에서 상세 로그 확인

---

## 4단계: pg_cron 비즈니스 로직 점검 (매일)

**목적**: API는 200인데 데이터가 이상한 경우 감지
**비용**: $0 (Supabase pg_cron)
**실행**: 매일 오전 9시 (KST)

### 점검 쿼리

```sql
-- pg_cron으로 매일 실행
SELECT
  -- 1) 오늘 D-3 알림 미발송 건
  (SELECT count(*) FROM work_assignments 
   WHERE due_date = CURRENT_DATE + interval '3 days' 
   AND notification_sent = false) as unsent_d3,

  -- 2) 법령진단 결과 rules_count=0 (비정상)
  (SELECT count(*) FROM diagnosis_results 
   WHERE created_at > now() - interval '24 hours' 
   AND rules_count = 0) as empty_diagnosis,

  -- 3) fix_chat 세션 중 current_turn=0 비율 (24시간)
  (SELECT count(*) FROM fix_chat_sessions 
   WHERE created_at > now() - interval '24 hours' 
   AND current_turn = 0) as abandoned_sessions,

  -- 4) 24시간 내 생성된 세션 총 수
  (SELECT count(*) FROM fix_chat_sessions 
   WHERE created_at > now() - interval '24 hours') as total_sessions;
```

### 알림 조건
- unsent_d3 > 0 → SMS "D-3 알림 미발송 {n}건"
- empty_diagnosis > 0 → SMS "법령진단 빈 결과 {n}건"
- abandoned_sessions / total_sessions > 0.8 → SMS "채팅 이탈율 80% 초과"

### 구현: Supabase Edge Function
- pg_cron이 Edge Function 호출
- Edge Function이 쿼리 실행 → 조건 판단 → MessageMi SMS 발송

---

## 적용 규칙

### 🔒 로직 확정된 기능 → 4단계 전부 적용

해당 기능:
- 법령진단 (무료/유료)
- Fix Chat 대화
- 인증 (로그인/회원가입)
- 점검 일정 (inspection_sets, work_assignments)
- D-3 알림 발송

### 🔓 개발 중인 기능 → 1~2단계만

해당 기능:
- 교육사업
- 공급자 등록/매칭
- 결제 (KG이니시스)
- SaaS 대시보드

기능이 확정되면 3~4단계를 추가.

---

## 작업 순서

| 순서 | 항목 | 소요 | 담당 |
|------|------|------|------|
| 1 | Sentry 가입 + main.py 2줄 추가 | 30분 | 백엔드 |
| 2 | /health 엔드포인트 + UptimeRobot 모니터 추가 | 1시간 | 백엔드 |
| 3 | scripts/smoke_test.py + GitHub Actions yml | 반나절 | 백엔드 |
| 4 | Edge Function + pg_cron 설정 | 반나절 | 백엔드 |

---

## 절대 규칙

- 🔒 알림은 MessageMi SMS만 사용 (카카오 알림톡 금지)
- 🔒 Smoke Test에서 실제 사용자 데이터를 건드리지 않음 (테스트 전용 계정/데이터 사용)
- 🔒 pg_cron 점검은 SELECT만 (INSERT/UPDATE/DELETE 금지)
- 🔒 모니터링 자체가 서비스에 부하를 주지 않도록 (매시간 5건 이내 API 호출)
