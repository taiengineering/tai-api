# WO-TAI-DOC260-G3-EVIDENCE-CONTRACT-027 — C2 최종 계약

**STATUS**: C2_CLOSED_FINAL / GPT_IV_R4_CONDITIONAL_PASS  
**OWNER_APPROVAL**: D1 조건부 승인 접수 (2026-10-26)  
**CODE_CHANGE**: 0  
**DB_WRITE**: 0  
**MIGRATION_APPLY**: 0  
**선행 문서**: `WO-027-EVIDENCE-CONTRACT-C2-CORRECTED.md`  
**GPT_IV 지적 보완**: 승인 기록 경로·롤백 범위·원자성·LEG 오류 메시지 (2026-10-26)

---

## 계약 범위

Owner 승인 범위: D1 기준 Evidence 승인 계약 설계 확정.  
C3 코드 구현, DB 변경, Migration 적용, PR 병합, 운영 배포, 고객 활성화는 별도 승인 필요.

---

## §1. Evidence 상태값 기준표 (불변 근거)

### §1-1. runtime_evidence_field.status

| 항목 | 값 | 근거 |
|------|-----|------|
| DB CHECK 허용값 | CANDIDATE / NEEDS_HUMAN_REVIEW / APPROVED_BY_HUMAN / REJECTED_BY_HUMAN | DB 직접 확인 |
| 생성 초기값 | CANDIDATE | INSERT 경로 확인 |
| 터미널 승인값 | **APPROVED_BY_HUMAN** | DB CHECK 직접 근거 |
| 터미널 거부값 | REJECTED_BY_HUMAN | DB CHECK 직접 근거 |
| 코드 현재 요구값 | APPROVED_FOR_RUNTIME_USE | `document_confirm_svc.py:61` — **오류** |
| 현재 DB 상태 | 202행 전부 CANDIDATE | GPT IV 직접 확인 |
| UPDATE 경로 | **없음** (코드베이스 전체) | C1-A 조사 결과 |

> APPROVED_FOR_RUNTIME_USE는 runtime_form_schema 전용 상태. evidence 계층에 적용 불가.  
> STEP4A_VERIFY.sql:46은 `runtime_field`(rf) 기준이며 runtime_evidence_field 직접 근거 아님.

### §1-2. evidence_field_candidate.status

| 항목 | 값 | 근거 |
|------|-----|------|
| DB CHECK 현재 허용값 | CANDIDATE / NEEDS_HUMAN_REVIEW / AMBIGUOUS / UNRESOLVED | DB 직접 확인 |
| 승인 상태 존재 여부 | **없음** | DB CHECK 확인 |
| 코드 현재 요구값 | APPROVED_FOR_RUNTIME_USE | `document_confirm_svc.py:59` — **오류** |
| UPDATE 경로 | **없음** (코드베이스 전체) | C1-A 조사 결과 |

> D1 적용 시 DB CHECK에 APPROVED_BY_HUMAN / REJECTED_BY_HUMAN 추가 필요.

### §1-3. runtime_form_schema.status (참조)

| 단계 | 값 |
|------|-----|
| 초기 | CANDIDATE |
| 중간 승인 | APPROVED_BY_HUMAN |
| 최종 승격 | APPROVED_FOR_RUNTIME_USE |

---

## §2. Evidence Candidate 승인 계약 (D1)

### §2-1. 상태 전이 정의

```
evidence_field_candidate.status 전이 (D1 승인):

  CANDIDATE
    │
    ├─→ NEEDS_HUMAN_REVIEW  (검토 필요 표시 — 리뷰어 지정)
    │
    ├─→ APPROVED_BY_HUMAN   ← 신규 추가 (D1)
    │     승인 조건:
    │       - reviewer_id 존재 (승인 주체 명시)
    │       - review_comment 존재 (승인 근거 명시)
    │       - schema_candidate_id 일치 확인 (R2-C2)
    │     의미: 문서 증빙 후보의 사용 승인
    │     법률 판단 아님: LEG 의무 발생 판단과 무관
    │
    ├─→ REJECTED_BY_HUMAN   ← 신규 추가 (D1)
    │     거부 조건: reviewer_id + review_comment 존재
    │
    └─→ AMBIGUOUS / UNRESOLVED (기존 유지 — 검토 중 상태)
```

### §2-2. DB 스키마 변경 대상 (Migration 설계안)

```sql
-- Migration: evidence_field_candidate CHECK 확장 (C3 구현 시 적용)
-- evidence_field_candidate.status CHECK 현재값:
--   CHECK (status IN ('CANDIDATE','NEEDS_HUMAN_REVIEW','AMBIGUOUS','UNRESOLVED'))
-- 변경 후:
ALTER TABLE evidence_field_candidate
  DROP CONSTRAINT IF EXISTS evidence_field_candidate_status_check;
ALTER TABLE evidence_field_candidate
  ADD CONSTRAINT evidence_field_candidate_status_check
    CHECK (status IN (
      'CANDIDATE',
      'NEEDS_HUMAN_REVIEW',
      'AMBIGUOUS',
      'UNRESOLVED',
      'APPROVED_BY_HUMAN',    -- D1 신규
      'REJECTED_BY_HUMAN'     -- D1 신규
    ));
-- NOTE: 이 SQL은 설계안. C3 Migration 파일로 이관 후 Owner 별도 실행 승인 필요.
```

