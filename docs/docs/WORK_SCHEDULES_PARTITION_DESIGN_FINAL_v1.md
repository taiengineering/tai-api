# WORK_SCHEDULES_PARTITION_DESIGN_FINAL_v1

> 작성일: 2026-08-23
> 대상: TAI Safe `work_schedules` 파티셔닝
> 상태: **PLANNING / PHYSICAL DESIGN CLOSED**
> DB 적용 상태: **미적용**

---

## 1. 문서 목적

본 문서는 `WP-PARTITION-00`부터 `WP-PARTITION-02A`까지 수행한 조사·설계·검증 결과를 고정한다.

이 문서 이후에는 `work_schedules`의 파티셔닝 필요성이나 기본 물리구조를 다시 기획하지 않는다.

다음 단계는 **설계 변경이 아니라 실행 가능성 검증(Dry-run)** 이다.

---

## 2. 작업 배경

초기 예상 파티셔닝 대상은 다음 두 영역이었다.

- 점검 스케줄
- 문서

그러나 서비스 오픈 전이라는 점을 고려하여 특정 테이블만 바로 변경하지 않고 전체 DB를 대상으로 파티셔닝 필요성을 먼저 조사했다.

`WP-PARTITION-00` 전수조사 결과 실제 증식 구조가 확인되었다.

핵심 발견:

- `work_schedules`는 반복 규칙 master가 아니라 **회차별 append operational table**
- `safety_inspection_results`는 점검 1건 × 체크항목 수만큼 증가하는 최상위 고증식 테이블
- `work_assignments`는 예상과 달리 schedule 종속 mixed/current-state 성격
- `report_events`는 로그가 아니라 Operational SoT
- 기존 문서의 `runtime_document_data`는 레거시가 아니라 ACTIVE 문서엔진
- 로그/이벤트 일부는 별도 LOG-PROJECT 대상으로 분리

---

## 3. 전수조사 최종 Scope

### P0
```text
work_schedules
safety_inspection_results
```

### P1
```text
safety_inspections
```

### P2
```text
work_assignments
report_events
```

### HOLD
```text
worker_attendance
```

### LOG-PROJECT
```text
business_event
runtime_notification_metrics
runtime_notification_event
```

### DOCUMENT 별도 재검토
```text
runtime_document_data
generated_document
runtime_document_approval
runtime_lifecycle_audit_log
evidence_vault_link
```

---

## 4. work_schedules 실체

실제 코드 조사 결과 `work_schedules`는 단일 반복 규칙을 유지하는 테이블이 아니다.

흐름:

```text
inspection_set
→ cycle 계산
→ work_schedules 회차 INSERT
→ 완료
→ 다음 회차 계산
→ 신규 work_schedules INSERT
```

따라서 서비스 운영기간에 따라 지속적으로 증가한다.

주요 조회는:

```text
factory_id
+ planned_date
+ status_code
+ obligation_type/source_type
```

구조다.

---

## 5. 최종 Partition 방향

확정 물리 방향:

```text
PARTITION BY HASH(factory_id)
MODULUS 16
```

`LIST(factory_id)`는 사용하지 않는다.

이유:

- factory 수가 이미 수천 단위
- factory 증가마다 partition DDL이 필요
- partition 수가 tenant 수와 함께 계속 증가
- 운영 복잡도가 불필요하게 커짐

HASH 고정 bucket 방식으로 tenant 증가와 partition 수를 분리한다.

---

## 6. Target Key Contract

현행:

```text
PRIMARY KEY (id)

UNIQUE (
    inspection_set_id,
    planned_date
)
```

Target:

```text
PRIMARY KEY (
    id,
    factory_id
)

UNIQUE (
    inspection_set_id,
    planned_date,
    factory_id
)
```

`inspection_set_id → factory_id` 함수 종속 관계가 실제 DB와 코드에서 검증되었다.

따라서 UNIQUE에 `factory_id`가 추가되더라도 기존 업무 의미는 변하지 않는다.

---

## 7. inspection_set / factory 관계

검증 결과:

```text
inspection_sets.factory_id NULL = 0
```

`inspection_set` 하나가 여러 factory에서 공유되는 구조가 아니다.

또한:

```text
work_schedules.factory_id
=
inspection_sets.factory_id
```

불일치 0건.

schedule 생성 코드도 `inspection_set.factory_id`를 그대로 schedule에 복사한다.

