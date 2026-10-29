---
title: WO-TAI-SLACK-BOT-UNIFIED-001-R3 파일럿 게이트 Addendum FINAL
wo: WO-TAI-SLACK-BOT-UNIFIED-001-R3
version: ADDENDUM-001
status: ADDENDUM_FINAL
date: 2026-10-29
author: Claude Code (보조)
---

# WO-TAI-SLACK-BOT-UNIFIED-001-R3 Pilot Gate Addendum FINAL

## 발행 배경

GPT IV (WO-TAI-SLACK-BOT-UNIFIED-001-R3-PILOT-GATE-ADDENDUM-001) 심사 결과
`GPT_IV_CONDITIONAL_PASS / ARCHITECTURE_LOCKED / DURABILITY_CORRECTION_REQUIRED / TOKEN_ROTATION_PENDING`
판정 수령. 기존 5개 산출물을 재작성하지 않고 본 Addendum으로 3건 계약 결함(COR-01 ~ COR-03)을 정정하며,
Owner 파일럿 구현 승인의 선결 조건을 확정한다.

---

## A-01 DB 스키마 정정 (COR-01 해소)

### 정정 전 (원안)

```sql
CREATE TABLE public.slack_relay_event_log (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id        text NOT NULL UNIQUE,
    channel_id      text NOT NULL,
    status          text NOT NULL DEFAULT 'PENDING',
    retry_count     int  NOT NULL DEFAULT 0,
    error_detail    text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);
```

### 정정 후 (Addendum 확정)

```sql
CREATE TABLE public.slack_relay_event_log (
    id                   uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id             text        NOT NULL UNIQUE,          -- 멱등 키 (Slack event_id)
    channel_id           text        NOT NULL,                 -- 대상 채널 ID
    message_text         text        NOT NULL,                 -- 재전송용 메시지 원문 보관
    sender_id            text,                                 -- 발신자 Slack user_id (선택)
    source_message_ts    text,                                 -- 원본 메시지 ts (포워딩 추적용)
    status               text        NOT NULL DEFAULT 'PENDING',
    retry_count          int         NOT NULL DEFAULT 0,
    next_attempt_at      timestamptz,                          -- Worker 재시도 스케줄 시각
    dispatch_started_at  timestamptz,                          -- SENDING 전이 시각
    claim_token          text,                                 -- Worker 인스턴스 펜싱 토큰
    error_detail         text,
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now()
);

-- 인덱스
CREATE INDEX idx_srel_status_next ON public.slack_relay_event_log (status, next_attempt_at);
CREATE INDEX idx_srel_event_id    ON public.slack_relay_event_log (event_id);
```

### 추가된 필드 근거

| 필드 | 근거 |
|------|------|
| `message_text` | DB PENDING 기록 후 프로세스 재시작 시 메모리 없이 복구 전송 가능 |
| `sender_id` | 감사 로그, 발신자 기반 필터링 |
| `source_message_ts` | Slack 포워딩 메시지 추적; 중복 탐지 보조 |
| `next_attempt_at` | 재시도 Worker가 처리 대상 행을 인덱스로 조회 |
| `dispatch_started_at` | SENDING 상태 진입 시각 — CLAIMING 이전에 이미 Slack API를 호출했는지 감사 가능 |
| `claim_token` | Worker 재시작 시 stale UPDATE를 방지하는 낙관적 잠금 |

### 멱등 삽입 (COR-01 추가 정정)

```sql
INSERT INTO public.slack_relay_event_log
    (event_id, channel_id, message_text, sender_id, source_message_ts, status)
VALUES
    (%s, %s, %s, %s, %s, 'PENDING')
ON CONFLICT (event_id) DO NOTHING;
-- NOT: INSERT OR IGNORE (SQLite 문법 — PostgreSQL 부정확)
```

---

## A-02 데이터 보관 및 접근 정책 (COR-01 보완)