### §2-3. 승인 주체·기록 저장 경로 계약

**evidence_field_candidate 테이블에는 reviewer_id / review_comment / approved_at 컬럼 없음.**  
단순 status UPDATE만으로 승인 처리 불가. 아래 2단계 처리 방식으로 원자성 확보.

#### 저장 경로: `runtime_review_decision` 재사용

| 컬럼 | 계약값 |
|------|--------|
| `review_domain` | `'EVIDENCE'` (기존 활성 권한 1건 존재 — GPT IV 확인) |
| `source_entity_id` | `evidence_field_candidate.id` |
| `review_action` | `'APPROVE'` 또는 `'REJECT'` |
| `reviewer_id` | 필수 (NULL 불허) |
| `review_reason` | APPROVE 시 Optional / REJECT 시 필수 |

#### 승인 흐름 (2단계, 단일 트랜잭션)

```
[단계 1] POST /bridge/review-decisions
         review_domain='EVIDENCE'
         source_entity_id=<evidence_field_candidate.id>
         reviewer_id=<승인자>
         review_action='APPROVE'
         → fn_validate_review_authority() 트리거 자동 검증
           (EVIDENCE 도메인 활성 권한 확인)
         → runtime_review_decision 행 INSERT

[단계 2] evidence_field_candidate.status UPDATE
         CANDIDATE → APPROVED_BY_HUMAN
         WHERE id = source_entity_id
           AND 단계 1 성공 (트랜잭션 내)

원자성: 단계 1·2가 단일 DB 트랜잭션 안에서 실행되어야 함.
        단계 2 실패 시 단계 1 롤백.
        단계 1 성공·단계 2 미실행 상태 금지.
```

#### 권한 검증 보완 계약

`fn_validate_review_authority()`는 해당 도메인에 활성 권한이 **존재하는지만** 검사.  
개별 reviewer_id가 실제 권한 보유자인지 검사하지 않음 (GPT IV R2 확인).

**운영 DB EVIDENCE 권한 실제 구성 (GPT IV R2 확인)**:

| 항목 | 값 |
|------|-----|
| 승인 도메인 | `EVIDENCE` |
| 승인 역할 | `SAFETY_MANAGER` |
| 승인 대상 | 특정 사용자 UUID 지정 |
| 권한 상태 | `ACTIVE` |

**C3-04 구현 시 권한 검증 계약 (C2-FINAL-CLOSE 확정)**:

```
[단계 0] 요청자 신원 검증:
  인증된 요청자 identity == reviewer_id
  불일치 시 → 403 (사칭 차단)

[단계 1] 권한 검증 — AND 조건 (OR 금지):
  SELECT 1
  FROM runtime_review_authority
  WHERE review_domain = 'EVIDENCE'
    AND authority_status = 'ACTIVE'
    AND approved_user_id = <서버_검증_reviewer_id>  -- 사용자 UUID 일치 (AND)
    AND approval_role = 'SAFETY_MANAGER'            -- 역할 일치 (AND)
    AND approval_scope LIKE '%증빙%'                -- scope 포함 확인
  → 결과 없으면 403 반환 (승인 금지)

  금지: approved_user_id 일치 OR approval_role 일치 조건
  금지: 클라이언트 전달 역할 문자열 직접 사용
        → 역할은 서버 인증·인가 데이터(JWT claims 또는 DB 프로필)에서 확인

[단계 2] 중복·부정 전이 차단:
  SELECT status FROM evidence_field_candidate WHERE id = <target_id> FOR UPDATE
  현재 status = 'CANDIDATE' 또는 'NEEDS_HUMAN_REVIEW'가 아니면 → 409 (이미 처리됨)
  동일 source_entity_id로 review_action='APPROVE'인 decision 이미 존재 → 409 (중복 차단)

[단계 3] review_reason 필수화:
  review_reason = NULL 또는 빈 문자열 → 400 반환
  공백만 있는 문자열(strip 후 빈 값) → 400 반환
```

| 항목 | 계약값 |
|------|--------|
| 승인 기록 위치 | `runtime_review_decision` (reviewer_id·review_reason·review_action) |
| review_reason | **필수** — NULL·빈 문자열·공백 전부 거부 (API 레벨 강제) |
| reviewer_id 검증 | approved_user_id **AND** approval_role **AND** approval_scope (OR 금지) |
| 역할 출처 | 서버 인증 데이터 (클라이언트 전달 임의 문자열 사용 금지) |
| 중복 승인 | 동일 evidence_field_candidate에 APPROVE decision 존재 시 409 |
| 부정 전이 | APPROVED_BY_HUMAN / REJECTED_BY_HUMAN 상태에서 재승인 차단 |
| 자동 승격 | **금지** — 기존 CANDIDATE 레코드 자동 승격 없음 |
| Fail-Closed | CANDIDATE / AMBIGUOUS / UNRESOLVED = 봉인 차단 유지 |
| REJECT 시 review_reason | 필수 (기존 `review_bridge.py:116` + Evidence 승인도 동일 적용) |

