---
title: Relay Worker 복구 상태 머신 계약
wo: WO-TAI-SLACK-BOT-UNIFIED-001-R3
version: ADDENDUM-001
status: ADDENDUM_FINAL
date: 2026-10-29
---

# Relay Worker 복구 상태 머신 (COR-02 해소)

## 배경

원안(BackgroundTask 단독)은 프로세스 재시작 시 인플라이트(CLAIMING) 메시지가 영구 손실된다.
GPT COR-02 지적: SENDING 상태 부재 + claim_token 펜싱 부재 → 중복 전송 또는 유실 위험.
본 문서는 7-상태 머신 + claim_token 펜싱 + 복구 Worker 계약을 확정한다.

---

## 상태 정의

| 상태 | 의미 | 다음 상태 |
|------|------|-----------|
| `PENDING` | DB에 저장됨, 아직 Worker가 가져가지 않음 | → CLAIMED |
| `CLAIMED` | Worker가 처리 의사를 표명; Slack API 호출 전 | → SENDING |
| `SENDING` | Slack API 호출 진행 중 (dispatch_started_at 기록됨) | → SENT / UNKNOWN / RETRY |
| `SENT` | Slack API `ok=true` 수신 확인 | (종료) |
| `RETRY` | 일시적 오류; next_attempt_at 이후 재시도 대상 | → CLAIMED |
| `UNKNOWN` | Slack API 응답 모호 (타임아웃/네트워크 단절) | → 수동 검토 or RETRY |
| `FAILED_PERMANENT` | retry_count ≥ MAX_RETRY or 영구 오류 | (종료) |

**UNKNOWN 상태 원칙**: Slack API를 호출했으나 응답 수신 여부 불명확 시
`ok=true` 증거 없이 SENT 전이 금지. UNKNOWN → 운영자 수동 확인 후 처리.

---

## 전이 다이어그램

```
[PENDING] ─claim─────────────────────────────────→ [CLAIMED]
               └─ (claim_token 발급 + updated_at CAS)

[CLAIMED] ─dispatch_started_at 기록──────────────→ [SENDING]

[SENDING] ─Slack ok=true────────────────────────→ [SENT]
          ─Slack ok=false / HTTP 4xx permanent──→ [FAILED_PERMANENT]
          ─Slack HTTP 5xx / timeout────────────→ [RETRY] (retry_count+1)
          ─응답 수신 불명 (네트워크 단절)──────→ [UNKNOWN]

[RETRY]   ─next_attempt_at 도래────────────────→ [CLAIMED]  (claim_token 갱신)
          ─retry_count ≥ MAX_RETRY─────────────→ [FAILED_PERMANENT]
```

---

## claim_token 펜싱 계약

### PENDING → CLAIMED 전이

```sql
UPDATE public.slack_relay_event_log
SET    status    = 'CLAIMED',
       claim_token = :new_token,   -- Worker 인스턴스별 UUID
       updated_at  = now()
WHERE  id     = :row_id
  AND  status = 'PENDING'          -- CAS: 다른 Worker가 먼저 가져가면 0행 영향
RETURNING id;
-- 0행 반환 시: 이미 다른 Worker가 가져감 → 건너뜀
```

### CLAIMED → SENDING 전이

```sql
UPDATE public.slack_relay_event_log
SET    status               = 'SENDING',
       dispatch_started_at  = now(),
       updated_at            = now()
WHERE  id          = :row_id
  AND  claim_token = :my_token     -- 펜싱: 내 토큰이 아니면 0행 영향
RETURNING id;
-- 0행 반환 시: stale Worker → Slack API 호출 중단
```

### SENDING → SENT / RETRY / UNKNOWN / FAILED_PERMANENT

```sql
UPDATE public.slack_relay_event_log
SET    status       = :new_status,
       retry_count  = retry_count + :delta,   -- RETRY 시 1, 나머지 0
       next_attempt_at = :next_ts,            -- RETRY 시만 설정
       error_detail = :error,
       updated_at   = now()
WHERE  id          = :row_id
  AND  claim_token = :my_token;
```

