# OBJ01 Canonical Document Architecture v1

> 문서 ID: TAI-SAFE-DOC-OBJ01-CANONICAL-ARCHITECTURE-v1
> 기준일: 2026-10-07
> 상태: DESIGN FIXED / IMPLEMENTATION NOT STARTED
> 상위 계획: TAI_SAFE_DOCUMENT_COMPLETION_MASTER_PLAN_v1.md
> 선행 Object: OBJ00 CLOSED FINAL
> 기준 원칙: CURRENT SOURCE/DB 우선, 문서는 소스와 대조 후에만 채택
> 설계/판정: GPT
> 구현: Claude Code
> Production mutation: 0

---

# 0. 설계 목적

TAI Safe 문서 기능을 새로 만드는 것이 아니라, 이미 존재하는 document_forms, document_type_mapping, document_type_registry, runtime_form_schema 계열, runtime_document_data, runtime_document_archive, renderer/fetcher, generated_document, documents 자산을 소비자 기준 하나의 문서 경험으로 수렴시킨다.

최종 소비자 경험:

~~~
문서 리스트
   ↓
문서 선택
   ↓
HTML Web View
   ↓
조회 / 수정 / 저장
   ↓
필요 시 확정
   ↓
다운로드 요청
   ↓
PDF / DOCX / XLSX / 지원 형식 생성
   ↓
다운로드
~~~

파일은 문서의 본체가 아니다.

---

# 1. 증거 신뢰 우선순위

문서엔진의 사실 판정은 다음 순서를 따른다.

~~~
1. CURRENT SOURCE
2. CURRENT PRODUCTION DB
3. RECENT COMMIT / PR
4. RECENT DESIGN DOCUMENT
5. OLD DOCUMENT / HANDOFF
~~~

오래된 문서가 현재 코드/DB와 충돌하면 문서 내용을 폐기한다.

최근 문서도 CONTRACT/DESIGN과 STATUS/PROGRESS를 분리한다. 설계 계약은 현재 소스가 확인하는 부분만 유지하고, 진행상태는 현재 Git/DB가 확인하지 않으면 신뢰하지 않는다.

현재 소스/DB와 대조하여 유지하는 기존 핵심 결정:

- Lazy Source + Confirmed Snapshot
- runtime_document_data = working state
- runtime_document_archive = confirmed immutable state
- generated_document = output artifact registry
- PDF = derived output
- explicit confirm sealing
- document_type_mapping / registry 재사용

이번 범위에서 승계하지 않는 과거 결정:

- delta/voucher edit model
- document body 대량 사전저장
- 파일 중심 UX
- 생성 시마다 PDF 자동저장

---

# 2. D-01 — Consumer Contract

소비자가 보는 기본 흐름을 고정한다.

~~~
LIST
 → OPEN
 → HTML VIEW
 → EDIT
 → SAVE
 → [OPTIONAL CONFIRM]
 → EXPORT ON DEMAND
~~~

PDF/DOCX/XLSX 등 파일 생성은 다운로드 요청 시에만 수행한다.

금지:
- 문서 리스트 진입 시 PDF 사전생성
- 문서 작성 저장 시 PDF 자동생성
- 배치로 모든 문서 PDF 생성
- PDF를 문서 본체로 취급
- format별 별도 업무로직

---

# 3. D-02 — Canonical Document State

소비자에게 HTML이 문서처럼 보이지만 기술적 SoT는 HTML string이 아니다.

Canonical 상태:

~~~
Resolved Document State
= Source Values
+ User Working Values
+ Schema
+ Context
+ Source Trace
+ Evidence Manifest
~~~

이 상태로부터 HTML Web View, PDF, DOCX, XLSX 및 승인된 Export Renderer를 만든다.

HTML은 Primary Consumer View이고 구조화된 state가 Canonical Data다.

DOCX/XLSX를 PDF에서 변환하지 않는다. 각 renderer는 같은 ResolvedDocumentModel을 입력으로 받는다.

---

# 4. D-03 — Document Catalog SoT

SoT = document_forms.

역할:
TAI가 소비자에게 제공하는 문서 종류가 무엇인지 정의하는 Product Catalog.

현재 260건.

포함:
- 문서 식별자
- 이름
- 섹터
- 분류
- 법적 근거 메타
- 제출/보관 메타
- 자동화 가능성 메타
- 제공상태

포함하지 않음:
- 실제 사용자가 작성한 값
- PDF 파일
- Confirmed Snapshot

