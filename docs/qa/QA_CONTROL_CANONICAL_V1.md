# QA Control Canonical Contract v1

**WO:** WO-QA-CONTROL-PHASE2A-001 + PATCH-2A-01 + PATCH-2A-02
**Status:** READY FOR OWNER REVIEW
**Date:** 2026-10-01
**Migration:** `supabase/migrations/20261001000000_create_qa_control_canonical_v1.sql`
**Seed:** `supabase/migrations/20261001000001_seed_qa_items_p0.sql`

---

## 1. Architecture

```
tai-qa        = QA Scenario / Assertion SoT (feature files)
tai-api       = QA Control Authority (API + DB write)
Supabase DB   = QA 운영 데이터 SoT
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
| expected_summary | text | YES | **display-only** — runtime assertion 사용 금지 |
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
| frequency_type | text | NO | MANUAL/MINUTES/HOURLY/DAILY/WEEKLY |
| frequency_value | integer | YES | > 0. MINUTES/HOURLY에서 필수 |
| anchor_time | time | YES | DAILY/WEEKLY에서 필수. MINUTES/HOURLY는 NULL/값 모두 허용 |
| day_of_week | smallint | YES | 0=Sun…6=Sat. WEEKLY에서 필수 |
| timezone | text | NO | DEFAULT 'Asia/Seoul' |
| next_run_at | timestamptz | YES | 스케줄러가 계산 |
| last_scheduled_at | timestamptz | YES | |
| created_at | timestamptz | NO | |
| updated_at | timestamptz | NO | |

**Semantic CHECK** (`qa_schedules_semantic_chk`):

| frequency_type | enabled | frequency_value | anchor_time | day_of_week |
|---------------|---------|-----------------|-------------|-------------|
| MANUAL | **false** | NULL | NULL | NULL |
| MINUTES | any | **> 0** | any | **NULL** |
| HOURLY | any | **> 0** | any | **NULL** |
| DAILY | any | **NULL** | **NOT NULL** | **NULL** |
| WEEKLY | any | **NULL** | **NOT NULL** | **0..6** |

→ MANUAL + enabled=true 일 수 없음. frequency_type 불일치 조합 DB에서 차단.

### `qa_runs` — 실행 요청 단위

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| id | uuid PK | NO | TAI 내부 Run ID |
| trigger_type | text | NO | CHECK: SCHEDULE/MANUAL/PR/RETRY |
| run_status | text | NO | DEFAULT 'QUEUED'. CHECK: QUEUED/RUNNING/COMPLETED/ERROR/CANCELED |
| github_run_id | bigint | YES | non-NULL 중복 금지 (partial unique index) |
| github_run_attempt | integer | YES | **CHECK: IS NULL OR >= 1** (PATCH-2A-02) |
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

### `qa_run_targets` — 실행 요청 대상 (PATCH-2A-01)

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| id | uuid PK | NO | |
| run_id | uuid FK→qa_runs | NO | |
| qa_item_id | uuid FK→qa_items | NO | |
| ordinal | integer | YES | 실행 순서 힌트. NULL = 순서 제한 없음. **CHECK: IS NULL OR >= 1** (PATCH-2A-02) |
| created_at | timestamptz | NO | |

UNIQUE: `(run_id, qa_item_id)` — 같은 run에 같은 항목 중복 금지.

**역할:**
```
qa_run_targets = 실행하기로 한 것 (request side)
qa_run_results = 실제 실행 결과 (evidence side)
```

QUEUED/RUNNING 상태에서도 대상 QA 항목을 DB에서 식별 가능.

### `qa_run_results` — 시나리오별 raw 실행 결과

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| id | uuid PK | NO | |
| run_id | uuid FK→qa_runs | NO | |
| qa_item_id | uuid FK→qa_items | NO | |
| result_status | text | NO | CHECK: **PASS/FAIL/BLOCKED/SKIPPED** |
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

**Composite FK** (`qa_run_results_target_fk`, PATCH-2A-02):
```
FOREIGN KEY (run_id, qa_item_id) REFERENCES qa_run_targets(run_id, qa_item_id)
```
→ result는 반드시 해당 run의 target에 존재하는 항목이어야 한다. target 밖 항목 INSERT는 DB FK 오류.

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
MANUAL  MINUTES  HOURLY  DAILY  WEEKLY
```

### Run Trigger
```
SCHEDULE  MANUAL  PR  RETRY
```

### Run Status
```
QUEUED  RUNNING  COMPLETED  ERROR  CANCELED
```

### Result Status (DB raw)
```
PASS  FAIL  BLOCKED  SKIPPED
```

### Effective Status (API/UI derived)
```
PASS  FAIL  FLAKY  BLOCKED  SKIPPED  NEVER_RUN
```

**FLAKY** 정의:
```
같은 run_id + qa_item_id에서:
attempt 1 = FAIL
attempt 2 = PASS
→ effective_status = FLAKY
```

**NEVER_RUN** 정의:
```
qa_run_results에 해당 qa_item의 history 없음
→ effective_status = NEVER_RUN
```

