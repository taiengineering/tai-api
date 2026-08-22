# WORK_SCHEDULES_PARTITION_PRODUCTION_CUTOVER_RUNBOOK_v1

> 작성일: 2026-08-23
> 최종 정정: 2026-08-23 (REV-A — 실측 운영환경 반영 5건)
> 상위: WORK_SCHEDULES_PARTITION_DESIGN_FINAL_v1.md
> 관련: WORK_SCHEDULES_PARTITION_CODE_COMPAT_v1.md
> 상태: **RUNBOOK DESIGN = READY / PRODUCTION APPLY = NOT APPROVED**

```text
이 문서는 실행 지시서가 아니라 승인 대기 절차서다.
운영자 승인 없이 어떤 단계도 실행하지 않는다.
```

---

## 0. 이 문서를 읽는 법

명령 블록은 두 종류로만 표기한다. **혼동하면 사고가 난다.**

```text
[READ ONLY]        조회만 한다. 되돌릴 것이 없다.
[MUTATION]         상태를 바꾼다. 승인 게이트 통과 후에만 실행한다.
```

인간 승인 지점은 `GATE-*` 로 표시하고, 자동으로 다음 단계로 넘어가지 않는다.

### REV-A 정정 요약 (2026-08-23)

```text
1. CI PASS          → LOCAL PYTEST PASS (GitHub Actions unavailable)
2. post-deploy.yml  → AUTO SMOKE UNAVAILABLE / MANUAL SMOKE REQUIRED
3. writer inventory → 3-layer (application / database / external)
4. pg_cron job 1    → 전/후 모두 DISABLED, 재활성화 금지
5. GATE-SESSION     → 신규 추가 (필수 human gate)
```

---

## 1. Canonical Artifact (고정)

이 SHA 외의 artifact 사용을 금지한다. 복사·수정본 실행 금지.

### DB UP

```text
path    docs/sql/20260822_work_schedules_partition_up.sql
commit  b81e7018fe2207cd29919317ffe964e942391fce
blob    ac8adc58356c86d333044e6353152504a7175758
sha256  147f75f2864fd3bb261fb6ebedae7b34b5621b311d556e5d0d8e6b028300cca7
```

### DB DOWN

```text
path    docs/sql/20260822_work_schedules_partition_down.sql
commit  0972a18e9f158ce49c5d7163ab31860ebcb4f7db
blob    96da5c88e041b486d6dda52b51efaec1fff39d01
sha256  57768a50dd9e7643bb1708ec198e48bfc62d0474852faf433b15ae7f2e9df20d
```

### Code Patch

```text
branch            wo-work-schedules-partition-code-compat
base              0972a18e9f158ce49c5d7163ab31860ebcb4f7db
canonical HEAD    23d16ac21c87dcbdf5ff2a1b590fd8d797121349
PR                #187 (draft, DO NOT MERGE)
변경 파일          routers/work_schedules.py
                  routers/worker_check.py
                  routers/legal_engine_patch.py
                  routers/inspection_checklist.py
```

---

## 2. Production 환경 (실측)

```text
플랫폼        Railway
project       tai-api            7c3ab53b-feb6-40a4-a4f0-7ade3f6e524b
environment   production         9dacb6f0-5d2a-4064-839e-e050af50bf30
service       tai-api-prod       4cf52678-1fbf-42f4-8bd7-f59fab98c3ae
source        taiengineering/tai-api (DOCKERFILE)
health        /health
sleep         when inactive = true
도메인         api.taieng.co.kr

DB            Supabase vwlahtguyggrhvslabax (PostgreSQL 17.6)
org plan      pro
DB 크기        4,773 MB
```

### 현재 production 배포 SHA

```text
0972a18e9f158ce49c5d7163ab31860ebcb4f7db
```

**patch base 와 동일하다. CODE DRIFT = 0.**

---

## 3. 가장 중요한 사실 4가지

이것을 모르면 순서를 틀린다.

### 3-1. main merge = 자동배포

Railway 가 `taiengineering/tai-api` 를 직접 바라본다. **main 에 머지하는 순간 배포가 시작된다.**

```text
DB UP 이전에 main merge 금지
```

### 3-2. 코드는 구 schema 와 호환되지 않는다

patch 는 child INSERT payload 에 `factory_id` 를 추가한다. 파티션 적용 전 DB 에 배포하면 컬럼이 없어 INSERT 가 실패한다.

```text
코드 선배포 불가능
```

### 3-3. GitHub Actions 가 작동하지 않는다 [REV-A]

