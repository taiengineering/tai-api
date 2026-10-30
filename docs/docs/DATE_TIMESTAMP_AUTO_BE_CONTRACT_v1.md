---
title: DOC260 DATE / timestamp_auto — BE 확정 경로 계약 (v1)
status: DESIGN_DRAFT_R1
wo: WO-DOC260-MAINLINE-DATE-BE-CONTRACT-003
collected_by: Claude Code (DESIGN role)
collected_date: 2026-10-30
revised_date: 2026-10-30
revision: R1
review_required: GPT_DATE_BE_CONTRACT_IV_R1
---

# DATE_TIMESTAMP_AUTO_BE_CONTRACT — WO-003 설계 계약 (R1)

**선행 Gate:** `DATE_TIMESTAMP_AUTO_CONNECTION_GATE_v1.md` — SOURCE_AND_DATA_PASS  
**CODE_CHANGE:** 0 · **DB_CHANGE:** 0 · **MERGE:** NO · **DEPLOY:** NO  
**PR #181:** HOLD 유지

> **R1 보정 이력 (2026-10-30):** GPT_DATE_BE_CONTRACT_IV CONDITIONAL_PASS 수신.  
> R1-01: WP-A 분류를 잠정 분류로 재표기 + DATA_SEMANTIC_GAP 13건 / law_ref NULL 15건 명시.  
> R1-02: DATE manifest에 `field_id`, `value_source`, `value_semantic_class` 추가.  
> R1-03: 확정 트랜잭션 내 DATE manifest 생성 위치를 Step으로 명시.  
> R1-04: FE DATE family 인식과 BE DATE 봉인 지원이 별도 Gate임을 명시.

---

## 1. 설계 범위

이 문서는 `document_confirm_svc.py` 를 중심으로 한 Document Engine 확정 경로에서 `DATE` 증적 family를 안전하게 처리하기 위한 최소 백엔드 계약을 정의한다.

**포함:**
- DATE 증적 의미 분류 (WP-A)
- BE 확정 경로 최소 계약 (WP-B)
- FE PR #181 정합 확인 및 보정 명세 (WP-C)
- 활성화 Gate 분리 (WP-D)
- 최소 테스트 계약 (§6)

**포함하지 않음:**
- 코드 변경
- 운영 DB 변경
- Evidence Candidate 승인
- LEG Gate
- `timestamp_auto` 별도 family 구현
- 전체 260종 재검증

---

## 2. WP-A — DATE 증적 의미 계약 분류

### 2.1 분류 기준

| 분류 코드 | 정의 | 서버 처리 방향 |
|-----------|------|----------------|
| BUSINESS_EVENT_DATE | 실제 사건(점검·사고·선임·회의 등) 발생 날짜. 사용자가 직접 입력. | 그대로 보존. 서버 시각 주입 금지. |
| DATA_SEMANTIC_GAP | 단일 필드에 날짜 이외의 정보(장소 등)가 혼합되어 있음. | 별도 필드 분리 여부 Owner 결정 필요. 현재 그대로 보존. |
| SEMANTIC_UNRESOLVED | 원천 서식만으로 의미를 확정할 수 없음. | LEG / Owner 결정 전 봉인 차단 유지. |

**적용 원칙:** 업무 날짜와 서버 증적 시각(`confirmed_at`)은 독립적이며 혼용 불가.

### 2.2 필드명 패턴별 잠정 분류 (R1 보정)

> **주의:** 이 분류는 필드명 패턴 기반 **잠정 분류**다. 원천 서식 및 LEG 확인 없이 법적 의미를 확정하지 않는다.  
> 104건을 전부 BUSINESS_EVENT_DATE로 확정하지 않는다.

| 필드명 패턴 | 예시 | 잠정 분류 | 비고 |
|-------------|------|-----------|------|
| `*_datetime` (단순) | `inspection_datetime`, `incident_datetime` | BUSINESS_EVENT_DATE (잠정) | 사건 발생 일시 |
| `*_date` (사건 기반) | `inspection_date`, `appointment_date`, `occurrence_date` | BUSINESS_EVENT_DATE (잠정) | 사건 날짜 |
| `*_datetime_location`, `*_datetime_*` (복합) | `meeting_datetime_location`, `incident_datetime_location` | DATA_SEMANTIC_GAP | 날짜 + 장소·담당자 등 혼합 |
| `*_date_agency`, `approval_date_*` | `approval_date_agency` | DATA_SEMANTIC_GAP | 날짜 + 기관 혼합 |
| `submission_date`, `*_submission_*` | `submission_date` | SEMANTIC_UNRESOLVED | 사용자 기재 날짜 vs. 시스템 제출 시각 구분 필요 |
| `*_start_date`, `*_end_date` | `contract_start_date` | BUSINESS_EVENT_DATE (잠정) | 계약·기간 범위 날짜 |

