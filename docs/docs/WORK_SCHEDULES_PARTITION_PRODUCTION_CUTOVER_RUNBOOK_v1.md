# WORK_SCHEDULES_PARTITION_PRODUCTION_CUTOVER_RUNBOOK_v1

> 작성일: 2026-08-23
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
DB 크기        4,773 MB
```

### 현재 production 배포 SHA

```text
0972a18e9f158ce49c5d7163ab31860ebcb4f7db
```

**patch base 와 동일하다. CODE DRIFT = 0.**

---

## 3. 가장 중요한 사실 3가지

이것을 모르면 순서를 틀린다.

### 3-1. main merge = 자동배포

Railway 가 `taiengineering/tai-api` 를 직접 바라본다. **main 에 머지하는 순간 배포가 시작된다.**
code deploy 를 별도 수동 단계로 취급하면 안 된다.

```text
DB UP 이전에 main merge 금지
```

### 3-2. 코드는 구 schema 와 호환되지 않는다

patch 는 child INSERT payload 에 `factory_id` 를 추가한다.
파티션 적용 전 DB 에 배포하면 컬럼이 없어 INSERT 가 실패한다.

```text
코드 선배포 불가능
```

### 3-3. PR 생성만으로 CI 가 돈다

`.github/workflows/ci.yml` 이 `pull_request → main` 에서 실행된다.
따라서 **PR 은 DB UP 전에 열어도 안전하다.** merge 만 하지 않으면 된다.

CI 가 읽는 테이블은 `master_building_legal_rules` 뿐이며, 파티션 대상 4개 테이블과 무관하다.

```text
CI DB-READ COMPATIBILITY = COMPATIBLE
cutover 전/후 실행 순서 제약 없음
```

---

## 4. Writer Inventory (전수, 확정)

파티션 FK 영향을 받는 child INSERT writer 는 5개이며 전부 커버됐다.

| writer | runtime | freeze method | verification |
|---|---|---|---|
| `work_schedules.py` `_apply_one_update()` | FastAPI | Railway 서비스 정지/트래픽 차단 | `pg_stat_activity` |
| `worker_check.py` `submit_check()` | FastAPI | 동일 | 동일 |
| `legal_engine_patch.py` `auto_assign_schedules()` | FastAPI | 동일 | 동일 |
| `inspection_checklist.py` `start_inspection()` | FastAPI | 동일 | 동일 |
| `equipment_checkins.py` | FastAPI | 동일 | 동일 |
| work_schedules INSERT ×14 (부모) | FastAPI | 동일 | 동일 |
| `overdue_checker.py` `/overdue/check` | **cron-job.org (외부)** | **OPERATOR ACTION REQUIRED** | 콘솔 next run 확인 |

```text
UNCOVERED INSERT WRITERS = 0
Edge Function            = 없음
RPC                      = 15건, 전부 무관(통계·검색·리인덱스)
```

**FastAPI writer 6종은 Railway 서비스 하나를 멈추면 전부 정지한다.**
외부 트리거는 cron-job.org 하나뿐이다.

---

## 5. 실행 순서 (고정)

```text
[1] PR 생성
[2] GitHub CI PASS 확인          ← main merge 금지
[3] GATE-PITR
[4] GATE-CRON
[5] maintenance 시작
[6] cron pause
[7] Railway writer stop / traffic block
[8] active writer = 0 확인
[9] production PRECHECK
[10] canonical UP checksum 확인
[11] GATE-DB-UP  ← 승인
[12] DB UP 실행
[13] DB POSTCHECK
[14] GATE-DEPLOY ← 승인
[15] PR merge to main
[16] Railway 자동배포
[17] deployment SHA 확인
[18] /health (cold start 고려)
[19] post-deploy smoke
[20] assignment / inspection / schedule smoke
[21] GATE-GO-NOGO ← 승인