```text
최근 workflow run 5건 = 전부 2026-05-01, 전부 failure
그 이후 4개월간 run 0건
PR #187 head 5128513e → check-runs 0건
```

따라서 **CI PASS 는 획득 불가능**하다. TEST GATE 는 **local pytest** 로 대체한다(§4 참조).

원인 조사는 이번 WP 범위 밖이다. `ISSUE-CI-DISABLED-01` 로 별건 유지한다.

### 3-4. post-deploy.yml 은 실행 경로가 아니다 [REV-A]

```text
post-deploy.yml = AVAILABLE FILE
                ≠ AVAILABLE EXECUTION PATH
```

Actions 가 죽어 있으므로 `workflow_dispatch` 로 호출할 수 없다.

```text
AUTO SMOKE   = UNAVAILABLE
MANUAL SMOKE = REQUIRED
```

smoke 는 operator 가 직접 수행한다(§16 참조).

---

## 4. TEST GATE [REV-A — CI 대체]

### 실행 기준

```text
TEST REVISION = PR HEAD
(23d16ac 는 code patch SHA, PR HEAD 는 문서 포함 전체 상태)
```

### 명령

```bash
git checkout wo-work-schedules-partition-code-compat
python3 -m venv .venv-test && source .venv-test/bin/activate
pip install -r requirements-test.txt

export INTERNAL_API_SECRET=test
export ANTHROPIC_API_KEY=test

pytest tests/ -v --tb=short \
  --ignore=tests/check_db_integrity.py \
  --ignore=tests/check_mapping_coverage.py \
  --ignore=tests/test_legal_engine.py \
  --ignore=tests/test_legal_engine_52.py \
  --ignore=tests/test_legal_engine_layer.py \
  --ignore=tests/wait_for_deploy.py \
  --ignore=tests/test_member_inquiries_save.py \
  --ignore=tests/test_law_collector.py
```

마지막 2개 ignore 는 `ci.yml` 에 없는 추가분이다. collection error 로 **pytest 전체가 중단되기 때문**이며, `ISSUE-TEST-COLLECTION-ERROR-01` 로 별건 유지한다.

### 실측 결과 (2026-08-23)

```text
497 passed / 11 failed
patch 인접 24 passed / 0 failed
  (test_route_order / test_status_vocab_c2 /
   test_company_scope_e1 / test_inspection_sets_current)

PATCH-CAUSED = 0
PRE-EXISTING = 8
ENV          = 3
```

### 판정 기준

```text
PATCH-CAUSED 실패 0    → TEST GATE PASS
PATCH-CAUSED 실패 존재 → CUTOVER BLOCKED
```

기존 실패는 blocker 가 아니다. 단 **분류 없이 넘어가지 않는다.**

---

## 5. Writer Inventory — 3 LAYER [REV-A]

> **교훈**: 이 작업에서 writer 누락이 네 차례 발견됐다.
> 코드 grep 2회 → pg_cron 1회 → cron_job_master 1회.
> **코드만 보고 writer inventory 를 닫으면 안 된다.**

### LAYER 1 — APPLICATION

| writer | freeze method | verification |
|---|---|---|
| `work_schedules.py` `_apply_one_update()` | Railway 서비스 정지 | `pg_stat_activity` |
| `worker_check.py` `submit_check()` | 동일 | 동일 |
| `legal_engine_patch.py` `auto_assign_schedules()` | 동일 | 동일 |
| `inspection_checklist.py` `start_inspection()` | 동일 | 동일 |
| `equipment_checkins.py` | 동일 | 동일 |
| work_schedules INSERT ×14 (부모) | 동일 | 동일 |
| `overdue_checker.py` ×2 | 동일 (UPDATE only) | 동일 |

```text
CHILD INSERT WRITERS = 5, 전부 patch 커버
```

### LAYER 2 — DATABASE

| 항목 | 실측 | 조치 |
|---|---|---|
| trigger (4개 테이블) | **0건** | — |
| event trigger | 6건 (Supabase 시스템) | 무관 |
| function/procedure 전수 | 대상 참조 = `generate_daily_assignments()` **1건** | **비활성화 완료** |
| matview | `dashboard_stats` (READ 집계) | 무관 |
| view | 0건 | — |
| publication | `supabase_realtime`, 대상 0개 | 무관 |
| subscription | 0건 | — |
| **pg_cron** | 10건 | **3건 비활성화 완료** |

**pg_cron 상세**