#### 2.2.1 GPT IV 독립검증에서 확인된 수량 (R1)

GPT_DATE_BE_CONTRACT_IV에서 운영 DB 직접 조회를 통해 다음 수치를 보고했다:

| 항목 | 수량 | 처리 방향 |
|------|------|-----------|
| DATA_SEMANTIC_GAP 해당 복합 필드 | 13건 | 현재는 BUSINESS_EVENT_DATE와 동일하게 처리. 별도 분리 WO에서 해결. |
| source_trace.law_ref = NULL | 15건 | 비법정 확정 불가. 원천 검증 추가 필요. 구현 WO 선행 조건. |
| BUSINESS_EVENT_DATE 잠정 (나머지) | 76건 이하 | 잠정 분류. LEG Gate 통과 전 봉인 불가. |

이 수치는 GPT IV 독립검증 결과이며 Claude Code가 직접 확인한 값이 아니다.

### 2.3 분류 원칙 (R1 보정)

1. 104건을 일괄로 BUSINESS_EVENT_DATE로 확정하지 않는다. 패턴 기반 잠정 분류를 유지한다.
2. 서버 현재 시각을 업무 날짜 필드에 자동 주입하지 않는다.
3. `confirmed_at` (문서 확정 시각)은 업무 날짜 필드와 독립적으로 기록된다.
4. DATA_SEMANTIC_GAP 필드(13건 포함)는 현 단계에서 날짜 값 보존으로 처리하며, 별도 분리 WO에서 해결한다.
5. SEMANTIC_UNRESOLVED 필드는 LEG / Owner 결정 전까지 Evidence 봉인 차단을 유지한다.
6. source_trace.law_ref = NULL 15건은 구현 WO 진입 전 원천 확인이 필요하다.

### 2.4 `timestamp_auto` 설계 범위 제한

- `timestamp_auto` 는 이 WO에서 구현하지 않는다.
- 104개 DATE 증적 중 `timestamp_auto` 가 적합한 필드가 존재하는 경우, 별도 Evidence Family 계약 WO에서 설계한다.
- 현재 `evidence_family` DB 컬럼값이 `"DATE"` 인지 `"timestamp_auto"` 인지 운영 DB에서 2차 검증이 필요하다 (구현 WO 선행 조건).

---

## 3. WP-B — BE 확정 경로 최소 계약

### 3.1 변경 대상 파일

| 파일 | 변경 유형 | 변경 범위 |
|------|-----------|-----------|
| `services/document_confirm_svc.py` | 상수 추가 + 검증 분기 + manifest 생성 | 최소 수정 |
| `services/document_schema_renderer.py` | 매개변수 추가 (선택) | 필요 시만 |

### 3.2 상수 계약

```python
# 기존 (변경하지 않음)
_ALLOWED_EVIDENCE_CANDIDATE_STATUSES = frozenset({"APPROVED_FOR_RUNTIME_USE"})
_ALLOWED_EVIDENCE_FIELD_STATUSES     = frozenset({"APPROVED_FOR_RUNTIME_USE"})

# 변경: DATE family 추가
_ALLOWED_EVIDENCE_FAMILIES    = frozenset({"ATTACHMENT", "DATE"})
_ALLOWED_EVIDENCE_INPUT_TYPES = frozenset({"file", "date"})

# 신규: DATE family 식별자
_DATE_EVIDENCE_FAMILIES = frozenset({"DATE"})
_FILE_EVIDENCE_FAMILIES = frozenset({"ATTACHMENT"})

# 기존 유지 (ATTACHMENT 전용)
_ALLOWED_UPLOAD_TYPES = frozenset({"attachment"})
```

### 3.3 `_resolve_evidence_connections()` 수정 계약

기존 `upload_type` 검증 블록을 family 분기로 교체한다.