---

# 5. D-04 — Catalog → Type Mapping SoT

SoT = document_type_mapping.

현재 30건을 폐기하지 않는다.

~~~
document_forms.doc_id
      ↓
document_type_mapping
      ↓
doc_type + doc_detail
~~~

예:
- DOC-OSH-056 → TBM
- DOC-OSH-046 → PPE
- DOC-BLD-009 → EQUIP / ELEC
- DOC-BLD-011 → EQUIP / ELEV

새로운 병렬 TYPE mapping 테이블을 만들지 않는다.

현재 document_type_mapping.doc_id가 UNIQUE이므로 기본 계약은 1 catalog document → 1 canonical document type으로 유지한다.

---

# 6. D-05 — Renderer / Fetcher Registry SoT

SoT = document_type_registry.

역할:

~~~
doc_type
  ↓
template_file
fetcher_key
evidence_source
fetcher_status
~~~

현재 8종:
APPT, CHK, CONLOG, EDU, EQUIP, INSP, PPE, TBM.

doc_type별 전용 API/전용 generator를 계속 추가하지 않는다.

Registry는 dispatch metadata이며 실제 생성 로직은 Canonical Document Service에서 공통 처리한다.

---

# 7. D-06 — Runtime Schema SoT

SoT:
- runtime_form_schema
- runtime_field
- runtime_checklist_item
- runtime_evidence_field

역할:
HTML Web View에서 무엇을 보여주고 무엇을 사용자가 수정할 수 있는지 정의한다.

현재:
- runtime_form_schema 324
- APPROVED_FOR_RUNTIME_USE 1
- CANDIDATE 323

323 CANDIDATE를 자동 승인하지 않는다.

현재 APPROVED 1건도 catalog와 직접 binding되어 있지 않다.

OBJ02에서 기존 document_type_mapping에 Runtime Schema binding을 추가하는 방향을 우선 설계/검증한다. 새로운 병렬 mapping 체계는 기본안으로 채택하지 않는다.

후보 방향:

~~~
document_forms.doc_id
  ↓
document_type_mapping
  ├─ doc_type
  ├─ doc_detail
  └─ runtime_form_schema_id   [OBJ02 candidate extension]
~~~

실제 migration 여부는 OBJ02에서 constraint/consumer 영향 검증 후 확정한다.

---

# 8. D-07 — Source Assembly Contract

Fetcher는 공통 계약을 가진다.

~~~
{
  values: {},
  context: {},
  source_trace: [],
  evidence_manifest: []
}
~~~

values:
문서에 표시할 source-derived 값.

context:
company / factory / equipment / worker / task 등 화면·렌더 context.

source_trace:
어떤 원천 row/version에서 가져왔는지 추적.

evidence_manifest:
파일/점검/확인 기록 등 증빙 연결 정보.

금지:
- 법적 적용성 추론
- 없는 source 값 생성
- GPT 보완
- template 안에서 DB 조회

Fetcher는 데이터 조립만 한다.

---

# 9. D-08 — Working Document State

SoT = runtime_document_data.

역할:
현재 사용자가 작성/수정 중인 문서의 Working State.

현재 구현을 재사용한다.

이번 완결 범위에서는 current full working state 방식을 유지한다. 과거 delta/voucher 방식은 도입하지 않는다.

Open 시:

~~~
Source Assembly
      +
saved runtime_data_json
      ↓
Resolved Working State
      ↓
HTML Web View
~~~

기본 merge precedence:

~~~
explicit user saved value
> source auto-filled value
> empty
~~~

source-owned read-only field는 user override를 허용하지 않을 수 있으며 schema metadata로 결정한다.

---

# 10. D-09 — HTML Web View

HTML은 소비자의 기본 문서 화면이다.

기능:
- 조회
- 직접 입력
- 체크
- 수정
- 저장
- validation
- source 자동입력 표시
- 확정
- Export

HTML은 Resolved State의 browser projection이다.

HTML source 자체를 일반 편집 데이터로 저장하지 않는다. Rich text가 필요하면 해당 field value만 저장한다.

별도 PDF Preview를 기본 UX로 요구하지 않는다.

HTML Web View = 기본 View + Edit + Preview.

---

# 11. D-10 — Save Contract

사용자가 저장하면:

~~~
HTML controls
  ↓
validated structured values
  ↓
runtime_document_data
~~~

만 저장한다.

이 시점 기본값:

~~~
PDF generation = 0
DOCX generation = 0
XLSX generation = 0
Storage artifact write = 0
~~~

문서 저장과 파일 생성을 분리한다.

---

# 12. D-11 — Confirm Contract

확정은 다운로드와 다른 행위다.

명시적 Confirm 시:

~~~
Working State
   ↓
resolve
   ↓
deterministic render artifacts
   ↓
hash
   ↓
runtime_document_archive
   ↓
runtime_document_approval
   ↓
working state seal
~~~

현재 구현된 confirm_document_atomic()과 Snapshot/Hash 구조를 재사용한다.

Confirmed SoT = runtime_document_archive.

확정 이후 회사명, 사업장 주소, 설비명, 담당자, source row, template, runtime schema가 바뀌어도 과거 확정 문서가 변하지 않아야 한다.

Snapshot은 최소 다음을 포함한다.
- runtime values
- source trace
- evidence manifest
- rendered body
- template identity
- confirmed_at
- confirmed_by
- document version
- snapshot schema version
- snapshot hash

---

# 13. D-12 — Draft Export vs Confirmed Export

Draft Export:

~~~
Working State
  ↓
resolve current model
  ↓
export renderer
  ↓
download
~~~

확정 전에도 다운로드 가능하며 UI에 DRAFT 상태를 명확히 표시한다.

Confirmed Export:

~~~
runtime_document_archive
  ↓
frozen snapshot
  ↓
export renderer
  ↓
download
~~~

source DB를 재조회하지 않는다.

---

# 14. D-13 — Format-Neutral Export

모든 파일형식은 동일 Document State를 소비한다.

~~~
                 Resolved State
                      │
        ┌─────────────┼─────────────┐
        ↓             ↓             ↓
      PDF           DOCX          XLSX
    Renderer       Renderer       Renderer
        │             │             │
        └─────────────┼─────────────┘
                      ↓
                   Download
~~~

PDF renderer는 동일 모델의 print HTML을 거쳐 Gotenberg를 사용할 수 있다.

---

# 15. D-14 — Export On Demand

파일은 다운로드 요청이 있을 때만 만든다.

~~~
POST EXPORT
  ↓
resolve state/snapshot
  ↓
renderer(format)
  ↓
binary
  ↓
stream download
~~~

일반 다운로드의 기본은 transient generation이다.

하지 않음:
- 미리 파일 저장
- 모든 작성문서 파일화
- 모든 format 사전생성

---

# 16. D-15 — Persisted Artifact Exception

모든 다운로드 파일을 Storage에 영구보관하지 않는다.

다음처럼 exact binary 보존이 필요한 경우만 persisted artifact로 취급한다.

- 제출본 보관 정책
- 전자서명 완료본
- 외부기관 전송본
- 고객이 명시적으로 보관한 파일
- 감사/증빙 정책상 exact binary 필요

이 경우:

~~~
snapshot
  ↓
renderer
  ↓
binary
  ↓
Storage
  ↓
generated_document
~~~

로 기록한다.

---

# 17. D-16 — generated_document 역할

generated_document는 Document SoT가 아니다.

역할:
Persisted Output Artifact Registry.

GENERATED 정의는 다음이 모두 존재해야 한다.

~~~
snapshot_id
storage_path
artifact hash
actual object
generator_version
~~~

현재 DB의 chk_gd_generated_complete 방향을 유지한다.

현재 constraint는 NOT VALID이며 과거 legacy 9건이 위반 상태다.

Transient streaming download에는 generated_document=GENERATED row를 만들지 않는다.

실제 파일을 보관한 경우에만 Artifact Registry에 완료 row를 만든다.

---

# 18. D-17 — documents 테이블 역할

현재 documents는 generic file library다.

현재 실제 row 4건은 모두 견적서 파일이다.

따라서 소비자의 문서 리스트 SoT로 사용하지 않는다.

문서 리스트는 document catalog + runtime/snapshot 상태에서 만든다.

documents는 다음 용도로 제한한다.
- 사용자가 업로드한 파일
- persistent generated artifact
- 외부 증빙 첨부
- exact binary 보관본

---

# 19. D-18 — Consumer Document List Projection

소비자가 보는 문서 리스트는 파일목록이 아니다.

~~~
document_forms
   ↓
document_type_mapping
   ↓
document_type_registry
   ↓
runtime schema binding
   ↓
user/company/factory context
   ↓
working / confirmed state
   ↓
DOCUMENT LIST PROJECTION
~~~