---

## §3. Runtime Evidence 승인 계약

### §3-1. 상태 전이 정의

```
runtime_evidence_field.status 전이:

  CANDIDATE
    │
    ├─→ NEEDS_HUMAN_REVIEW  (검토 필요)
    │
    ├─→ APPROVED_BY_HUMAN   ← 터미널 승인 (DB 기존 허용값)
    │     승인 조건:
    │       - STEP4E 승격 절차 내에서만 전이
    │       - form_schema_id = 대상 스키마 일치 확인
    │       - evidence_candidate_id FK 유효성 확인
    │     의미: 이 schema의 evidence 필드를 런타임에서 사용 승인
    │
    └─→ REJECTED_BY_HUMAN   ← 터미널 거부 (DB 기존 허용값)
```

### §3-2. 코드 정합화 대상

```python
# services/document_confirm_svc.py:57–61 — C3 수정 대상

# 현재 (오류)
_SCHEMA_STATUS_APPROVED = "APPROVED_FOR_RUNTIME_USE"
_ALLOWED_EVIDENCE_CANDIDATE_STATUSES = frozenset({_SCHEMA_STATUS_APPROVED})
_ALLOWED_EVIDENCE_FIELD_STATUSES     = frozenset({_SCHEMA_STATUS_APPROVED})

# 정합화 후 (D1 기준)
_SCHEMA_STATUS_APPROVED              = "APPROVED_FOR_RUNTIME_USE"  # schema 전용 — 유지
_ALLOWED_EVIDENCE_FIELD_STATUSES     = frozenset({"APPROVED_BY_HUMAN"})   # R2-01
_ALLOWED_EVIDENCE_CANDIDATE_STATUSES = frozenset({"APPROVED_BY_HUMAN"})   # R1-02 (D1 적용 후)
```

> R2-01 에러 메시지도 함께 정정 필요 (`document_confirm_svc.py:117`).

### §3-3. DB UPDATE 대상 (STEP4E 실행 시)

```
대상 스키마: runtime_form_schema.id = 4e07df2e-904a-4fe6-ad18-cecc0f5e57f3
             (DOC-CON-048 runtime schema)

runtime_evidence_field:
  form_schema_id = 4e07df2e ... 인 행만 CANDIDATE → APPROVED_BY_HUMAN
  현재 확인된 ID: 948088d5-627f-4825-a906-2b86a3d27de5
  UPDATE 조건: STEP4E 승격 절차 내 원자 트랜잭션으로만 실행

evidence_field_candidate:
  id = 5e5687b3-e62f-480c-ad75-1efc41706e3b
  schema_candidate_id = 2f41ab16-4748-4bf7-84a3-55a20f74efda (DOC-CON-048 candidate)
  UPDATE: CANDIDATE → APPROVED_BY_HUMAN (D1 Migration 적용 후)
```

---

## §4. STEP4E 서식 승격 계약

### §4-1. 기존 STEP4D와의 차이

| 항목 | STEP4D (GEN-INSPECT-RESULT-001) | STEP4E (evidence 포함 스키마) |
|------|----------------------------------|-------------------------------|
| evidence_count PRECONDITION | = 0 | ≥ 1 |
| runtime_evidence_field 처리 | ABORT if > 0 | CANDIDATE → APPROVED_BY_HUMAN |
| evidence_field_candidate 검증 | 해당 없음 | APPROVED_BY_HUMAN 확인 |
| 적용 대상 | GEN-INSPECT-RESULT-001 전용 | evidence 포함 스키마 전반 |

### §4-2. STEP4E_UP 실행 순서 계약