```python
# 변경 전 (ATTACHMENT 전용)
ev_upload_type = str(ev.get("upload_type") or "")
if ev_upload_type not in _ALLOWED_UPLOAD_TYPES:
    raise ConfirmError(422, ...)

# 변경 후 (분기 처리)
if ev_family in _FILE_EVIDENCE_FAMILIES:
    ev_upload_type = str(ev.get("upload_type") or "")
    if ev_upload_type not in _ALLOWED_UPLOAD_TYPES:
        raise ConfirmError(
            422,
            f"evidence field {ev_id!r}: upload_type={ev_upload_type!r} not supported "
            f"(allowed: {sorted(_ALLOWED_UPLOAD_TYPES)})"
        )
elif ev_family in _DATE_EVIDENCE_FAMILIES:
    pass  # DATE 증적은 upload_type 없음 — file upload 경로 없음
```

`_resolve_evidence_connections()` 반환 구조에 `ev_family` 추가:

```python
connections.append({
    "evidence_field":    ev,
    "runtime_field":     matched,
    "ev_candidate_status": str(efc.get("status") or "UNKNOWN"),
    "ev_family":         ev_family,   # 신규
})
```

### 3.4 확정 루프 수정 계약 (`confirm_document_atomic()`)

기존 단일 루프를 family별 분기로 교체한다.

```python
attachment_evidence_manifest: list = []
date_evidence_manifest: list = []

for ev_conn in ev_connections:
    ev_field         = ev_conn["evidence_field"]
    rf               = ev_conn["runtime_field"]
    ev_candidate_status = ev_conn["ev_candidate_status"]
    ev_family        = ev_conn["ev_family"]           # 신규 필드

    # R1-02: candidate 상태 — family 공통 (변경 없음)
    if ev_candidate_status not in _ALLOWED_EVIDENCE_CANDIDATE_STATUSES:
        raise ConfirmError(422, ...)

    field_id   = str(rf.get("id") or "")
    field_key  = str(rf.get("field_key") or "")
    input_type = str(rf.get("input_type") or "")

    # R1-03-C: input_type 허용 목록 (DATE 추가됨)
    if input_type not in _ALLOWED_EVIDENCE_INPUT_TYPES:
        raise ConfirmError(422, ...)

    if ev_family in _FILE_EVIDENCE_FAMILIES:
        # 기존 ATTACHMENT 경로 (변경 없음)
        snap = runtime_values.get(field_key)
        if snap is None:
            raise ConfirmError(422, ...)
        manifest_entry = verify_file_snapshot_for_evidence(
            snapshot=snap, document_id=..., field_id=field_id, field_key=field_key
        )
        manifest_entry["evidence_field_id"] = str(ev_field.get("id") or "")
        attachment_evidence_manifest.append(manifest_entry)

    elif ev_family in _DATE_EVIDENCE_FAMILIES:
        # 신규 DATE 경로
        date_value = runtime_values.get(field_key)
        _verify_date_evidence_value(
            date_value=date_value,
            ev_field_id=str(ev_field.get("id") or ""),
            field_key=field_key,
        )
        date_manifest_entry = {
            "evidence_field_id": str(ev_field.get("id") or ""),
            "field_key":         field_key,
            "date_value":        str(date_value),
            "evidence_family":   "DATE",
            "input_type":        "date",
        }
        date_evidence_manifest.append(date_manifest_entry)
```

### 3.5 `_verify_date_evidence_value()` 계약 (신규 함수)

```python
import re

_ISO_DATE_RE = re.compile(r'^\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])$')

def _verify_date_evidence_value(
    *,
    date_value: Any,
    ev_field_id: str,
    field_key: str,
) -> None:
    """DATE 증적 필드 값 검증. FAIL-CLOSED."""
    if date_value is None:
        raise ConfirmError(
            422,
            f"evidence field {ev_field_id!r}: "
            f"date value missing in runtime_data_json[{field_key!r}]"
        )
    if not isinstance(date_value, str):
        raise ConfirmError(
            422,
            f"evidence field {ev_field_id!r}: "
            f"date value must be str, got {type(date_value).__name__!r}"
        )
    if not _ISO_DATE_RE.match(date_value):
        raise ConfirmError(
            422,
            f"evidence field {ev_field_id!r}: "
            f"date value {date_value!r} must be ISO format YYYY-MM-DD"
        )
```

