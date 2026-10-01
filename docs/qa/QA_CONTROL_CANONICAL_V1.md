# QA Control Canonical Contract v1

**WO:** WO-QA-CONTROL-PHASE2A-001  
**Status:** READY FOR OWNER REVIEW  
**Date:** 2026-10-01  
**Migration:** `supabase/migrations/20261001000000_create_qa_control_canonical_v1.sql`  
**Seed:** `supabase/migrations/20261001000001_seed_qa_items_p0.sql`

---

## 1. Architecture

```
tai-qa        = QA Scenario / Assertion SoT (feature files)
tai-api       = QA Control Authority (API + DB write)
Supabase DB   = QA 운영 데이터 SoT (qa_items / qa_schedules / qa_runs / qa_run_results)
admin UI      = QA Control / Monitoring UI
```

**Frontend access rule:**
```
Admin Front → tai-api → Supabase    (ONLY valid path)
Admin Front → Supabase REST direct  (FORBIDDEN — RLS blocks)
```

Phase 2-A scope: DB contract only. API / Scheduler / Admin Front 구현은 별도 WO.

---

## 2. Table Contract

### `qa_items` — QA 항목 정본

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| id | uuid PK | NO | gen_random_uuid() |
| scenario_id | text UNIQUE | NO | tai-qa scenario 제목과 1:1 |
| site_code | text | NO | CHECK: WWW/SAFE/API/ADMIN/MKT/WORKER/EXTERNAL |
| category | text | NO | free text (AUTH/MYPAGE/SEARCH/DIAGNOSIS/LANDING/…) |
| name | text | NO | 한국어 시나리오명 |
| description | text | YES | 실행 조건 설명 |
| expected_summary | text | YES | **display-only** — runtime assertion 금지 |
| priority | text | NO | CHECK: P0/P1/P2/P3 |
| runner_type | text | NO | CHECK: PLAYWRIGHT/API/HEALTH |
| enabled | boolean | NO | DEFAULT true |
| created_at | timestamptz | NO | DEFAULT now() |
| updated_at | timestamptz | NO | DEFAULT now() |

### `qa_schedules` — 항목별 실행 스케줄

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| id | uuid PK | NO | |
| qa_item_id | uuid FK→qa_items | NO | UNIQUE (1항목 1스케줄) |
| enabled | boolean | NO | DEFAULT false |
| frequency_type | text | NO | CHECK: MINUTES/HOURLY/DAILY/WEEKLY/MANUAL |
| frequency_value | integer | YES | > 0. MINUTES/HOURLY에서 사용 |
| anchor_time | time | YES | DAILY/WEEKLY 기준 시간 |
| day_of_week | smallint | YES | 0=Sun…6=Sat. WEEKLY only |
| timezone | text | NO | DEFAULT 'Asia/Seoul' |
| next_run_at | timestamptz | YES | 스케줄러가 계산 |
| last_scheduled_at | timestamptz | YES | |
| created_at | timestamptz | NO | |
| updated_at | timestamptz | NO | |

### `qa_runs` — 실행 요청 단위

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| id | uuid PK | NO | TAI 내부 Run ID |
| trigger_type | text | NO | CHECK: SCHEDULE/MANUAL/PR/RETRY |
| run_status | text | NO | DEFAULT 'QUEUED'. CHECK: QUEUED/RUNNING/COMPLETED/ERROR/CANCELED |
| github_run_id | bigint | YES | non-NULL 중복 금지 (partial unique index) |
| github_run_attempt | integer | YES | |
| head_sha | text | YES | |
| branch_name | text | YES | |
| requested_by | text | YES | |
| requested_at | timestamptz | NO | DEFAULT now() |
| started_at | timestamptz | YES | |
| finished_at | timestamptz | YES | |
| error_code | text | YES | |
| error_summary | text | YES | |
| created_at | timestamptz | NO | |
| updated_at | timestamptz | NO | |

**주의:** `qa_runs.id` ≠ `github_run_id`. TAI 내부 authority와 외부 실행기 reference는 별개.

### `qa_run_results` — 시나리오별 실행 결과

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| id | uuid PK | NO | |
| run_id | uuid FK→qa_runs | NO | |
| qa_item_id | uuid FK→qa_items | NO | |
| result_status | text | NO | CHECK: PASS/FAIL/FLAKY/BLOCKED/SKIPPED |
| attempt | integer | NO | DEFAULT 1. >= 1 |
| duration_ms | integer | YES | >= 0 |
| http_status | integer | YES | |
| error_code | text | YES | |
| error_summary | text | YES | |
| artifact_ref | text | YES | 내부 reference만. signed URL/token 저장 금지 |
| started_at | timestamptz | YES | |
| finished_at | timestamptz | YES | |
| checked_at | timestamptz | NO | DEFAULT now() |
| created_at | timestamptz | NO | |

UNIQUE: `(run_id, qa_item_id, attempt)` — retry별 row 독립 보존.

---

## 3. Status Enums / Check Values

### Priority
```
P0  P1  P2  P3
```

### Runner Type
```
PLAYWRIGHT  API  HEALTH
```

### Site Code
```
초기: WWW  SAFE  API  ADMIN
확장 가능: MKT  WORKER  EXTERNAL
```