```
STEP4E_UP 실행 순서 (원자 트랜잭션 내):

  PRECONDITION 검증:
    [P1] runtime_form_schema.status = 'CANDIDATE'
    [P2] runtime_field 전 행 status = 'APPROVED_BY_HUMAN' (Field Gate G3 통과 후)
    [P3] runtime_field required_status = CANDIDATE_ONLY 행 0개
         ※ DOC-CON-048 4개 필드: Packet A 실행 후 REQUIRED_BY_HUMAN 상태 확인 필수
    [P4] evidence_count ≥ 1

  before_state snapshot 범위 (STEP4D_UP 패턴 확장):
    schema_status
    fields (id, field_key, status, required_status) ← 롤백 복원 대상
    evidence_fields (id, status, evidence_candidate_id)
    evidence_candidate_decision_ref (runtime_review_decision.id, status 당시값) ← 신규

  대상 행 잠금:
    트랜잭션 B 시작 시 대상 schema / field / evidence_field SELECT FOR UPDATE
    (동시 변경 통제)

  STEP 1: evidence_field_candidate 검증
    [S1-1] form_schema_id 해당 evidence_field_candidate 전 행 조회
    [S1-2] 각 행 status = 'APPROVED_BY_HUMAN' 확인 (D1 적용 후, 트랜잭션 A 완료 확인)
    [S1-3] schema_candidate_id 일치 확인 (R2-C2)
    [S1-4] FK: evidence_candidate_id → evidence_field_candidate.id 유효성

  STEP 2: runtime_evidence_field → APPROVED_BY_HUMAN
    [S2-1] form_schema_id 해당 전 행 status = 'CANDIDATE' 확인
    [S2-2] UPDATE status = 'APPROVED_BY_HUMAN'
    [S2-3] UPDATE 행 수 = evidence_count 일치 검증

  STEP 3: runtime_form_schema → APPROVED_BY_HUMAN (1단계)
    [S3-1] UPDATE status = 'APPROVED_BY_HUMAN' WHERE status = 'CANDIDATE'
    [S3-2] 영향 행 수 = 1 검증

  STEP 4: Gate 검증
    [G-EV]  runtime_evidence_field 전 행 status = 'APPROVED_BY_HUMAN'
    [G-EFC] evidence_field_candidate 전 행 status = 'APPROVED_BY_HUMAN'
    [G-FK]  evidence_candidate_id FK chain 유효
    [G-FLD] runtime_field 전 행 status = 'APPROVED_BY_HUMAN' (재확인)
    [G-FLD2] runtime_field required_status = CANDIDATE_ONLY 행 0개 (재확인)

  STEP 5: runtime_form_schema → APPROVED_FOR_RUNTIME_USE (2단계)
    [S5-1] UPDATE status = 'APPROVED_FOR_RUNTIME_USE' WHERE status = 'APPROVED_BY_HUMAN'
    [S5-2] 영향 행 수 = 1 검증

  FINAL ASSERT:
    runtime_form_schema.status = 'APPROVED_FOR_RUNTIME_USE'
    runtime_evidence_field 전 행 status = 'APPROVED_BY_HUMAN'
    evidence_field_candidate 전 행 status = 'APPROVED_BY_HUMAN'
    runtime_field 전 행 status = 'APPROVED_BY_HUMAN'
    runtime_field CANDIDATE_ONLY = 0
```

### §4-3. Audit 계약 (STEP4D_UP 재사용)

```sql
-- STEP4E Audit INSERT 계약 (C3 구현 시)
-- v_before 범위: schema_status + fields(field_key/status/required_status) + evidence_fields
INSERT INTO runtime_form_audit_log
  (source_table, source_id, action, schema_version,
   before_state, after_state, reviewer_id, review_comment,
   rollback_snapshot, rollback_available)
VALUES
  ('runtime_form_schema', v_schema_id,
   'PROMOTE_TO_RUNTIME_USE_WITH_EVIDENCE', 1,
   v_before,             -- schema + fields + evidence_fields 포함 (STEP4D_UP 확장)
   v_after,
   <reviewer_id>,        -- NULL 불허 (STEP4D와 차이)
   <review_comment>,     -- NULL/빈 문자열 불허
   v_before,             -- rollback_snapshot = before_state (STEP4E_DOWN 복원용)
   true);                -- rollback_available = true 필수
```

> `rollback_available=true` 없으면 STEP4E_DOWN 롤백 불가. 필수.  
> `before_state`에 `fields`(status+required_status) 포함 필수 — STEP4E_DOWN이 이 값을 기준으로 복원.

### §4-4. Rollback 계약 및 원자성 (STEP4D_DOWN 재사용 패턴)

#### STEP4E 롤백 범위

**evidence_field_candidate 승인은 STEP4E와 독립된 결정.**

| 항목 | 계약 |
|------|------|
| Evidence Candidate 승인 (`evidence_field_candidate.status`) | STEP4E 실패·롤백 시 **원복 안 함** |
| 근거 | Evidence Candidate 승인은 "이 증빙 후보를 사용 가능한 것으로 본다"는 지속적 결정. schema 승격 실패와 무관. |
| Evidence Candidate 원복 | 별도 관리자 결정 필요 (`/bridge/review-decisions` REJECT action) |
| **runtime_field.status** | **STEP4E 롤백 시 CANDIDATE 복원** (STEP4D_DOWN 패턴 재사용) |
| **runtime_field.required_status** | **STEP4E 롤백 시 CANDIDATE_ONLY 복원** |
| runtime_evidence_field.status | STEP4E 롤백 시 CANDIDATE 복원 |
| runtime_form_schema.status | STEP4E 롤백 시 CANDIDATE 복원 |

> **GPT IV R2 지적 보완**: 기존 STEP4E R2 계약에서 `runtime_field` 복원 누락. STEP4D_UP.sql은 `runtime_field.status` + `required_status`를 before_state에 포함하고 STEP4D_DOWN.sql은 이를 복원함. STEP4E_DOWN도 동일하게 포함.

#### STEP4D_DOWN 재사용 불가 이유

STEP4D_DOWN.sql:37 — `runtime_evidence_field = 0` PRECONDITION:
```sql
+ (SELECT count(*) FROM runtime_evidence_field WHERE form_schema_id = v_schema_id)
-- → 이 값이 0이 아니면 ABORT
```
DOC-CON-048는 Evidence 1건 이상 → STEP4D_DOWN 직접 재사용 불가. STEP4E_DOWN을 신규 설계해야 함.

