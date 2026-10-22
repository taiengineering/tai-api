# M004 Owner Service Release Decision Packet

> WO: WO-TAI-M004-AUTO-WEB-SERVICE-RELEASE-GATE-001  
> 작성일: 2026-10-22  
> 작성자: Claude Code (실행) — GPT 독립검증 대기  
> 상태: OWNER_DIRECTION_R1_APPLIED / GPT_IV_PENDING / OWNER_GATE_PENDING  
> R1 정정 (2026-10-22): D1=LEGAL_FORM_CLASS 추가 / D2=AUTO_FORM 135→133 정정 / D3=C-3 삭제 / D4=SCHEMA_REVIEW_CANDIDACY→FORM_CONFORMANCE_STATUS  
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
1. 이 95건 중 실제 웹 편집 서비스를 제공할 문서 ID 확정
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
| R2 EXACT_CONTRACT 중 tai_auto=True | 1 (DOC-BLD-020/address) |
| R2 EXACT_CONTRACT 중 tai_auto=False | 1 (DOC-OSH-049/work_location) |
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

## 다음 단계

1. **GPT 독립검증 (진행 중)**: G1/G2/G3 개별 문서 ID·분류 산식·R2/R3 근거 대조 — 현재 NOT_VERIFIED
2. **Owner 결정**: B-1 중 최소 1건 doc_id 확정 → G2 스키마 승격 (C-1 Migration 불필요 — FK 이미 연결)
3. **활성화 단계**: 개별 승인 doc_id에 한해 `runtime_form_schema.status` UPDATE 실행 (FK 없이 가능)
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
WEB_NOT_APPLICABLE_AUTO_SOURCE = 35
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
AUTO_FORM_EXACT_CONTRACT_TAI_AUTO_TRUE = 1 (DOC-BLD-020/address)
AUTO_FORM_EXACT_CONTRACT_TAI_AUTO_FALSE = 1 (DOC-OSH-049/work_location)
AUTO_FORM_TAI_AUTO_TRUE_UNVERIFIED = 133 (D2 정정)

G1_MATRIX = docs/document-engine/M004_SERVICE_MODE_MATRIX.csv (260행)
G2_MATRIX = docs/document-engine/M004_WEB_SCHEMA_APPROVAL_MATRIX.csv (260행)
G3_MATRIX = docs/document-engine/M004_AUTO_SAFETY_GATE.csv (260행)
OWNER_DECISION_PACKET = docs/document-engine/M004_OWNER_SERVICE_RELEASE_DECISION_PACKET.md

NEW_CODE = 0
PROD_DB_WRITE = 0
MIGRATION = 0
MERGE = NO
DEPLOY = NO

CLAUDE_RESULT = G1/G2/G3 매트릭스 + Owner 결정 패킷 생성 완료
GPT_IV = PENDING
OWNER_GATE = PENDING
```