PASS → writer 재개 → cron 재개 → maintenance OFF → observation
FAIL → maintenance 유지 → rollback 진입
```

---

## 6. GATE-PITR (인간 승인)

DB UP 이전에 반드시 통과해야 한다.

```text
확인 위치
Supabase Dashboard
> Project vwlahtguyggrhvslabax
> Project Settings > Database > Backups
```

체크리스트:

```text
[ ] PITR 활성 여부 확인
[ ] 보존기간(retention) 확인 및 기록: ______일
[ ] restore 절차 확인 (문서/UI 경로 숙지)
[ ] operator 가 실제 restore 를 수행할 권한 보유 확인
[ ] cutover 직전 시각 기록 (복구 목표 시점): ______
```

```text
하나라도 미확인/NO → PRODUCTION DB UP = BLOCKED
```

### 참고 실측 [READ ONLY 결과]

```text
wal_level       = logical
archive_mode    = on
archive_command = /usr/bin/admin-mgr wal-push (wal-g)
```

WAL 아카이빙 기반은 갖춰져 있으나, **플랜별 PITR 활성 여부·보존기간·복원 권한은 SQL 로 확인 불가**하다.
migration DOWN 을 backup 대체물로 취급하지 않는다.

---

## 7. GATE-CRON (인간 승인)

```text
확인 위치
cron-job.org 콘솔
```

체크리스트:

```text
[ ] cron-job.org 로그인
[ ] POST /overdue/check job 식별
[ ] job pause 실행
[ ] next run 없음 확인
[ ] 다른 job 이 4개 대상 테이블을 건드리지 않는지 확인
```

```text
미확인 → PRODUCTION DB UP = BLOCKED
```

### 배경

`/overdue/check` 는 인증 없는 머신 엔드포인트이며 매일 09:00 KST 실행된다(코드 주석 기준).
인증이 없으므로 애플리케이션 레벨에서 차단할 수 없다. **콘솔 pause 가 유일한 확실한 수단이다.**

동작은 `work_assignments` UPDATE 뿐이라 파티션 FK 위반을 일으키지는 않지만, cutover 중 동시 write 는 차단해야 한다.

> maintenance window 를 09:00 KST 를 피해 잡으면 위험이 줄지만, pause 를 생략하는 근거가 되지는 않는다.

---

## 8. Maintenance 시작 · Writer Freeze

### [MUTATION] Railway writer 정지

```text
방법 선택 (운영자 판단)
  A. Railway 콘솔에서 tai-api-prod 서비스 일시정지
  B. 도메인/트래픽 차단
```

### [READ ONLY] active writer 확인

```sql
SELECT count(*) AS active_ws_sessions
FROM pg_stat_activity
WHERE state = 'active'
  AND query ILIKE '%work_schedules%';

SELECT count(*) AS total_active
FROM pg_stat_activity
WHERE state = 'active' AND pid <> pg_backend_pid();
```

```text
active_ws_sessions = 0 이 될 때까지 대기
0 이 아니면 DB UP 진입 금지
```

---

## 9. Production PRECHECK

### [READ ONLY]

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

기대값 (2026-08-22 실측 기준):

```text
ws_columns  = 37
ws_indexes  = 12
checks      = 0
triggers    = 0
owner       = postgres
rls_enabled = true
rls_forced  = false
policies    = 6
comments    = 26
grants      = 28
relkind     = r
```

```text
하나라도 다르면 artifact 전제가 깨진 것 → CUTOVER BLOCKED → 02A 재검토
```

---

## 10. UP artifact checksum 확인

### [READ ONLY]

```bash
# 저장소를 canonical commit 으로 체크아웃한 상태에서
shasum -a 256 docs/sql/20260822_work_schedules_partition_up.sql
```

기대값:

```text
147f75f2864fd3bb261fb6ebedae7b34b5621b311d556e5d0d8e6b028300cca7
```

```text
불일치 → 실행 금지
복사본·수정본 실행 금지. canonical 파일 그대로 사용한다.
```

---

## 11. GATE-DB-UP (인간 승인)

```text
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

전부 체크된 뒤에만 다음으로 진행한다.

---

## 12. DB UP 실행

### [MUTATION]

```text
canonical UP artifact 를 그대로 실행
docs/sql/20260822_work_schedules_partition_up.sql
```

내부 동작 요약:

```text
ACCESS EXCLUSIVE LOCK (4개 테이블)
→ HARD PRECHECK (실패 시 자동 중단)
→ PRE-state 스냅샷 저장
→ shadow partitioned table 생성 (HASH 16)
→ 37컬럼 명시 COPY
→ full-row equality 검증
→ index 8개 / outbound FK / comments 26 복제
→ child factory_id 컬럼 추가 + backfill
→ pair CHECK 추가
→ cutover swap
→ child 복합 FK (MATCH FULL / ON DELETE SET NULL)
→ RLS·policy·owner·grants 복원
→ POSTCHECK (EXACT contract equality)
→ COMMIT
```