### 3.6 evidence_manifest 병합 계약

`build_render_artifacts()` 호출 전에 두 manifest를 병합한다. 렌더러 시그니처는 변경하지 않는다.

```python
# 두 manifest 병합 (렌더러에 단일 리스트로 전달)
combined_evidence_manifest = attachment_evidence_manifest + date_evidence_manifest

artifacts = build_render_artifacts(
    ...
    attachment_evidence_manifest=combined_evidence_manifest,  # 기존 매개변수 재사용
)
```

**대안 (선택적):** 렌더러가 DATE manifest를 다르게 표시해야 한다면 별도 매개변수를 추가한다. 현재 단계에서는 병합이 더 단순하다.

### 3.7 DATE manifest 항목 형식 계약 (R1 보정)

```json
{
  "evidence_field_id": "<uuid-str>",
  "field_id": "<uuid-str>",
  "field_key": "inspection_datetime",
  "date_value": "2026-10-15",
  "value_source": "USER_INPUT",
  "value_semantic_class": "BUSINESS_EVENT_DATE",
  "evidence_family": "DATE",
  "input_type": "date"
}
```

**필드 정의:**

| 필드 | 타입 | 생성 주체 | 의미 |
|------|------|-----------|------|
| `evidence_field_id` | str (UUID) | DB (runtime_evidence_field.id) | 증적 필드 연결 ID |
| `field_id` | str (UUID) | DB (runtime_field.id) | 연결된 런타임 필드 ID |
| `field_key` | str | DB (runtime_field.field_key) | 런타임 값과의 연결 키 |
| `date_value` | str (ISO YYYY-MM-DD) | **사용자 입력** | 업무 날짜 원본값. 서버 시각 아님. |
| `value_source` | str | 시스템 생성 (항상 "USER_INPUT") | 값의 생성 원천. 서버 자동 생성과 구분. |
| `value_semantic_class` | str | 잠정 분류 기반 | `BUSINESS_EVENT_DATE` \| `DATA_SEMANTIC_GAP` \| `SEMANTIC_UNRESOLVED` |
| `evidence_family` | str | DB (runtime_evidence_field.evidence_family) | 항상 "DATE" |
| `input_type` | str | DB (runtime_field.input_type) | 항상 "date" |

**hash 안전성 확인:**

| 필드 | Python 타입 | JSON-native | datetime 포함 | Q4 FAIL-CLOSED 미발동 |
|------|-------------|-------------|---------------|----------------------|
| `evidence_field_id` | str | O | X | O |
| `field_id` | str | O | X | O |
| `field_key` | str | O | X | O |
| `date_value` | str | O | X | O — "2026-10-15" 는 str, datetime 객체가 아님 |
| `value_source` | str | O | X | O |
| `value_semantic_class` | str | O | X | O |
| `evidence_family` | str | O | X | O |
| `input_type` | str | O | X | O |

모든 필드가 Python str → `datetime` / `UUID` / `Decimal` 객체 불포함 → `compute_confirmed_snapshot_hash()` FAIL-CLOSED 미발동.

> **R1 추가:** str 타입이라는 사실만으로 법적 증적 무결성을 보증하지 않는다. `value_source = "USER_INPUT"` 와 `value_semantic_class` 필드는 날짜 값의 원천과 의미를 명시해 감사 추적에 사용된다. 법적 증적 무결성은 LEG Gate (Gate B) 를 통해 별도 검증한다.

### 3.8 확정 트랜잭션 내 DATE manifest 생성 위치 (R1-03 신규)

기존 확정 트랜잭션(`confirm_document_atomic()`)의 원자 순서를 보존한다. DATE manifest는 아래 지점에서 생성된다.

```
Step 14a-2 (변경): ATTACHMENT + DATE evidence validation + manifest 생성
  ├── ev_family in _FILE_EVIDENCE_FAMILIES → ATTACHMENT 경로 (기존 유지)
  │     └── verify_file_snapshot_for_evidence() → attachment_evidence_manifest
  └── ev_family in _DATE_EVIDENCE_FAMILIES → DATE 경로 (신규)
        └── _verify_date_evidence_value() → date_evidence_manifest

Step 14a-3 (신규): manifest 병합 (clock_timestamp() 호출 전)
  combined_evidence_manifest = attachment_evidence_manifest + date_evidence_manifest

Step 14b (변경 없음): build_render_artifacts(attachment_evidence_manifest=combined_evidence_manifest)
  └── rendered_body 생성 — combined manifest 포함

Step 15 (변경 없음): clock_timestamp() 1회 캡처 → confirmed_at
  └── DATE manifest 생성 이후이므로 date_value ≠ confirmed_at 혼동 없음

Step 16 (변경 없음): compute_confirmed_snapshot_hash(evidence_manifest=artifacts["evidence_manifest"])
  └── rendered_body + evidence_manifest 모두 동일 combined 기반

Step 17 (변경 없음): Archive INSERT
Step 18 (변경 없음): Approval INSERT
Step 19 (변경 없음): Seal UPDATE
```

