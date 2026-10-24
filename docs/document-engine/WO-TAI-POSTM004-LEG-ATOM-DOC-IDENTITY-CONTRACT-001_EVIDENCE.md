# WO-TAI-POSTM004-LEG-ATOM-DOC-IDENTITY-CONTRACT-001 EVIDENCE

**작성:** 2026-10-24 · READ-ONLY · PROD_DB_WRITE=0 · CODE_CHANGE=0

---

## C1 — 기존 정본 계약 확인

### 조사 원문

| 소스 | 경로 | SHA |
|------|------|-----|
| LEG 파이프라인 정의서 | `leg-wo-sm-core22-final/docs/leg/check-contract-wiring/DEFINITION_consumer-pipeline_v1.md` | `8883e69` |
| TAI canonical_writer.py | `services/inspection_sets_svc/canonical_writer.py` | `3e299eb5` |
| TAI canonical_bridge.py | `services/inspection_sets_svc/canonical_bridge.py` | `3e299eb5` |
| TAI doc_m004_dryrun.py | `services/doc_m004_dryrun.py` | `3e299eb5` |
| TAI doc_m004_binding_adapter.py | `services/doc_m004_binding_adapter.py` | `3e299eb5` |

### C1-1 LEG 정의서 판정

**DEFINITION_consumer-pipeline_v1.md line 485:**
```
Identity: `legal_obligation_atom_id` (atom EXACT). `legal_rule_id` 기반 identity 아님.
```

**lines 665–670 (구 계약 명시 DEPRECATED):**
```
- `master_building_legal_rules` 를 identity/enrich JOIN SoT 로 쓰는 구 설명
- `legal_rule_id` 를 canonical identity 로 쓰는 구 계약
  (`factory_diagnosis_results.result_data.inspection_required` · `rule_code` · ... 기반 생성)
```

판정: `legal_rule_id` (TEXT 규칙코드) 기반 identity = **명시적 DEPRECATED**.  
현행 SoT identity = `legal_obligation_atom_id` (UUID v5) EXACT.

### C1-2 TAI canonical_writer.py 계약

```python
# canonical_writer.py line 97–98
"legal_rule_id": None,
"legal_rule_code": None,
```

주석: `# legacy identity 비움 (atom/law 대입 0)`

**결론:** canonical_writer는 신규 inspection_sets row에 `legal_rule_id`/`legal_rule_code`를 명시적으로 null로 설정한다. atom_id만 운반된다.

### C1-3 C1 권위

- 생성 주체: LEG 파이프라인 정의서 (PRJ 거버넌스 정본)
- 적용 범위: 모든 LEGAL_ENGINE source inspection_sets
- atom_id ↔ TAI TEXT 규칙코드 연결 계약: **현재 정본 범위에서 존재하지 않음**

---

## C2 — 식별자 연결 검증

### 식별자 출처 및 타입 표

| 식별자 | 위치 | 타입 | 예시 |
|--------|------|------|------|
| A: LEG `atom_id` | inspection_sets.legal_obligation_atom_id | UUID v5 | `e8ff59ed-a77d-5034-bb89-1d80dcf0205c` |
| B: LEG approved obligation | inspection_sets (canonical rows) | 69건 | atom_id != null, rule_id = null |
| C: 권위 있는 식별자 연결 계약 | — | **NOT_FOUND** | — |
| D: TAI legacy rule_code | doc_rule_mapping.rule_id | TEXT | `CTL-CON-101`, `CON3-CPR-002` |
| E: TAI doc_id | doc_rule_mapping.doc_id | TEXT | `DOC-OSH-070`, `DOC-CON-LAW-015` |
| F: document_forms.id | document_forms | UUID | (운영 DB 내 260종) |

### 연결별 검증 결과

**A→B: LEG atom_id → inspection_sets canonical rows**
- inspection_sets 전체: TOTAL 미측정(Supabase 페이지네이션)
- canonical rows (atom_id != null): **69건 확인**
- 모든 canonical row: `legal_rule_id = null`, `legal_rule_code = null`
- 관계: 1:1 (atom_id UNIQUE constraint)
- 승인 근거: LEG DEFINITION_consumer-pipeline_v1 §4B-1