전체가 단일 트랜잭션이므로 **중간 실패 시 자동 롤백되고 원본은 무변경**이다.

### 예상 소요 [한계]

```text
local dry-run  : work_assignments 371건 backfill
production     : work_assignments 5,991건 backfill

→ lock 유지 시간이 dry-run 보다 길다.
→ 정확한 시간은 UNBENCHMARKED. 관찰 대상.
```

---

## 13. DB POSTCHECK

UP artifact 내부 POSTCHECK 가 자동 수행하지만, 커밋 후 독립 확인한다.

### [READ ONLY]

```sql
SELECT relkind, CASE WHEN relkind='p' THEN 'OK' ELSE 'FAIL' END AS partitioned
FROM pg_class WHERE oid='public.work_schedules'::regclass;

SELECT count(*) AS partitions FROM pg_inherits
WHERE inhparent='public.work_schedules'::regclass;   -- 16 기대

SELECT array_length(conkey,1) AS pk_cols FROM pg_constraint
WHERE conrelid='public.work_schedules'::regclass AND contype='p';  -- 2 기대

SELECT count(*) AS ws_rows FROM public.work_schedules;

SELECT count(*) AS wa_pair_violation FROM public.work_assignments
WHERE (schedule_id IS NULL) <> (factory_id IS NULL);   -- 0 기대

SELECT count(*) AS si_pair_violation FROM public.safety_inspections
WHERE (assignment_id IS NULL) <> (factory_id IS NULL); -- 0 기대

SELECT conname, confmatchtype FROM pg_constraint
WHERE conname IN ('work_assignments_schedule_fkey','safety_inspections_schedule_fkey');
-- confmatchtype = 'f' (MATCH FULL) 기대

SELECT CASE WHEN to_regclass('public.work_schedules_old') IS NOT NULL
            THEN 'OK(rollback anchor 존재)' ELSE 'FAIL' END AS old_table;
```

```text
하나라도 기대와 다르면 → rollback 판단 진입
```

---

## 14. GATE-DEPLOY (인간 승인)

```text
[ ] DB POSTCHECK 전항목 PASS
[ ] work_schedules_old 존재 확인 (rollback anchor)
[ ] GitHub CI PASS 확인 (PR)
[ ] 운영자 승인 서명: ______
```

---

## 15. Code Deploy

### [MUTATION] PR merge

```text
PR: wo-work-schedules-partition-code-compat → main
merge 방식은 저장소 관행에 따른다.
cherry-pick·수동 복붙 금지.
```

**merge 즉시 Railway 자동배포가 시작된다.**

### [READ ONLY] 배포 SHA 확인

```text
Railway 콘솔 또는 MCP 로 tai-api-prod 최신 deployment 확인
기대 SHA = merge 결과 commit (23d16ac 계열)
```

```text
배포 SHA 가 예상과 다르면 STOP
```

---

## 16. Smoke Gate

### 16-1. Health (cold start 고려)

```bash
curl -sS -o /dev/null -w "%{http_code}\n" https://api.taieng.co.kr/health
```

```text
sleep when inactive = true
→ 첫 호출이 cold start 로 지연/실패할 수 있다.
→ 1회 실패를 즉시 rollback 근거로 삼지 않는다.
→ 30초 간격으로 3회까지 재시도 후 판정한다.
```

### 16-2. post-deploy smoke (기존 workflow 재사용)

```text
GitHub Actions > Post-Deploy Smoke Test > Run workflow (workflow_dispatch)
```

### 16-3. Smoke A — schedule read

```text
GET /work-schedules?factory_id=...&planned_date_from=...
GET /work-schedules/factory/{factory_id}
GET /work-schedules/{schedule_id}
```

확인:

```text
HTTP 200
response schema 불변
factory scope 정상
단건 조회 정상 (partition pruning 없음 — 정상 동작)
```

### 16-4. Smoke B — assignment (Patch#1)

안전한 test object 로 신규 배정 1건 생성.

```text
PATCH /work-schedules/{id}  (assigned_user_id 지정)
```

확인:

```sql
SELECT schedule_id, factory_id FROM work_assignments
ORDER BY created_at DESC LIMIT 1;
-- factory_id 가 parent 와 일치해야 한다
```

### 16-5. Smoke C — inspection (Patch#2 / Patch#4)