| jobid | jobname | 스케줄 | 상태 |
|---|---|---|---|
| **1** | `daily_assignments` | `10 0 * * *` | **DISABLED (영구)** |
| 2 | daily_health | `0 0 * * *` | active, 무관 |
| **3** | `qa_send` | `0,30 * * * *` | **DISABLED (임시)** |
| **4** | `qa_collect` | `2,32 * * * *` | **DISABLED (임시)** |
| 5~9 | kosha_* | 일/주 | active, 무관 |
| 10 | health_cleanup | `0 3 * * *` | active, 무관 |

### LAYER 3 — EXTERNAL

**① cron-job.org**

```text
POST /overdue/check   매일 09:00 KST, 인증 없음
실행 이력 = 0건 (overdue_history 0행, wa_escalated 0, last_reminded null)
→ 사실상 비활성이나 콘솔 pause 는 여전히 필수 (GATE-CRON)
```

**② `cron_job_master` / `cron_schedule_config` (자체 스케줄러)** [REV-A 신규]

API 레벨 스케줄러가 별도로 존재한다. `python-httpx` 로 매분 동작하며 `cron_job_log` 에 기록한다.

```text
cron_job_master        32 job 정의
cron_schedule_config   8 job 스케줄 연결 (전부 is_enabled=true)
```

대상 테이블 관련 job 4건은 **전부 비활성**이다.

| job_code | endpoint | master_active | scheduled |
|---|---|---|---|
| `SCHEDULE_GENERATE_ALL` | `/legal-engine/generate-schedules` | **false** | 없음 |
| `DUE_ALERT_DAILY` | `/notifications/trigger-due-alerts` | true | **없음** |
| `OVERDUE_PREPARE` | `/overdue/prepare` | **false** | 없음 |
| `OVERDUE_DISPATCH` | `/overdue/dispatch` | **false** | 없음 |

스케줄 활성 8건(`INTEGRITY_EVALUATE` `*/5`, `SYSTEM_HEALTH_CHECK` `*/10`, `DB_STATS_COLLECT`, `REPORT_DAILY`, `KCSC_SYNC`, `LAW_*` 3건)은 **4개 대상 테이블에 write 하지 않는다.**

```text
[주의] CONTROL_BRIDGE_EVALUATE 는 sched_enabled=null 인데도 실행 기록이 있다.
       스케줄 설정 없이 도는 경로가 존재한다는 뜻이다.
       direct://control_bridge_evaluate — 대상 테이블 무관 확인.
```

### 최종

```text
LAYER 1 APPLICATION  CLOSED
LAYER 2 DATABASE     CLOSED
LAYER 3 EXTERNAL     CLOSED

UNCOVERED WRITERS = 0
```

---

## 6. 실행 순서 (고정) [REV-A]

```text
[1] PR 생성 (draft 유지)
[2] TEST GATE — local pytest PASS      ← CI 대체
[3] GATE-SESSION                        ← 신규
[4] GATE-PITR
[5] GATE-CRON
[6] maintenance 시작
[7] cron pause (cron-job.org)
[8] Railway writer stop / traffic block
[9] active writer = 0 확인
[10] production PRECHECK
[11] canonical UP checksum 확인
[12] GATE-DB-UP  ← 승인
[13] DB UP 실행
[14] DB POSTCHECK
[15] GATE-DEPLOY ← 승인
[16] PR merge to main
[17] Railway 자동배포
[18] deployment SHA 확인
[19] /health (cold start 고려)
[20] MANUAL smoke A~E                   ← workflow_dispatch 불가
[21] GATE-GO-NOGO ← 승인

PASS → writer 재개 → pg_cron job 3·4 재활성화 → maintenance OFF → observation
FAIL → maintenance 유지 → rollback 진입
```

---

## 7. GATE-SESSION (인간 승인) [REV-A 신규]

> **배경**: 운영자가 멀티 윈도우로 여러 Claude 세션을 병렬 운용한다.
> 2026-08-23 오후 `column work_assignments.factory_id does not exist` 에러 5건이
> 다른 세션의 조회 쿼리에서 발생한 것이 확인됐다(READ only, writer 아님).
>
> **사람도 writer 다.** maintenance 는 애플리케이션만 막는다.

체크리스트:

```text
[ ] cutover 중 다른 Claude/운영 세션의 taieng DB 작업 금지 공지
[ ] 다른 세션 종료 또는 대기 상태 확인
[ ] Supabase Dashboard SQL Editor 사용 중지 확인
[ ] pg_stat_activity 로 예상 외 연결 확인
[ ] 운영자 서명: ______
```

확인 SQL:

```sql
SELECT pid, usename, application_name, client_addr, state,
       left(query, 80) AS q, state_change
FROM pg_stat_activity
WHERE datname = current_database()
  AND pid <> pg_backend_pid()
  AND state <> 'idle'
ORDER BY state_change DESC;
```

```text
예상 외 세션 존재 → PRODUCTION DB UP = BLOCKED
```

---

## 8. GATE-PITR (인간 승인)

```text
확인 위치
Supabase Dashboard > Project vwlahtguyggrhvslabax
> Database > Backups > Point in time
```

### 실측 (2026-08-23)

```text
PITR add-on   = NOT ENABLED  ("Enable add-on" 버튼 노출)
일일 백업      = PHYSICAL 7일치 (15~21 Aug)
최신 백업      = 21 Aug 2026 18:34 UTC
복구 공백      = 약 23시간
Restore 버튼   = 노출 (권한 있음)

WAL 아카이빙   = archive_mode=on, archive_timeout=120
                archived 21,382건, failed 0
```

**WAL 아카이빙이 도는 것은 PITR 구독의 증거가 아니다.** Supabase 는 모든 프로젝트에서 내부 백업 목적으로 항상 아카이빙한다.

### 비용

```text
7일 보존 $100/월 · 14일 $200 · 28일 $400
시간당 과금 → cutover 기간만 활성화 시 24~48h = 약 $3.3~6.7
⚠ Spend Cap 미적용 — 끄는 것을 잊으면 계속 청구된다
⚠ Small compute add-on 이상 필요할 수 있음
```

### 체크리스트

```text
[ ] PITR add-on 활성화
[ ] 활성화 후 "Point in time" 탭에 실제 복구 가능 시점 생성 확인
    ※ 버튼만 누른 것으로 PASS 처리 금지
[ ] 보존기간 기록: ______일
[ ] restore 절차 확인
[ ] operator restore 권한 확인
[ ] cutover 직전 복구 목표 시점 기록: ______
[ ] observation 종료 후 비활성화 예정 기록
```

```text
하나라도 미확인/NO → PRODUCTION DB UP = BLOCKED
```

migration DOWN 을 backup 대체물로 취급하지 않는다.

---

## 9. GATE-CRON (인간 승인)

```text
[ ] cron-job.org 로그인
[ ] POST /overdue/check job 식별
[ ] job pause 실행
[ ] next run 없음 확인
[ ] 다른 job 이 4개 대상 테이블을 건드리지 않는지 확인
[ ] pg_cron job 1 = disabled 유지 확인
[ ] pg_cron job 3·4 = disabled 확인 (cutover 후 복구 대상)
```

```text
미확인 → PRODUCTION DB UP = BLOCKED
```

`/overdue/check` 는 인증 없는 머신 엔드포인트라 애플리케이션 레벨 차단이 불가능하다. **콘솔 pause 가 유일한 확실한 수단이다.**

---

## 10. Maintenance 시작 · Writer Freeze

### [MUTATION] Railway writer 정지

```text
A. Railway 콘솔에서 tai-api-prod 서비스 일시정지
B. 도메인/트래픽 차단
```

### [READ ONLY] active writer 확인

```sql
SELECT count(*) AS active_ws_sessions
FROM pg_stat_activity
WHERE state = 'active' AND query ILIKE '%work_schedules%';

SELECT count(*) AS total_active
FROM pg_stat_activity
WHERE state = 'active' AND pid <> pg_backend_pid();
```

```text
active_ws_sessions = 0 이 될 때까지 대기
0 이 아니면 DB UP 진입 금지
```

---

## 11. Production PRECHECK

### [READ ONLY] 데이터 무결성 6항목

```sql
SELECT
  (SELECT count(*) FROM work_schedules WHERE factory_id IS NULL) AS ws_factory_null,
  (SELECT count(*) FROM work_schedules ws JOIN inspection_sets s ON s.id=ws.inspection_set_id
     WHERE ws.factory_id IS DISTINCT FROM s.factory_id) AS set_factory_mismatch,
  (SELECT count(*) FROM (SELECT inspection_set_id, planned_date, factory_id FROM work_schedules
     WHERE inspection_set_id IS NOT NULL AND planned_date IS NOT NULL
     GROUP BY 1,2,3 HAVING count(*)>1) d) AS dup_unique_candidate,
  (SELECT count(*) FROM work_assignments wa WHERE wa.schedule_id IS NOT NULL
     AND NOT EXISTS (SELECT 1 FROM work_schedules ws WHERE ws.id=wa.schedule_id)) AS wa_orphan,
  (SELECT count(*) FROM safety_inspections si WHERE si.assignment_id IS NOT NULL
     AND NOT EXISTS (SELECT 1 FROM work_schedules ws WHERE ws.id=si.assignment_id)) AS si_orphan,
  (SELECT count(*) FROM equipment_checkins ec JOIN work_schedules ws ON ws.id=ec.schedule_id
     WHERE ec.factory_id IS DISTINCT FROM ws.factory_id) AS ec_mismatch;
```