**FLAKY, NEVER_RUN 모두 DB에 저장하지 않음.** API가 raw 데이터로부터 파생.

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

Playwright retry 시나리오:

**DB raw rows:**
```
qa_run_results row 1: run_id=X, qa_item_id=Y, attempt=1, result_status='FAIL'
qa_run_results row 2: run_id=X, qa_item_id=Y, attempt=2, result_status='PASS'
```

**API 파생:**
```
effective_status = 'FLAKY'
```

DB에는 `FLAKY`를 저장하지 않는다. raw attempt을 보존하는 구조만 제공. aggregation 구현 = Phase 2-B/C.

---

## 6. Run / Target / Result Distinction

```
qa_runs         = 실행 요청 1건 (GitHub Actions 1 workflow run)
qa_run_targets  = 해당 run에서 실행하기로 한 QA 항목 (request side)
qa_run_results  = 실제 실행된 raw 시나리오 결과 (evidence side)
```

관계:
```
qa_runs.id (1) ──→ (N) qa_run_targets.run_id
qa_runs.id (1) ──→ (N) qa_run_results.run_id
qa_items.id (1) ──→ (N) qa_run_targets.qa_item_id
qa_items.id (1) ──→ (N) qa_run_results.qa_item_id
```

**Request/Evidence Integrity (PATCH-2A-02):**
```
qa_run_results(run_id, qa_item_id)
    → FK → qa_run_targets(run_id, qa_item_id)
```

- result는 반드시 target을 참조해야 한다.
- target에 없는 qa_item의 result는 DB에서 INSERT 불가 (FK 차단).
- request side(target)와 evidence side(result)의 정합성은 DB FK가 보장.

**상태별 조회 패턴:**
```
QUEUED / RUNNING:  qa_run_targets로 대상 QA 항목 파악 (qa_run_results 없음)
COMPLETED:         qa_run_results로 실제 결과 조회 (target 범위 내 보장)
```

---

## 7. Legacy Deprecation

| 테이블 | 상태 | 처리 |
|--------|------|------|
| auto_qa_checks | DEPRECATED | row=0, UNTOUCHED |
| auto_qa_log | DEPRECATED | row=0, UNTOUCHED |
| auto_qa_pending | DEPRECATED | row=0, UNTOUCHED |

별도 cleanup WO에서 DROP 여부 결정.

---

## 8. Security Rule

```
RLS = ENABLED (qa_items, qa_schedules, qa_runs, qa_run_targets, qa_run_results)
anon direct access = NONE (정책 없음 = 차단)
authenticated direct access = NONE (정책 없음 = 차단)
tai-api service_role = DB 접근 authority
browser = QA 테이블 접근 금지
```

**secret/token 저장 금지 컬럼:**
- `artifact_ref`: 내부 reference만 (GitHub artifact ID / storage key). signed URL 저장 금지.
- `error_summary`: 예외 메시지 원문 노출 최소화.

---

## 9. Scheduler Authority Rule

현재 schedule authority:
```
tai-qa/.github/workflows/p0-smoke.yml
cron: '0 23 * * *'  (23:00 UTC = 08:00 KST)
```

Phase 2-A: 모든 qa_schedules.enabled = false, frequency_type = MANUAL.
DB Scheduler가 아직 authority가 아니다.

Phase 2-E: DB Scheduler가 authority 이전. GitHub cron 유지/제거 별도 전환 작업.
전환 전까지 schedule authority 2개 동시 활성화 금지.

---

## 10. Phase 2-B Handoff

Phase 2-A 완료 체크리스트:
- [x] Canonical 5-table contract 확정 (PATCH-2A-01에서 5개로 확정)
- [x] status/check constraint 확정
- [x] Run / Target / Result 3분리 완료
- [x] FLAKY 표현 가능 구조 (raw attempts 보존)
- [x] schedule semantic constraint 존재
- [x] current P0 10건 mapping 완료
- [x] expected_summary = display-only 명시
- [x] RLS ON (5개 테이블)
- [x] frontend direct access 없음
- [x] legacy 3 table untouched
- [x] migration 작성
- [x] contract 문서 작성
- [x] result→target composite FK (PATCH-2A-02)
- [x] ordinal >= 1 CHECK (PATCH-2A-02)
- [x] github_run_attempt >= 1 CHECK (PATCH-2A-02)
- [ ] production DB apply (Owner Approval 대기)
- [ ] verification V1~V13+ dynamic (apply 후 실행)

Phase 2-B handoff 항목:
```
1. GET  /admin/qa/items               — 항목 목록 + last_result join
2. PATCH /admin/qa/items/{id}         — enabled 토글
3. GET  /admin/qa/runs                — run 이력
4. POST /admin/qa/runs                — manual dispatch (targets 생성 포함)
5. POST /admin/qa/runs/{id}/results   — ingestion endpoint (GitHub Actions callback)
6. GET  /admin/qa/runs/{id}           — run 상세 + targets + results
```

Phase 2-B 시작 조건: GPT 검증 + Owner production apply 승인.