#### STEP4E_DOWN 계약 (C2-FINAL-CLOSE 확정)

```
STEP4E_DOWN 진입 조건:
  [D1] rollback_available=true인 PROMOTE_TO_RUNTIME_USE_WITH_EVIDENCE 감사로그 1건 존재
  [D2] runtime_form_schema.status = 'APPROVED_FOR_RUNTIME_USE'
  [D3] runtime_field 전 행 status = 'APPROVED_BY_HUMAN'
  [D4] runtime_evidence_field 전 행 status = 'APPROVED_BY_HUMAN'
  [D5] 같은 승격에 대한 롤백이 이미 수행된 적 없음
       (ROLLBACK_FROM_RUNTIME_USE_WITH_EVIDENCE audit = 0건)

롤백 차단 기준 (ABORT — 부분 복원 불허):
  [B1] 승격 이후 runtime_inspection_bridge / runtime_document_data
       / generated_document / rendered_form / company_form_mapping
       / runtime_checklist_item 참조 1건 이상 → ABORT
  [B2] 현재 status가 Snapshot 계약과 불일치 → ABORT
  [B3] 승인·승격 Audit의 유효성 확인 실패 (rollback_available=false) → ABORT
  [B4] 롤백 후 FK 참조 무결성 보장 불가 → ABORT
  [B5] 같은 승격의 롤백이 이미 수행됨 (중복 롤백 차단) → ABORT
  [B6] 생성 문서·렌더링·봉인 결과 존재 → ABORT

Before Snapshot 범위:
  schema_status
  fields (id, field_key, status, required_status)
  evidence_fields (id, status, evidence_candidate_id)
  evidence_candidate_decision_ref (runtime_review_decision.id, 당시 status)  ← 신규

Rollback 순서 (원자 트랜잭션, 부분 복원 금지):
  1. 대상 행 SELECT FOR UPDATE (동시 변경 통제)
  2. runtime_form_schema   → CANDIDATE
  3. runtime_field         → CANDIDATE + required_status → CANDIDATE_ONLY
  4. runtime_evidence_field → CANDIDATE (form_schema_id 해당 전 행)
  5. runtime_form_audit_log 롤백 기록
     (action='ROLLBACK_FROM_RUNTIME_USE_WITH_EVIDENCE',
      rollback_available→false, 롤백 주체·시점·사유 기록)
  ※ evidence_field_candidate.status = 변경 없음 (독립 결정 보존)
  ※ 트랜잭션 A 승인 이력 = 변경 없음

감사 계약 (GPT IV R4 지적 반영 — 트랜잭션 분리):

  PostgreSQL에서 실패한 트랜잭션 안의 INSERT도 함께 롤백됨.
  따라서 성공·실패 감사 기록은 다른 트랜잭션 전략 적용.

  성공 경로:
    상태 복원 + 성공 Audit INSERT → 동일 트랜잭션으로 COMMIT
    action='ROLLBACK_FROM_RUNTIME_USE_WITH_EVIDENCE'

  실패 경로:
    [1] 상태 변경 전체 롤백 (트랜잭션 B 전체)
    [2] 별도 자율 트랜잭션(autonomous tx)에서 실패 Audit INSERT:
        action  = 'ROLLBACK_ABORTED'
        payload = {
          target_schema_id: v_schema_id,
          abort_gate: <차단된 B1~B6 중 해당 항목>,
          reason: <RAISE EXCEPTION 메시지>,
          actor: <실행 주체>,
          attempted_at: now()
        }
    [3] 실패 Audit INSERT 자체가 실패하면 → 운영 오류로 보고
        자동 재승격·재시도 금지
        (별도 운영 알림 경로 → Owner 수동 확인)
```

#### 원자성 계약 (GPT IV 지적 반영)

```
STEP4E 내 원자성 요구사항:
  하나의 DB 트랜잭션 안에서:
    - runtime_evidence_field.status UPDATE
    - runtime_form_schema.status UPDATE (2단계)
    - runtime_form_audit_log INSERT
  모두 성공하거나 모두 롤백.

evidence_field_candidate 승인과 STEP4E는 별도 트랜잭션:
  - evidence_field_candidate 승인 (runtime_review_decision INSERT + status UPDATE) = 트랜잭션 A
  - STEP4E 승격 = 트랜잭션 B
  - 트랜잭션 A 완료 확인 후 트랜잭션 B 시작
  - 트랜잭션 B 실패 시 트랜잭션 A 변경은 유지 (독립)
```

---

## §4B. Evidence Candidate 승인과 LEG 법적 판단 분리 계약

**GPT IV 지적 A 반영**: document_confirm_svc.py 오류 메시지의 "LEG gate" 표현 오류.

| 항목 | 계약 |
|------|------|
| evidence_field_candidate 승인 | **문서 증빙 후보의 사용 승인** — 법적 의무 발생 판단 아님 |
| LEG 역할 | 의무 발생 판단, 법적 요건 확인 — DOC 계층이 수행 불가 |
| 혼동 금지 | `review_domain='EVIDENCE'` 승인 ≠ LEG 법적 허가 |
| 코드 오류 메시지 | `"confirm blocked until LEG gate passes"` → `"confirm blocked until evidence approval gate passes"` |
| 수정 대상 | `services/document_confirm_svc.py:393` (C3-04B에서 수정) |