```text
6개 값 전부 0 이어야 한다.
하나라도 0 이 아니면 DB UP 금지 → 02A 재검토
```

### [READ ONLY] Schema Drift 재확인

```sql
SELECT
  (SELECT count(*) FROM information_schema.columns
    WHERE table_schema='public' AND table_name='work_schedules') AS ws_columns,
  (SELECT count(*) FROM pg_indexes
    WHERE schemaname='public' AND tablename='work_schedules') AS ws_indexes,
  (SELECT count(*) FROM pg_constraint WHERE conrelid='work_schedules'::regclass AND contype='c') AS checks,
  (SELECT count(*) FROM pg_trigger WHERE tgrelid='work_schedules'::regclass AND NOT tgisinternal) AS triggers,
  (SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid='work_schedules'::regclass) AS owner,
  (SELECT relrowsecurity FROM pg_class WHERE oid='work_schedules'::regclass) AS rls_enabled,
  (SELECT relforcerowsecurity FROM pg_class WHERE oid='work_schedules'::regclass) AS rls_forced,
  (SELECT count(*) FROM pg_policies WHERE schemaname='public' AND tablename='work_schedules') AS policies,
  (SELECT count(*) FROM pg_description d JOIN pg_class c ON c.oid=d.objoid
     JOIN pg_namespace n ON n.oid=c.relnamespace AND n.nspname='public'
    WHERE c.relname='work_schedules') AS comments,
  (SELECT count(*) FROM information_schema.role_table_grants
    WHERE table_schema='public' AND table_name='work_schedules') AS grants,
  (SELECT relkind FROM pg_class WHERE oid='work_schedules'::regclass) AS relkind;
```

기대값 (2026-08-22 실측):

```text
ws_columns=37  ws_indexes=12  checks=0  triggers=0
owner=postgres  rls_enabled=true  rls_forced=false
policies=6  comments=26  grants=28  relkind=r
```

```text
하나라도 다르면 → CUTOVER BLOCKED → 02A 재검토
```

---

## 12. UP artifact checksum 확인

```bash
shasum -a 256 docs/sql/20260822_work_schedules_partition_up.sql
```

```text
기대값 147f75f2864fd3bb261fb6ebedae7b34b5621b311d556e5d0d8e6b028300cca7
불일치 → 실행 금지
복사본·수정본 실행 금지
```

---

## 13. GATE-DB-UP (인간 승인)

```text
[ ] TEST GATE (local pytest) PASS
[ ] GATE-SESSION 통과
[ ] GATE-PITR 통과
[ ] GATE-CRON 통과
[ ] maintenance ON
[ ] active writer = 0
[ ] PRECHECK 6항목 전부 0
[ ] Schema Drift 없음
[ ] UP checksum 일치
[ ] 실행 시각 기록: ______
[ ] 운영자 승인 서명: ______
```

---

## 14. DB UP 실행

### [MUTATION]

```text
canonical UP artifact 를 그대로 실행
docs/sql/20260822_work_schedules_partition_up.sql
```

내부 동작:

```text
ACCESS EXCLUSIVE LOCK (4개 테이블)
→ HARD PRECHECK → PRE-state 스냅샷
→ shadow partitioned table (HASH 16) → 37컬럼 명시 COPY
→ full-row equality 검증 → index 8 / FK / comments 26 복제
→ child factory_id 추가 + backfill → pair CHECK
→ cutover swap → child 복합 FK (MATCH FULL)
→ RLS·policy·owner·grants 복원 → POSTCHECK → COMMIT
```

단일 트랜잭션이므로 **중간 실패 시 자동 롤백되고 원본은 무변경**이다.

### 예상 소요 [한계]

```text
local dry-run  work_assignments 371건 backfill
production     work_assignments 5,991건 backfill
→ lock 유지 시간이 더 길다. UNBENCHMARKED.
```

---

## 15. DB POSTCHECK