```text
POST /worker-check/submit          (Patch#2 경로)
POST /inspection/start/{ws_id}     (Patch#4 경로)
```

확인:

```sql
SELECT assignment_id, factory_id FROM safety_inspections
ORDER BY inspection_date DESC LIMIT 2;
-- pair 정상, factory_id 저장 확인
```

```text
safety_inspection_results 생성 흐름이 깨지지 않았는지도 확인
```

### 16-6. Smoke D — schedule generation

```text
POST /schedule-engine/generate/{inspection_set_id}
```

확인:

```text
중복 체크 정상 (inspection_set_id + planned_date)
INSERT 시 factory_id 가 세트에서 복사되는지
```

### 16-7. Smoke E — auto-assign (Patch#3)

```text
POST /work-schedules/auto-assign?factory_id=...
```

```text
[주의] 이 엔드포인트는 INSERT 실패를 삼킨다
       (ISSUE-WS-SILENT-INSERT-FAILURE-01).
       API 응답의 assigned 수치를 믿지 말고
       반드시 DB 에서 직접 확인한다.
```

```sql
SELECT count(*) FILTER (WHERE factory_id IS NULL) AS null_factory,
       count(*) AS total
FROM work_assignments WHERE created_at > '<cutover 시각>';
-- null_factory = 0 이어야 한다
```

---

## 17. Smoke 실패 분류

실패 시 즉시 다음 중 하나로 분류한다. **UNKNOWN 상태에서 연속 수정 금지.**

```text
DB MIGRATION DEFECT     UP artifact 문제
CODE PATCH DEFECT       patch 4건 문제
DEPLOYMENT DEFECT       배포/환경 문제
PRE-EXISTING DEFECT     ISSUE-WS-SCHEMA-DRIFT-01 등 기존 결함
COLD START              첫 호출 지연 (재시도로 해소)
UNKNOWN                 원인 미확정 → 조사 우선
```

특히 `resolved_at` · `cycle_code` · `is_active` 관련 오류는
**파티션 회귀가 아니라 기존 결함**(ISSUE-WS-SCHEMA-DRIFT-01)이다. 혼동하지 않는다.

---

## 18. GATE-GO-NOGO (인간 승인)

```text
[ ] health PASS
[ ] post-deploy smoke PASS
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

## 19. GO 경로

```text
[MUTATION] Railway writer 재개
[MUTATION] cron-job.org job 재개
[MUTATION] maintenance OFF
→ observation window 진입
```

```sql
-- 통계 갱신
ANALYZE public.work_schedules;
```

```text
work_schedules_old 은 DROP 하지 않는다. (rollback anchor 유지)
```

---

## 20. Rollback Trigger

다음은 즉시 rollback 후보다.

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
ISSUE-WS-SCHEMA-DRIFT-01 기존 결함 → 별도 판정
```

---

## 21. Rollback 절차

### 전제

```text
work_schedules_old 가 존재해야 한다.
없으면 이 DOWN 은 사용할 수 없다 (artifact 가 §0 에서 즉시 ABORT).
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
[9] maintenance OFF
```

### GATE-ROLLBACK

```text
[ ] work_schedules_old 존재 확인
[ ] DOWN checksum 일치
[ ] 실패 원인 분류 완료 (UNKNOWN 아님)
[ ] 운영자 승인 서명: ______
```

### DOWN 내부 동작

```text
FAST-PATH ONLY (old 없으면 즉시 ABORT)
→ ACCESS EXCLUSIVE LOCK
→ child 복합 FK / pair CHECK 제거
→ FULL RECONCILIATION
     신규 INSERT 회수 / 37컬럼 UPDATE / 삭제분 DELETE
→ 37컬럼 full-row equality 검증
→ swap (파티션 DROP → old RENAME)
→ child additive 컬럼 제거
→ 원본 FK 복원 (ec = ON DELETE SET NULL)
→ owner·RLS·contract EXACT 검증
→ COMMIT
```

### 실패 지점별 상태

```text
UP copy 실패           트랜잭션 롤백 / 원본 무변경 / 재시도 안전
UP 검증 실패           트랜잭션 롤백 / 원본 무변경
UP swap 실패           트랜잭션 롤백 / 원본 무변경
UP 성공 + 기능검증 실패  DOWN 실행 / 데이터 손실 없음
DOWN reconcile 실패     트랜잭션 롤백 / 파티션 유지 / 재시도 안전
old DROP 후 DOWN 시도   즉시 ABORT (부분 실행 없음)
```