---

## §5. LEG→DOC 책임경계 (C2-C 확정)

| 항목 | 계약 |
|------|------|
| LEG 역할 | 의무 발생 판단 및 법적 적용 여부 결정 |
| DOC 역할 | LEG가 확정한 의무 결과와 승인된 연결 계약만 소비 |
| DOC에서 금지 | 법령 재판단, 추정 매핑, 신규 의무 등록 |
| DOC-CON-048 LEG 연결 | `CONTRACT_UNVERIFIED` 유지 (CON 섹터 obligation_form_mapping = 0건) |
| evidence_field_candidate 승인 | **문서 증빙 후보의 사용 승인**. 법적 의무 발생 판단 아님 |
| runtime_evidence_field 승인 | **Runtime 증빙 필드 사용 승인**. 법적 의무 판단 아님 |
| attached_documents 의미 확정 | **별도 Owner Gate** — 이번 C2 계약 범위 아님 |
| STEP4E 설계 완료 | G4 승격 승인과 별개 (Owner 별도 결정 필요) |
| G4 승격 승인 | 고객 공개 승인과 별개 (factory_scope_verified + G5) |

---

## §6. Gate 분리 계약

```
[G3] Field 승인 Gate (WO-026 Packet A로 해소)
  조건: runtime_field.required_status != CANDIDATE_ONLY 전 필드
  현황: HOLD — Packet A Owner 실행 대기

[G-EFC] Evidence Candidate 승인 Gate (신규, D1)
  조건: evidence_field_candidate.status = 'APPROVED_BY_HUMAN'
  현황: BLOCKED — D1 Migration + 승인 절차 미완

[G-EV] Runtime Evidence 승인 Gate (신규)
  조건: runtime_evidence_field.status = 'APPROVED_BY_HUMAN'
  현황: BLOCKED — STEP4E UPDATE 미완

[G4] 서식 승격 Gate (STEP4E)
  조건: runtime_form_schema.status = 'APPROVED_FOR_RUNTIME_USE'
  진입 조건: G3 + G-EFC + G-EV 모두 충족 후
  현황: BLOCKED

[G5] 고객 노출 Gate (G4와 분리, catalog_aggregator)
  조건: runtime_form_schema.status = 'APPROVED_FOR_RUNTIME_USE'
        AND factory_scope_verified = true
        AND company_form_mapping ≥ 1
  DOC-CON-048 현황: company_form_mapping = 0 → BLOCKED (G4 이후에도 자동 노출 없음)
```

---

## §7. C3 실행 순서 및 테스트 기준

C3는 **별도 Owner 승인** 후 시작.

### §7-1. C3 실행 순서

```
C3-01: D1 Migration 설계 (evidence_field_candidate CHECK 확장)
       → 파일: supabase/migrations/YYYYMMDD_evidence_field_candidate_d1.sql
       → Owner 실행 승인 필요

C3-02: document_confirm_svc.py 상태 allowlist 정정
       → _ALLOWED_EVIDENCE_FIELD_STATUSES = frozenset({"APPROVED_BY_HUMAN"})
       → _ALLOWED_EVIDENCE_CANDIDATE_STATUSES = frozenset({"APPROVED_BY_HUMAN"})
       → 에러 메시지 정정 (line 117, 121~124)

C3-03: STEP4E_UP / STEP4E_DOWN SQL 작성
       → docs/sql/YYYYMMDD_WP_PERSISTENCE_02A_STEP4E_UP.sql
       → docs/sql/YYYYMMDD_WP_PERSISTENCE_02A_STEP4E_DOWN.sql

C3-04: 승인 관리 경로 구현
       → evidence_field_candidate 승인: review_bridge.py 재사용 + status UPDATE 원자 결합
       → review_authority 개별 reviewer 검증 추가
       → runtime_evidence_field.status UPDATE: STEP4E 내 원자 처리 (별도 API 불필요)

C3-04B: document_confirm_svc.py 에러 메시지 정합화
       현재 오류 (line 393): "confirm blocked until LEG gate passes"
         → LEG gate라는 표현이 법적 의무 판단으로 오인될 수 있음
       정합화 후: "confirm blocked until evidence approval gate passes"
         (Evidence Candidate 승인 = 법적 판단 아님. 증빙 사용 승인)

C3-05: 테스트 작성 (test_document_confirm_svc.py 확장)
       → R2-T01_APPROVED_BY_HUMAN_passes
       → R2-T02_CANDIDATE_still_blocked
       → R1-02_APPROVED_BY_HUMAN_passes (D1 Migration 후)
```

### §7-2. C3 테스트 기준