**일관성 보장:**

| 값 | 생성 시점 | Step 관계 |
|----|-----------|-----------|
| `date_value` (사용자 업무 날짜) | Step 14a-2 읽기 (from runtime_values) | Step 15 이전 |
| `confirmed_at` (서버 확정 시각) | Step 15 clock_timestamp() | Step 14 이후 |
| `rendered_body` | Step 14b | combined manifest 포함 |
| `evidence_manifest` | Step 14b 산출물 | combined 기반 |
| `snapshot_hash` | Step 16 | runtime_values + rendered_body + evidence_manifest + confirmed_at 동일 기반 |

`clock_timestamp()` 는 여전히 1회만 호출한다. DATE manifest 생성 시 별도 서버 시각을 캡처하지 않는다.

### 3.9 `confirmed_at` 관계

| 시각 | 생성 주체 | 저장 위치 | 의미 |
|------|-----------|-----------|------|
| `confirmed_at` | DB `clock_timestamp()` | `runtime_document_archive` | 문서 확정 시각 (시스템) |
| `date_value` | 사용자 입력 | `runtime_data_json` → snapshot → DATE manifest | 업무 사건 날짜 (업무) |

이 둘은 독립적이며 상호 대체 불가. DATE manifest에 `confirmed_at` 을 중복 기록하지 않는다 (`evidence_manifest` 전체에 이미 포함됨).

### 3.10 Archive / hash 불변성

- DATE manifest는 기존 `evidence_manifest` JSON에 포함된다.
- `evidence_manifest`는 Q4 hash 입력 중 하나 (`compute_confirmed_snapshot_hash(evidence_manifest=...)`)
- 기존 확정된 Archive 행은 변경하지 않는다. 불변 트리거(`trg_rdarch_no_update`) 적용 대상.
- DATE 증적 추가로 인한 `snapshot_schema_version` 변경은 없다 (`_SNAPSHOT_SCHEMA_VERSION = 1` 유지).

### 3.11 과거 확정 문서 호환성

- 기존 확정 문서: `evidence_manifest = []` 또는 ATTACHMENT 항목만 → 변경 없음.
- 신규 확정 문서 (DATE 포함 서식): 위 manifest 형식 적용.
- 하위 호환 break 없음.

---

## 4. WP-C — FE PR #181 계약 정합

### 4.1 PR #181 현재 상태

| 항목 | 상태 |
|------|------|
| `date` input_type VTextField 렌더링 | 구현 완료 |
| CANDIDATE 증적 차단 (CHILD_STATUS_DRIFT) | 구현 완료 |
| `evidence_fields` 존재 시 에디터 전체 차단 | 구현 완료 |
| DATE family 에디터 허용 | **미구현 — 추가 필요** |

### 4.2 PR #181 이후 FE 보정 필요 사항

현재 FE는 `evidence_fields.length > 0` 이면 에디터를 일괄 차단한다. DATE 전용 증적만 있는 서식에서도 차단이 발생한다.

**보정 계약 (구현 WO에 포함):**

```typescript
// 현재 (모든 증적 차단)
if (rawEvidence.length > 0) {
  unsupportedReason.value = 'EVIDENCE_CONTRACT_UNSUPPORTED'
  return
}

// 보정 후 (DATE 전용은 통과)
const unsupportedEvidence = rawEvidence.filter(
  (e) => e.evidence_family !== 'DATE'
)
if (unsupportedEvidence.length > 0) {
  unsupportedReason.value = 'EVIDENCE_CONTRACT_UNSUPPORTED'
  return
}
// DATE 전용인 경우 에디터 활성화 허용
```