각 item 최소 계약:
- document_key
- doc_id
- doc_name
- doc_type
- doc_detail
- availability
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

사용자 상태 예:
- 작성 가능
- 작성 중
- 확정
- 원본 제공
- 준비 중

내부 개발상태를 그대로 소비자에게 노출하지 않는다.

---

# 20. D-19 — Catalog vs Document Instance

Catalog:
지게차 점검표.

Instance:
2026-10-07 / 인천공장 / 지게차 01호 / 지게차 점검표.

관계:

~~~
Document Catalog
   ↓
Open/Create
   ↓
Document Instance
   ↓
Working State
   ↓
Confirmed Snapshot(s)
   ↓
Export(s)
~~~

---

# 21. D-20 — Canonical Internal Services

API route보다 서비스 계층을 먼저 단일화한다.

Catalog Service:
- list_available_documents()
- get_document_definition()

Resolve Service:
- resolve_working_document()
- resolve_confirmed_document()

Working State Service:
- open_or_create_document()
- save_document()
- submit_document()

Confirm Service:
- 기존 confirm_document_atomic() 재사용

Render Service:
- render_html(resolved_model)

Export Service:
- export_document(resolved_model, format)

Artifact Service:
- persist_export_artifact() — 보관이 필요한 경우만

---

# 22. D-21 — Legacy 3-Path Convergence

현재:

~~~
PATH 1
/document-engine/documents/{id}/generate
→ PENDING INSERT only

PATH 2
/documents/{doc_type}/generate
→ PDF stream

PATH 3
/document-forms/{doc_id}/generate
→ TBM PDF + documents save
~~~

목표는 API path를 한 번에 삭제하는 것이 아니다.

~~~
Legacy / Runtime API
Generic API
TBM API
      │
      ↓
Canonical Resolve Service
      ↓
Canonical Render / Export Service
      ↓
binary stream
      ↓
[optional persist]
~~~

기존 consumer를 단계적으로 canonical service에 연결한다.

OBJ02/OBJ03에서 소비자 전수확인 전 기존 route를 삭제하지 않는다.

---

# 23. D-22 — Current Runtime Generate 의미 변경

현재 POST /document-engine/documents/{id}/generate 는 PENDING row만 만든다.

목표 계약은 실제 export 결과를 반환하는 것이다.

비동기 Queue가 향후 필요할 경우 다운로드와 별도의 Job contract로 분리한다.

PENDING row 생성 자체를 사용자 파일 다운로드 완료로 취급하지 않는다.

---

# 24. D-23 — Authentication / Tenant Scope

문서 읽기/수정/확정/export는 company/factory scope를 강제한다.

기존 confirm authz의 원칙을 유지한다.
- authenticated current user
- company ownership
- factory ownership
- actor spoof 차단
- fail-closed

금지:
- body company_id 신뢰
- body actor_id 신뢰
- cross-company document exposure
- public signed URL 영구노출

---

# 25. D-24 — Legal Boundary

Document Engine은 문서 작성/렌더링 엔진이다.

판단하지 않는다.
- 이 사업장에 문서 의무가 있는지
- 책임주체가 누구인지
- 법 위반인지
- 제출 의무가 확정되는지

법적 적용성은 LEG가 담당한다.

Document Catalog의 법적 근거 metadata는 표시/연결 정보다.

---

# 26. D-25 — GPT Boundary

GPT는 canonical architecture의 필수 구성요소가 아니다.

후속 OBJ에서 자유서술 보조를 붙일 수 있다.

GPT가 들어가더라도:

~~~
Structured State
→ GPT draft field
→ Human edit/confirm
→ Working State
~~~

로만 동작한다.

GPT가 schema 변경, 법적 의무 판단, official form 구조 변경, confirm을 수행하지 않는다.

---

# 27. D-26 — Official Form

법정 고정양식도 소비자 진입은 동일하게 한다.

~~~
LIST
 → HTML View / 작성화면
 → Edit
 → Export
~~~

단 출력은 공식 서식 형식을 보존해야 한다.

가능한 delivery mode:
- OFFICIAL_ORIGINAL
- OFFICIAL_FILLABLE
- TAI_STANDARD
- TAI_GENERATED
- EXTERNAL_ONLY

공식 원본 자체가 HWP/XLSX/PDF인 경우 그 포맷을 그대로 제공할 수 있다.

---

# 28. D-27 — Export Format Capability

모든 문서가 모든 format을 지원할 필요는 없다.

