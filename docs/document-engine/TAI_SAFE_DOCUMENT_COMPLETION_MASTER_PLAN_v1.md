# TAI Safe Document Completion Master Plan v1

> 문서 ID: TAI-SAFE-DOCUMENT-COMPLETION-MASTER-PLAN-v1  
> 기준일: 2026-10-07  
> 상태: PLANNED / IMPLEMENTATION NOT STARTED  
> 방식: Object-based execution  
> 대상: TAI Safe SaaS 문서 모듈  
> 기준 저장소: taiengineering/tai-api + taiengineering/tai-admin  
> 연계: 45cminc/doc(eng:DOC)은 디지털화/마이그레이션 보조 엔진으로만 사용  
> Production mutation: 본 계획 문서 작성 시점 0  
> Owner Approval: 구현 Object별 별도 승인 필요

---

# 0. 목적

이 계획의 목표는 새 문서엔진을 만드는 것이 아니다.

이미 존재하는 다음 자산을 하나의 제품 경로로 완결한다.

- document_forms 260종 카탈로그
- form_templates 11종 법정 별지
- document_form_master 64종 표준/자유서식
- runtime_form_schema 324종
- runtime_field 1,308개
- runtime_checklist_item 802개
- runtime_evidence_field 202개
- document_type_registry 8종
- Jinja2 + Gotenberg 실제 PDF renderer
- inspection/tbm fetcher
- 문서 upload/list/download/storage 기능
- 서식작성 Vue UI
- 증빙이행 리포트 PDF 생성
- eng:DOC 파일 디지털화/OCR 자산

최종 사용자 경험은 다음과 같아야 한다.

```
문서 찾기
  ↓
서식 선택
  ↓
회사/사업장/설비/작업 데이터 자동반영
  ↓
필수입력/자유서술 작성
  ↓
미리보기
  ↓
PDF/DOCX 또는 공식원본 다운로드
  ↓
문서함 저장
  ↓
버전/확정본/증빙 관리
  ↓
검색·법령·SaaS 업무와 연결
```

---

# 1. 현재 기준선

## 1.1 Git anchors

- tai-api main: `aa46bbb7ed07416784f3310681540c9fce7eef92`
- tai-admin main: `94f2491c468df73d2a50e50551a51a5a6de44224`
- 45cminc/ui main: `a57d9fc7adc0f1e3459bae99014c524f3bf703b2`
- 45cminc/doc main: `218091f6adc0895294ac6c9da74f565e557084ea`

## 1.2 DB 실측

| 자산 | 건수 |
|---|---:|
| document_forms | 260 |
| form_templates | 11 |
| document_form_master | 64 |
| document_type_registry | 8 |
| runtime_form_schema | 324 |
| runtime_field | 1,308 |
| runtime_checklist_item | 802 |
| runtime_evidence_field | 202 |
| runtime_document_data | 1 |
| generated_document | 1,544 |
| documents | 4 |

상태 분포:

- runtime_form_schema: APPROVED_FOR_RUNTIME_USE 1 / CANDIDATE 323
- runtime_document_data: DRAFT 1
- generated_document: GENERATED 9 / PENDING 1,527 / FAILED 4 / TEMPLATE_MISSING 4

## 1.3 실제 생성 기반

Registry 8종:

- APPT — 선임보고 — NO_SOURCE
- CHK — 점검 체크리스트 — inspection fetcher
- CONLOG — 공사일지 — 신규 fetcher 필요
- EDU — 교육일지 — 신규 fetcher 필요
- EQUIP — 설비점검기록부 — inspection fetcher
- INSP — 안전점검일지 — inspection fetcher
- PPE — 보호구 착용 점검 — inspection fetcher
- TBM — 작업 전 안전점검회의 — tbm fetcher

실제 HTML 템플릿 파일:

- DOC-CHK.html
- DOC-EQUIP.html
- DOC-INSP.html
- DOC-OSH-056.html
- DOC-PPE.html
- DOC-COMPLIANCE-REPORT.html

## 1.4 현재 핵심 단절

### GAP-A: Catalog ↔ Runtime Schema binding 없음

`document_forms` 260건에 Runtime Schema를 직접 가리키는 안정적 key가 없다.

현재 프론트는 다음 필드 중 하나를 기대한다.

- form_schema_id
- runtime_form_schema_id
- schema_id

그러나 document_forms 실제 컬럼에는 없다.

### GAP-B: Runtime generate가 실제 파일을 생성하지 않음

`POST /document-engine/documents/{id}/generate`는 현재 `generated_document` row를 `PENDING`으로 INSERT할 뿐 실제 PDF/DOCX object를 만들지 않는다.