| 항목 | 정책 |
|------|------|
| 보관 기간 | SENT / FAILED_PERMANENT: 90일 후 자동 삭제 (pg_cron 또는 파티션) |
| UNKNOWN 상태 | 30일 후 운영자 수동 검토 후 삭제 또는 재시도 |
| RLS | `anon` / `authenticated`: SELECT/INSERT/UPDATE/DELETE 모두 FALSE; `service_role`: TRUE |
| 민감 필드 | `message_text`에 개인정보 포함 시 암호화 (AES-256, 별도 WO) |
| 감사 | `updated_at`, `claim_token`, `dispatch_started_at` 변경 이력 보존 |

---

## A-03 이벤트 수신 엔드포인트 계약 (A-03 확정)

**경로**: `POST /slack/events`

**Permission Guard 처리**:
- 현행 Guard: `PERMISSION_GUARD_ENFORCE=platform,payments` → `/slack/*` ADVISORY (차단 없음)
- 권장 처리: `permission_guard.py` `_PUBLIC` 튜플에 `("POST", "/slack/events")` 추가 (1행)
  - 이유: Bearer 토큰 없는 Slack 서버 요청은 정상이며 ADVISORY warning 로그 불필요
  - Owner 승인 후 구현

**Slack URL Verification 처리 (필수)**:
```python
if payload.get("type") == "url_verification":
    return {"challenge": payload["challenge"]}
```

**Signing Secret 검증**: `slack_signature_verifier.py` `verify_slack_signing_secret()` 재사용
- 환경변수: `SLACK_SIGNING_SECRET` (신규 추가 필요)
- max_age_seconds: 300 (기본값 유지)

---

## A-04 파일럿 범위 확정 (A-04 확정)

| 항목 | 값 |
|------|-----|
| 릴레이 채널 | 1개 (신규 private 채널, Owner 직접 생성) |
| 수신 채널 | 1개 (테스트 전용, 본선 채널 제외) |
| 메시지 타입 | text only (Blocks, 파일, 멘션 제외) |
| 본선 채널 포함 여부 | 파일럿 기간 중 절대 불포함 |
| 파일럿 기간 | Owner 지정 (권장: 2주) |
| 성공 기준 | T01~T25 PASS + E2E 수동 1회 PASS + 7일 오류율 < 1% |

---

## A-05 구현 파일 목록 (Owner 승인 후)

| 파일 | 작업 | 비고 |
|------|------|------|
| `routers/slack_events.py` | 신규 생성 (~90줄) | URL verification + HMAC 검증 + DB 삽입 |
| `services/slack_relay_svc.py` | 신규 생성 (~80줄) | Worker 상태 머신 + claim_token 펜싱 |
| `services/permission_guard.py` | 1줄 수정 | `_PUBLIC`에 `("POST", "/slack/events")` 추가 |
| `migrations/20261029XXXXXX_slack_relay_event_log.sql` | 신규 생성 | A-01 스키마 + RLS |
| `tests/test_slack_relay.py` | 신규 생성 (~200줄) | T01~T25 |
| `main.py` or `router_registry` | 라우터 등록 | `include_router(slack_events.router)` |

---

## 미해소 사항 (Owner 결정 대기)

| 코드 | 내용 | 상태 |
|------|------|------|
| TOKEN_ROTATION | `SLACK_BOT_TOKEN1` 재발급 절차 | TOKEN_ROTATION_SAFE_PROCEDURE.md 참조 |
| API_APP_ID | Slack App `api_app_id` 확인 | Slack App 관리 콘솔에서 Owner 직접 확인 |
| RELAY_CH_ID | 파일럿 릴레이 채널 생성 + ID | Owner 직접 생성 |
| SCOPE | `groups:history` 스코프 추가 | Slack App 관리 콘솔 OAuth & Permissions |

---

## 판정

이 Addendum이 Owner 확인·서명되면 기존 5개 산출물 + 본 Addendum = 파일럿 구현 Gate 충족.
구현 시작은 `OWNER_PILOT_IMPLEMENTATION_APPROVAL_REQUEST.md` Owner 서명 이후.
