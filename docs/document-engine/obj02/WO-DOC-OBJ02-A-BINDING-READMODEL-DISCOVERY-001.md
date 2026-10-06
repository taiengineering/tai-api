# WO-DOC-OBJ02-A-BINDING-READMODEL-DISCOVERY-001

> Object: OBJ02 — Catalog ↔ Runtime Schema Binding & Document List Read Model
> Stage: A — READ-ONLY Evidence
> Date: 2026-10-07
> GPT: analysis / design / independent verification
> Claude Code: investigation / execution / evidence collection
> Owner: approval
> Production mutation: 0

---

# 0. 목적

OBJ01에서 고정한 Web Document First architecture를 구현하기 전에 현재 Production 데이터와 코드에서 다음 세 축의 실제 연결 가능성을 정확히 확인한다.

1. document_forms 260
2. document_type_mapping 30 + document_type_registry 8
3. runtime_form_schema 324

이번 단계는 mapping을 만드는 작업이 아니다.

정확한 식별자와 명시적 source trace만 수집하여 GPT가 OBJ02-B binding contract를 설계할 수 있게 한다.

---

# 1. 반드시 먼저 읽을 기준

현재 branch의 다음 문서:

- docs/document-engine/obj00/OBJ00_CURRENT_STATE_EVIDENCE.md
- docs/document-engine/obj01/OBJ01_CANONICAL_DOCUMENT_ARCHITECTURE_v1.md

과거 문서는 단독 근거로 사용하지 않는다.

조사 원칙:

CURRENT SOURCE
→ CURRENT DB
→ RECENT COMMIT/PR
→ RECENT DOC
→ OLD DOC

문서와 소스가 다르면 소스를 사실로 기록한다.

---

# 2. 절대 금지

이번 Stage A:

- application code change = 0
- DB write = 0
- migration = 0
- schema status change = 0
- CANDIDATE approval = 0
- document_type_mapping insert/update = 0
- semantic mapping = 0
- fuzzy matching = 0
- LLM matching = 0
- deploy = 0
- storage write = 0

---

# 3. Git Anchor

조사 시작 시 현재 remote main과 작업 branch SHA를 다시 기록한다.

특히 document 관련 현재 main source가 OBJ01 조사 이후 바뀌었는지 확인한다.

다음 파일들의 latest relevant commit을 기록한다.

- document_type_mapping을 생성/사용하는 migration/service
- document_type_registry 관련 migration/service
- runtime_form_schema 생성/승격 관련 코드
- document_forms service/router
- document-forms frontend
- document schema candidate/binding 관련 코드

관련 기능의 마지막 commit 전후 ±2~3 commit에서 같은 시점의 PLAN/WO/RESULT/HANDOFF가 있으면 찾되, 현재 source와 대조 후 사실/의도/obsolete를 구분한다.

산출:
GIT_HISTORY_EVIDENCE.md

---

# 4. OBJ02-A1 — Catalog 260 Canonical Snapshot

document_forms 260건을 현재 Production에서 재추출한다.

최소:
- id
- doc_id
- doc_name
- sector
- category
- law_ref
- obligation
- tai_grade
- tai_difficulty
- priority
- file_url
- required_fields
- has_legal_form
- tai_auto
- tai_method
- doc_format
- doc_owner
- is_external_writer
- is_active

산출:
DOCUMENT_CATALOG_CURRENT.csv

row count 및 doc_id uniqueness를 함께 확인한다.

---

# 5. OBJ02-A2 — Type Mapping 30 Coverage

document_type_mapping 전체를 추출한다.

최소:
- id
- doc_id
- doc_type
- doc_detail
- source_note
- created_at
- updated_at

다음을 exact join으로 계산한다.

document_type_mapping.doc_id
→ document_forms.doc_id

분류:
- MAPPED_EXISTING_CATALOG
- MAPPING_ORPHAN
- CATALOG_UNMAPPED

수치:
- catalog total
- mapped catalog
- unmapped catalog
- orphan mapping
- coverage %

doc_type별 mapping 수와 doc_detail 분포도 기록한다.

산출:
DOCUMENT_TYPE_MAPPING_CURRENT.csv
CATALOG_TYPE_MAPPING_COVERAGE.csv
TYPE_MAPPING_CENSUS.md

---

# 6. OBJ02-A3 — Registry 8 Verification

document_type_registry 8행을 현재 코드와 대조한다.

각 doc_type:
- template_file
- actual template file exists?
- fetcher_key
- actual fetcher implementation exists?
- fetcher_status
- evidence_source
- current consumer
- supported output today
- missing dependency

