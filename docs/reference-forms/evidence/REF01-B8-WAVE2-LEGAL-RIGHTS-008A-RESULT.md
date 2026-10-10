---
wo: WO-REF01-060-B8-WAVE2-LEGAL-RIGHTS-EVIDENCE-008A
evidence_type: LEGAL_RIGHTS_EVIDENCE_008A_CORRECTION
status: EVIDENCE_COMPLETE_GPT_GATE_PENDING
date: 2026-10-10
base_head: 84e8461a
parent_wo: WO-REF01-060-B8-WAVE2-LEGAL-RIGHTS-EVIDENCE-008
---

# REF01-B8-WAVE2-LEGAL-RIGHTS-008A-RESULT

WO-REF01-060-B8-WAVE2-LEGAL-RIGHTS-EVIDENCE-008A 정정 결과.  
WO-008 GPT 조건부 PASS 후 3가지 오류 항목 수정.

---

## 1. 정정 배경

GPT WO-008 검토 결과 조건부 PASS. 다음 3가지 항목 정정 지시:

| 항목 | WO-008 오류 | WO-008A 정정 내용 |
|------|------------|-----------------|
| A | `LEGAL_RPC_ROUTE = LEGAL_SOT_UNAVAILABLE` — governance RPC 자체 접근 불가로 오해 유발 | governance RPC 접근 성공이나 반환값이 산업안전 법령 아님 → `LEGAL_RPC_CONTRACT_UNRESOLVED` |
| B | GOV-01 JSON `legal_duty_class = REVIEW_REQUIRED` ↔ 결과문서 `CONDITIONAL_COUNT = 1` 불일치 | JSON을 `ACTIVITY_DUTY_CONFIRMED_CONDITIONAL`로 업데이트하여 일치시킴 |
| C | KOSHA MSDS 상업 재사용 경고를 C039-C044 전체에 동일 적용 | 3가지 CASE로 구분 (CASE A: MSDS 원본 직접 재사용 / CASE B: 파생 서식 / CASE C: TAI 독자 관리 서식) |

---

## 2. governance RPC 실제 접근 결과

### 접근 방법

- MCP `mcp__claude_ai_guri-cf__execute_sql` 도구를 통한 45cm-prj-db governance 스키마 직접 조회
- 프로젝트: `iapzwbysfzootqnldtan` (45cm-prj-db)

### 조회 결과 요약

| 조회 | 결과 |
|------|------|
| `governance.get_active_items_for_scope('LEG', NULL)` | **332건 반환** (WO-008A에서 16건으로 기술한 것은 오류 — WO-008B 정정) |
| 산업안전·화학물질·MSDS 관련 용어 검색 | 0건 |
| 법령 조문·시행일·적용조건 확인 | 미완료 |
| `governance.external_standards` | SARIF, FINDING-V1, OTEL, OCSF (기술 표준; 한국 법령 없음) |
| `governance.external_sources` | ESLint, Playwright, Ruff 등 (개발 도구) |
| `GOVERNANCE_SOURCE_OF_TRUTH.md` | NOT_FOUND (파일명 기준 검색; SoT 부재 증거 아님) |
| tai-leg 저장소 | 404 (존재하지 않음) |

### 결론

```
GOVERNANCE_RPC_ACCESSIBLE              = YES
GOVERNANCE_RPC_ITEM_COUNT              = 332건 (WO-008A에서 16건으로 기술한 것은 오류)
GOVERNANCE_RPC_INDUSTRIAL_SAFETY_TERMS = 0건
GOVERNANCE_SCHEMA_LAW_PRESENCE         = UNVERIFIED (전체 법령 유무 미확정)
LEGAL_RPC_CONTRACT_STATUS              = UNRESOLVED
LEGAL_RPC_ROUTE                        = LEGAL_RPC_CONTRACT_UNRESOLVED
```

이 판정은 WO-008의 `LEGAL_SOT_UNAVAILABLE`를 대체한다. 차이:  
- `LEGAL_SOT_UNAVAILABLE`: governance 접근 자체 불가로 해석될 수 있음  
- `LEGAL_RPC_CONTRACT_UNRESOLVED`: governance 접근은 성공했으나 승인된 법령 조회 RPC 계약이 식별되지 않음

**주의 (WO-008B 정정)**: WO-008A에서 "governance DB는 산업 법령 SoT가 아님"으로 단정한 것은 과잉 해석. 해당 RPC에서 산업안전 용어가 없었다는 사실만 확인됨. governance 스키마 전체 법령 유무는 미확정.

---

## 3. GOV-01 JSON 정정 내역

**변경 전** (`legal_duty_class`):
```
"REVIEW_REQUIRED"
```

**변경 후** (`legal_duty_class` + 추가 필드):
```json
"legal_duty_class": "ACTIVITY_DUTY_CONFIRMED_CONDITIONAL",
"legal_duty_class_basis": "2차 연구 문서 증거 (OBJ-REF-01-GOVERNANCE-WORKFLOW-15.md S1/S2) — governance RPC 확인 아님",
"activity_duty_status": "SECONDARY_EVIDENCE_ONLY — 법 제24조 기록 의무 언급 (report 15 S1)",
"applicability_status": "UNVERIFIED — 시행령 별표9 적용 사업장 조건 미확인",
"prescribed_form_status": "NOT_APPLICABLE — 법 제24조는 특정 양식 지정 없음; TAI 열 구조는 법정 별지 아님",
"field_mandatory_status": "UNVERIFIED — 법정 필수 기재 항목 목록 미확인",
"legal_review_status": "PENDING"
```