---

## 복구 Worker 계약

### 역할
- BackgroundTask: 이벤트 수신 즉시 1회 전송 시도 (빠른 경로)
- Recovery Worker: PENDING/RETRY 행을 주기 스캔하여 재전송

### Recovery Worker 실행 방식 (둘 중 Owner 선택)

**옵션 A: FastAPI lifespan background coroutine**
```python
async def _recovery_loop():
    while True:
        await _process_pending_rows()
        await asyncio.sleep(RECOVERY_INTERVAL_SEC)   # 권장: 30초

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_recovery_loop())
    yield
    task.cancel()
```

**옵션 B: cron_job_master (TAI 스케줄러)**
- 매 1분 `POST /internal/slack-relay/recover` 호출
- 장점: 기존 스케줄러 재사용, 프로세스 재시작에 독립
- 단점: 1분 최소 지연

Owner가 옵션 선택 후 구현 승인.

### PENDING/RETRY 스캔 쿼리

```sql
SELECT id, event_id, channel_id, message_text, claim_token
FROM   public.slack_relay_event_log
WHERE  status IN ('PENDING', 'RETRY')
  AND  (next_attempt_at IS NULL OR next_attempt_at <= now())
ORDER BY created_at
LIMIT  :batch_size;   -- 권장: 10
```

### stale CLAIMED 복구 (재시작 후 처리)

```sql
UPDATE public.slack_relay_event_log
SET    status    = 'RETRY',
       claim_token = NULL,
       next_attempt_at = now() + INTERVAL '1 minute',
       updated_at  = now()
WHERE  status  = 'CLAIMED'
  AND  updated_at < now() - INTERVAL '5 minutes';
-- SENDING → UNKNOWN 도 동일 패턴 (INTERVAL '10 minutes' 권장)
```

---

## MAX_RETRY 정책

| 오류 종류 | 즉시 FAILED_PERMANENT | RETRY 상한 |
|-----------|----------------------|-----------|
| HTTP 400/403 (채널 없음, 권한 없음) | O | — |
| HTTP 429 (rate limit) | — | 5회; next_attempt_at = Retry-After 헤더 기준 |
| HTTP 5xx / timeout | — | 3회; 지수 백오프 (1분, 5분, 15분) |
| ok=false (channel_not_found 등) | O | — |

---

## 테스트 계획 (T19~T25 추가)

| ID | 검증 항목 |
|----|-----------|
| T19 | PENDING → CLAIMED: claim_token 발급, 동시 Worker 경쟁 시 1개만 성공 |
| T20 | CLAIMED → SENDING: claim_token 불일치 시 전이 거부 |
| T21 | SENDING → SENT: Slack ok=true 모의 → 상태 SENT, claim_token NULL |
| T22 | SENDING → RETRY: HTTP 5xx → retry_count+1, next_attempt_at 설정 |
| T23 | SENDING → UNKNOWN: timeout → UNKNOWN, SENT 전이 금지 확인 |
| T24 | stale CLAIMED 복구: 5분 경과 CLAIMED → RETRY 전이 |
| T25 | retry_count ≥ MAX_RETRY → FAILED_PERMANENT 전이 |

---

## BackgroundTask와 Recovery Worker 역할 분리 요약

| 경로 | 역할 | 실패 시 |
|------|------|---------|
| BackgroundTask (이벤트 수신 즉시) | PENDING row 생성 + 1회 빠른 전송 시도 | PENDING/RETRY 잔류 → Recovery Worker가 처리 |
| Recovery Worker (주기 스캔) | PENDING/RETRY 재처리 + stale CLAIMED 복구 | 알람 발송 + 운영자 검토 |

메시지 `message_text`가 DB에 저장되어 있으므로 프로세스 재시작 후에도 복구 전송 가능.
