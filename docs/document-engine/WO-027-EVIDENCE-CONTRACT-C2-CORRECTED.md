# WO-TAI-DOC260-G3-EVIDENCE-CONTRACT-027 — C2 정정 계약

**STATUS**: GPT_IV_RESUBMIT_PENDING  
**CODE_CHANGE**: 0  
**DB_WRITE**: 0  
**작성일**: 2026-10-26  

---

## 정정 배경

GPT IV CONDITIONAL_HOLD 판정 후 C2 계약 정정. 지적 사항:

1. STEP4A_VERIFY.sql:46은 `runtime_field`(rf) 기준 — `runtime_evidence_field` 직접 근거 아님
2. `catalog_aggregator.py` WEB_EDIT = APPROVED_FOR_RUNTIME_USE **AND** factory_scope_verified
3. G4 승격 ≠ 고객 노출
4. C2 A안 전체 일관된 Evidence 승인 계약 확정 선행 필요

---

## C1-A 재확인 — 상태값 직접 근거 (정정)

### runtime_evidence_field.status

| 항목 | 값 |
|------|-----|
| DB CHECK 허용값 | CANDIDATE / NEEDS_HUMAN_REVIEW / APPROVED_BY_HUMAN / REJECTED_BY_HUMAN |
| 코드 요구값 (`_ALLOWED_EVIDENCE_FIELD_STATUSES`) | APPROVED_FOR_RUNTIME_USE |
| 불일치 | **APPROVED_FOR_RUNTIME_USE는 DB CHECK에 없음** |
| 터미널 승인 상태 (DB 직접 근거) | **APPROVED_BY_HUMAN** |
| UPDATE 경로 | 코드베이스 전체 없음 — 생성 시 CANDIDATE 고정 |
| 현재 DB (GPT IV 확인) | 202행 전부 CANDIDATE |

근거 파일: `services/document_confirm_svc.py:117–124`

> **중요 보정**: 이전 C2에서 STEP4A_VERIFY.sql:46을 근거로 제시한 것은 오류.  
> line 46은 `runtime_field rf` 기준 bad_status_cnt 검사이며 `runtime_evidence_field`와 무관.  
> 직접 근거 = DB CHECK 제약조건 (APPROVED_BY_HUMAN이 허용 목록에 포함됨).

### evidence_field_candidate.status

| 항목 | 값 |
|------|-----|
| DB CHECK 허용값 | CANDIDATE / NEEDS_HUMAN_REVIEW / AMBIGUOUS / UNRESOLVED |
| 코드 요구값 (`_ALLOWED_EVIDENCE_CANDIDATE_STATUSES`) | APPROVED_FOR_RUNTIME_USE |
| 불일치 | **APPROVED_FOR_RUNTIME_USE는 DB CHECK에 없음** |
| 승인 상태 존재 여부 | **DB에 승인 상태 자체 없음** |
| UPDATE 경로 | 코드베이스 전체 없음 |

근거 파일: `services/document_confirm_svc.py:386–394`

---

## C2 정정 계약 — 일관된 Evidence 승인 경로

### Gate 분리 명확화 (GPT IV 지시 반영)

```
G4 승격 (schema APPROVED_FOR_RUNTIME_USE)
  └─ catalog_resolver: availability = READY_FOR_EDIT
  └─ catalog_aggregator WEB_EDIT:
       APPROVED_FOR_RUNTIME_USE AND factory_scope_verified → READY
       APPROVED_FOR_RUNTIME_USE NOT factory_scope_verified → BLOCKED
       DOC-CON-048 company_form_mapping = 0 → WEB_EDIT = BLOCKED (G4 후에도 즉각 노출 없음)

고객 노출 Gate = G4 승격 + factory_scope_verified + company_form_mapping ≥ 1 (별도)
```

### R2-01 정정 계약 (runtime_evidence_field.status)

**올바른 터미널 승인값**: `APPROVED_BY_HUMAN`

**필요 변경 사항**:
1. **코드 수정** (A안 세부): `_ALLOWED_EVIDENCE_FIELD_STATUSES = frozenset({"APPROVED_BY_HUMAN"})`
2. **DB UPDATE**: 현재 202행 CANDIDATE → 적격 행만 APPROVED_BY_HUMAN으로 UPDATE (Owner 승인 후)

**현재 코드 → 정정 대상**:
```python
# services/document_confirm_svc.py:57–61
# 수정 전
_SCHEMA_STATUS_APPROVED = "APPROVED_FOR_RUNTIME_USE"
_ALLOWED_EVIDENCE_CANDIDATE_STATUSES = frozenset({_SCHEMA_STATUS_APPROVED})
_ALLOWED_EVIDENCE_FIELD_STATUSES = frozenset({_SCHEMA_STATUS_APPROVED})

# 수정 후 (Owner 승인 조건)
_SCHEMA_STATUS_APPROVED = "APPROVED_FOR_RUNTIME_USE"          # schema 전용 — 유지
_ALLOWED_EVIDENCE_FIELD_STATUSES = frozenset({"APPROVED_BY_HUMAN"})  # R2-01 정정
_ALLOWED_EVIDENCE_CANDIDATE_STATUSES = ???                    # R1-02 — Owner 결정 필요
```