`ACTIVITY_DUTY_CONFIRMED_CONDITIONAL` 분류 근거: report 15 S1에서 법 제24조 회의록 작성·보존 의무 인용. **2차 증거이며 RPC 확인 아님.** 사업장 조건(시행령 별표9)·필수 기재 항목·법정 별지 여부 모두 UNVERIFIED.

---

## 4. C039-C044 KOSHA MSDS 경고 범위 정정

**WO-008 오류**: KOSHA MSDS 상업 재사용 경고를 C039-C044 모두에 동일 적용.

**WO-008A 정정**: 3가지 CASE로 구분.

| CASE | 설명 | 해당 서식 | 경고 적용 여부 |
|------|------|---------|------------|
| A | KOSHA MSDS 시스템 원본 MSDS 데이터 직접 복사 | C040 일부 가능성 | 직접 적용 (명시 경고) |
| B | MSDS 관련 관리 서식이나 KOSHA MSDS 데이터 직접 복사 미확인 | C040, C044 | 적용 여부 불확실 (원본 비교 필요) |
| C | 법령 참조 구조를 갖춘 TAI 독자 관리 서식 — KOSHA MSDS 시스템과 직접 관련 없음 | C039, C041, C042, C043 | 직접 적용 근거 없음 |

**주의**: CASE 구분은 잠정 분류. 원본 파일 미검사로 TAI 독자성 또한 미확인. 모든 서식 `rights_status = RIGHTS_UNVERIFIED` 유지.

---

## 5. 변경 파일

| 파일 | 변경 내용 |
|------|---------|
| `evidence/legal-rights-008/REF01_B8_14_LEGAL_RIGHTS_MATRIX.json` | 13종 `rpc` 필드: `LEGAL_SOT_UNAVAILABLE` → `LEGAL_RPC_CONTRACT_UNRESOLVED` + `rpc_accessed`/`rpc_content` 추가. GOV-01 `legal_duty_class` 정정 + 추가 필드 (WO-008에서 일부 완료) |
| `evidence/legal-rights-008/REF01_B8_14_LEGAL_RPC_TRACE.md` | §1 재작성: governance DB 실제 접근 결과 §1.1 추가. 판정 `LEGAL_SOT_UNAVAILABLE` → `LEGAL_RPC_CONTRACT_UNRESOLVED`. 한계 §4 업데이트. |
| `evidence/legal-rights-008/REF01_B8_14_SOURCE_LICENSE_TRACE.md` | B 그룹 CASE A/B/C 구분 표 추가. 개별 서식 표에 `KOSHA MSDS 경고 적용` 열 추가. |
| `evidence/REF01-B8-WAVE2-LEGAL-RIGHTS-008-RESULT.md` | `LEGAL_RPC_ROUTE` 정정. governance RPC 접근 결과 단락 추가. `NEW_HEAD`/`REMOTE_HEAD` 주석 업데이트. |
| `evidence/REF01-B8-WAVE2-LEGAL-RIGHTS-008A-RESULT.md` | 본 정정 결과 문서 (신규) |

정규 JSON 14종·PDF 14종·DOCX 14종·공통 엔진·DB 스키마·행 변경 없음.

---

## 6. 요약 카운트 (변경 없음)

| 항목 | 값 |
|------|---|
| 대상 서식 수 | 14/14 |
| 법령 의무 RPC 확인 (공식) | 0 |
| 조건부 활동의무 (2차 증거) | 1 (GOV-01) |
| REVIEW_REQUIRED | 13 |
| 원본 파일 검사 완료 | 0/14 |
| 유사도 확인 | 0/14 |
| 권리 확인 | 0/14 |
| 상업적 재배포 승인 | 0/14 |
| 법률 전문가 검토 필요 | 14/14 |
| 제3자 유사성 위험 (주의) | 3 (C029, C031, C033) |

---

## 7. 상태

```
WO                                   = WO-REF01-060-B8-WAVE2-LEGAL-RIGHTS-EVIDENCE-008A
PARENT_WO                            = WO-REF01-060-B8-WAVE2-LEGAL-RIGHTS-EVIDENCE-008
BASE_HEAD                            = 84e8461a
FORMS                                = 14/14
LEGAL_RPC_ROUTE                      = LEGAL_RPC_CONTRACT_UNRESOLVED
GOVERNANCE_RPC_ACCESSIBLE            = YES
GOVERNANCE_RPC_LAW_CONTENT           = NONE
LEGAL_RPC_RESULTS                    = EVIDENCED=0 / REVIEW_REQUIRED=13 / CONDITIONAL=1
SOURCE_TRACE                         = EVIDENCED=0 / UNVERIFIED=14
RIGHTS_TRACE                         = SPECIFIC_PERMISSION=0 / UNVERIFIED=14
COMMERCIAL_REDISTRIBUTION_AUTHORIZED = NO
PRODUCTION_DB_WRITE                  = 0
CHANGED_FILES                        = 5 (evidence files only)
B8_CLOSED_FINAL                      = NO
PR_MERGE                             = BLOCKED
DEPLOY                               = BLOCKED
PUBLICATION                          = INTERNAL_POC_ONLY
NEXT_GATE                            = GPT_INDEPENDENT_LEGAL_RIGHTS_008A_REVIEW
```