반면 `POST /documents/{doc_type}/generate`는 Jinja2 + Gotenberg로 실제 PDF byte를 생성한다.

즉 생성 경로가 이원화돼 있다.

### GAP-C: Frontend contract mismatch

서식작성 UI는 runtime generate 응답에서 다음 URL을 기대한다.

- pdf_url
- file_url
- signed_url
- download_url
- output_url

현재 runtime generate는 이를 반환하지 않는다.

### GAP-D: Runtime schema 승격 미완료

324개 schema 중 323개가 CANDIDATE다.

### GAP-E: 문서함 실사용 미연결

문서 관리 API는 존재하지만 documents 실제 row는 4건뿐이며 생성형 문서의 정식 저장/스냅샷 계약이 완결되지 않았다.

---

# 2. 전체 완료 정의

문서모듈은 다음이 모두 충족되어야 CLOSED FINAL이다.

1. 문서 카탈로그에서 선택 가능한 문서가 실제 생성 경로와 연결됨.
2. Runtime Schema와 Catalog의 안정 binding이 존재함.
3. 실제 PDF 생성이 단일 canonical output path를 사용함.
4. 생성 완료 상태는 실제 object 존재 이후에만 GENERATED로 기록됨.
5. preview/download/save가 동일 생성 계약을 사용함.
6. 회사/사업장 scope가 보장됨.
7. 확정본 문서는 immutable snapshot으로 저장 가능함.
8. 생성형 문서는 최신 운영데이터로 재생성 가능함.
9. 법정 별지 원본은 임의변형 없이 제공 가능함.
10. 자유서식/실무문서는 TAI 표준 템플릿으로 제공 가능함.
11. 문서별 source/법적 근거/version/retention metadata가 추적 가능함.
12. 260종 전체가 READY / PARTIAL / EXTERNAL_ONLY / NOT_AUTOMATABLE 등 명확한 상태를 가짐.
13. 통합검색에서 실무문서를 검색할 수 있음.
14. GPT는 보조작성만 하며 법적 적용성·의무판정은 하지 않음.
15. E2E QA와 Production evidence가 존재함.

---

# 3. Object 실행 구조

---

## OBJ00 — Baseline Freeze & Ownership Inventory

### 목적
문서 관련 모든 현재 자산과 소유권을 고정한다.

### 작업
- tai-api / tai-admin / DB / Storage / Gotenberg / Railway current state 수집
- 모든 문서 관련 Router/Service/Table/Template/UI inventory
- duplicate/legacy/archive 경로 분리
- canonical 생성 경로 후보 확정
- eng:DOC와 TAI Safe Document Engine boundary 고정

### 산출물
- CURRENT_STATE_EVIDENCE.md
- OWNERSHIP_MATRIX.md
- ROUTE_MATRIX.md
- TABLE_MATRIX.md
- TEMPLATE_MATRIX.md

### Gate
- 코드/DB mutation 0
- 모든 사용중/미사용/legacy 경로 분류 완료

### 완료판정
`OBJ00 = CLOSED`

---

## OBJ01 — Canonical Document Architecture

### 목적
문서 생명주기와 생성경로를 하나의 canonical architecture로 확정한다.

### 설계 결정 대상
- Catalog SoT
- Runtime Schema SoT
- Template Registry SoT
- Generated Output SoT
- Snapshot SoT
- Storage ownership
- preview/generate/download/save 계약
- official form vs generated form 경계

### 권장 원칙
```
Catalog
  ↓ binding
Runtime Schema
  ↓ data
Runtime Document
  ↓ render request
Canonical Generator
  ↓
Output Object
  ↓
Generated Document metadata
  ↓
Documents / Snapshot
```

### 금지
- 두 개의 독립 생성 엔진 유지
- PENDING row만 생성하고 성공 처리
- URL 없는 "GENERATED"
- UI가 backend 계약을 추측하는 fallback chain 유지

### 산출물
- DOCUMENT_CANONICAL_ARCHITECTURE_v1.md
- STATE_MACHINE_v1.md
- OUTPUT_CONTRACT_v1.md

### Gate
Owner architecture approval

---

## OBJ02 — Catalog ↔ Runtime Schema Binding

### 목적
260개 document_forms와 Runtime Schema를 안정적으로 연결한다.

### 작업
- 현재 260 catalog와 324 schema 비교
- exact match 기준 수립
- alias/semantic 자동 확정 금지
- 1:1 / 1:N / N:1 / unbound 분류
- binding 테이블 또는 canonical FK 설계
- candidate binding → human approved binding lifecycle
- frontend가 임의 field fallback을 하지 않고 canonical binding을 사용