---

## 22. Observation Window

cutover 후 즉시 cleanup 하지 않는다.

관찰 항목:

```text
500 error rate
assignment creation error
inspection submission error
schedule generation error
FK / CHECK violation
DB CPU
DB lock 대기
query latency
partition routing 분포
```

성능 중점 관찰 (local EXPLAIN 기준 예상):

```text
factory + planned_date      → 1개 partition (pruning 작동)
factory + status + date     → 1개 partition (pruning 작동)
id direct lookup            → 16개 partition 접근 (pruning 없음)
duplicate check(set+date)   → pruning 없음
```

```text
id direct lookup latency
schedule duplicate check latency
→ 이 둘을 반드시 관찰한다
```

관찰 기간은 운영 상황에 맞춰 운영자가 결정한다.

---

## 23. Cleanup (별도 승인)

다음은 cutover 성공과 별개다.

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

---

## 24. Residual Risk

이번 cutover 를 승인하더라도 다음은 해소되지 않는다.

### R1 SUPABASE E2E = UNVERIFIED

Supabase branch 검증이 `MIGRATIONS_FAILED` 로 실패해(production schema ↔ repository migration baseline 불일치) 실제 Supabase 환경 E2E 를 수행하지 못했다.
검증은 local PostgreSQL 17.6 에서만 이뤄졌다.

```text
수용 방식: maintenance window + strict rollback-ready
```

### R2 PERFORMANCE = UNBENCHMARKED

66행 / 720행 규모에서만 plan shape 를 확인했다. 대규모 latency 는 미측정.

### R3 RISK-WS-EC-PARTIAL-NULL-01

```text
equipment_checkins 복합 FK 는 MATCH SIMPLE 이며 pair CHECK 가 없다.
현재 writer 가 factory_id 를 보장하나,
DB 단독으로는 모든 partial-null pair 를 거부하지 못한다.
```

### R4 ISSUE-WS-SILENT-INSERT-FAILURE-01

```text
auto_assign_schedules() 가 INSERT 실패를 catch 후 continue 한다.
assigned_total 과 실제 성공 건수가 불일치할 수 있고
API 가 success 를 오보고할 수 있다.
→ Smoke E 에서 반드시 DB 직접 확인
```

### R5 backfill lock time

```text
production work_assignments = 5,991건
local dry-run                = 371건
→ ACCESS EXCLUSIVE LOCK 유지 시간이 더 길다. 측정 필요.
```

### R6 Railway cold start

```text
sleep when inactive = true
→ maintenance 해제 후 첫 요청 지연
→ 1회 실패로 rollback 판단 금지
```

### R7 ISSUE-WS-SCHEMA-DRIFT-01 (기존 결함)

```text
resolved_at / cycle_code / is_active — work_schedules 에 없는 컬럼
파티션과 무관. smoke 실패 시 원인 분리 필요.
```

### R8 ISSUE-REPO-MERGE-CONFLICT-01 (개발환경)

```text
로컬 main 이 origin 과 diverged, building_register.py 머지 중단 상태.
production 배포 SHA 와 무관함이 확인됐으므로 cutover blocker 아님.
단, merge 작업 시 깨끗한 작업 디렉터리에서 수행할 것.
```

---

## 25. 현재 판정

```text
WP-PARTITION-03

RUNBOOK DESIGN           = READY
CODE DRIFT               = PASS / NO DRIFT
WRITER COVERAGE          = PASS / UNCOVERED = 0
WRITER FREEZE DESIGN     = PASS / OPERATOR ACTION REQUIRED
CI PATH                  = AVAILABLE
CI DB-READ COMPATIBILITY = PASS / COMPATIBLE
POST-DEPLOY SMOKE        = AVAILABLE

PITR                     = HUMAN GATE (UNVERIFIED)
CRON FREEZE              = HUMAN GATE (UNVERIFIED)

SUPABASE E2E             = UNVERIFIED
PERFORMANCE              = UNBENCHMARKED

CUTOVER READINESS        = CONDITIONAL
PRODUCTION APPLY         = NOT APPROVED
```

---

## 26. 이 문서가 승인하지 않는 것

```text
production DB mutation
Supabase DDL 실행
main merge
code deploy
migration 실행
old table cleanup
```

실행 승인은 GATE 별 운영자 서명으로만 이뤄진다.