```sql
SELECT relkind FROM pg_class WHERE oid='public.work_schedules'::regclass;  -- 'p'
SELECT count(*) FROM pg_inherits WHERE inhparent='public.work_schedules'::regclass;  -- 16
SELECT array_length(conkey,1) FROM pg_constraint
 WHERE conrelid='public.work_schedules'::regclass AND contype='p';  -- 2
SELECT count(*) FROM public.work_schedules;
SELECT count(*) FROM public.work_assignments
 WHERE (schedule_id IS NULL) <> (factory_id IS NULL);   -- 0
SELECT count(*) FROM public.safety_inspections
 WHERE (assignment_id IS NULL) <> (factory_id IS NULL); -- 0
SELECT conname, confmatchtype FROM pg_constraint
 WHERE conname IN ('work_assignments_schedule_fkey','safety_inspections_schedule_fkey');  -- 'f'
SELECT to_regclass('public.work_schedules_old') IS NOT NULL AS rollback_anchor;  -- true
```

```text
하나라도 기대와 다르면 → rollback 판단 진입
```

---

## 16. GATE-DEPLOY (인간 승인)

```text
[ ] DB POSTCHECK 전항목 PASS
[ ] work_schedules_old 존재 확인 (rollback anchor)
[ ] 운영자 승인 서명: ______
```

---

## 17. Code Deploy

### [MUTATION] PR merge

```text
PR #187: wo-work-schedules-partition-code-compat → main
cherry-pick·수동 복붙 금지
```

**merge 즉시 Railway 자동배포가 시작된다.**

### [READ ONLY] 배포 SHA 확인

```text
Railway 콘솔 또는 MCP 로 tai-api-prod 최신 deployment 확인
배포 SHA 가 예상과 다르면 STOP
```

---

## 18. MANUAL Smoke Gate [REV-A]

> **`post-deploy.yml` workflow_dispatch 는 사용할 수 없다.**
> GitHub Actions 가 작동하지 않으므로 아래를 operator 가 직접 수행한다.

### 18-1. Health (cold start 고려)

```bash
curl -sS -o /dev/null -w "%{http_code}\n" https://api.taieng.co.kr/health
```

```text
sleep when inactive = true
→ 첫 호출이 cold start 로 지연/실패할 수 있다
→ 1회 실패를 즉시 rollback 근거로 삼지 않는다
→ 30초 간격 3회 재시도 후 판정
```

### 18-2. smoke script 직접 실행

```bash
export API_URL=https://api.taieng.co.kr
export TEST_EMAIL=...
export TEST_PASSWORD=...
python scripts/smoke_test.py
```

secret 이 없으면 아래 업무 smoke 로 대체한다.

### 18-3. Smoke A — schedule read

```text
GET /work-schedules?factory_id=...&planned_date_from=...
GET /work-schedules/factory/{factory_id}
GET /work-schedules/{schedule_id}
```

확인: HTTP 200 / response schema 불변 / factory scope 정상

### 18-4. Smoke B — assignment (Patch#1)

```text
PATCH /work-schedules/{id}  (assigned_user_id 지정)
```

```sql
SELECT schedule_id, factory_id FROM work_assignments
ORDER BY created_at DESC LIMIT 1;  -- factory_id 가 parent 와 일치
```

### 18-5. Smoke C — inspection (Patch#2 / Patch#4)

```text
POST /worker-check/submit          (Patch#2)
POST /inspection/start/{ws_id}     (Patch#4)
```

```sql
SELECT assignment_id, factory_id FROM safety_inspections
ORDER BY inspection_date DESC LIMIT 2;
```

`safety_inspection_results` 생성 흐름도 확인한다.

### 18-6. Smoke D — schedule generation

```text
POST /schedule-engine/generate/{inspection_set_id}
```

중복 체크(set+date) 및 factory_id 복사 확인.

### 18-7. Smoke E — auto-assign (Patch#3)

```text
POST /work-schedules/auto-assign?factory_id=...
```

```text
[주의] 이 엔드포인트는 INSERT 실패를 삼킨다
       (ISSUE-WS-SILENT-INSERT-FAILURE-01).
       API 응답의 assigned 수치를 믿지 말고 DB 에서 직접 확인한다.
```

```sql
SELECT count(*) FILTER (WHERE factory_id IS NULL) AS null_factory, count(*) AS total
FROM work_assignments WHERE created_at > '<cutover 시각>';  -- null_factory = 0
```

---

## 19. Smoke 실패 분류

```text
DB MIGRATION DEFECT     UP artifact 문제
CODE PATCH DEFECT       patch 4건 문제
DEPLOYMENT DEFECT       배포/환경 문제
PRE-EXISTING DEFECT     기존 결함
COLD START              첫 호출 지연 (재시도로 해소)
UNKNOWN                 원인 미확정 → 조사 우선
```