### 권장 상태
- UNMAPPED
- CANDIDATE
- REVIEWED
- APPROVED
- DEPRECATED

### 산출물
- DOCUMENT_SCHEMA_BINDING_MATRIX.csv
- BINDING_CONTRACT.md
- migration
- API patch
- frontend patch

### Acceptance
- document_forms 260건 모두 mapping status 보유
- APPROVED row만 runtime 생성 가능
- unknown/ambiguous mapping fail-close

---

## OBJ03 — Canonical Output Generation

### 목적
실제 파일 생성 경로를 하나로 만든다.

### 현재 문제
- runtime generate = metadata PENDING
- generic generator = 실제 PDF byte
- frontend = URL 기대

### 작업
- `/document-engine/documents/{id}/generate`와 실제 renderer 통합
- 기존 `services/document_engine/generator.py` 재사용
- Gotenberg output 생성
- storage upload
- object 존재 검증
- sha256/content length/mime 검증
- generated_document GENERATED 승격
- signed URL 반환
- idempotency key
- retry-safe
- failure state 기록

### 출력 계약 예
```json
{
  "generation_id": "...",
  "runtime_document_id": "...",
  "status": "GENERATED",
  "mime_type": "application/pdf",
  "storage_ref": "...",
  "sha256": "...",
  "file_size": 12345,
  "download_url": "...",
  "template_version": "...",
  "generated_at": "..."
}
```

### Acceptance
- object 미생성 상태에서 GENERATED 0
- 실제 PDF magic bytes 검증
- preview/download 둘 다 동일 canonical renderer 사용
- 동일 request retry 시 중복 폭주 없음

---

## OBJ04 — Document Library & Snapshot Lifecycle

### 목적
생성된 문서를 실제 SaaS 문서함과 연결한다.

### 문서 두 종류

#### A. Regenerable Document
운영데이터 기반으로 언제든 최신 재생성.

예:
- 점검일지
- 설비점검
- TBM
- 증빙리포트

#### B. Frozen Document
특정 시점의 제출/승인/확정 사실.

예:
- 제출본
- 승인본
- 사고조사 확정본
- 서명 완료본

### 작업
- generated output → documents 연결
- snapshot metadata
- storage_ref
- source trace
- template version
- runtime data hash
- immutable final state
- retention policy
- expiry metadata
- soft delete / legal hold 검토

### Acceptance
- 생성 → 문서함 → signed download E2E PASS
- frozen snapshot 재생성 없이 동일 hash 유지
- company scope isolation PASS

---

## OBJ05 — Core Template Pack Completion

### 목적
현재 준비된 A급/핵심 문서를 먼저 실사용 수준으로 완성한다.

### 1차 대상
- INSP
- CHK
- EQUIP
- TBM
- PPE
- COMPLIANCE REPORT

### 2차 대상
- APPT
- CONLOG
- EDU

### 작업
- field completeness
- Korean print layout
- A4 page break
- company/factory metadata
- signature/approval placeholders
- source/legal basis footer
- template version
- sample fixtures
- PDF visual QA

### Acceptance
각 유형:
- preview PASS
- PDF PASS
- required field PASS
- empty state PASS
- long text overflow PASS
- Korean font/render PASS

---

## OBJ06 — Official Form Channel

### 목적
법정 별지 등 공식 양식을 임의 변경하지 않고 사용할 수 있게 한다.

### 원칙
- 국가기관 공식 HWP/PDF/Excel 원본 우선
- 원본 출처 URL 기록
- 법령/별표/별지 version 기록
- TAI가 official form body를 임의 재설계하지 않음
- 자동입력이 필요한 경우 overlay/fill strategy를 별도 검증

### 사용자 기능
- 공식원본 다운로드
- 작성 안내
- 제출기관/방법/시기
- 법적 근거
- 가능하면 TAI 자동입력본 별도 제공

### Acceptance
- source provenance 100%
- outdated version detection
- official/original vs TAI-generated 명확 구분

---

## OBJ07 — GPT Assisted Writing Layer

### 목적
법적 판정이 아닌 자유서술 작성시간을 줄인다.

### GPT 허용
- 작업절차 초안
- 위험요인 서술 초안
- 통제조치 서술 보조
- 비상조치 문장 초안
- 교육내용 초안
- 문서 설명문 초안

### GPT 금지
- 문서 의무 여부 판단
- 법적 책임주체 확정
- 공식 필수항목 삭제/추가
- 법정 별지 형식 변형
- 승인 자동화
- 근거 없는 값 생성