**B→C: 승인된 atom_id ↔ TAI TEXT 규칙코드 연결 계약**
- canonical rows에서 `legal_rule_id != null` 건수: **0건**
- 코드에서 atom_id → rule_code 변환 계약: **없음**
- 정본 문서에서 mapping 정의: **없음**
- **→ IDENTITY_CONTRACT_NOT_FOUND**

**C→D: TAI TEXT 규칙코드 → doc_rule_mapping**
- doc_rule_mapping: 227건 / 고유 rule_id: 107개 / 고유 doc_id: 110개
- review_status: 전건 PENDING
- 관계: N:M (rule_id 1개가 복수 doc에 매핑 — 107개 중 53개 복수 문서)
- 승인 근거: review_status=PENDING → **없음**

**D→E: doc_rule_mapping.doc_id → document_forms**
- TEXT doc_id → document_forms.doc_id: 매핑 가능
- 경로는 존재하나 D 진입 불가(C 차단)

**E→F: document_forms → Runtime**
- WEB48 활성화 49종 포함 → READY_FOR_EDIT 가능
- 단 C 차단으로 도달 불가

### 부분 legacy 경로 (DEPRECATED)

| 항목 | 값 |
|------|-----|
| inspection_sets legacy rows (atom_id=null) | 315건 |
| legacy.legal_rule_id TEXT 코드 유니크 | 151개 |
| doc_rule_mapping 유니크 rule_id | 107개 |
| **교집합 (정확 일치)** | **7개** |
| 교집합이 매핑하는 문서 | DOC-OSH-070(6건), DOC-OSH-006(1건), DOC-OSH-037(1건) |
| 이 legacy rows의 legal_obligation_atom_id | null (canonical 아님) |
| LEG 정의서 상태 | DEPRECATED identity 경로 |

이 legacy 7건은 DEPRECATED atom_id가 없는 구형 행이다. 현행 canonical atom_id → doc 경로로 재사용 불가.

### C2 결론

- EXACT_AUTHORIZED_LINK_COUNT (atom_id → doc_id): **0**
- CONFLICT_COUNT: 0 (contract 자체가 존재하지 않으므로 충돌도 없음)
- **C2_RESULT: IDENTITY_CONTRACT_NOT_FOUND**

---

## C3 — 기존 소비 경로 확인

C2 = `IDENTITY_CONTRACT_NOT_FOUND`이므로 C3는 제한된 범위만 확인한다.

### 기존 어댑터 실제 호출·조회 경로

```
resolve_binding(obligation_code)                     [binding_adapter.py]
  └─ classify_one_obligation(ob)                     [dryrun.py]
       ├─ _step1_form_codes() → obligation_form_mapping.obligation_code   (11건)
       ├─ _step2_form_template() → form_templates.form_code
       ├─ _step3_rule_doc() → rule_doc_mapping.rule_id (→ doc_id)         ← 0건
       ├─ _step4_document_form() → document_forms.doc_id
       └─ _step5_runtime_schema() → runtime_form_schema.catalog_document_id
```

**핵심 문제 2건:**

1. **테이블명 불일치 (단순 오타 아님):**
   - `_step3_rule_doc()`가 읽는 테이블: `rule_doc_mapping` (0건, UUID 기반, law_rule_drafts 연결)
   - 실제 매핑 데이터: `doc_rule_mapping` (227건, TEXT 규칙코드 기반)
   - 두 테이블은 다른 스키마/목적 — 단순 교체 불가

2. **rule_id 전달 경로 없음:**
   - `resolve_binding()`은 `obligation_code`만 받음
   - ob dict에 `legal_rule_id` 미포함 (comment: "실제 legal_obligations에 없는 컬럼")
   - 따라서 `_step3_rule_doc()`에 전달되는 `rule_id_raw` = None → skip
   - doc_rule_mapping을 읽더라도 rule_code가 전달되지 않아 조회 불가

