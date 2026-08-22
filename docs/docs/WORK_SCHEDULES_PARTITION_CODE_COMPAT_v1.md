# WORK_SCHEDULES_PARTITION_CODE_COMPAT_v1

> 작성일: 2026-08-23
> 상위: WORK_SCHEDULES_PARTITION_DESIGN_FINAL_v1.md
> 상태: **CODE PATCH 작성 완료 / 배포 미승인**
> 브랜치: `wo-work-schedules-partition-code-compat`
> base: `0972a18e9f158ce49c5d7163ab31860ebcb4f7db`

```text
PRODUCTION DB MUTATION = 0
MIGRATION APPLY        = 0
DEPLOY                 = 0
MERGE TO MAIN          = 0
```

---

## 1. 문서 목적

`work_schedules` 파티션 전환과 함께 반드시 배포되어야 하는 코드 변경 2건과, 그 변경이 새 schema 계약을 통과함을 증명하는 검증 기록을 고정한다.

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

## 3. Patch #1 — work_assignments

```text
FILE : routers/work_schedules.py
FUNC : _apply_one_update()
VER  : v1.2.7 → v1.2.8
```

### 적용 범위

```text
신규 assignment INSERT 경로만 변경
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

### 성능 영향

```text
신규 배정 1건당 SELECT 1회 증가
재배정(UPDATE) 경로는 증가 없음
```

---

## 4. Patch #2 — safety_inspections

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

이 두 경우에만 `work_schedules` 에서 factory 를 보완한다. 무조건 조회가 아니다.

### 구버전 앱 호환

```text
assignment 없는 제출
→ assignment_id NULL + factory_id NULL
→ pair CHECK 통과 (정상)
```

### 변경하지 않은 것

```text
항목 검증 로직 (inspection_set_item_id)
safety_inspection_results INSERT
response 계약
```

---

## 5. 공통 설계 원칙

```text
factory 를 모르는 상태로 child 를 저장하지 않는다
→ 409 로 명시적 실패
→ 조용한 무결성 우회 금지
```

---

## 6. 검증 결과 (Local PostgreSQL 17.6)

파티션 적용 DB 에서 패치된 write 패턴을 재현해 검증했다.

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

### pair 계약 위반

```text
work_assignments   377건 중 위반 0
safety_inspections 221건 중 위반 0
```

### C-3 의 의미

패치 이전 payload(`factory_id` 누락)가 **23514 CHECK 로 거부**됐다.

이것이 이 패치가 필수인 직접 근거이며, 동시에 무결성이 조용히 깨지지 않음을 보여준다.

### C-6 SKIP 사유

검증용 bootstrap 스키마에 `work_assignments.updated_at` 을 재현하지 않아 실행되지 않았다.

패치 결함이 아니라 검증 스크립트의 스키마 누락이다. UPDATE 경로는 diff 상 무변경이므로 간접 확인만 된 상태로 남긴다.

---

## 7. API contract 정적 검증

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

## 8. 배포 제약 (가장 중요)

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

## 9. 이번 변경에 포함하지 않은 것

```text
ISSUE-WS-SCHEMA-DRIFT-01
```

기존 코드가 존재하지 않는 컬럼을 UPDATE 하는 것을 발견했다.

```text
resolved_at   — work_schedules 에 없음
cycle_code    — work_schedules 에 없음
is_active     — work_schedules 에 없음 (실제는 active_yn)
```

파티셔닝과 무관한 기존 결함이므로 **이번 패치에 섮지 않았다.**

별건 WP 로 처리한다.

---

## 10. 현재 상태

```text
CODE PATCH             = PASS (브랜치 커밋 완료)
DB WRITE COMPATIBILITY = PASS
COMPOSITE FK COMPAT    = PASS
API CONTRACT           = STATIC PASS
C-6 UPDATE 경로        = SKIP
FULL API E2E           = NOT EXECUTED
SUPABASE E2E           = UNVERIFIED
DEPLOY                 = NOT APPROVED
MERGE TO MAIN          = NOT APPROVED
```

---

## 11. 다음 단계

```text
WP-PARTITION-03
Production Cutover Runbook
```

이 브랜치의 merge 시점과 배포 순서는 03 에서 확정한다.