### 입력 우선순위
1. SaaS existing data
2. approved document schema
3. approved legal/source metadata
4. user input
5. GPT only for remaining narrative field

### 상태
- AI_DRAFT
- HUMAN_EDITED
- HUMAN_CONFIRMED

### Acceptance
- AI 값과 source value 구분 가능
- user confirmation 전 final 처리 금지
- prompt/model/version trace 저장

---

## OBJ08 — Member Document UX

### 목적
현재 서식작성 화면을 실제 사용 가능한 제품으로 완결한다.

### 화면
1. 문서 찾기
2. 문서 상세
3. 자동작성 가능 여부
4. 사업장/설비/작업 선택
5. 동적 필드
6. 자동입력 표시
7. GPT 보조작성
8. Preview
9. Download
10. Save to Document Library
11. History

### UX 원칙
- 260개를 평면 목록으로 던지지 않음
- 사용자 업무/설비/작업/법적근거로 좁힐 수 있음
- "왜 필요한 문서인지" 표시
- "우리 회사에 의무인지"는 LEG CTA로 분리
- 자동작성 가능/부분가능/원본다운로드만 가능 상태 표시

### Acceptance
모바일/데스크톱 핵심 시나리오 PASS

---

## OBJ09 — Security / Scope / Audit / Quality Gate

### 목적
문서가 실제 증빙으로 사용될 수 있는 최소 신뢰조건을 만든다.

### 검증
- Auth
- company scope
- factory scope
- RLS/API ownership
- signed URL expiry
- storage path isolation
- generated object integrity
- audit trail
- status transition
- human approval
- template version
- source trace
- stale legal source
- PII exposure

### Acceptance
- cross-company access = 0
- anonymous protected download = 0
- generated output without trace = 0
- invalid transition = 0

---

## OBJ10 — 260 Catalog Completion Program

### 목적
260종 전체를 "등록만 된 목록"에서 제공 가능한 제품 자산으로 전환한다.

### 각 문서 상태

```
DOWNLOAD_READY
AUTOFILL_READY
PARTIAL_AUTOFILL
TEMPLATE_NEEDED
FETCHER_NEEDED
OFFICIAL_SOURCE_ONLY
EXTERNAL_SUBMISSION_ONLY
NOT_AUTOMATABLE
DEPRECATED
REVIEW_REQUIRED
```

### 우선순위
P0:
- 자주 사용하는 공통 실무문서
- SaaS existing data로 자동화 가능한 문서

P1:
- 설비/작업 특화 핵심문서
- 공식 별지

P2:
- 업종 특화
- 낮은 빈도

P3:
- 외부 전문작성자/기관 의존

### 완료 정의
260개 모든 row가:
- 상태
- source
- schema binding
- delivery method
- automation level
- validation status
를 가진다.

---

## OBJ11 — Integrated Search Document Connection

### 목적
문서모듈을 통합검색의 핵심 차별축으로 연결한다.

### Search result type
`DOCUMENT`

### 검색 결과 metadata
- 문서명
- 문서유형
- 관련 설비/작업/위험
- 법적근거
- source authority
- official/TAI template
- download availability
- autofill availability
- SaaS CTA

### 예
```
검색: 지게차

정보
- 법령
- KOSHA
- 사고사례
- 안전자료

실무문서
- 지게차 작업계획서
- 작업전 점검표
- 설비점검기록
- 위험성평가 관련양식
```

### SEO
승인된 문서 상세페이지는 검색엔진 index 대상 검토 가능.
자유생성 개인 문서는 index 금지.

### Acceptance
Search → Document → SaaS funnel 측정 가능

---

## OBJ12 — Production E2E & Closeout

### 대표 E2E

E1. 회원 → 문서검색 → 빈양식 다운로드  
E2. 회원 → 사업장 선택 → 자동작성 → PDF 다운로드  
E3. SaaS → 기존 점검데이터 → 점검일지 생성  
E4. TBM → PDF → 문서함 저장 → 재다운로드  
E5. 공식 별지 → 원본 다운로드  
E6. GPT 보조필드 → Human confirm → 생성  
E7. 다른 회사 문서 접근 차단  
E8. 템플릿 누락 fail-close  
E9. renderer 장애 시 FAILED 기록  
E10. 동일 요청 retry idempotency  
E11. frozen snapshot 동일 hash  
E12. Search → Document 상세 → SaaS CTA