분류:
- IMPLEMENTED
- PARTIAL
- METADATA_ONLY
- MISSING

판정은 파일 존재/코드 호출 근거만 사용한다.

산출:
TYPE_REGISTRY_RUNTIME_EVIDENCE.md

---

# 7. OBJ02-A4 — Runtime Schema 324 Source Trace Census

runtime_form_schema 324 전체에서 다음을 추출한다.

- id
- schema_candidate_id
- document_family
- form_type
- form_name
- field_count
- checklist_count
- evidence_count
- status
- version
- source_trace
- created_at
- updated_at

source_trace JSON에 실제 존재하는 key를 전수 census한다.

예:
- doc_id
- form_code
- source_id
- source_table
- 기타

각 key의:
- non-null count
- distinct count
- source_table별 분포

산출:
RUNTIME_SCHEMA_CURRENT.csv
RUNTIME_SCHEMA_SOURCE_TRACE_CENSUS.md

---

# 8. OBJ02-A5 — Exact Binding Evidence

Catalog ↔ Runtime Schema를 자동 확정하지 않는다.

오직 아래 exact evidence만 생성한다.

## E1 — doc_id exact
runtime_form_schema.source_trace.doc_id
= document_forms.doc_id

## E2 — explicit source_id route
runtime_form_schema.source_trace.source_table + source_id가
form_templates 또는 document_form_master의 실제 PK를 가리키는지 확인.

그 source row가 document_forms와 연결되는 명시적 FK/코드가 현재 DB에 있는지 확인.

## E3 — form_code exact
runtime_form_schema.source_trace.form_code
= form_templates.form_code
또는
= document_form_master.form_code

그 form_code에서 document_forms.doc_id로 가는 명시적 mapping이 존재하는지 확인.

## E4 — existing explicit FK / mapping table
현재 DB에 catalog/schema 직접 연결 테이블 또는 FK가 있는지 전수 조사.

### 금지

- doc_name == form_name 유사도
- 부분일치
- token overlap
- embedding
- fuzzy
- 사람이 이름 보고 임의 연결

결과 분류:

- EXPLICIT_DIRECT_BINDING
- EXACT_DOC_ID_EVIDENCE
- EXACT_SOURCE_ROW_EVIDENCE
- EXACT_FORM_CODE_EVIDENCE
- NO_EXACT_BINDING
- AMBIGUOUS_EXACT_EVIDENCE

산출:
CATALOG_RUNTIME_EXACT_BINDING_EVIDENCE.csv

---

# 9. OBJ02-A6 — Approved Schema 1건 집중 추적

현재 APPROVED_FOR_RUNTIME_USE schema를 별도 추적한다.

확인:
- schema id
- source_trace
- source table/source row
- form_code
- 관련 runtime_field 5개
- catalog doc_id 직접연결 여부
- document_type_mapping 연결 여부
- document_type_registry doc_type 연결 여부
- frontend에서 선택 가능한 catalog와 실제 연결 여부

판정은:
- DIRECTLY_BOUND
- INDIRECT_EXACT_EVIDENCE_ONLY
- UNBOUND

중 하나.

산출:
APPROVED_SCHEMA_TRACE.md

---

# 10. OBJ02-A7 — Candidate 323 Safety Check

323 CANDIDATE에 대해 승인 여부를 판단하지 않는다.

다음만 집계한다.

- source_table별 count
- form_type별 count
- document_family별 count
- exact doc_id evidence count
- exact form_code evidence count
- exact source_id resolvable count
- duplicate source identity count

목적:
향후 Human Review 단위를 설계하기 위한 모수 확인.

산출:
CANDIDATE_SCHEMA_CENSUS.md

---

# 11. OBJ02-A8 — Current Frontend List Contract

현재 소비자 관련 두 화면을 다시 확인한다.

- /document-forms
- /engine-document

각각:
- 어떤 table/API를 list source로 보는지
- catalog/type/schema 중 무엇을 노출하는지
- selected row key
- HTML editable view가 실제 무엇으로 만들어지는지
- runtime_form_schema binding을 어떤 key로 기대하는지
- 현재 list→open→edit→save chain의 실제 break point

현재 source만 근거로 기록한다.

산출:
CURRENT_LIST_VIEW_CONTRACT.md

---

# 12. OBJ02-A9 — Document List Read Model Evidence

아직 DB view를 만들지 않는다.

현재 데이터만 이용해 소비자 list에 필요한 field가 어디에서 오는지 source matrix를 작성한다.

최소 consumer field:

- document_key
- doc_id
- doc_name
- doc_type
- doc_detail
- availability
- runtime_schema_id
- working_document_id
- working_status
- confirmed_snapshot_id
- last_saved_at
- last_confirmed_at
- supported_export_formats
- can_edit
- can_confirm
- can_export
- source_type

각 field마다:
- current source table/column
- direct available?
- derived?
- missing?
- ambiguity?

산출:
DOCUMENT_LIST_READMODEL_SOURCE_MATRIX.md

---

# 13. OBJ02-A10 — Schema Binding Extension Feasibility

OBJ01 후보안:

document_type_mapping.runtime_form_schema_id

를 구현하지 말고 feasibility만 조사한다.

확인:
- document_type_mapping 현재 PK/UNIQUE/FK
- runtime_form_schema PK/version/status
- 1 doc_id → 1 schema가 현재 데이터로 성립하는지
- schema version upgrade 시 pointer 정책 문제
- official/source-only 문서에서 schema nullable 필요성
- existing consumer 영향
- migration rollback 가능성

대안 비교는 사실 기반으로만 작성한다.

A. document_type_mapping에 runtime_form_schema_id 추가
B. 별도 binding table
C. runtime_form_schema.source_trace만 사용

Claude는 추천안을 확정하지 않는다.

각 방식의:
- required DDL
- current-source impact
- cardinality support
- migration risk

만 작성한다.

산출:
SCHEMA_BINDING_FEASIBILITY.md

---

# 14. OBJ02-A11 — Format Capability Evidence

현재 실제 지원 renderer와 DB export type을 확인한다.

- PDF
- HTML
- XLSX
- DOCX
- HWP
- PRINT_VIEW
- API_RESPONSE
- 기타

각 format:
- DB status/check 허용?
- renderer 구현?
- 실제 route?
- frontend consumer?
- production evidence?

OBJ01 원칙대로 unsupported format을 지원한다고 가정하지 않는다.

산출:
EXPORT_FORMAT_CAPABILITY.md

---

# 15. 결과 폴더

다음 위치:

docs/document-engine/obj02/

필수 파일:

- OBJ02_A_CURRENT_STATE.md
- GIT_HISTORY_EVIDENCE.md
- DOCUMENT_CATALOG_CURRENT.csv
- DOCUMENT_TYPE_MAPPING_CURRENT.csv
- CATALOG_TYPE_MAPPING_COVERAGE.csv
- TYPE_MAPPING_CENSUS.md
- TYPE_REGISTRY_RUNTIME_EVIDENCE.md
- RUNTIME_SCHEMA_CURRENT.csv
- RUNTIME_SCHEMA_SOURCE_TRACE_CENSUS.md
- CATALOG_RUNTIME_EXACT_BINDING_EVIDENCE.csv
- APPROVED_SCHEMA_TRACE.md
- CANDIDATE_SCHEMA_CENSUS.md
- CURRENT_LIST_VIEW_CONTRACT.md
- DOCUMENT_LIST_READMODEL_SOURCE_MATRIX.md
- SCHEMA_BINDING_FEASIBILITY.md
- EXPORT_FORMAT_CAPABILITY.md

총 16개 예상.

---

# 16. 최종 보고 형식

OBJ02-A READ-ONLY RESULT

GIT
tai-api remote main =
working branch =
document scope drift = YES / NO

CATALOG
document_forms =
doc_id unique =
mapped =
unmapped =
orphan mappings =
coverage =

TYPE MAPPING
rows =
doc_types =
details =

REGISTRY
rows =
implemented =
partial =
metadata_only =
missing =

RUNTIME SCHEMA
total =
approved =
candidate =

SOURCE TRACE
doc_id non-null =
form_code non-null =
source_id non-null =
source_table distribution =

EXACT BINDING
explicit direct =
exact doc_id =
exact source row =
exact form_code =
no exact =
ambiguous =

APPROVED SCHEMA
id =
binding state =

FRONTEND
list source =
open/edit source =
current break point =

EXPORT
PDF =
HTML =
XLSX =
DOCX =
HWP =

BINDING FEASIBILITY
A mapping-column =
B binding-table =
C source-trace-only =
NO RECOMMENDATION MADE

MUTATION
application code = 0
DB write = 0
storage write = 0
deploy = 0

FILES CREATED =
OBJ02-A = COMPLETE / INCOMPLETE
GPT INDEPENDENT VERIFICATION = REQUIRED

---

# 17. Stop Condition

결과 제출 후 정지한다.

금지:
- OBJ02-B migration
- binding insert/update
- schema approval
- frontend patch
- OBJ03
- deploy

GPT가 결과를 독립검증한 뒤 OBJ02-B 설계/작업지시를 발행한다.
