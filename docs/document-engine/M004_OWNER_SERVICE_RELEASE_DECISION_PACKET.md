# M004 Owner Service Release Decision Packet

> WO: WO-TAI-M004-AUTO-WEB-SERVICE-RELEASE-GATE-001  
> 작성일: 2026-10-22  
> 작성자: Claude Code (실행) — GPT 독립검증 대기  
> 상태: FORM_CONFORMANCE_MAINLINE_001_APPLIED / WEB_REQUIREDNESS_GATE_001_APPLIED / REQUIREDNESS_CORR-001_APPLIED / ACTIVATION_PILOT_001_TECHNICAL_READY / ACTIVATION_PILOT_CORR-001_APPLIED / ACTIVATION_PILOT_CORR-002_APPLIED / GPT_IV_PENDING / OWNER_GATE_PENDING  
> R1 정정 (2026-10-22): D1=LEGAL_FORM_CLASS 추가 / D2=AUTO_FORM 135→133 정정 / D3=C-3 삭제 / D4=SCHEMA_REVIEW_CANDIDACY→FORM_CONFORMANCE_STATUS  
> WO-MAINLINE (2026-10-22): CORR-A 오류 정정 + FORM_CONFORMANCE 260건 판정 + SCHEMA_PROMOTION_READY 24건 확인  
> WO-WEB-REQUIREDNESS-GATE-001 (2026-10-22): NON_LEGAL+증빙없음+서명없음 65종 318필드 필수여부 계약 분석 완료  
> REQUIREDNESS-CORR-001 (2026-10-22): OPTIONAL→NOT_REQUIRED(87건) / DOC-SERA-011 multi_row BLOCKED / 318필드 input_type DB 실증 완료  
> ACTIVATION-PILOT-CORR-001 (2026-10-22): ISOLATION_CONFIRMED_FRONTEND_NOT_WIRED / P8+G4 precondition 추가 / review_comment 교정 / conditional rollback guard 추가
> ACTIVATION-PILOT-CORR-002 (2026-10-22): CORR-001 격리 주장 교정 — ISOLATION_CONFIRMED_FORM_SCHEMA_ID_NOT_WIRED / P4B+P9+G5+F5 추가 / rollback audit guard 추가 / PRJ Step4D 경로 명시  
> 기준 데이터: 기존 스냅샷 + R2 binding + R3 handoff 수치 재사용. DB SELECT 0건 추가 수행.  
> 변경: NEW_CODE=0 / PROD_DB_WRITE=0 / MIGRATION=0 / PR=0 / MERGE=0 / DEPLOY=0

---

## 통합 수치 요약

| 항목 | 수치 |
|---|---|
| SaaS 카탈로그 (ACTIVE) | 260 |
| 스키마 연결 (catalog_document_id via source_trace) | 260 / 260 |
| 스키마 APPROVED_FOR_RUNTIME_USE (catalog 연결) | **0** |
| 스키마 CANDIDATE | 260 |
| R2 필드 바인딩 (catalog-linked) | 1,246 |
| R2 EXACT_CONTRACT | 2 (DOC-BLD-020/address, DOC-OSH-049/work_location) |
| effective_safe (GPT IV override 후) | **0** |
| R3 타입 호환 후보 | 225 (handoff 기준) |
| R3 타입 갭 | 35 (handoff 기준) |
| AUTO_SOURCE 코드 존재 (inspection/TBM) | 35 |
| WEB SCHEMA GATE: FORM_CONTRACT_UNVERIFIED (no LEG) | 95 |
| WEB SCHEMA GATE: FORM_CONTRACT_UNVERIFIED + LEG_GATE | 111 |
| WEB SCHEMA GATE: NOT_APPLICABLE (AUTO_SOURCE 별도 트랙) | 35 |
| WEB SCHEMA GATE: FORM_CONTRACT_UNVERIFIED (schema UNVERIFIED) | 19 |
| LEG Gate 필요 (has_legal_form=True) | 138 |
| 고객 자동입력 허용 | **0** |

---

## Gate 상태 요약

| Gate | 현재 상태 | 근거 |
|---|---|---|
| G1 서비스 모드 | 260종 전부 OWNER_PENDING 또는 NOT_VERIFIED | 문서별 Owner 승인 목록 없음. tai_auto/doc_format은 모드 확정 근거 아님 |
| G2 WEB 스키마 | **ALL BLOCKED** — CANDIDATE 260/260 | APPROVED+catalog-linked 0건. 고객 WEB 작성 차단 |
| G3 AUTO 안전 | **effective_safe=0** | R2 EXACT_CONTRACT 2건도 GPT IV 보류. AUTO_SOURCE 35건은 별도 코드 경로 존재하나 고객 활성화 BLOCKED |
| Gate A | DIRECT_RUNTIME_CREATE: 코드 경로 가능 (catalog-미연결 승인 스키마 1건) | 운영 LIVE E2E 미검증 |
| Gate B | CATALOG_READY_FOR_EDIT: **BLOCKED** | 0 APPROVED catalog-linked |
| Gate C | LEGAL_FORM_RELEASE: **BLOCKED** | doc_rule_mapping 227건 PENDING; FORM647 BLOCKED |
| Gate D | BUSINESS_OCCURRENCE_LINK: DESIGN_GAP | PRE_WORK 계약 미확정 |

---

## A. 증거 기반 확정 항목 (Owner 추가 조사 불필요)

### A-1. AUTO_SOURCE 점검·TBM 코드 존재 확인