| 테스트 ID | 조건 | 기대 결과 |
|-----------|------|-----------|
| C3-T01 | runtime_evidence_field.status=APPROVED_BY_HUMAN | 봉인 통과 |
| C3-T02 | runtime_evidence_field.status=CANDIDATE | 422 차단 |
| C3-T03 | evidence_field_candidate.status=APPROVED_BY_HUMAN (D1 후) | 봉인 통과 |
| C3-T04 | evidence_field_candidate.status=CANDIDATE | 422 차단 |
| C3-T05 | STEP4E_UP 실행 후 schema.status=APPROVED_FOR_RUNTIME_USE | 승격 성공 |
| C3-T06 | STEP4E_DOWN 실행 후 runtime_form_schema·runtime_field·runtime_evidence_field 복원 | 롤백 성공 |
| C3-T07 | STEP4E_DOWN 후 evidence_field_candidate.status 변경 없음 | 독립 결정 보존 |
| C3-T07B | STEP4E_DOWN 후 runtime_field.required_status = CANDIDATE_ONLY 복원 | 필드 상태 복원 |
| C3-T08 | evidence_field_candidate 승인 시 runtime_review_decision INSERT + status UPDATE 동시 | 원자성 |
| C3-T09 | reviewer_id = 권한 없는 사용자 → 403 | AND 조건 검증 |
| C3-T09B | reviewer_id = UUID 일치이나 역할 불일치 → 403 | AND 조건 (OR 불허) |
| C3-T10 | 에러 메시지에 "LEG gate" 미포함 | LEG 혼동 방지 |
| C3-T11 | 동일 evidence_field_candidate 중복 APPROVE → 409 | 중복 차단 |
| C3-T12 | APPROVED_BY_HUMAN 상태에서 재승인 → 409 | 부정 전이 차단 |
| C3-T13 | review_reason 빈 문자열로 승인 요청 → 400 | 필수 사유 강제 |
| C3-T14 | STEP4E_DOWN 시 runtime_document_data 1건 존재 → ABORT | 롤백 차단 B1 |
| C3-T15 | 롤백 ABORT 시 별도 트랜잭션으로 실패 Audit INSERT 성공 | 실패 감사 별도 TX |
| C3-T16 | STEP4E_DOWN 성공 후 성공 Audit = 동일 TX 커밋 확인 | 성공 감사 동일 TX |
| C3-T17 | STEP4E_DOWN ABORT 후 상태 변경 없음 + 실패 Audit만 존재 | 부분 복원 방지 |

---

## §7-3. C3 구현 승인 패킷

**C3 실행 승인 ≠ 이 패킷 제출. 패킷은 설계·범위 확인용.**

### 파일별 변경 예상 범위

| 파일 | 변경 유형 | C3 단계 |
|------|-----------|---------|
| `supabase/migrations/YYYYMMDD_evidence_field_candidate_d1.sql` | 신규 Migration | C3-01 |
| `services/document_confirm_svc.py` | 상태값 2행 + 에러 메시지 정정 | C3-02, C3-04B |
| `docs/sql/YYYYMMDD_WP_PERSISTENCE_02A_STEP4E_UP.sql` | 신규 SQL | C3-03 |
| `docs/sql/YYYYMMDD_WP_PERSISTENCE_02A_STEP4E_DOWN.sql` | 신규 SQL | C3-03 |
| `routers/review_bridge.py` 또는 신규 `routers/evidence_review.py` | 권한 검증 강화 + 원자 처리 | C3-04 |
| `tests/test_document_confirm_svc.py` | 테스트 C3-T01~T15 추가 | C3-05 |

### DB Migration 및 운영 적용 순서

```
[M1] C3-01 Migration 작성 → 로컬 검증
[M2] Owner 실행 승인 → 운영 DB 적용
     (evidence_field_candidate CHECK 확장)
[M3] C3-02/04/04B 코드 변경 → PR 작성
[M4] C3-05 테스트 통과 → PR 병합 승인
[M5] C3-03 STEP4E SQL 작성 → 문서 보관
     (실행은 G4 승격 Owner 결정 시)
[M6] G4 승격: Owner가 C3-03 SQL 실행
[M7] G5 고객 공개: factory_scope_verified + company_form_mapping 별도 Gate
```

### 기존 LEG 판단 및 고객 Gate 불변 확인

| 항목 | 확인 |
|------|------|
| LEG 의무 판단 | 변경 없음 — DOC가 접근 불가 |
| DOC-CON-048 LEG 연결 | CONTRACT_UNVERIFIED 유지 |
| G3 attached_documents 의미 | 별도 Owner Gate 유지 |
| G5 고객 공개 | factory_scope_verified + company_form_mapping ≥ 1 별도 Gate |
| WO-024 구현 | 보존 (FK 연결 로직 변경 없음) |

---

## §8. 불변 사항