### Closeout Evidence
- Git SHA
- migration list
- DB counts
- template manifest
- API contract test
- generated file hashes
- storage evidence
- frontend build
- production deployment identity
- E2E report
- rollback plan

### 최종 판정
```
DOCUMENT MODULE CLOSED FINAL = YES
```
는 OBJ00~OBJ12 모두 PASS일 때만 선언한다.

---

# 4. Object dependency

```
OBJ00
 ↓
OBJ01
 ↓
OBJ02 ─────────────┐
 ↓                 │
OBJ03              │
 ↓                 │
OBJ04              │
 ↓                 │
OBJ05 ─→ OBJ06     │
 ↓                 │
OBJ07              │
 ↓                 │
OBJ08              │
 ↓                 │
OBJ09              │
 ↓                 │
OBJ10              │
 ↓                 │
OBJ11              │
 ↓                 │
OBJ12              │
 └─────────────────┘
```

OBJ06는 OBJ05와 일부 병렬 가능하지만, production publication은 OBJ09 이후.

---

# 5. 구현 우선순위

## Release 1 — Working Core
OBJ00~OBJ05

목표:
- 현재 5개 핵심유형이 실제로 작성/preview/download/save 가능
- 생성경로 통합
- schema binding 완성

이 단계만 끝나도 실사용 베타 가능.

## Release 2 — Usable Library
OBJ06~OBJ09

목표:
- 공식양식
- GPT 보조작성
- 회원 UX
- 보안/감사

## Release 3 — Full Catalog
OBJ10

목표:
- 260종 상태 정리
- 우선순위별 확장

## Release 4 — Acquisition Connection
OBJ11~OBJ12

목표:
- 통합검색과 연결
- Search → Document → SaaS conversion 측정

---

# 6. 하지 않는 것

- eng:DOC의 placeholder PDF renderer를 TAI Safe 생성경로로 사용하지 않는다.
- 260개 템플릿을 한 번에 만들지 않는다.
- 323 CANDIDATE schema를 일괄 APPROVED 하지 않는다.
- GPT가 법령 적용성을 판단하게 하지 않는다.
- 문서별 별도 전용 generator를 계속 늘리지 않는다.
- frontend에서 backend response를 추측하는 fallback을 유지하지 않는다.
- 생성 성공 이전에 GENERATED를 기록하지 않는다.
- 원본 법정 양식을 TAI 디자인으로 임의 변경하지 않는다.
- 검색용 문서와 private customer document를 같은 index 정책으로 다루지 않는다.

---

# 7. 역할 분담

## GPT
- 분석
- 설계
- Object 정의
- 작업지시
- semantic 판정
- 독립검증
- PASS/FAIL 판정

## Claude Code
- 조사
- 코드 실행
- 구현
- 테스트 실행
- 증거수집
- PR 생성 준비

Claude Code는 architecture/semantic 결정을 하지 않는다.

## Owner
- 정책결정
- Scope 승인
- Human Review
- Production 승인

---

# 8. 첫 실행 작업

다음 실제 작업은 **OBJ00 Read-Only Discovery**다.

Production DB/code mutation 없이 다음을 다시 수집한다.

1. 모든 문서 관련 routes/services/templates
2. 260 document_forms full export
3. 324 runtime_form_schema full export
4. binding 가능한 exact identifiers
5. generated_document 1,544건 provenance
6. documents/storage 현황
7. Gotenberg production health
8. tai-admin 실제 route/menu exposure
9. Railway deployment identity
10. legacy vs active paths

OBJ00 증거를 GPT가 독립검증한 뒤 OBJ01 architecture를 확정한다.

---

# 9. 성공 시 제품 형태

최종적으로 TAI 문서기능은 다음 세 레벨을 제공한다.

### Level 1 — Free/Member Asset
실무 표준양식/공식원본 검색·다운로드

### Level 2 — SaaS Automation
사업장·설비·작업·점검 데이터 자동주입

### Level 3 — Enterprise/SI
자사 양식, 결재, ERP/그룹웨어, migration, custom workflow

통합검색은 Level 1 유입을 만들고,
문서 자동화가 Level 2 전환을 만들며,
고객 고유문서 요구가 Level 3 SI로 연결된다.

---

# 10. 최종 원칙

> **새 문서엔진을 만들지 않는다. 이미 만들어진 TAI 문서 자산을 하나의 canonical path로 완결한다.**

> **문서의 수보다 실제로 바로 작성·다운로드·보관할 수 있는 비율을 KPI로 둔다.**

> **법령엔진은 필요 여부를 판단하고, 문서엔진은 검증된 형식으로 문서를 만든다. GPT는 작성만 보조한다.**