**단, 이 보정은 아래 두 조건이 선행돼야 한다:**
1. BE_DATE_CODE_READY (Gate A)
2. 해당 서식의 evidence_field.status = `APPROVED_FOR_RUNTIME_USE` (기존 R1-02 유지)

### 4.3 FE/BE 승인 경계 명시 (R1-04)

FE의 DATE family 인식과 BE의 DATE 봉인 지원은 **별도 Gate**다.

| Gate | 항목 | 조건 |
|------|------|------|
| FE DATE 인식 | evidence_family = 'DATE' 필터링 | PR #181 + 에디터 gate 보정 |
| BE DATE 봉인 | _ALLOWED_EVIDENCE_FAMILIES + manifest | Gate A Code Ready |
| Evidence 승인 | CANDIDATE → APPROVED_FOR_RUNTIME_USE | Gate B (LEG Gate) |

FE gate 보정만 완료해도 BE가 미구현이면 확정 시 422 거부. 두 Gate가 동시에 Code Ready여야 실제 확정이 가능하다.

PR #181의 기존 코드는 변경하지 않는다. FE 보정은 별도 커밋 또는 PR #181 추가 커밋으로 처리한다.

---

## 5. WP-D — 활성화 Gate 분리

### Gate A: CODE_READY

**조건:**
- BE: `document_confirm_svc.py` DATE family 지원 구현 완료
- BE: `_verify_date_evidence_value()` 구현 및 단위 테스트 PASS
- BE: DATE manifest 형식 확정 및 Q4 hash 검증 PASS
- FE: evidence gate DATE 통과 보정 구현 완료
- FE: 기존 ATTACHMENT 경로 회귀 없음 (기존 테스트 PASS)

**이 상태에서 허용:** 테스트 환경에서 DATE 증적 확정 경로 검증.  
**이 상태에서 불허:** 미승인 DATE 증적을 포함한 서식의 실제 사용.

### Gate B: EVIDENCE_APPROVAL_READY

**조건 (각 서식/증적 단위):**
- LEG 확인 완료 (법적 의무 여부)
- evidence_field_candidate.status = `APPROVED_FOR_RUNTIME_USE`
- runtime_evidence_field.status = `APPROVED_FOR_RUNTIME_USE`
- SEMANTIC_UNRESOLVED 필드 해소 또는 별도 처리 결정

**현재 상태:** 104건 전부 `CANDIDATE`. 이 Gate는 이 WO의 범위 밖.

### Gate C: RUNTIME_USE_READY

**조건:**
- Gate A + Gate B 완료
- 입력 → 저장 → 확정 → 렌더 → 출력 E2E 검증 PASS
- 운영 환경 연기테스트 PASS

**현재 상태:** Gate A 설계 중. Gate B/C 미착수.

### 차단 유지 사항

- `runtime_review_authority` SUSPENDED 상태 우회 금지
- 미승인 DATE 증적 일괄 승인 금지
- PR #181 HOLD — Gate A Code Ready 전까지 Merge 금지

---

## 6. 최소 테스트 계약

후속 구현 WO에서 작성할 테스트 범위를 정의한다. 구현 전이므로 코드가 아닌 계약으로 명시한다.

| 테스트 | 시나리오 | 기대 결과 |
|--------|----------|-----------|
| T-DATE-01 | 미승인 DATE 증적 포함 서식 확정 | HTTP 422, 상태 변경 없음 |
| T-DATE-02 | 승인된 DATE 증적 + 유효 날짜 값 확정 | HTTP 200, Archive 생성, evidence_manifest에 DATE 항목 포함 |
| T-DATE-03 | 승인된 DATE 증적 + 날짜 값 없음 (null) | HTTP 422 |
| T-DATE-04 | 승인된 DATE 증적 + 날짜 형식 오류 (예: "2026/10/15") | HTTP 422 |
| T-DATE-05 | 기존 ATTACHMENT 증적 포함 서식 확정 | 회귀 없음, 기존 동작 유지 |
| T-DATE-06 | ATTACHMENT + DATE 혼합 증적 서식 확정 | 각각 경로로 처리, Archive 정합 |
| T-DATE-07 | DATE manifest Q4 hash 결정성 | 동일 입력 → 동일 hash |
| T-DATE-08 | 기존 확정 Archive 행 (ATTACHMENT만) | 변경 없음, 불변 트리거 유지 |
| T-DATE-09 | `confirmed_at` vs `date_value` 독립성 | `date_value`가 `confirmed_at`을 덮어쓰지 않음 |