- WO-024 구현 (tai-api PR#709 cb66e5c3 / tai-admin PR#176 91e26952) 보존
  - R2 FK 연결 로직 (`_resolve_evidence_connections`) 올바름
  - 상태 allowlist 값만 오류 → C3-02에서 최소 수정
- Packet A UUID 정정본 유효 (runtime_form_schema.id=4e07df2e)
- G3 Field 4개 REQUIRED_BY_HUMAN HOLD 유지
- DOC-CON-048 LEG 연결 CONTRACT_UNVERIFIED 유지
- evidence 파일 SHA256·FK·권한 검증 로직 유지

---

## §9. Owner 후속 승인 항목

| 항목 | 내용 | 현재 상태 |
|------|------|-----------|
| C3-01-EXEC | D1 Migration DB 실행 | 별도 승인 필요 |
| C3-02-EXEC | document_confirm_svc.py PR 병합 | 별도 승인 필요 |
| C3-03-EXEC | STEP4E SQL Owner 실행 (DOC-CON-048) | 별도 승인 필요 |
| C3-04-EXEC | 승인 관리 경로: review_bridge 재사용 + reviewer 검증 보완 + status UPDATE 원자 결합 | 별도 승인 필요 |
| C3-04B-EXEC | 에러 메시지 정합화 (LEG gate → evidence approval gate) | 별도 승인 필요 |
| WO-026-PKT-A | Packet A SQL Owner 실행 | 별도 승인 필요 (G3 해소) |
| G4-EXEC | STEP4E 실행 승인 | C3 전체 완료 후 |
| G5-EXEC | 고객 공개 승인 | G4 + factory_scope_verified + LEG 연결 후 |

---

## §10. 요약 상태

```
WO-027-C2-FINAL
  OWNER_APPROVAL = D1_CONDITIONAL (2026-10-26)
  GPT_IV_R1      = CONDITIONAL_HOLD → C2 정정 후 RESUBMIT
  GPT_IV_R2      = PARTIAL_PASS → rollback+권한 보완 후 RESUBMIT
  GPT_IV_R3      = PARTIAL_PASS → runtime_field 롤백·권한 AND 조건·rollback차단6개 보완
  GPT_IV_R4      = CONDITIONAL_PASS (2026-10-26) — C2 설계 루프 종료
  CODE_CHANGE    = 0
  DB_WRITE       = 0
  G3             = HOLD
  G4             = BLOCKED
  CUSTOMER_USE   = BLOCKED

식별자 (DOC-CON-048):
  runtime_form_schema.id      = 4e07df2e-904a-4fe6-ad18-cecc0f5e57f3
  document_schema_candidate   = 2f41ab16-4748-4bf7-84a3-55a20f74efda
  document_forms.id           = a1d2d277-8552-4370-bb1d-ce6321c7a685
  runtime_evidence_field.id   = 948088d5-627f-4825-a906-2b86a3d27de5
  evidence_field_candidate.id = 5e5687b3-e62f-480c-ad75-1efc41706e3b
```

---

## §11. WO-TAI-DOC260-G3-027-C2-FINAL-CLOSE 제출 결과

```
WO = WO-TAI-DOC260-G3-027-C2-FINAL-CLOSE

C2-A_AUTHORITY_CONTRACT     = PASS
  - AND 조건 확정 (OR 금지)
  - 역할 서버 검증 출처 명시
  - review_reason 필수화 (API 레벨)
  - 중복·부정 전이 차단 계약

C2-B_STEP4E_CONTRACT        = PASS
  - runtime_field status+required_status 롤백 포함
  - Before Snapshot 범위 확장 (evidence_candidate_decision_ref 추가)
  - 롤백 차단 기준 6개 확정
  - 롤백 성공·실패 감사 기록 계약
  - STEP4D_DOWN 재사용 불가 사유 및 STEP4E_DOWN 신규 설계

C2-C_LEG_BOUNDARY           = PASS
  - LEG/DOC 책임경계 유지
  - attached_documents 의미 확정 = 별도 Owner Gate
  - STEP4E 설계 완료 ≠ G4 승격 ≠ 고객 공개 분리 명시

C2_DELTA_COMPLETE           = YES (C2-A/B/C 보완 완료)
C2_FINAL_DOCUMENT           = WO-027-EVIDENCE-CONTRACT-C2-FINAL.md
DOCUMENT_LOCATION           = docs/document-engine/WO-027-EVIDENCE-CONTRACT-C2-FINAL.md
DOCUMENT_SHA256             = SELF_REF_NOT_STABLE (SHA 필드 자체가 문서 포함시 변동 — 제출 시 별도 계산)
DOCUMENT_GIT_STATUS         = LOCAL (tai-api main 미병합 — C3 승인 전 설계 문서)

C3_01_05_IMPLEMENTATION_PACKET = §7-3 참조 (파일별 범위·Migration 순서·테스트 계획)

REMAINING_OWNER_DECISIONS =
  C3 전체 구현 승인 (C3-01~05)
  G4 STEP4E 실행 승인 (C3-03 SQL)
  G5 고객 공개 승인 (factory_scope_verified + G5)
  attached_documents 의미 확정 (별도 Owner Gate)

G3             = HOLD
G4             = BLOCKED
CUSTOMER_USE   = BLOCKED

CODE_CHANGE    = 0
DB_WRITE       = 0
MIGRATION_APPLY= 0
PR_MERGE       = 0
PROD_DEPLOY    = 0

GPT_IV_R4      = CONDITIONAL_PASS (2026-10-26)
C2_STATUS      = CLOSED_FINAL (설계 루프 종료)
C3_OWNER_APPROVAL = PENDING
```
