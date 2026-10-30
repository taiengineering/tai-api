---
title: DOC260 DATE / timestamp_auto — FE·DB 연결 Gate 검증 보고서 (v1)
status: GATE_PASS_BE_HOLD
wo: WO-DOC260-MAINLINE-DATE-CONTRACT-GATE-002
collected_by: Claude Code (DESIGN role)
collected_date: 2026-10-30
revised_date: 2026-10-30
revision: R2
review_required: GPT_DATE_BE_CONTRACT_IV_R2
---

# DATE_TIMESTAMP_AUTO_CONNECTION_GATE — WO-002 Gate 결과

**선행 WO:** WO-DOC260-MAINLINE-DATE-SUPPORT-001 (PR #181 Draft HOLD)  
**다음 단계:** WO-DOC260-MAINLINE-DATE-BE-CONTRACT-003

---

## 1. Gate 범위

이 문서는 DOC260 서식의 `DATE` / `timestamp_auto` 증적 연결에 대해 FE와 DB 수준에서 무엇이 검증됐고, 무엇이 차단되어 있는지를 기록한다.

---

## 2. DB 연결 구조 — GATE_PASS

| 검증 항목 | 결과 | 비고 |
|-----------|------|------|
| DATE / timestamp_auto input_type 증적 수 | 104건 | 전체 운영 카탈로그 기준 |
| 연결 서식 수 | 97종 | 260종 중 |
| Runtime 필드 타입 `date` 연결 | 104/104 | FK 정합 PASS |
| Runtime 필드 정확히 1건 연결 | 104/104 | 중복·누락 0건 |
| APPROVED_BY_HUMAN 증적 | 0건 | 전부 CANDIDATE |
| Evidence Candidate 승인 완료 | 0건 | LEG Gate 미통과 |

**판정:** DB FK 구조는 올바르다. 그러나 104건 전부 `CANDIDATE` 상태이며 LEG Gate를 통과하지 않았다.

---

## 3. FE 연결 상태 — GATE_PASS (차단 포함)

### PR #181 검증 항목

| 항목 | 판정 |
|------|------|
| `date` input_type FE 렌더링 | PASS — VTextField type="date" |
| CANDIDATE 증적 차단 (CANDIDATE_ONLY → CHILD_STATUS_DRIFT) | PASS |
| evidence_fields 존재 시 에디터 전체 차단 | PASS — EVIDENCE_CONTRACT_UNSUPPORTED |
| `timestamp_auto` FE 구현 | NOT_FOUND — codebase에 없음 |

### 에디터 활성화 조건 (현재)

```
isEditorReady = availability === 'READY_FOR_EDIT'
  && canCreate
  && activeSchemaStatus === 'APPROVED_FOR_RUNTIME_USE'
  && unsupportedReason === null
```

`evidence_fields.length > 0` → `unsupportedReason = 'EVIDENCE_CONTRACT_UNSUPPORTED'` → 에디터 비활성.

97종 DATE 증적 포함 서식은 현재 **에디터 접근 전 차단** 상태.

---

## 4. BE 확정 경로 — GATE_FAIL (구현 없음)

### 현재 `document_confirm_svc.py` 허용 목록

```python
_ALLOWED_EVIDENCE_INPUT_TYPES = frozenset({"file"})
_ALLOWED_EVIDENCE_FAMILIES    = frozenset({"ATTACHMENT"})
_ALLOWED_UPLOAD_TYPES         = frozenset({"attachment"})
```

### DATE 증적 통과 실패 경로

1. `evidence_family = "DATE"` → `"DATE" not in {"ATTACHMENT"}` → ConfirmError(422) 발생 지점: `_resolve_evidence_connections()` line ~127
2. `input_type = "date"` → `"date" not in {"file"}` → ConfirmError(422) 발생 지점: line ~399
3. `upload_type = "timestamp_auto"` → `"timestamp_auto" not in {"attachment"}` → ConfirmError(422) 발생 지점: line ~135

> **R2 보정:** 운영 DB에서 DATE 증적의 `upload_type = "timestamp_auto"` 실측 확인 (P0 evidence matrix). 이전 기술의 "upload_type = NULL" 가정은 부정확했다.

DATE 증적이 하나라도 포함된 서식의 확정 호출은 **전부 422로 거부**된다.

---

## 5. `timestamp_auto` 의미 계약 — DESIGN_REQUIRED

### 관찰 사실

- `timestamp_auto` 식별자가 현재 FE/BE codebase 어디에도 존재하지 않는다.
- `evidence_family` 컬럼에 실제 저장된 값이 `"DATE"` 인지 `"timestamp_auto"` 인지 운영 DB에서 확인 필요.
- GPT IV 독립검증 판정: DATE 증적 104개에 서버 현재 시각을 자동 주입하는 방식은 허용 불가.

### timestamp_auto 와 DATE 의 관계 (설계 후보)

| 개념 | 정의 | 현재 상태 |
|------|------|-----------|
| `DATE` | 사용자가 직접 입력하는 업무 날짜 | DB에 104건 CANDIDATE |
| `timestamp_auto` | 서버가 자동 생성하는 타임스탬프 | 구현체 없음, 별도 계약 필요 |
| `confirmed_at` | 문서 확정 시 서버 기록 (clock_timestamp) | 기존 인프라 구현 완료 |

**결론:** `timestamp_auto` 는 현재 104개 DATE 증적에 적용해서는 안 된다. `confirmed_at` 이 문서 수준 시스템 타임스탬프를 이미 담당한다.

---

## 6. Gate 최종 판정

| Gate | 판정 | 비고 |
|------|------|------|
| DB FK 연결 구조 | GATE_PASS | 104건 정합 |
| FE date 렌더링 | GATE_PASS | PR #181 |
| FE CANDIDATE 차단 | GATE_PASS | EVIDENCE_CONTRACT_UNSUPPORTED |
| BE DATE 확정 경로 | GATE_FAIL | _ALLOWED_EVIDENCE_FAMILIES 미포함 |
| timestamp_auto 계약 | DESIGN_REQUIRED | 별도 Gate |

**전체:** `SOURCE_AND_DATA_PASS / IMPLEMENTATION_HOLD`

PR #181 HOLD 유지. BE 계약 문서(WO-003) 완료 후 구현 Gate 진입.

---

## 7. 다음 단계

WO-DOC260-MAINLINE-DATE-BE-CONTRACT-003 → `DATE_TIMESTAMP_AUTO_BE_CONTRACT_v1.md` 작성 → GPT_DATE_BE_CONTRACT_IV → 구현 WO 발행.

---

## 8. GPT_DATE_BE_CONTRACT_IV 수신 결과 (R1)

GPT IV 판정: **CONDITIONAL_PASS**

| 보정 항목 | 내용 | 반영 위치 |
|-----------|------|-----------|
| R1-01 | 104건 BUSINESS_EVENT_DATE 확정 취소 → 잠정 분류로 재표기. DATA_SEMANTIC_GAP 13건, law_ref NULL 15건 명시. | BE_CONTRACT §2.2 |
| R1-02 | DATE manifest에 field_id / value_source / value_semantic_class 추가 | BE_CONTRACT §3.7 |
| R1-03 | 확정 트랜잭션 내 manifest 생성 위치 Step 명시. clock_timestamp() 1회 원칙 유지 확인. | BE_CONTRACT §3.8 (신규) |
| R1-04 | FE DATE family 인식과 BE DATE 봉인 지원이 별도 Gate임을 명시 | BE_CONTRACT §4.3 |

검증 한계: GPT IV는 본 문서를 main GitHub에서 직접 조회하지 못했음 (untracked). R1 보정 후 Draft PR 제출로 원문 독립검증 가능 상태 확보.
