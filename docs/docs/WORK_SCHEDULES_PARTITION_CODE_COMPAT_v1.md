# WORK_SCHEDULES_PARTITION_CODE_COMPAT_v1

> 작성일: 2026-08-23 (REV-1 갱신)
> 상위: WORK_SCHEDULES_PARTITION_DESIGN_FINAL_v1.md
> 상태: **CODE PATCH 작성 완료 / 배포 미승인**
> 브랜치: `wo-work-schedules-partition-code-compat`
> base: `0972a18e9f158ce49c5d7163ab31860ebcb4f7db`
> **canonical code HEAD: `23d16ac21c87dcbdf5ff2a1b590fd8d797121349`**

```text
PRODUCTION DB MUTATION = 0
MIGRATION APPLY        = 0
DEPLOY                 = 0
MERGE TO MAIN          = 0
```

---

## 1. 문서 목적

`work_schedules` 파티션 전환과 함께 반드시 배포되어야 하는 코드 변경과, 그 변경이 새 schema 계약을 통과함을 증명하는 검증 기록을 고정한다.

이 브랜치는 **배포 산출물이 아니라 준비된 변경**이다.

---

## 2. 변경이 필요한 이유

파티션 전환 후 schema 계약이 바뀐다.

```text
work_schedules
PRIMARY KEY (id, factory_id)

work_assignments
FOREIGN KEY (schedule_id, factory_id)
  REFERENCES work_schedules (id, factory_id) MATCH FULL
CHECK ((schedule_id IS NULL) = (factory_id IS NULL))

safety_inspections
FOREIGN KEY (assignment_id, factory_id)
  REFERENCES work_schedules (id, factory_id) MATCH FULL
CHECK ((assignment_id IS NULL) = (factory_id IS NULL))
```

따라서 child INSERT 시 `factory_id` 를 함께 저장하지 않으면 write 가 실패한다.

중요한 점은 이 실패가 **명시적**이라는 것이다. CHECK 제약이 없었다면 MATCH SIMPLE 의 NULL 생략 규칙으로 인해 FK 검사가 건너뛰어지고 무결성이 조용히 깨졌을 것이다.

---

## 3. REV-1 사유 (2026-08-23)