문서별 supported_export_formats를 가진다.

예:
- TBM: HTML, PDF
- 위험성평가: HTML, PDF, XLSX
- 공식 별지: HTML, PDF, ORIGINAL_HWP

현재 DB의 generated_document export CHECK는 DOCX를 허용하지 않는다.

따라서 DOCX 등 신규 format은 별도 migration + renderer implementation + test 없이 활성화하지 않는다.

---

# 29. D-28 — Versioning

세 가지 버전을 구분한다.

Schema Version:
작성 필드 구조 버전.

Document Version:
사용자가 Confirm한 문서 버전.

Renderer Version:
PDF/DOCX/XLSX 생성기 버전.

확정 Snapshot은 최소 document_version, snapshot_schema_version, template_identity를 고정한다.

Persisted artifact는 추가로 generator_version, artifact_hash를 가진다.

---

# 30. D-29 — Canonical State Machine

기존 runtime_state_transition_rule을 상태 전이 SoT로 유지한다.

Export는 상태 전이와 별개다.

즉 DRAFT + export, APPROVED + export 둘 다 가능할 수 있다. 단 UI에서 status를 명확히 표시한다.

---

# 31. D-30 — Storage Policy

Working state:
DB only.

HTML View:
on-demand render.

Draft file export:
기본 streaming only.

Confirmed snapshot:
DB immutable state.

Confirmed file export:
기본 on-demand render.

Exact binary preservation required:
Storage + generated_document.

따라서 Document Count는 Stored File Count와 같지 않다.

---

# 32. Canonical Architecture

~~~
                          ┌──────────────────────┐
                          │   document_forms     │
                          │   Catalog SoT        │
                          └──────────┬───────────┘
                                     │ doc_id
                                     ↓
                          ┌──────────────────────┐
                          │document_type_mapping │
                          │Type/Detail Mapping   │
                          └──────────┬───────────┘
                                     │
                       ┌─────────────┴─────────────┐
                       ↓                           ↓
            document_type_registry        runtime_form_schema
             template / fetcher           field/check/evidence
                       │                           │
                       └─────────────┬─────────────┘
                                     ↓
                           SOURCE ASSEMBLY
                                     │
                                     ↓
                         RESOLVED DOCUMENT MODEL
                                     │
                    ┌────────────────┼─────────────────┐
                    ↓                ↓                 ↓
               HTML WEB VIEW   Working State       Confirm
                    │          runtime_document       │
                    │               _data             ↓
                    │                         runtime_document_archive
                    │                           Confirmed SoT
                    │                                │
                    └──────────────┬─────────────────┘
                                   ↓
                              EXPORT SERVICE
                     ┌─────────────┼─────────────┐
                     ↓             ↓             ↓
                    PDF          DOCX          XLSX
                     │             │             │
                     └─────────────┼─────────────┘
                                   ↓
                              STREAM DOWNLOAD
                                   │
                       [persist exact binary?]
                              YES / NO
                               │      │
                               ↓      └─→ end
                         Storage Object
                               ↓
                       generated_document
                        Artifact Registry
                               ↓
                         documents(optional)
                          File Library Index
~~~

---

# 33. Consumer Flows

FLOW-A — 새 문서 열기

~~~
문서 리스트
→ 문서 선택
→ Catalog/Mapping/Schema resolve
→ Source Assembly
→ HTML Web View
~~~

필요 시 first save에서 working instance 생성.

FLOW-B — 수정

~~~
HTML View
→ user edit
→ validation
→ runtime_document_data save
→ 다시 HTML render
~~~

파일 생성 없음.

FLOW-C — Draft Download

~~~
Working State
→ resolve current model
→ selected renderer
→ stream response
~~~

Storage write 기본 0.

FLOW-D — Confirm

~~~
Working State
→ submit/review
→ atomic confirm
→ immutable archive snapshot
~~~

파일 생성은 필수 아님.

FLOW-E — Confirmed Download

~~~
archive snapshot
→ selected renderer
→ stream response
~~~

원본 source DB 재조회 없음.

---

# 34. API Contract Direction

OBJ01에서는 최종 URL을 강제하지 않는다.

Canonical capability는 다음으로 고정한다.

- LIST
- GET VIEW
- SAVE
- CONFIRM
- EXPORT

권장 conceptual endpoints:

~~~
GET  /document-workspace
GET  /document-workspace/{ref}
PUT  /document-workspace/{ref}
POST /document-workspace/{ref}/confirm
POST /document-workspace/{ref}/export
~~~