3. **운영 현황 (binding_adapter 주석 2026-10-13 기준):**
   - `rule_doc_mapping = 0건 → doc_id 항상 UNVERIFIED`
   - `APPROVED schema catalog_linked = 0건`
   - `의무 기반 READY_FOR_EDIT = 0 (정상)`

### 작동 중인 경로 (의무 기반 유일 경로)

`obligation_form_mapping` → `form_templates` → `bylseq` 경로:
- 11건 매핑 → 5건 form_templates 일치 → `CATALOG_LINKED` 판정 가능
- 단 `doc_rule_mapping`(227건)과 연결 없음
- WEB48 49종과의 연결 확인 불가 (form_code ↔ doc_id 계약 없음)

### C3_RESULT: NOT_APPLICABLE (C2 IDENTITY_CONTRACT_NOT_FOUND)

---

## 최종 분류

```
FINAL_CLASSIFICATION = IDENTITY_CONTRACT_NOT_FOUND
```

**ROOT_CAUSE (단일 차단점):**

LEG 현행 canonical identity = `legal_obligation_atom_id` (UUID v5).  
TAI 기존 매핑 연결 키 = TEXT 규칙코드 (`doc_rule_mapping.rule_id`).  
이 두 식별자를 권위 있게 연결하는 계약·테이블·코드가 현재 소스 범위 내에 존재하지 않는다.  
canonical_writer.py는 이 연결을 명시적으로 차단(null 설정)한다.

**MINIMAL_REPAIR_SCOPE (현재 미승인):**

다음 중 하나가 권위 있는 계약으로 확인·승인되어야 한다:

| 옵션 | 내용 | 선행 조건 |
|------|------|----------|
| P1 | LEG atom_id → TAI TEXT 규칙코드 lineage 테이블/매핑 정의 | LEG Owner 계약 결정 |
| P2 | obligation_form_mapping(11건) → document_forms 직접 확장 (법령코드 경로 포기) | TAI + LEG Owner |
| P3 | doc_rule_mapping review_status 승인 + law_name/article로 obligation 역매핑 | Owner D1 결정 대기 |

현재 구현 없음. 선행 조건 미충족.

---

## 검증 요약

```
WO = WO-TAI-POSTM004-LEG-ATOM-DOC-IDENTITY-CONTRACT-001

LEG_SOURCE_SHA = 8883e69 (DEFINITION_consumer-pipeline_v1.md)
TAI_SOURCE_SHA = 3e299eb5 (canonical_writer/bridge/dryrun/binding_adapter)

C1_CONTRACT_SOURCE = DEFINITION_consumer-pipeline_v1.md line 485 + canonical_writer.py line 97-98
C1_AUTHORITY = LEG PRJ 거버넌스 정본 + TAI 코드 명시적 null 설정
C1_RESULT = legal_rule_id DEPRECATED / atom_id CANONICAL / atom→rule_code 계약 없음

C2_IDENTITY_CHAIN = A(atom_id)→B(69 canonical rows)→C(CONTRACT_NOT_FOUND)
C2_EXACT_AUTHORIZED_LINK_COUNT = 0
C2_CONFLICT_COUNT = 0
C2_RESULT = IDENTITY_CONTRACT_NOT_FOUND

C3_CONSUMER_ENTRYPOINT = resolve_binding(obligation_code) → _step3_rule_doc → rule_doc_mapping(0건)
C3_EXISTING_MAPPING_CONSUMPTION = 0건 (rule_doc_mapping 0건 / rule_id 전달 경로 없음)
C3_APPROVAL_GATE = PENDING 227건 전건 미승인
C3_RESULT = NOT_APPLICABLE

FINAL_CLASSIFICATION = IDENTITY_CONTRACT_NOT_FOUND
ROOT_CAUSE = atom_id(UUID) ↔ TAI TEXT 규칙코드 권위 있는 연결 계약 없음
MINIMAL_REPAIR_SCOPE = P1/P2/P3 중 하나 Owner 결정 후 별도 WO

M004 = CLOSED_FINAL
INSP15 = AUTO_SOURCE_ONLY
PROD_DB_WRITE = 0
CODE_CHANGE = 0

GPT_INDEPENDENT_VERIFICATION = PENDING
```