### Schedule Frequency
```
MINUTES  HOURLY  DAILY  WEEKLY  MANUAL
```

### Run Trigger
```
SCHEDULE  MANUAL  PR  RETRY
```

### Run Status
```
QUEUED  RUNNING  COMPLETED  ERROR  CANCELED
```

### Result Status
```
PASS  FAIL  FLAKY  BLOCKED  SKIPPED
```

`NEVER_RUN`은 DB에 저장하지 않는다 — 이력 부재를 API/UI가 파생 표현.

---

## 4. Site / Category Rule

**site_code** = 서비스 진입점 (URL 기준)

| site_code | 대상 URL |
|-----------|----------|
| WWW | taieng.co.kr |
| SAFE | safe.taieng.co.kr |
| API | api.taieng.co.kr |
| ADMIN | admin.taieng.co.kr |
| MKT | mkt.45cm.com |

**category** = 기능 영역 (자유 text, 예시)

```
AUTH        로그인/인증
MYPAGE      마이페이지
SEARCH      통합검색
DIAGNOSIS   법령진단
LANDING     메인/랜딩
PAYMENT     결제
LEGAL       법규엔진
```

category는 site_code와 독립. SEARCH, MYPAGE, AUTH 등은 category이지 site_code가 아니다.

---

## 5. FLAKY Definition

Playwright retry 결과:
- attempt 1 = FAIL
- attempt 2 = PASS
→ 최종 운영 상태 = **FLAKY**

DB 저장 방식:
```
qa_run_results row 1: attempt=1, result_status='FAIL'
qa_run_results row 2: attempt=2, result_status='PASS'
```
두 row를 독립 보존. API summary는 FLAKY로 집계 (Phase 2-B/C 구현).

Phase 2-A: raw attempt 보존 구조 제공. aggregation 구현은 Phase 2-B/C.

---

## 6. Run vs Result Distinction

```
qa_runs       = 실행 요청 1건 (GitHub Actions 1 workflow run)
qa_run_results = 해당 run에서 실행된 시나리오별 결과 (N개)
```

관계:
```
qa_runs.id (1) ──→ (N) qa_run_results.run_id
qa_items.id (1) ──→ (N) qa_run_results.qa_item_id
```

같은 시나리오라도 retry = attempt 번호가 다른 별도 row.

---

## 7. Legacy Deprecation

| 테이블 | 상태 | 처리 |
|--------|------|------|
| auto_qa_checks | DEPRECATED | row=0, UNTOUCHED |
| auto_qa_log | DEPRECATED | row=0, UNTOUCHED |
| auto_qa_pending | DEPRECATED | row=0, UNTOUCHED |

기존 3개 테이블은 이번 WO에서 수정/삭제하지 않는다. 별도 cleanup WO에서 DROP 여부 결정.

---

## 8. Security Rule

```
RLS = ENABLED (qa_items, qa_schedules, qa_runs, qa_run_results)
anon direct access = NONE (정책 없음 = 차단)
authenticated direct access = NONE (정책 없음 = 차단)
tai-api service_role = DB 접근 authority
browser anon key = QA 테이블 접근 불가
```

**secret/token 저장 금지 컬럼:**
- `artifact_ref`: 내부 reference만. signed URL / GitHub download URL permanent 저장 금지.
- `error_summary`: 예외 메시지 원문 노출 최소화 (수집 시 truncate 권고).

---

## 9. Scheduler Authority Rule

현재 schedule authority:
```
tai-qa/.github/workflows/p0-smoke.yml
cron: '0 23 * * *'  (23:00 UTC = 08:00 KST)
```

Phase 2-A: 모든 qa_schedules.enabled = false, frequency_type = MANUAL.
→ DB Scheduler가 아직 authority가 아니다.

Phase 2-E: DB Scheduler가 authority 이전. GitHub cron 유지/제거 별도 전환 작업.
→ 전환 전까지 schedule authority 2개 동시 활성화 금지.

---

## 10. Phase 2-B Handoff

Phase 2-A 완료 조건:
- [x] Canonical 4-table contract 확정
- [x] status/check constraint 확정
- [x] Run / Result 분리 완료
- [x] FLAKY 표현 가능 구조
- [x] schedule contract 존재
- [x] current P0 10건 mapping 완료
- [x] expected_summary = display-only 명시
- [x] RLS ON
- [x] frontend direct access 없음
- [x] legacy 3 table untouched
- [x] migration 작성
- [x] contract 문서 작성
- [ ] production DB apply (Owner Approval 대기)
- [ ] verification V1~V13 (apply 후 실행)

Phase 2-B handoff 항목:
```
1. GET  /admin/qa/items              — 항목 목록 + last_result join
2. PATCH /admin/qa/items/{id}        — enabled 토글
3. GET  /admin/qa/runs               — run 이력
4. POST /admin/qa/runs               — manual dispatch
5. POST /admin/qa/runs/{id}/results  — ingestion endpoint (GitHub Actions callback)
6. GET  /admin/qa/runs/{id}          — run 상세 + results
```

Phase 2-B 시작 조건: GPT 검증 + Owner production apply 승인.