---

## 7. HOLD 및 Owner 결정사항

| 항목 | 상태 | 해제 조건 |
|------|------|-----------|
| PR #181 HOLD | 유지 | Gate A Code Ready + GPT_DATE_BE_CONTRACT_IV PASS |
| 104건 CANDIDATE 승인 | 금지 | 각 서식 LEG Gate 통과 후 개별 승인 |
| `timestamp_auto` 별도 family 구현 | HOLD | 별도 WO 발행 후 Owner 승인 |
| DATA_SEMANTIC_GAP 필드 분리 | HOLD | Owner 설계 결정 후 |
| `submission_date` SEMANTIC_UNRESOLVED 해소 | HOLD | LEG / Owner 결정 |
| ATTACHMENT 확정 경로 변경 | 금지 | 이 WO 범위 밖 |
| `snapshot_schema_version` 변경 | 금지 | 별도 스키마 버전 업 Gate 필요 |

---

## 8. 다음 구현 WO 완료 조건

아래 조건이 모두 충족되면 구현 WO를 CLOSED로 판정한다.

1. `_ALLOWED_EVIDENCE_FAMILIES` 에 `"DATE"` 추가
2. `_ALLOWED_EVIDENCE_INPUT_TYPES` 에 `"date"` 추가
3. `_DATE_EVIDENCE_FAMILIES`, `_FILE_EVIDENCE_FAMILIES` 상수 추가
4. `_verify_date_evidence_value()` 구현 및 단위 테스트 T-DATE-03/04 PASS
5. `_resolve_evidence_connections()` 분기 수정
6. 확정 루프 DATE 경로 구현
7. DATE manifest 생성 및 병합
8. T-DATE-01 ~ T-DATE-09 전체 PASS
9. 기존 ATTACHMENT 테스트 회귀 없음
10. FE evidence gate DATE 통과 보정 (별도 커밋)
11. GPT_DATE_BE_CONTRACT_IV: PASS 후 Owner Code 구현 승인

---

## 9. FE / BE / DB 계약 매트릭스

| 계층 | 항목 | 현재 상태 | 계약 후 상태 |
|------|------|-----------|--------------|
| DB | runtime_evidence_field.evidence_family = "DATE" | CANDIDATE 104건 | 변경 없음 |
| DB | evidence_field_candidate.status | CANDIDATE | APPROVED 필요 (Gate B) |
| BE | _ALLOWED_EVIDENCE_FAMILIES | {"ATTACHMENT"} | {"ATTACHMENT", "DATE"} |
| BE | _ALLOWED_EVIDENCE_INPUT_TYPES | {"file"} | {"file", "date"} |
| BE | DATE 값 검증 | 없음 | ISO YYYY-MM-DD 검증 |
| BE | DATE manifest 생성 | 없음 | evidence_manifest 포함 |
| BE | Q4 hash 안전성 | ATTACHMENT만 | DATE 항목 추가 후도 안전 |
| FE | `date` 입력 렌더링 | PASS (PR #181) | 변경 없음 |
| FE | DATE 증적 에디터 게이트 | EVIDENCE_CONTRACT_UNSUPPORTED | DATE 전용 시 허용 (보정 필요) |
| FE | CANDIDATE 차단 | PASS (PR #181) | 변경 없음 |

---

## 10. 기존 API / 서비스 재사용 범위

| 기존 컴포넌트 | 재사용 여부 | 비고 |
|---------------|-------------|------|
| `_resolve_evidence_connections()` | 재사용 (분기 추가) | upload_type 검증 분기 |
| `verify_file_snapshot_for_evidence()` | 재사용 (ATTACHMENT 전용 유지) | DATE에 미적용 |
| `build_render_artifacts()` | 재사용 (서명 변경 없음) | combined manifest 전달 |
| `compute_confirmed_snapshot_hash()` | 재사용 (변경 없음) | DATE manifest 자동 포함 |
| `clock_timestamp()` 확정 타임스탬프 | 재사용 | DATE manifest에 중복 포함하지 않음 |
| Archive 불변 트리거 | 유지 | DATE 추가 후도 동일 |

별도 Evidence 엔진 신규 구축 없음. 기존 확정 트랜잭션 구조 재사용.