따라서 `factory_id`는 schedule 생성 시 임의 입력값이 아니다.

---

## 8. Application Identity

DB PK는 복합키로 변경되지만 application identity는 계속:

```text
schedule.id
```

를 사용한다.

예:

```text
/work-schedules/{schedule_id}
.eq("id", schedule_id)
.in_("id", ids)
```

`id` 생성은 UUID 기반이므로 cross-partition collision 위험은 수용 가능으로 판정한다.

단:

```text
WHERE id = ?
```

조회는 `factory_id` predicate가 없으면 partition pruning이 발생하지 않는다.

이는 향후 benchmark 항목으로 유지한다.

---

## 9. Child FK 영향

`work_schedules`를 partitioned parent로 변경하면 기존 단일-column FK를 유지할 수 없다.

영향 child:

```text
work_assignments
safety_inspections
equipment_checkins
```

Target 관계:

```text
(schedule_id, factory_id)
→ work_schedules(id, factory_id)
```

### work_assignments

`factory_id` 신규 additive 필요.

값:

```text
parent work_schedules.factory_id
```

### safety_inspections

`factory_id` 신규 additive 필요.

단 이 컬럼은:

```text
canonical tenant key 아님
assignment_id가 존재할 때 사용하는 FK companion
업무 tenant filter로 사용 금지
```

계약으로 고정한다.

### equipment_checkins

이미 `factory_id` 보유.

기존 delete semantics:

```text
ON DELETE SET NULL
```

을 보존하기 위해:

```text
ON DELETE SET NULL (schedule_id)
```

방향을 사용한다.

---

## 10. Composite FK NULL Contract

`MATCH SIMPLE`의 NULL 우회 문제를 방지하기 위해 `work_assignments`, `safety_inspections`에는:

```text
MATCH FULL
```

및 pair CHECK를 적용한다.

예:

```text
CHECK (
    (schedule_id IS NULL)
    =
    (factory_id IS NULL)
)
```

이를 통해 child가 `factory_id` 없이 조용히 저장되는 것을 막는다.

---

## 11. Index 설계

기존 `work_schedules`에는 12개 index가 존재했다.

실제 코드 predicate와 index scan을 함께 조사하여 재편한다.

핵심 방향:

```text
factory_id + planned_date
factory_id + status_code + planned_date
factory_id + is_excluded
```

등 실제 factory-scoped 조회를 중심으로 구성한다.

확정 정리:

```text
event_type
→ DROP
```

코드 predicate 없음.

```text
is_excluded
→ MERGE
```

factory scope와 함께 사용.

```text
status_date
→ MERGE
```

factory + status + planned_date 조합으로 흡수.

HASH partition 내부에도 여러 factory가 존재하므로 `factory_id` leading index의 의미는 유지된다.

---

## 12. Migration Strategy

채택 전략:

```text
Shadow Table
→ Copy
→ Full Validation
→ FK Rewire
→ Swap
```

일반 table을 현재 구조 그대로 in-place partitioned table로 변환하는 방식은 사용하지 않는다.

---

## 13. Data Integrity 검증

UP/DOWN 모두 단순 row count나 id checksum으로 검증하지 않는다.

전체 37컬럼을 명시하고:

```text
A EXCEPT B
B EXCEPT A
```

양방향 결과 0건을 강제한다.

따라서:

- status 변경
- description 변경
- planned_date 변경
- 기타 column 손상

등 id가 동일한 데이터 손상도 검출한다.

---

## 14. Rollback Contract

DOWN은 **FAST-PATH ONLY**로 설계한다.

조건:

```text
work_schedules_old 존재
```

하지 않으면 시작 즉시 ABORT.

`work_schedules_old` 삭제는 migration 완료 직후 하지 않는다.

별도 cleanup 승인 전까지 rollback anchor로 유지한다.

DOWN 시:

```text
신규 INSERT reconciliation
전체 컬럼 UPDATE reconciliation
삭제 row reconciliation
full-row equality
```

를 수행한다.

---

## 15. Concurrent Write 통제

migration 중 write race를 허용하지 않는다.

SQL 수준:

```text
ACCESS EXCLUSIVE LOCK
```

운영 수준:

```text
maintenance ON
→ active writer = 0 확인
→ DB UP
→ patched code deploy
→ smoke test
→ maintenance OFF
```

순서를 고정한다.

---

## 16. 필수 코드 Patch

DB migration과 함께 필요한 내부 변경은 2건이다.