| doc_type | 코드 상태 | 제한 |
|---|---|---|
| Inspection (CHK/INSP/PPE/EQUIP) | InspectionFetcher 코드 존재. INFRA_PRESENT=PASS | runtime_data_json 우회. 신규 경로(_FETCHERS dict) 미등록. auto_document_preview/pdf 라우터 별도 존재 |
| TBM DOC-OSH-056 | TbmFetcher OLD path 등록됨 | 프론트엔드 미연결. runtime_data_json 우회. generate 구 경로만 |
| TBM DOC-CON-012 | _FETCHERS 미등록 | BLOCKED |

**결론:** AUTO_SOURCE 코드는 존재하나 현재 고객 서비스로 직접 연결되지 않음. 단위 테스트 격리 증거만 있음 (PR #678 208/208 PASS).

### A-2. WEB 엔진 코드 존재 확인

- `document_engine_api.py` CREATE/UPDATE/RENDER/PDF 엔드포인트 존재
- `document_engine_svc.py` PATCH merge, CANDIDATE 차단, 감사 로그
- Vue 편집기 (`useDocumentFormsEditor.ts`) 5중 게이트 유지
- 208개 테스트 PASS (PR #678)

**결론:** 엔진 코드는 완전히 구현됨. 차단 원인은 코드 누락이 아닌 스키마 승인 게이트.

### A-3. R2 EXACT_CONTRACT 2건 (재활성화 금지)

| doc_id | field | R2 분류 | GPT IV 결과 |
|---|---|---|---|
| DOC-BLD-020 | address | EXACT_CONTRACT | effective_safe=False (GPT override) |
| DOC-OSH-049 | work_location | EXACT_CONTRACT | effective_safe=False (GPT override) |

**결론:** R2 GPT 보류 그대로 유지. 이 2건을 자동입력 허용으로 처리 금지. 별도 Owner 재검토 후에만 변경 가능.

---

## B. Owner 승인 필요 항목

### B-1. WEB 스키마 승인 — 95건 (LEG gate 없음)

**설명:** 다음 조건을 모두 충족하는 문서

- LEGAL_FORM_CLASS = NON_LEGAL (has_legal_form=False)
- AUTO_SOURCE 별도 트랙 아님 (FORM_CONFORMANCE_STATUS ≠ NOT_APPLICABLE)
- doc_format ≠ ORIGINAL_ONLY
- field_count > 0

**차단 원인:** 스키마 CANDIDATE. `CANDIDATE → APPROVED_FOR_RUNTIME_USE` 전환에 Owner+PRJ Gate 필요.

**FORM_CONFORMANCE_STATUS:** 95건 전부 `FORM_CONTRACT_UNVERIFIED`  
(required_fields 존재, 스키마 있음 — 필드 키 수준 대조는 R2 ZIP 96d71937 기반 별도 검증 필요)

**Owner 결정 필요 내용:**  
> Owner 역할: 운영 변경 승인 + 고객 서비스 공개 승인. 기술 정합 증거는 FORM_CONFORMANCE_EVIDENCE.csv 참조.

1. 이 95건 중 실제 웹 편집 서비스를 제공할 문서 ID 확정 (증거 기반: FORM_CONFORMANCE_STATUS 확인 후)
2. 각 문서의 스키마 승인 기준 (필드 구성, 편집기 호환성 여부)
3. 개별 승인 시 PRJ Gate를 통한 DB 변경 승인

**참고 파일:** `M004_WEB_SCHEMA_APPROVAL_MATRIX.csv` — FORM_CONFORMANCE_STATUS = FORM_CONTRACT_UNVERIFIED (LEG_GATE_REQUIRED = NO)

### B-2. WEB 스키마 승인 — 111건 (LEG gate 추가 필요)

**설명:** LEGAL_FORM_CLASS ≠ NON_LEGAL인 문서. 스키마 승인 외에 법령 게이트 별도 필요.

**차단 원인:**
1. 스키마 CANDIDATE (B-1과 동일)
2. 법정서식: LEG Gate 미충족 (doc_rule_mapping 전건 PENDING, FORM647 BLOCKED)

**FORM_CONFORMANCE_STATUS:** 111건 전부 `FORM_CONTRACT_UNVERIFIED`  
(required_fields 존재, 스키마 있음 — 필드 키 수준 대조는 R2 ZIP 96d71937 기반 별도 검증 필요)

**Owner 결정 필요 내용:**
1. 법정서식 WEB 제공 시 LEG Gate를 어떻게 처리할 것인가
2. 법령 검증 완료 전 임시 WEB 제공 가능 여부 (현재 정책상 BLOCKED)
3. Gate C 해소 경로 (LEG + PRJ 공동 승인 필요)

**참고 파일:** `M004_WEB_SCHEMA_APPROVAL_MATRIX.csv` — FORM_CONFORMANCE_STATUS = FORM_CONTRACT_UNVERIFIED (LEG_GATE_REQUIRED = YES)

### B-3. AUTO_SOURCE 고객 연결 승인 — 35건

**설명:** inspection/TBM 소스 신호를 가진 35개 문서. 코드 경로 존재.

**차단 원인:**
- 프론트엔드 미연결 (auto_document_preview/pdf 라우터가 고객 UI에 노출되지 않음)
- runtime_data_json 우회 경로: WEB 편집과 동일 스키마 공유 불가

**Owner 결정 필요 내용:**
1. 점검/TBM AUTO_SOURCE 결과를 고객에게 어떤 경로로 제공할 것인가
2. 기존 `/auto-document-preview`, `/auto-document-pdf` 라우터 노출 승인 여부
3. AUTO_SOURCE 문서와 WEB 문서의 동일 스키마 공유 정책

**참고 파일:** `M004_AUTO_SAFETY_GATE.csv` — OVERALL=AUTO_SOURCE_CODE_EXISTS_CUSTOMER_BLOCKED

### B-4. AUTO_FORM 법정 자동입력 — 133건 (tai_auto=True 중 R2 UNVERIFIED)

**수치 정정 (D2):**

| 구분 | 건수 |
|---|---|
| tai_auto=True 전체 | 134 |
| tai_auto=False 전체 | 126 |
| R2 EXACT_CONTRACT 중 tai_auto=True | 1 (DOC-OSH-049/work_location) |
| R2 EXACT_CONTRACT 중 tai_auto=False | 1 (DOC-BLD-020/address) |
| tai_auto=True UNVERIFIED (미확정) | **133** (= 134 − 1 EXACT) |

**설명:** tai_auto=True 134건 중 R2 EXACT_CONTRACT 1건(GPT 보류 중) 제외 133건.  
R2 EXACT_CONTRACT 2건 모두 effective_safe=False (A-3 참조) — 자동입력 차단 유지.

**차단 원인:** R2 binding = UNVERIFIED. effective_safe=0 전체 유지.

**Owner 결정 필요 내용:**
1. tai_auto=True 134건 중 실제 자동입력 바인딩 재검증 대상 선정
2. R2 재검증 범위 및 GPT IV 재제출 경로
3. 자동입력 허용 기준 (어떤 소스 바인딩이 sufficient한가)

---

## C. 구현 결함 항목

### C-1. ~~catalog_document_id FK 미설정~~ — GPT IV 정정: 이미 연결 완료

**GPT IV 정정 (2026-10-22):**  
GPT가 운영 TAI Supabase DB를 직접 SELECT한 결과, `runtime_form_schema.catalog_document_id`는 260/260 연결 완료 상태.  
Claude 분석에 사용한 `obj00/RUNTIME_FORM_SCHEMA_324_SNAPSHOT.csv`는 FK 연결 이전 시점의 스냅샷이었음.

**현황 (DB 실측):**
- `runtime_form_schema.catalog_document_id` 연결: 260 / 260
- `catalog_resolver.py`의 `.eq("catalog_document_id", catalog_document_id)` 쿼리 정상 동작 가능
- Gate B 차단 원인: FK 부재가 아닌 **스키마 status = CANDIDATE** (0 APPROVED)

**수정 필요 여부:** DB Migration 불필요. FK는 이미 연결됨.  
**실제 차단 원인:** 스키마 상태 승격 (CANDIDATE → APPROVED_FOR_RUNTIME_USE) 만 필요.

**Owner 결정:** 개별 스키마 상태 승격 대상 문서 ID 목록 확정 후 DB 상태 변경 실행 가능 (Migration 없음, UPDATE 단 건 처리).

### C-2. WEB_EDIT 채널 BLOCKED (catalog_aggregator.py)

**현황:** `catalog_aggregator.py`의 WEB_EDIT 채널 로직은 스키마 승인 + 사업장 권한을 검증. 현재 승인 스키마 0건 → 260종 전부 WEB_EDIT=BLOCKED.

**영향:** 관리자 카탈로그 UI에서 WEB_EDIT=BLOCKED로 표시됨. 정상 동작.

**수정 불필요:** 차단이 정상. 스키마 승인 완료 시 자동 해제됨.

---

## 통합 차단 상태 (문서 ID별)

| 상태 | 건수 | 설명 |
|---|---|---|
| WEB READY | 0 | CANDIDATE 스키마 0 APPROVED |
| WEB FORM_CONTRACT_UNVERIFIED (LEG gate 없음) | 95 | 스키마 승인만 필요. LEGAL_FORM_CLASS=NON_LEGAL |
| WEB FORM_CONTRACT_UNVERIFIED (LEG gate 필요) | 111 | 스키마 + LEG Gate. LEGAL_FORM_CLASS≠NON_LEGAL |
| WEB NOT_APPLICABLE (AUTO_SOURCE 별도 트랙) | 35 | 점검/TBM 별도 경로 |
| WEB FORM_CONTRACT_UNVERIFIED (schema UNVERIFIED) | 19 | schema 증거 부족 |
| AUTO_SOURCE 고객 연결 BLOCKED | 35 | 코드 있음, 프론트 미연결 |
| AUTO_FORM UNVERIFIED (tai_auto=True, R2 미확정) | 133 | 바인딩 미확립 (D2 정정) |
| AUTO_FORM NOT_APPLICABLE (tai_auto=False) | 126 | auto 신호 없음 |
| AUTO_FORM OWNER_PENDING (R2 EXACT → GPT override) | 2 | effective_safe=False (A-3) |
| CUSTOMER_AUTOFILL_PERMITTED | 0 | 전건 NO |

> 하나의 문서가 WEB과 AUTO 양쪽 항목에 중복 포함될 수 있으므로 합계 ≠ 260.

---

## Owner 즉시 결정 요청 항목 (우선순위 순)

| 순위 | 결정 ID | 내용 | 산출물 참조 |
|---|---|---|---|
| P1 | B-1-SCHEMA | WEB 95건 중 첫 승인 대상 doc_id 선정 | M004_WEB_SCHEMA_APPROVAL_MATRIX.csv — FORM_CONFORMANCE_STATUS=FORM_CONTRACT_UNVERIFIED, LEG_GATE_REQUIRED=NO |
| P2 | B-3-AUTO | AUTO_SOURCE 점검/TBM 고객 연결 경로 결정 | M004_AUTO_SAFETY_GATE.csv |
| P3 | B-2-LEG | 법정서식 111건 LEG Gate 경로 확정 | LEG 협의 필요. LEGAL_FORM_CLASS 분포: DIGITAL=88, COPY=31, ORIGINAL=19 |
| P4 | B-4-AUTO2 | tai_auto=True 133건(D2 정정) R2 재검증 범위 | R2 ZIP 96d71937 기반 |
| ~~P3~~ | ~~C-1-FK~~ | ~~catalog_document_id Migration 승인~~ | **GPT IV 정정: FK 이미 연결됨, Migration 불필요** |

---

## D. 입력폼 정합성 검증 결과 (WO-TAI-M004-FORM-CONFORMANCE-MAINLINE-001)

| 항목 | 수치 | 근거 |
|---|---|---|
| FORM_CONFORMANCE_PASS | **24** | P0 Wave 1+2 field_key 완전 일치 (WO-DOC-OBJ02-C1-P0-CANDIDATE-QUALITY-AUDIT-001) |
| FORM_CONTRACT_UNVERIFIED | **236** | P0 외: runtime field_key 데이터 없음 (필드 수 일치 확인됨, 키 수준 미검증) |
| FORM_REFERENCE_MISSING | **0** | 260건 전부 required_fields 존재 |
| NOT_APPLICABLE (G2) | **11** | 비P0 AUTO_SOURCE (WEB 제공 범위 미확정) |
| SCHEMA_PROMOTION_READY | **24** | FORM_CONFORMANCE_PASS 전건. PRJ 운영 변경 승인 별도 필요 |
| SCHEMA_PROMOTION_BLOCKED | **0** | P0 중 LEGAL_ORIGINAL_ONLY 없음 |
| SCHEMA_PROMOTION_UNVERIFIED | **236** | FORM_CONTRACT_UNVERIFIED 전건 |

**SCHEMA_PROMOTION_READY 24건:** P0 Wave 1+2 (CHK/INSP/PPE/EQUIP/TBM). PRJ Gate 운영 변경 승인 후 `runtime_form_schema.status CANDIDATE → APPROVED_FOR_RUNTIME_USE` 가능. 운영 DB DDL/DML 금지 유지.

**FORM_CONFORMANCE_EVIDENCE:** `docs/document-engine/M004_FORM_CONFORMANCE_EVIDENCE.csv` (260행, 24컬럼)

---

## E. 웹 편집기 필수여부 게이트 분석 결과 (WO-TAI-M004-WEB-REQUIREDNESS-GATE-001 + CORR-001)

**대상 코호트:** NON_LEGAL + evidence_count=0 + signature 필드 없음 = **65종 / 318필드**

| 항목 | 수치 | 비고 |
|---|---|---|
| 분석 대상 문서 | 65 | BUILDING=7, COMMON=20, INDUSTRIAL=6, CONSTRUCTION=26, SPECIAL_FACILITY=6 |
| 분석 대상 필드 | 318 | 65종 전체 필드 |
| REQUIRED_BY_HUMAN 후보 | 231 | SOURCE is_mandatory=True 필드 |
| NOT_REQUIRED 후보 | 87 | SOURCE is_mandatory=False 필드 (CORR-001: OPTIONAL→NOT_REQUIRED) |
| 타입 지원 PASS (RUNTIME_VERIFIED) | 290 | text=259, textarea=31. 운영 DB 실증 기준 |
| 타입 지원 PASS (P0_VERIFIED) | 27 | P0 코호트 필드 (C2B E2E B3 근거 포함) |
| 타입 지원 BLOCKED | 1 | DOC-SERA-011 / submitted_document_list (multi_row — 미지원) |
| TYPE_COMPATIBLE_DOCS | 64 | DOC-SERA-011 제외 |
| TYPE_BLOCKED_DOCS | 1 | DOC-SERA-011 (multi_row 별도 타입 계약 필요) |

**input_type 실증 결과 (운영 DB SELECT, CORR-001 실행):**

| input_type | 건수 | 편집기 지원 (SUPPORTED_FIELD_TYPES) | 판정 |
|---|---|---|---|
| `text` | 286 | SUPPORTED | PASS |
| `textarea` | 31 | SUPPORTED | PASS |
| `multi_row` | 1 | NOT_SUPPORTED | BLOCKED_UNSUPPORTED_TYPE |

> 편집기 계약: `useDocumentFormsEditor.ts` SUPPORTED_FIELD_TYPES = `{'text', 'textarea', 'date', 'signature'}`. `multi_row` → `UNKNOWN_FIELD_TYPE:multi_row` 에러 발생.

**게이트 판정:**

| Gate | 판정 | 근거 |
|---|---|---|
| PARENT_SCHEMA_GATE | **BLOCKED** (65종 전부) | 스키마 status=CANDIDATE. APPROVED_FOR_RUNTIME_USE 필요 |
| FIELD_STATUS_GATE | **BLOCKED** (318필드 전부) | required_status=CANDIDATE_ONLY. REQUIRED_BY_HUMAN/NOT_REQUIRED 전환 필요 |
| EVIDENCE_GATE | NOT_APPLICABLE | evidence_count=0 (65종 전부) |
| SIGNATURE_GATE | NOT_APPLICABLE | signature 필드 없음 (65종 전부) |
| TYPE_COMPATIBILITY | **BLOCKED** (1필드) | DOC-SERA-011/submitted_document_list: multi_row 미지원 |

**기술적 변경 준비 상태:**
- 317필드 `CHANGE_READY=YES_PENDING_PRJ_APPROVAL` (64종 전체 + DOC-SERA-011 4필드)
- 1필드 `CHANGE_READY=NO_TYPE_CONTRACT_REQUIRED` (DOC-SERA-011/submitted_document_list)
- DOC-SERA-011: 4필드는 PRJ 승인 후 변경 가능. 1필드(multi_row)는 타입 계약 해소 전 차단 유지

**활성화 경로 (PRJ Gate 승인 후):**
1. `runtime_form_schema.status`: CANDIDATE → APPROVED_FOR_RUNTIME_USE (64종. DOC-SERA-011은 타입 계약 해소 후)
2. `runtime_field.required_status`: CANDIDATE_ONLY → REQUIRED_BY_HUMAN(231건) / NOT_REQUIRED(87건)

**산출물:**
- `docs/document-engine/M004_FIELD_REQUIREDNESS_GATE.csv` (318행, 18컬럼 — 필드별 상세)
- `docs/document-engine/M004_65DOC_REQUIREDNESS_SUMMARY.csv` (65행 — 문서별 요약)

---

## 다음 단계

1. **GPT 독립검증 (진행 중)**: G1/G2/G3 개별 문서 ID·분류 산식·R2/R3 근거 대조 + FORM_CONFORMANCE_EVIDENCE 24건 PASS 판정 기준 독립검증
2. **Owner 결정**: SCHEMA_PROMOTION_READY 24건 중 PRJ Gate 승인 대상 doc_id 확정 → G2 스키마 승격 (FK 이미 연결)
3. **활성화 단계**: 개별 승인 doc_id에 한해 `runtime_form_schema.status` UPDATE + `runtime_field.required_status` UPDATE 실행
4. **배포**: Railway HOLD 유지. 코드 변경 없으므로 배포 불필요

---

## 완료 보고 (WO 형식)

```
WO = WO-TAI-M004-AUTO-WEB-SERVICE-RELEASE-GATE-001

SOURCE_GATES_VERIFIED = obj00 snapshot + obj02 catalog + R2 binding (memory) + R3 handoff수치
PRJ_CONTRACT = PRJ Gate 유지 (승인 없는 DB 변경 0건)
LEG_CONSUMER_CONTRACT = ACTIVE 상태 준수 (LEG 변경 0건)

CATALOG_TOTAL = 260
SCHEMA_LINKED = 260 (source_trace JSONB 경유)
SCHEMA_APPROVED_CURRENT = 0 (catalog-linked)

MODE_SOURCE_CONFIRMED = 0 (문서별 Owner 승인 목록 없음)
MODE_OWNER_PENDING = 260
MODE_UNVERIFIED = 0 (전건 검토됨, PENDING/BLOCKED 분류 완료)

WEB_FORM_CONTRACT_UNVERIFIED_NO_LEG = 95 (LEGAL_FORM_CLASS=NON_LEGAL)
WEB_FORM_CONTRACT_UNVERIFIED_WITH_LEG = 111 (LEGAL_FORM_CLASS≠NON_LEGAL)
WEB_FORM_CONFORMANCE_PASS = 24 (P0 Wave1+2, SCHEMA_PROMOTION_READY)
WEB_NOT_APPLICABLE_AUTO_SOURCE = 11 (비P0 AUTO_SOURCE, FORM-C UNVERIFIED)
WEB_BLOCKED_SCHEMA_ONLY = 260 (primary block: schema CANDIDATE)
WEB_BLOCKED_LEGAL = 138 (LEGAL_FORM_CLASS≠NON_LEGAL, subset of 260)
WEB_FORM_CONTRACT_UNVERIFIED_SCHEMA_UNVERIFIED = 19
LEGAL_FORM_CLASS_NON_LEGAL = 122
LEGAL_FORM_CLASS_DIGITAL_METADATA = 88
LEGAL_FORM_CLASS_COPY_METADATA = 31
LEGAL_FORM_CLASS_ORIGINAL_ONLY = 19

AUTO_EXISTING_SOURCE = 35 (코드 존재, 고객 연결 BLOCKED)
AUTO_SAFE_APPROVED_FIELDS = 0
AUTO_BLOCKED_FIELDS = 1246 (effective_safe=0, R2 전건)
AUTO_FORM_TAI_AUTO_TRUE = 134
AUTO_FORM_TAI_AUTO_FALSE = 126
AUTO_FORM_EXACT_CONTRACT_TAI_AUTO_TRUE = 1 (DOC-OSH-049/work_location)
AUTO_FORM_EXACT_CONTRACT_TAI_AUTO_FALSE = 1 (DOC-BLD-020/address)
AUTO_FORM_TAI_AUTO_TRUE_UNVERIFIED = 133 (D2 정정)

G1_MATRIX = docs/document-engine/M004_SERVICE_MODE_MATRIX.csv (260행)
G2_MATRIX = docs/document-engine/M004_WEB_SCHEMA_APPROVAL_MATRIX.csv (260행)
G3_MATRIX = docs/document-engine/M004_AUTO_SAFETY_GATE.csv (260행)
FORM_CONFORMANCE_EVIDENCE = docs/document-engine/M004_FORM_CONFORMANCE_EVIDENCE.csv (260행)
OWNER_DECISION_PACKET = docs/document-engine/M004_OWNER_SERVICE_RELEASE_DECISION_PACKET.md

FORM_CONFORMANCE_PASS = 24
FORM_CONTRACT_UNVERIFIED = 236
FORM_REFERENCE_MISSING = 0
SCHEMA_PROMOTION_READY = 24 (PRJ 운영 변경 승인 별도)
SCHEMA_PROMOTION_BLOCKED = 0
SCHEMA_PROMOTION_UNVERIFIED = 236
E2E_PRIOR_EVIDENCE_LINKED = 24 (P0 Quality Audit)
E2E_EVIDENCE_UNLOCATED = 236 (doc-specific E2E 미발견, 공통 엔진 PR#678 PASS)

NEW_CODE = 0
PROD_DB_WRITE = 0
MIGRATION = 0
MERGE = NO
DEPLOY = NO

CLAUDE_RESULT = G1/G2/G3 매트릭스 + Owner 결정 패킷 생성 완료
GPT_IV = PENDING
OWNER_GATE = PENDING
FORM_CONFORMANCE_MAINLINE_STATUS = CORR_A_APPLIED
FORM_CONFORMANCE_PASS = 24
FORM_CONTRACT_UNVERIFIED = 236
SCHEMA_PROMOTION_READY = 24
SCHEMA_PROMOTION_BLOCKED = 0
SCHEMA_PROMOTION_UNVERIFIED = 236
G2_NOT_APPLICABLE_REMAINING = 11
FORM_CONFORMANCE_EVIDENCE_FILE = docs/document-engine/M004_FORM_CONFORMANCE_EVIDENCE.csv
```

```
WO = WO-TAI-M004-WEB-REQUIREDNESS-GATE-001
STATUS = SUPERSEDED_BY_CORR-001 (수치 정정됨 — 아래 CORR-001 블록 참조)
```

```
WO = WO-TAI-M004-WEB-REQUIREDNESS-GATE-001-CORR-001

SOURCE_HEAD = 494f2f61
RESULT_COMMIT = 16673da4

DOCS_CHECKED = 65
FIELDS_CHECKED = 318

REQUIRED_BY_HUMAN_CANDIDATE = 231
NOT_REQUIRED_CANDIDATE = 87
INVALID_OPTIONAL_REMAINING = 0

EDITOR_SUPPORTED_FIELDS = 317
EDITOR_UNSUPPORTED_FIELDS = 1
TYPE_COMPATIBLE_DOCS = 64
TYPE_BLOCKED_DOCS = 1

DOC_SERA_011 = BLOCKED_UNSUPPORTED_TYPE (submitted_document_list: multi_row)

INPUT_TYPE_DISTRIBUTION = text=286 / textarea=31 / multi_row=1
INPUT_TYPE_VERIFIED_FROM_DB = 291 (RUNTIME_VERIFIED) + 27 (P0_VERIFIED) = 318
SUPPORTED_FIELD_TYPES_CONTRACT = useDocumentFormsEditor.ts: {text, textarea, date, signature}

PARENT_SCHEMA_GATE = BLOCKED (65종 전부 SCHEMA_CANDIDATE)
FIELD_STATUS_GATE = BLOCKED (318필드 전부 CANDIDATE_ONLY)
EVIDENCE_GATE = NOT_APPLICABLE (변동 없음)
SIGNATURE_GATE = NOT_APPLICABLE (변동 없음)

CHANGE_READY_YES = 317 fields / 64+1_partial schemas
CHANGE_READY_NO = 1 field (DOC-SERA-011/submitted_document_list)
SCHEMA_STATUS_CHANGE_REQUIRED = 64건 즉시 + DOC-SERA-011 1건 타입계약 해소 후

FIELD_REQUIREDNESS_GATE_FILE = docs/document-engine/M004_FIELD_REQUIREDNESS_GATE.csv (318행)
DOC_REQUIREDNESS_SUMMARY_FILE = docs/document-engine/M004_65DOC_REQUIREDNESS_SUMMARY.csv (65행)

PROD_DB_WRITE = 0
MIGRATION = 0
PRODUCTION_CODE_CHANGED = NO
MERGE = NO
DEPLOY = NO

GPT_IV = PENDING
OWNER_GATE = PENDING
```

```
WO = WO-TAI-M004-WEB-ACTIVATION-PILOT-001

PILOT_DOC = DOC-CON-044
SCHEMA_ID = 479a1881-3bec-47ac-a8bf-0f8ff8db2cf8
CATALOG_DOCUMENT_ID = a795be1d-08a4-4291-aa68-57b7ff59519d

── G1 PRJ 상태 전환 계약 ──
PRJ_SCHEMA_TRANSITION = CANDIDATE→APPROVED_BY_HUMAN→APPROVED_FOR_RUNTIME_USE (Step4D DO 블록 패턴)
PRJ_FIELD_STATUS_TRANSITION = CANDIDATE→APPROVED_BY_HUMAN (동일 DO 블록 내 원자 처리)
PRJ_REQUIREDNESS_TRANSITION = CANDIDATE_ONLY→REQUIRED_BY_HUMAN (동일 DO 블록 내 원자 처리)
PRJ_APPROVAL_MECHANISM = 수동 SQL DO 블록. API 엔드포인트 없음. Owner+PRJ 명시 승인 후 단일 execute_sql.
AUDIT_REQUIRED = runtime_form_audit_log INSERT action=PROMOTE_TO_RUNTIME_USE
ROLLBACK_MECHANISM = before_state JSON → rollback_snapshot 저장. 복구 DO 블록: runtime_document_data=0 + bridge=0 + schema=APPROVED 전제조건 확인 후 원자 복구 (CORR-001 CORR-4)

── G2 입력 계약 ──
FORM_CONTRACT = PASS
FIELD_COUNT_SPEC = 4 (document_forms.required_fields)
FIELD_COUNT_RUNTIME = 4 (runtime_field)
FIELD_KEY_MATCH = 4/4 (construction_project_overview / construction_procedure / construction_precautions / hazardous_work_and_safety_measures)
FIELD_LABEL_MATCH = 4/4 (건설공사 개요 / 시공 절차 / 시공 시 주의사항 / 위험공종 및 안전관리 대책)
FIELD_ORDER_MATCH = 4/4
INPUT_TYPE_SUPPORTED = text(3) + textarea(1) = 4/4 PASS
IS_MANDATORY_ALL_TRUE = True → REQUIRED_BY_HUMAN×4 / NOT_REQUIRED×0
EDITOR_GATE = PASS (signature=0 / evidence=0 / checklist=0 / multi_row=0)

── G3 기존 작성 경로 ──
CATALOG_LOOKUP = GET /documents/catalog/DOC-CON-044 → resolve_catalog_runtime_schema('a795be1d...')
CURRENT_AVAILABILITY = PREPARING (schema CANDIDATE) → can_create=False
POST_ACTIVATION_AVAILABILITY = READY_FOR_EDIT (schema APPROVED_FOR_RUNTIME_USE) → can_create=True
CREATE_GATE = document_engine_svc.py:127 — schema.status==APPROVED_FOR_RUNTIME_USE 통과
FACTORY_PERMISSION = require_scope_ids(company_id+factory_id) 또는 _ensure_factory_own() — 기존 인가 경로 변동 없음
SAVE_RESTORE_CONTRACT = runtime_document_data INSERT/SELECT — 기존 경로 변동 없음
HTML_PDF_CONTRACT = 기존 render/pdf 엔드포인트 — 변동 없음
REQUIRED_VALIDATION = required_status=REQUIRED_BY_HUMAN(4건) 설정 후 편집기 필수 검증 발동

── G4 차단 유지 ──
LEGAL_GATE = HOLD (has_legal_form=False이나 법령 참조 있음 — G1 gate에서 has_legal_form=FALSE 확인)
CUSTOMER_RELEASE = HOLD (PRJ+Owner 명시 승인 전 활성화 금지)
CUSTOMER_ISOLATION = ISOLATION_CONFIRMED_FRONTEND_NOT_WIRED (CORR-001 CORR-1 확인)
  → 고객 접근 경로(engine-document·document-forms 페이지)는 구 /document-forms API 전용
  → POST /documents / GET /documents/catalog 호출 0건 확인 (admin-vue3 전 파일 검색)
  → 스키마 활성화 → can_create=True(API) 상태 변경이나 현재 고객 UI 경로 없음
SECURITY_GATES = 변동 없음 (기존 인가·인증 게이트 완화 없음)
AUTO_FORM_GATE = UNCHANGED (tai_auto=False — AUTO_FORM 해당 없음)

── 사전조건 현황 ──
PRECONDITION_RUNTIME_DOCUMENTS = 0건 ✓
PRECONDITION_INSPECTION_BRIDGE = 0건 ✓
PRECONDITION_EVIDENCE_FIELDS = 0건 ✓
PRECONDITION_CHECKLISTS = 0건 ✓
PRECONDITION_EXISTING_APPROVED = 0건 ✓
PRECONDITION_AUDIT_LOG = 0건 ✓

── 산출물 ──
PILOT_ACTIVATION_SQL = docs/document-engine/M004_PILOT_ACTIVATION_PLAN_DOC_CON_044.sql (NOT EXECUTED)
COHORT_COMPATIBLE_DOCS = 64
COHORT_FIELDS = 313
COHORT_CHECKLISTS = 178
COHORT_EXPANSION_READY = PILOT_PASS_REQUIRED (파일럿 GPT IV + Owner 승인 후 64종 확장 판단)

PROD_DB_WRITE = 0
MIGRATION_APPLIED = 0
CUSTOMER_RELEASE = HOLD
DEPLOY = HOLD

RESULT_COMMIT = 2cc6d1a0
GPT_IV = PENDING
OWNER_OPERATION_APPROVAL = PENDING
```

```
WO = WO-TAI-M004-WEB-ACTIVATION-PILOT-001-CORR-001

CORR_TRIGGER = GPT SOURCE IV CONDITIONAL (ACTIVATION-PILOT-001)
CORR_COUNT = 4

── CORR-1: 고객 격리 실증 ──
ISOLATION_STATUS = ISOLATION_CONFIRMED_FRONTEND_NOT_WIRED  [CORR-002에서 교정됨 — 아래 참조]
EVIDENCE_1 = useEngineDocumentList.ts:103 → GET /document-forms (구 API 전용)
EVIDENCE_2 = useEngineDocumentDetail.ts:36 → GET /document-forms/{id} (구 API 전용)
EVIDENCE_3 = admin-vue3 전 파일 grep "POST /documents" → 0건 (신 엔진 미연결)
ISOLATION_PATH = 신 문서 엔진(POST /documents / GET /documents/catalog) 고객 UI 미연결
CUSTOMER_RELEASE_HOLD_BASIS = 전용 UI 연결 · QA 없이 고객 노출 금지 (격리 계약 확정)
  ※ CORR-002 교정: tai-admin/vue3/ (고객 SaaS 실제 경로)는 POST /document-engine/documents 사용함.
     격리 근거는 document_forms.form_schema_id 컬럼 부재(DB 검증) — CORR-001은 admin-vue3(어드민) 경로만 검색한 오류.

── CORR-2: 실행시점 불변조건 추가 ──
P8_ADDED = runtime_form_schema.catalog_document_id = v_catalog_id AND schema_candidate_id = v_cand_id (source provenance 동시 검증)
G4_ADDED = document_schema_candidate.id = v_cand_id → status='CANDIDATE' (승격 전 소스 불변 사전확인)
F4_ADDED = final assert: source provenance 불변 검증 (F2와 이중 교차검증)
EXISTING_SUFFICIENT = P1/P4/G1/G2/G3/F2/F3 기존 조건 유지

── CORR-3: reviewer_id=NULL 적절성 확인 + review_comment 교정 ──
REVIEWER_ID_NULL = CONFIRMED_VALID (Step4D B-1 계약 — nullable 허용, 별도 reviewer identity 계약 없음)
REVIEW_COMMENT_OLD = "PRJ+Owner approval obtained before execution" (실행 전 완료사실 주장 — 부정확)
REVIEW_COMMENT_NEW = "Execution requires explicit Owner+PRJ authorization before running this SQL" (요건 명시)

── CORR-4: 조건부 복구 가드 ──
ROLLBACK_GUARD_ADDED = DO 블록 전제조건: runtime_document_data=0 + bridge=0 + schema=APPROVED_FOR_RUNTIME_USE + ROW_COUNT=4 검증
ROLLBACK_AUTO_ABORT = 조건 불충족 시 EXCEPTION → 전체 롤백 자동
ROLLBACK_ESCALATION = 조건 불충족 시 Owner 에스컬레이션 명시

── 산출물 ──
ACTIVATION_SQL = docs/document-engine/M004_PILOT_ACTIVATION_PLAN_DOC_CON_044.sql (CORR-001 교정 완료, NOT EXECUTED)

PROD_DB_WRITE = 0
MIGRATION_APPLIED = 0
NEW_CODE = 0

RESULT_COMMIT = f2a7e30a
GPT_IV = SUPERSEDED_BY_CORR-002
OWNER_OPERATION_APPROVAL = PENDING
```

```
WO = WO-TAI-M004-WEB-ACTIVATION-PILOT-001-CORR-002

CORR_TRIGGER = GPT SOURCE IV CONDITIONAL (CORR-001) — ISOLATION_CONFIRMED_FRONTEND_NOT_WIRED 주장 불충족
CORR_COUNT = 5

── CORR-1: 격리 주장 교정 ──
ISOLATION_OLD = ISOLATION_CONFIRMED_FRONTEND_NOT_WIRED (CORR-001 오류)
ISOLATION_ROOT_CAUSE = CORR-001이 admin-vue3(어드민 전용 경로)만 검색하고 tai-admin/vue3(고객 SaaS 경로) 누락
ISOLATION_NEW = ISOLATION_CONFIRMED_FORM_SCHEMA_ID_NOT_WIRED

FRONTEND_CALL_PATH:
  tai-admin/vue3/src/pages/document-forms/useDocumentFormsList.ts:49
    → GET /document-forms?per_page=200 (OLD API 목록)
  tai-admin/vue3/src/pages/document-forms/useDocumentFormsGenerate.ts:73
    → POST /document-engine/documents {form_schema_id, factory_id, company_id, created_by}

ISOLATION_MECHANISM:
  document_forms 테이블 컬럼 조회 결과: id, doc_id, is_active (form_schema_id 없음, DB 직접 확인)
  document-formsFormat.ts:219 pickFormSchemaId(tpl) → tpl.form_schema_id||tpl.runtime_form_schema_id||tpl.schema_id||''
  → DOC-CON-044 선택 시 전부 undefined → '' 반환
  useDocumentFormsGenerate.ts:71 if (!formSchemaId) throw '이 서식에 연결된 form_schema_id가 없습니다.'
  → POST /document-engine/documents API 호출 미발생

CUSTOMER_EXPOSURE_STATUS:
  DOC-CON-044 → 고객 서식 목록 표시 (is_active=true)
  문서 생성 시도 → 프론트 에러 차단 (API 미호출)
  스키마 활성화가 이 차단 메커니즘을 변경하지 않음
  CAVEAT: 인증+factory scope 보유 시 직접 API 호출로 우회 가능

PRODUCTION_DEPLOYMENT_SCOPE = tai-admin/vue3 = 고객 SaaS 화면 (CF 배포됨)
API_CUSTOMER_ACCESS_CONTROL = 인증 필수 + factory scope 필수 + schema.status=APPROVED_FOR_RUNTIME_USE 필수 (document_engine_svc.py:127)

── CORR-2: SQL precondition 강화 ──
P4B_ADDED = field_label 4건 exact match (DB 실증값: 건설공사 개요/시공 절차/시공 시 주의사항/위험공종 및 안전관리 대책)
P9_ADDED = runtime_form_schema.version = 1 (DB 실증값)
G5_ADDED = document_forms.required_fields 4건 + 전부 is_mandatory=true (JSONB 직접 검증)
F5_ADDED = schema version 최종 불변 assert

DB_VERIFICATION:
  runtime_form_schema.version = 1 (조회 확인)
  runtime_field field_label 4건 = {건설공사 개요, 시공 절차, 시공 시 주의사항, 위험공종 및 안전관리 대책}
  document_forms.required_fields 4건, 전부 is_mandatory=true, source=법정, law_ref=건설기술진흥법 제62조의2

── CORR-3: rollback DO 블록 — 감사기록 존재 확인 추가 ──
ROLLBACK_AUDIT_GUARD = runtime_form_audit_log PROMOTE_TO_RUNTIME_USE = 1건 존재 확인
ROLLBACK_AUDIT_PRESERVE = 감사기록 삭제 금지 명시 (복구 후에도 이력 보존)

── CORR-4: PRJ Step4D 참조 명시 ──
PRJ_STEP4D_REFERENCE = docs/sql/20260825_WP_PERSISTENCE_02A_STEP4D_UP.sql (파일 존재 확인됨)
PRJ_STEP4D_STATUS = VERIFIED (로컬 파일 경로 실증)
REVIEWER_ID_NULL = CONFIRMED_VALID (Step4D B-1 계약 동일 패턴 재확인)

── CORR-5: BEFORE/AFTER 스냅샷 field_label 포함 ──
SNAPSHOT_ENHANCED = before/after 스냅샷에 field_label 추가 (감사 이력 풍부화)

── 산출물 ──
ACTIVATION_SQL = docs/document-engine/M004_PILOT_ACTIVATION_PLAN_DOC_CON_044.sql (CORR-002 교정 완료, NOT EXECUTED)

PROD_DB_WRITE = 0
MIGRATION_APPLIED = 0
NEW_CODE = 0

RESULT_COMMIT = [pending]
GPT_IV = PENDING
OWNER_OPERATION_APPROVAL = PENDING
```