**UNKNOWN 상태에서 연속 수정 금지.**

기존 결함으로 분류할 것:

```text
ISSUE-WS-SCHEMA-DRIFT-01   resolved_at·cycle_code·is_active 부재
ISSUE-PROD-STEP2-500-01    POST /legal-engine/diagnose/step2 가
                           cutover 이전부터 500 반환
                           → 동일 증상 시 파티션 회귀로 오판 금지
```

---

## 20. GATE-GO-NOGO (인간 승인)

```text
[ ] health PASS (cold start 재시도 포함)
[ ] Smoke A (read) PASS
[ ] Smoke B (assignment) PASS
[ ] Smoke C (inspection) PASS
[ ] Smoke D (generation) PASS
[ ] Smoke E (auto-assign, DB 직접 확인) PASS
[ ] pair violation = 0
[ ] 판정: GO / NO-GO
[ ] 운영자 서명: ______
```

---

## 21. GO 경로 [REV-A]

```text
[MUTATION] Railway writer 재개
[MUTATION] cron-job.org job 재개
[MUTATION] pg_cron job 3 (qa_send) 재활성화
[MUTATION] pg_cron job 4 (qa_collect) 재활성화
[MUTATION] maintenance OFF
→ observation window 진입
```

```sql
SELECT cron.alter_job(3, active := true);
SELECT cron.alter_job(4, active := true);
SELECT jobid, jobname, active FROM cron.job ORDER BY jobid;  -- 확인
ANALYZE public.work_schedules;
```

### ⚠ pg_cron job 1 은 재활성화하지 않는다

```text
job 1  daily_assignments
BEFORE  = disabled
CUTOVER = disabled
AFTER   = disabled
```

재활성화 전 필수 수정 3건:

```text
1. work_schedules.asset_id 컬럼 부재 → 참조 제거 또는 컬럼 추가
2. 중복 방지 로직 부재 → active_yn=true 전건을 매일 INSERT
3. factory_id 미포함 → 파티션 후 23514
```

`ISSUE-CRON-GEN-DAILY-ASSIGN-01` 로 별건 유지한다.
**이 job 은 work_assignments 5,991행 증식의 유력 원인이다.**

```text
work_schedules_old 은 DROP 하지 않는다. (rollback anchor 유지)
```

---

## 22. Rollback Trigger

```text
UP transaction 실패            (자동 롤백, 원본 무변경)
DB POSTCHECK 실패
배포 SHA 불일치
assignment write 실패 (23514/23503)
inspection write 실패
factory scope 오류 (타사 데이터 노출)
data mismatch
FK 위반 급증
unexpected 500 지속
```

제외:

```text
cold start 1회 실패        → 재시도 후 판정
ISSUE-WS-SCHEMA-DRIFT-01   → 기존 결함
ISSUE-PROD-STEP2-500-01    → 기존 결함
```

---

## 23. Rollback 절차

### 전제

```text
work_schedules_old 가 존재해야 한다.
없으면 DOWN artifact 가 §0 에서 즉시 ABORT 한다.
```

### 순서

```text
[1] maintenance 유지 (해제 금지)
[2] Railway writer 정지 유지
[3] DOWN checksum 확인
      57768a50dd9e7643bb1708ec198e48bfc62d0474852faf433b15ae7f2e9df20d
[4] GATE-ROLLBACK 승인
[5] DOWN artifact 실행
[6] PRE-state restoration 검증
[7] application code 를 pre-cutover revision 으로 복구
      → main revert 또는 Railway 이전 deployment redeploy
      → 목표 SHA: 0972a18e9f158ce49c5d7163ab31860ebcb4f7db
[8] read/write smoke
[9] pg_cron job 3·4 원상복구
[10] maintenance OFF
```

### GATE-ROLLBACK

```text
[ ] work_schedules_old 존재 확인
[ ] DOWN checksum 일치
[ ] 실패 원인 분류 완료 (UNKNOWN 아님)
[ ] 운영자 승인 서명: ______
```

### 실패 지점별 상태

```text
UP copy/검증/swap 실패   트랜잭션 롤백 / 원본 무변경 / 재시도 안전
UP 성공 + 기능검증 실패   DOWN 실행 / 데이터 손실 없음
DOWN reconcile 실패      트랜잭션 롤백 / 파티션 유지 / 재시도 안전
old DROP 후 DOWN 시도    즉시 ABORT (부분 실행 없음)
```

---

## 24. Observation Window

관찰 항목:

```text
500 error rate / assignment·inspection·generation error
FK / CHECK violation / DB CPU / lock 대기 / query latency
partition routing 분포
```