최초 02C 는 patch 2건(#1·#2)만 적용하고 PASS 로 닫혔다.

이후 `WP-PARTITION-03` 조사 단계에서 **writer inventory 를 전수 수행**한 결과, composite-FK 영향을 받는 child INSERT writer 가 2개 더 발견됐다.

```text
누락 1  legal_engine_patch.py  auto_assign_schedules()
누락 2  inspection_checklist.py start_inspection()
```

즉 최초 02C 의 근거였던 "writer 는 2개" 라는 전제가 틀렸다. 검색 방식(파일 단위 조회)이 아니라 **저장소 전체 grep 전수**로 바꾼 뒤에야 범위가 닫혔다.

REV-1 은 신규 기능이 아니라 **기존 writer 의 호환성 누락 보완**이다.

---

## 4. Patch #1 — work_assignments

```text
FILE : routers/work_schedules.py
FUNC : _apply_one_update()
VER  : v1.2.7 → v1.2.8
```

### 동작

```text
활성 assignment 있음
→ UPDATE (기존 그대로, 추가 조회 없음)

활성 assignment 없음
→ work_schedules 에서 factory_id 조회
→ 없으면 409
→ 있으면 factory_id 포함 INSERT

배정 해제
→ CANCELLED UPDATE (기존 그대로)
```

### 변경하지 않은 것

```text
함수 시그니처
호출자 3곳 (batch_update / bulk_assign / patch_work_schedule)
request · response 스키마
스코프 로직
UPDATE · CANCELLED 경로
```

---

## 5. Patch #2 — safety_inspections (worker_check)

```text
FILE : routers/worker_check.py
FUNC : submit_check()
VER  : v1.4.1 → v1.5.0
```

### 적용 방식

```text
기존 work_assignments 조회의 select 컬럼만 확장
  schedule_id → schedule_id, factory_id
```

즉 SELECT 를 새로 만들지 않았다.

### 보완 조회가 발생하는 경우

```text
body.schedule_id 를 앱이 직접 보낸 경로
work_assignments.factory_id 가 비어 있는 경우
```

### 구버전 앱 호환

```text
assignment 없는 제출
→ assignment_id NULL + factory_id NULL
→ pair CHECK 통과 (정상)
```

---

## 6. Patch #3 — work_assignments (legal engine)

```text
FILE   : routers/legal_engine_patch.py
FUNC   : auto_assign_schedules()
VER    : v1.3.0 → v1.4.0
COMMIT : 75537ba42f800bf8929f48689e6e1ee029b89748
```

### 변경

```python
assign_rows.append({
    "schedule_id": s["id"],
    "factory_id":  s["factory_id"],   # ← 추가
    ...
})
```

상위 SELECT 가 이미 `"id, factory_id, company_id, ..."` 를 조회하므로 **추가 DB 왕복이 없다.**

### 변경하지 않은 것

```text
manager 조회 로직
배치 INSERT 구조
work_schedules UPDATE 경로
response 계약
```

---

## 7. Patch #4 — safety_inspections (inspection_checklist)

```text
FILE   : routers/inspection_checklist.py
FUNC   : start_inspection()
VER    : v1.5.0 → v1.6.0
COMMIT : 23d16ac21c87dcbdf5ff2a1b590fd8d797121349
METHOD : B (기존 UPDATE 응답 재사용)
```

### 동작

```text
work_schedules UPDATE 성공
→ ws_res.data[0] 확보
→ factory_id = ws_res.data[0]["factory_id"]
→ 없으면 409
→ safety_inspections INSERT (assignment_id + factory_id)
```

**추가 SELECT 를 만들지 않았다.** UPDATE 응답에 이미 갱신된 행 전체가 오므로 그것을 재사용한다.
같은 파일의 `complete_inspection()` 이 이미 `ws.get("factory_id")` 로 동일 패턴을 쓰고 있어 코드 스타일도 일관된다.

---

## 8. 공통 설계 원칙

```text
factory 를 모르는 상태로 child 를 저장하지 않는다
→ 409 로 명시적 실패
→ 조용한 무결성 우회 금지
```

---

## 9. 검증 결과 — 최초 02C (Local PostgreSQL 17.6)

| 케이스 | 내용 | 결과 |
|---|---|---|
| C-1 | 신규 assignment INSERT | PASS (factory_id 저장) |
| C-2 | assignment factory mismatch | PASS (23503 FK 거부) |
| C-3 | **패치 이전 payload** | **PASS (23514 CHECK 거부)** |
| C-4 | inspection INSERT | PASS (factory_id 저장) |
| C-5 | inspection factory mismatch | PASS (23503 FK 거부) |
| C-6 | 기존 assignment UPDATE | SKIP (검증 스크립트 스키마 한계) |
| C-7 | assignment 없는 inspection | PASS (pair NULL 통과) |

### backfill 실측

```text
work_assignments   factory_id 백필  371건
safety_inspections factory_id 백필  216건
BACKFILL OK
```

---

## 10. 검증 결과 — REV-1 (Local PostgreSQL 17.6)

Patch #3 · #4 를 대상으로 파티션 적용 DB 에서 재검증했다.

| 케이스 | 내용 | 결과 |
|---|---|---|
| R1-1 | auto_assign payload (schedule + factory) | PASS |
| R1-2 | auto_assign wrong factory | PASS (23503 FK 거부) |
| R1-3 | start_inspection 정상 (UPDATE 응답 재사용) | PASS |
| R1-4 | **companion 누락 (factory_id NULL)** | **PASS (23514 CHECK 거부)** |

### pair 계약 위반

```text
work_assignments   위반 0
safety_inspections 위반 0
```

### R1-4 의 의미

`assignment_id` 는 있는데 `factory_id` 가 NULL 인 payload 가 **23514 로 거부**됐다.

Patch #4 가 없었다면 `start_inspection()` 이 정확히 이 payload 를 보냈을 것이고, 파티션 적용 후 **점검 시작 기능이 전량 실패**했을 것이다.

따라서 REV-1 은 단순 코드 보완이 아니라 **production cutover 필수 호환성 보완**이다.

---

## 11. Writer Coverage Matrix (최종)

저장소 전체 grep 전수 기준. 대상 4개 테이블의 모든 INSERT 경로.

| writer | target | op | factory_id | patch | covered |
|---|---|---|---|---|---|
| `work_schedules.py` `_apply_one_update()` | work_assignments | INSERT | parent 조회 | O | ✔ Patch#1 |
| `worker_check.py` `submit_check()` | safety_inspections | INSERT | 기존 조회 확장 | O | ✔ Patch#2 |
| `legal_engine_patch.py` `auto_assign_schedules()` | work_assignments | INSERT | `s["factory_id"]` | O | ✔ Patch#3 |
| `inspection_checklist.py` `start_inspection()` | safety_inspections | INSERT | `ws_res.data[0]` | O | ✔ Patch#4 |
| `equipment_checkins.py` | equipment_checkins | INSERT | payload 기존 포함 | X | ✔ 원래 안전 |
| work_schedules INSERT ×14 | work_schedules(부모) | INSERT | 전부 포함 | X | — |
| `overdue_checker.py` ×2 (cron) | work_assignments | UPDATE only | — | X | — |
| `.rpc()` ×15 | 무관(통계·검색·리인덱스) | — | — | X | — |
| Edge Function | **없음** | — | — | — | — |

```text
CHILD INSERT WRITERS
TOTAL     = 5
COVERED   = 5
UNCOVERED = 0
```

---

## 12. API contract 정적 검증

```text
request 스키마   무변경
response 스키마  무변경
라우트 · 경로     무변경
스코프 로직      무변경
함수 시그니처    무변경
추가 실패 응답   409 (factory 미확인)
```

409 는 기존에 FK/CHECK 위반으로 500 이 났을 자리이므로 계약이 오히려 명확해진다.

---

## 13. 배포 제약 (가장 중요)

이 코드는 **구 schema 와 호환되지 않는다.**

```text
파티션 적용 전 DB 에 배포하면
→ work_assignments.factory_id 컬럼 없음
→ INSERT 실패
```

따라서 반드시 다음 순서를 따른다.

```text
1. maintenance ON
2. active writer = 0 확인
3. UP migration 실행
4. 이 브랜치 배포
5. smoke test
6. maintenance OFF
```

코드 선배포는 불가능하다.

---

## 14. 이번 변경에 포함하지 않은 것

### ISSUE-WS-SCHEMA-DRIFT-01

기존 코드가 존재하지 않는 컬럼을 UPDATE 한다.

```text
resolved_at   — work_schedules 에 없음
cycle_code    — work_schedules 에 없음
is_active     — work_schedules 에 없음 (실제는 active_yn)
```

파티셔닝과 무관한 기존 결함이므로 이번 패치에 섞지 않았다.

### ISSUE-WS-SILENT-INSERT-FAILURE-01

```text
auto_assign_schedules()
work_assignments insert 실패를 catch 후 continue
assigned_total 증가와 실제 insert 성공 건수 불일치 가능
API success 오보고 가능
```

REV-1 에서도 **기록만** 하고 수정하지 않았다.

### RISK-WS-EC-PARTIAL-NULL-01

```text
equipment_checkins composite FK uses MATCH SIMPLE without pair CHECK.
Current writer guarantees factory_id, but DB alone does not reject
every partial-null pair.
```

이번 WP 에서 schema 를 변경하지 않는다. runbook residual risk 로 이관.

---

## 15. 현재 상태

```text
CODE PATCH             = PASS (patch 4건, 브랜치 커밋 완료)
DB WRITE COMPATIBILITY = PASS
COMPOSITE FK COMPAT    = PASS
WRITER COVERAGE        = COMPLETE (UNCOVERED = 0)
API CONTRACT           = STATIC PASS

C-6 UPDATE 경로        = SKIP (검증 스크립트 한계, 정적 확인)
UNIT/STATIC TEST       = NOT EXECUTED
FULL API E2E           = NOT EXECUTED
SUPABASE E2E           = UNVERIFIED
PERFORMANCE            = UNBENCHMARKED

DEPLOY                 = NOT APPROVED
MERGE TO MAIN          = NOT APPROVED
PRODUCTION APPLY       = NOT APPROVED
```

---

## 16. Canonical SHA

```text
PREVIOUS CANONICAL (02C 최초 검증 이력)
239d2eaa2cd05bae5561d66603ec3c8563eb8cfa

NEW CANONICAL CODE HEAD (REV-1)
23d16ac21c87dcbdf5ff2a1b590fd8d797121349
```

DB artifact 는 변경 없음.

```text
UP   docs/sql/20260822_work_schedules_partition_up.sql
     commit b81e7018 / blob ac8adc58
     sha256 147f75f2864fd3bb261fb6ebedae7b34b5621b311d556e5d0d8e6b028300cca7

DOWN docs/sql/20260822_work_schedules_partition_down.sql
     commit 0972a18e / blob 96da5c88
     sha256 57768a50dd9e7643bb1708ec198e48bfc62d0474852faf433b15ae7f2e9df20d
```

---

## 17. 다음 단계

```text
WP-PARTITION-03
Production Cutover Readiness / Runbook
```

이 브랜치의 merge 시점과 배포 순서는 03 에서 확정한다.
