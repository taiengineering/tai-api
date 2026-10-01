---
title: QA Control API v1
status: DRAFT (PR #472)
phase: 2-B
depends_on: QA_CONTROL_CANONICAL_V1.md (Phase 2-A)
---

# QA Control API v1

## 개요

Phase 2-A에서 확정된 5-table canonical schema 위의 API 레이어.
tai-api service_role만 DB에 접근. Admin Front → tai-api → Supabase.

**금지사항**: GitHub dispatch = 0 / Slack = 0 / DB schema mutation = 0

---

## 인증 방식

| 라우터 | 인증 |
|--------|------|
| `routers/admin_qa.py` | `get_current_user` + `_require_admin` (ALL scope) |
| `routers/internal_qa.py` | `X-Internal-Secret` 헤더 (`INTERNAL_API_SECRET` env) |

---

## Endpoints

### GET /admin/qa/summary

전체 QA 현황 요약.

**Response**
```json
{
  "total": 10,
  "enabled": 10,
  "status_counts": {
    "PASS": 7, "FAIL": 1, "FLAKY": 1, "NEVER_RUN": 1
  },
  "sites": [
    { "site_code": "WWW", "status_counts": { "PASS": 4, "FLAKY": 1 } },
    { "site_code": "SAFE", "status_counts": { "PASS": 3, "FAIL": 1 } }
  ]
}
```

`effective_status`는 항목별 최근 실행 결과에서 API가 파생. DB에 저장하지 않음.

---

### GET /admin/qa/items

QA 항목 목록. `schedule` + `effective_status` + 최근 실행 정보 포함.

**Query params**

| 파라미터 | 설명 |
|---------|------|
| `site_code` | WWW / SAFE / API / ADMIN / MKT / WORKER / EXTERNAL |
| `priority` | P0 / P1 / P2 / P3 |
| `enabled` | true / false |
| `category` | 자유 문자열 필터 |
| `effective_status` | PASS / FAIL / FLAKY / BLOCKED / SKIPPED / NEVER_RUN |
| `page` | 기본 1 |
| `page_size` | 기본 50, 최대 200 |

**Response item 추가 필드**
```json
{
  "effective_status": "PASS",
  "last_run_id": "uuid",
  "last_checked_at": "2026-10-01T09:00:00+09:00",
  "last_duration_ms": 1230,
  "last_error_summary": null,
  "schedule": { ... }
}
```

---

### PATCH /admin/qa/items/{qa_item_id}

`enabled` 필드만 수정 가능.
`name` / `description` / `expected_summary`는 tai-qa SoT와의 drift 방지를 위해 수정 불가.

**Request body**
```json
{ "enabled": false }
```

---

### PATCH /admin/qa/items/{qa_item_id}/schedule

스케줄 수정. `next_run_at`은 서버가 항상 `NULL`로 강제 (Phase 2-E scheduler authority가 계산).

**Request body** (허용 필드)
```json
{
  "enabled": true,
  "frequency_type": "DAILY",
  "anchor_time": "09:00:00",
  "timezone": "Asia/Seoul"
}
```

**API validation** (DB CHECK 이전에 400 반환)

| 조건 | 오류 |
|------|------|
| `MANUAL` + `enabled=true` | 400 |
| `DAILY` without `anchor_time` | 400 |
| `WEEKLY` without `anchor_time` | 400 |
| `WEEKLY` without `day_of_week` | 400 |
| `MINUTES`/`HOURLY` without `frequency_value > 0` | 400 |
| `timezone != "Asia/Seoul"` | 400 |

---

### GET /admin/qa/runs

실행 목록. `target_count` / `result_count` / `effective_counts` 포함.

**Query params**

| 파라미터 | 설명 |
|---------|------|
| `run_status` | QUEUED / RUNNING / COMPLETED / ERROR / CANCELED |
| `trigger_type` | SCHEDULE / MANUAL / PR / RETRY |
| `from_date` | ISO datetime (requested_at ≥) |
| `to_date` | ISO datetime (requested_at ≤) |
| `page` / `page_size` | 기본 1/20, 최대 100 |

---

### GET /admin/qa/runs/{run_id}

실행 상세. `targets` (item 정보 포함) + `results` (FLAKY 파생).

**target 필드**
```json
{
  "qa_item_id": "uuid",
  "scenario_id": "P0-WWW-001",
  "site_code": "WWW",
  "name": "Login flow",
  "ordinal": 1,
  "effective_status": "PASS"
}
```

**FLAKY 파생 규칙**: 해당 run에서 `final_attempt=PASS` + 이전 `attempt` 중 `FAIL` 하나라도 존재 → `flaky=true` 마킹.

---

### POST /admin/qa/runs

MANUAL 실행 생성 (상태: QUEUED).

**Request body** — client는 `qa_item_ids`만 제공
```json
{ "qa_item_ids": ["uuid1", "uuid2"] }
```

**서버 고정값**
- `trigger_type = MANUAL`
- `requested_by = current_user.id`
- `ordinal = 1..N`

**Validation**
- 1~100건
- 중복 금지
- 존재하지 않는 item 금지
- `enabled=false` item 금지

**오류 시 Compensating DELETE**: `qa_runs` INSERT 후 `qa_run_targets` 실패 시 run 롤백.

---

### POST /internal/qa/runs/{run_id}/results

GitHub Actions callback. `scenario_id`를 canonical input으로 사용 (tai-qa SoT).

**인증**: `X-Internal-Secret: <INTERNAL_API_SECRET>`

**Request body**
```json
{
  "run_status": "RUNNING",
  "github_run_id": 123456789,
  "github_run_attempt": 1,
  "head_sha": "abc123",
  "branch_name": "main",
  "started_at": "2026-10-01T09:00:00+09:00",
  "results": [
    {
      "scenario_id": "P0-WWW-001",
      "result_status": "PASS",
      "attempt": 1,
      "duration_ms": 1230
    }
  ]
}
```

---

## 핵심 계약

### FLAKY 파생
`final attempt = PASS` + 이전 attempt 중 `FAIL` 하나라도 존재 → `FLAKY`.
DB에 저장하지 않음. API 응답 시 파생.

### Idempotency
동일 `(run_id, qa_item_id, attempt)` + 모든 canonical evidence 동일 → skip.
어떤 필드라도 다름 → **409 RESULT_CONFLICT**.

### Lifecycle
```
QUEUED → RUNNING / ERROR / CANCELED
RUNNING → COMPLETED / ERROR / CANCELED
```
- Final 상태 + 동일 payload replay → **200 idempotent**
- Final 상태 + 다른 status 전이 → **409**
- Final 상태 + 새 result INSERT → **409**

### GitHub Identity
- `NULL → 최초 binding` 허용
- 동일 identity replay → 허용
- 다른 identity → **409 GITHUB_IDENTITY_MISMATCH**
- `github_run_id` / `github_run_attempt` 중 하나만 제공 → **422**

### Result Target Integrity
`scenario_id` → `qa_item_id` resolve 후 해당 run의 target 여부 API에서 검증.
target에 없는 item → **409 RESULT_NOT_TARGETED**.
DB composite FK는 2차 방어선.

### Error Redaction
`error_summary` 저장 시:
- `Authorization Bearer`, `access_token`, `refresh_token`, `password`, `api_key`, `secret`, `token=` → `[REDACTED]`
- 최대 1000자 truncation

### artifact_ref 보안
`token=`, `X-Amz-Signature=`, `sig=`, `signature=` 포함 시 → **400**.

---

## 잔여 (Phase 2-B 범위 외)

| 항목 | Phase |
|------|-------|
| Slack 알림 | 2-C |
| GitHub dispatch 연동 | 2-D |
| Scheduler authority 이전 | 2-E |
| legacy `auto_qa_*` cleanup | 별도 WO |