성능 중점 (local EXPLAIN 기준):

```text
factory + planned_date    → 1개 partition (pruning 작동)
factory + status + date   → 1개 partition (pruning 작동)
id direct lookup          → 16개 partition 접근
duplicate check(set+date) → pruning 없음
```

```text
id direct lookup latency
schedule duplicate check latency
→ 이 둘을 반드시 관찰한다
```

---

## 25. Cleanup (별도 승인)

```text
DROP TABLE public.work_schedules_old
DROP TABLE public._mig_ws_data_snapshot
DROP TABLE public._mig_ws_comments
DROP TABLE public._mig_ws_grants
DROP TABLE public._mig_ws_policies
DROP TABLE public._mig_ws_fingerprint
DROP TABLE public._mig_ws_factory_counts
```

```text
⚠ work_schedules_old 를 DROP 하면 FAST-PATH DOWN 이 불가능해진다.
observation window 종료 + 운영자 승인 후에만 수행한다.
별도 WP-PARTITION-04 로 분리한다.
```

**PITR 비활성화도 이 단계에서 수행한다** (Spend Cap 미적용이므로 잊지 말 것).

---

## 26. Residual Risk

### R1 SUPABASE E2E = UNVERIFIED

Supabase branch 검증이 `MIGRATIONS_FAILED` 로 실패해(production schema ↔ repository migration baseline 불일치) 실제 Supabase 환경 E2E 를 수행하지 못했다. 검증은 local PostgreSQL 17.6 에서만 이뤄졌다.

### R2 PERFORMANCE = UNBENCHMARKED

66행 / 720행 규모에서만 plan shape 를 확인했다.

### R3 RISK-WS-EC-PARTIAL-NULL-01

```text
equipment_checkins 복합 FK 는 MATCH SIMPLE 이며 pair CHECK 가 없다.
현재 writer 가 factory_id 를 보장하나,
DB 단독으로는 모든 partial-null pair 를 거부하지 못한다.
```

### R4 ISSUE-WS-SILENT-INSERT-FAILURE-01

`auto_assign_schedules()` 가 INSERT 실패를 catch 후 continue 한다. → Smoke E 에서 DB 직접 확인 필수.

### R5 backfill lock time

```text
production work_assignments = 5,991건 (local dry-run 371건)
→ ACCESS EXCLUSIVE LOCK 유지 시간이 더 길다
```

### R6 Railway cold start

```text
sleep when inactive = true → 첫 요청 지연, 1회 실패로 rollback 판단 금지
```

### R7 CI 부재 [REV-A]

```text
GitHub Actions 4개월 미실행. TEST GATE 를 local pytest 로 대체.
CI 가 잡아줄 회귀를 놓칠 가능성이 남는다.
```

### R8 멀티 세션 [REV-A]

```text
운영자가 여러 Claude 창을 병렬 운용한다.
GATE-SESSION 으로 관리하나, 사람의 준수에 의존한다.
```

### R9 writer discovery 반복 누락 [REV-A]

```text
이번 작업에서 writer 누락이 4회 발견됐다.
3-layer audit 으로 닫았으나, 이 시스템에 미지의 실행 경로가
더 있을 가능성을 완전히 배제할 수 없다.
→ observation window 에서 예상 외 write 를 관찰한다.
```

---

## 27. 현재 판정

```text
WP-PARTITION-03

RUNBOOK DESIGN            = READY (REV-A)
CODE DRIFT                = PASS / NO DRIFT
WRITER INVENTORY 3-LAYER  = CLOSED / UNCOVERED = 0
TEST GATE (local pytest)  = PASS
CI DB-READ COMPATIBILITY  = PASS
UNKNOWN ERROR SOURCE      = IDENTIFIED (운영자 세션, READ ONLY)
GATE-CRON                 = CONDITIONAL PASS

CI                        = UNAVAILABLE
AUTO SMOKE                = UNAVAILABLE / MANUAL REQUIRED

GATE-SESSION              = NOT YET
GATE-PITR                 = FAIL (add-on 미구독)

SUPABASE E2E              = UNVERIFIED
PERFORMANCE               = UNBENCHMARKED

CUTOVER READINESS         = CONDITIONAL
PRODUCTION APPLY          = NOT APPROVED
```

---

## 28. 이 문서가 승인하지 않는 것

```text
production DB mutation
Supabase DDL 실행
main merge
code deploy
migration 실행
old table cleanup
pg_cron job 1 재활성화
```

실행 승인은 GATE 별 운영자 서명으로만 이뤄진다.