실제 URL은 기존 route와 충돌/consumer 영향 검토 후 OBJ02/03에서 확정한다.

---

# 35. Current Asset → Target Role

| 현재 자산 | Target 역할 |
|---|---|
| document_forms | Catalog SoT |
| document_type_mapping | Catalog→Type mapping |
| document_type_registry | Renderer/Fetcher dispatch |
| runtime_form_schema | HTML/edit schema |
| runtime_field | field contract |
| runtime_checklist_item | checklist contract |
| runtime_evidence_field | evidence contract |
| runtime_document_data | Working State |
| runtime_document_archive | Confirmed SoT |
| runtime_document_approval | Confirm evidence |
| document_schema_renderer | confirmed deterministic evidence renderer 재사용 |
| services/document_engine/generator.py | export pipeline 재사용 후보 |
| services/document_engine/renderer.py | PDF renderer 재사용 후보 |
| generated_document | Persisted Artifact Registry |
| documents | Generic File Library only |
| eng:DOC | inbound digitization/migration, core export renderer 아님 |

---

# 36. Superseded / Deferred

폐기:
- PDF-first document model
- generated_document를 문서 본체로 사용
- documents를 소비자 문서목록 SoT로 사용
- 저장 시 자동 PDF 생성
- 모든 download Storage 영구보존
- doc_type별 독립 generator 증가
- 오래된 문서만 근거로 architecture 판정

보류:
- delta/voucher edit model
- partitioning
- 모든 format 동시 구현
- GPT writing
- eng:DOC output renderer 통합

---

# 37. OBJ02 Handoff

OBJ02를 Catalog ↔ Runtime Schema Binding & Document List Read Model로 수행한다.

목표:
1. 260 catalog와 현재 30 mapping coverage 계산
2. mapping 없는 230건 상태 분류
3. 30 mapping 각각의 runtime schema exact evidence 수집
4. APPROVED schema 1건과 catalog/type 관계 검증
5. document_type_mapping.runtime_form_schema_id 확장 가능성 검증
6. 필요한 상태/metadata 컬럼 최소안 설계
7. Document List Projection 계약 설계
8. DB migration은 GPT 승인 전 실행 금지
9. semantic/fuzzy 자동 binding 금지

OBJ02 완료 전:
- 323 CANDIDATE 승인 금지
- 260 bulk mapping 금지
- schema 자동생성 금지

---

# 38. OBJ03 Handoff

OBJ03 = Canonical Resolve / HTML View / Export Service.

핵심:
- 3-path internal convergence
- ResolvedDocumentModel
- render_html
- export(format)
- runtime generate stub 대체
- draft/confirmed resolver 분리
- transient export
- persisted artifact exception

---

# 39. OBJ01 Acceptance

다음이 모두 고정되면 PASS.

- Consumer list→HTML→edit→save→export contract
- file generated only on demand
- format-neutral document model
- Catalog SoT
- mapping SoT
- schema SoT
- working state SoT
- confirmed state SoT
- output artifact role
- file library role
- three-path convergence direction
- legal/GPT boundary
- explicit scope exclusions
- OBJ02 handoff scope

---

# 40. Final Decision

~~~
DOCUMENT PRODUCT MODEL
= WEB DOCUMENT FIRST

PRIMARY CONSUMER VIEW
= HTML

EDIT/SAVE
= STRUCTURED WORKING STATE

FILE GENERATION
= ON-DEMAND EXPORT ONLY

PDF/DOCX/XLSX
= SAME DOCUMENT MODEL / DIFFERENT RENDERERS

WORKING SoT
= runtime_document_data

CONFIRMED SoT
= runtime_document_archive

CATALOG SoT
= document_forms

TYPE MAPPING SoT
= document_type_mapping

RENDER/FETCH DISPATCH
= document_type_registry

SCHEMA SoT
= runtime_form_schema family

PERSISTED OUTPUT REGISTRY
= generated_document

GENERIC FILE LIBRARY
= documents

OLD DOC BLIND TRUST
= FORBIDDEN

NEW DOCUMENT ENGINE REBUILD
= NO
~~~

---

# 41. Status

~~~
OBJ00 = CLOSED FINAL
OBJ01 = DESIGN FIXED
OBJ01 IMPLEMENTATION = N/A
OBJ02 ENTRY = ALLOWED
PRODUCTION MUTATION = 0
~~~