### work_assignments

```text
routers/work_schedules.py
_apply_one_update()
```

INSERT 시:

```text
factory_id
```

전달.

### safety_inspections

```text
routers/worker_check.py
submit_check()
```

parent schedule에서 `factory_id`를 조회하여 INSERT에 전달.

이 patch는 구 schema와 backward-compatible하지 않으므로 DB migration과 동일 maintenance window에서 처리한다.

---

## 17. RLS / Security Contract

`work_schedules`:

```text
RLS ENABLED
policy 6개
```

현재 policy 조건은 매우 permissive한 상태로 확인되었다.

이는 파티셔닝 변경사항이 아니므로 migration에서 기존 contract를 그대로 복제한다.

단:

> RLS 정책 자체의 보안 적정성 검토는 별도 보안 작업으로 이관한다.

파티셔닝 작업에서 임의 수정하지 않는다.

---

## 18. PRE-state Exact Preservation

Migration package는 다음 contract를 snapshot으로 보존한다.

```text
owner
RLS enabled
RLS forced
policies
comments
grants
grantor
grantee
privilege
is_grantable
```

GRANT는 `WITH GRANT OPTION`까지 복원한다.

catalog 조회는:

```text
public.work_schedules
```

schema로 명시적으로 제한한다.

---

## 19. 검증 완료 Artifact

최종 설계 artifact:

```text
REV3_20260822_work_schedules_partition_up.sql
REV3_20260822_work_schedules_partition_down.sql
```

상태:

```text
UP DESIGN = PASS
DOWN DESIGN = PASS
```

아직:

```text
DB APPLY = 0
CODE APPLY = 0
COMMIT = 0
```

이다.

---

## 20. 완료 판정

```text
WP-PARTITION-00
= PASS / CLOSED

WP-PARTITION-01A
= PASS / CLOSED

WP-PARTITION-02A REV-3
= PASS / CLOSED
```

따라서:

```text
work_schedules
PLANNING = CLOSED
PHYSICAL DESIGN = CLOSED
MIGRATION PACKAGE DESIGN = CLOSED
```

---

## 21. 아직 승인되지 않은 것

본 문서가 다음을 승인하는 것은 아니다.

```text
production DB mutation
Supabase DDL execution
code deployment
migration execution
old table cleanup
```

실행 승인은 별도 Gate를 통과해야 한다.

---

## 22. 다음 단계

다음 작업:

```text
WP-PARTITION-02B
Migration Package
Static Execution Verification / Dry-run
```

목적:

```text
REV-3 SQL이 실제 PostgreSQL 환경에서
처음부터 끝까지 실행 가능한지 검증
```

검증 범위:

```text
UP
→ 16 HASH partitions 확인
→ constraint/FK 확인
→ RLS/grants/comments 확인
→ code patch
→ smoke test
→ DOWN
→ PRE-state exact restoration
→ UP 재실행 가능성
```

02B에서도 production DB mutation은 승인하지 않는다.

---

## 23. 별도 남은 작업

### safety_inspection_results

```text
P0
```

파티셔닝 필요성은 확정.

하지만:

```text
RETENTION PERIOD
HOT/COLD POLICY
ARCHIVE DESTINATION
DELETE POLICY
```

가 모두 미정의.

따라서:

```text
WP-RETENTION-01
```

을 먼저 수행한 뒤 물리설계를 확정한다.

---

### 문서엔진

조사 중 기존:

```text
runtime_document_data
```

가 ACTIVE document engine이라는 사실을 확인했다.

따라서 기존:

```text
D-09
기존 문서계열 레거시 격리
```

는 즉시 실행하지 않는다.

다음:

```text
WP-DOCUMENT-ARCH-01
```

에서:

```text
기존 ACTIVE engine
vs
lazy + delta + snapshot
```

을 비교하여 아키텍처를 다시 확정한다.

---

### 로그

로그 병합은:

```text
점검/파티셔닝
→ 문서
→ 로그
```

순서로 진행한다.

현재:

```text
LOG MERGE = NOT STARTED
```

---

## 24. 최종 기준

이 문서 이후 `work_schedules`에 대해서는 다시:

```text
파티셔닝이 필요한가?
factory_id가 맞는가?
HASH인가?
```

를 처음부터 재논의하지 않는다.

새 증거가 기존 결정과 충돌할 때만 재개한다.

다음 단계는 **기획이 아니라 실행 가능성 검증**이다.