> **주의**: 코드 수정만으로는 부족. DB의 202행이 CANDIDATE이므로 적격 행 식별 + UPDATE 필요.  
> UPDATE 경로 설계(누가/언제/어떤 조건으로 APPROVED_BY_HUMAN 전이하는지)가 없으면 코드 수정 후에도 영구 차단.

### R1-02 정정 계약 (evidence_field_candidate.status)

**현황**: DB CHECK에 승인 상태 없음 → 어떤 값도 `_ALLOWED_EVIDENCE_CANDIDATE_STATUSES` 통과 불가

**설계 선택지** (Owner 결정 필요):

| 선택지 | 내용 | 위험 |
|--------|------|------|
| **D1** | evidence_field_candidate.status CHECK에 APPROVED_BY_HUMAN / REJECTED_BY_HUMAN 추가 + admin 승인 경로 설계 | DB 스키마 변경 / Migration 필요 |
| **D2** | R1-02 검사 완화 — evidence_field_candidate.status가 NOT REJECTED 이면 허용 | 법적 미검증 상태로 봉인 허용 → 거버넌스 위험 |
| **D3** | evidence_field_candidate.status를 LEGAL_REQUIREDNESS로 분리 (별도 컬럼) | 스키마 구조 변경 |

**권고**: D1. 기존 `runtime_field.required_status` 패턴(CANDIDATE/APPROVED_FOR_RUNTIME_USE/REQUIRED_BY_HUMAN/CANDIDATE_ONLY) 참조해 evidence 전용 승인 컬럼 추가.

### STEP4D 확장 계약 (evidence 포함 스키마 승격)

DOC-CON-048(evidence_count=4)에는 STEP4D_UP(GEN-INSPECT-RESULT-001 전용, evidence_count=0 PRECONDITION) 직접 재사용 불가.

**필요 설계 요소** (Owner 결정 필요):

```
STEP4E_UP (evidence 포함 스키마 승격) 설계 요구사항:
  PRECONDITION: evidence_count >= 1
  순서:
    1. runtime_evidence_field.status → APPROVED_BY_HUMAN (202행 중 대상 식별)
    2. evidence_field_candidate.status → APPROVED_BY_HUMAN (D1 선택 시)
    3. runtime_form_schema.status → APPROVED_FOR_RUNTIME_USE (2단계: CANDIDATE→APPROVED_BY_HUMAN→APPROVED_FOR_RUNTIME_USE)
  
  Audit 필수 컬럼 (STEP4D_UP 참조):
    source_table, source_id, action, schema_version,
    before_state, after_state, reviewer_id, review_comment,
    rollback_snapshot, rollback_available
  
  주의: rollback_available=true 없으면 STEP4D_DOWN 롤백 불가
```

---

## Owner 결정 필요 항목 (갱신)

| 번호 | 항목 | 판단 기준 |
|------|------|-----------|
| [1] | evidence_field_candidate 승인 경로: D1/D2/D3 선택 | DB 스키마 변경 범위 |
| [2] | runtime_evidence_field.status UPDATE 경로 설계 | 관리자 API vs SQL 직접 실행 |
| [3] | STEP4D 확장 또는 STEP4E 신규 설계 | evidence 포함 서식 승격 흐름 |
| [4] | A안 구현 WO 발행 (코드 수정 + DB UPDATE) | [1][2][3] 결정 후 |

---

## 분리된 Gate 요약 (정정본)

```
[G3] Field 승인 Gate
  runtime_field.required_status != CANDIDATE_ONLY 전 필드 (R1-03-B)
  → Packet A SQL 실행으로 해소

[G-EV1] runtime_evidence_field 승인 Gate
  runtime_evidence_field.status = APPROVED_BY_HUMAN (R2-01 정정)
  → UPDATE 경로 설계 후 DB 업데이트 필요 (Owner 결정 [2])

[G-EV2] evidence_field_candidate 승인 Gate
  evidence_field_candidate.status = APPROVED_BY_HUMAN (R1-02 정정)
  → DB 스키마 변경 + UPDATE 경로 (Owner 결정 [1])

[G4] 서식 승격 Gate
  runtime_form_schema.status = APPROVED_FOR_RUNTIME_USE (R1-03-A)
  → STEP4D 확장 또는 STEP4E 설계 후 실행 (Owner 결정 [3])

[G5] 고객 노출 Gate (G4와 분리)
  factory_scope_verified = true
  company_form_mapping >= 1
  → DOC-CON-048는 현재 company_form_mapping=0 → BLOCKED 유지
```

---

## 불변 사항

- WO-024 구현 (PR#709/176) 보존 — R2 FK 연결 로직은 올바름, 상태 allowlist 값만 오류
- Packet A UUID 정정본 (runtime_form_schema.id=4e07df2e) 유효
- G3 Field 4개 REQUIRED_BY_HUMAN HOLD 유지
- CODE_CHANGE=0 / DB_WRITE=0 (이 문서는 설계 계약만)
