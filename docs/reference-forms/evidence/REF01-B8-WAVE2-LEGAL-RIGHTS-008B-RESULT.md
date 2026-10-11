---
wo: WO-REF01-060-B8-WAVE2-LEGAL-RIGHTS-EVIDENCE-008B
evidence_type: LEGAL_RIGHTS_EVIDENCE_008B_CORRECTION
status: EVIDENCE_COMPLETE_GPT_GATE_PENDING
date: 2026-10-10
base_head: 6440d28700b01c9ce541dff459d159bac342a97f
parent_wo: WO-REF01-060-B8-WAVE2-LEGAL-RIGHTS-EVIDENCE-008A
---

# REF01-B8-WAVE2-LEGAL-RIGHTS-008B-RESULT

WO-REF01-060-B8-WAVE2-LEGAL-RIGHTS-EVIDENCE-008B 정정 결과.  
WO-008A GPT 조건부 PASS 후 2가지 보정 항목 수정.

---

## 1. 정정 배경

GPT WO-008A 검토 결과 조건부 PASS. 다음 2가지 항목 보정 지시:

| 항목 | WO-008A 오류 | WO-008B 정정 내용 |
|------|------------|-----------------|
| RPC 증거 정확성 | `get_active_items_for_scope('LEG', NULL)` 반환값을 16건으로 기술; "governance DB는 산업 법령 SoT가 아님" 단정 | 실제 332건 반영; governance 스키마 전체 법령 유무 = UNVERIFIED로 수정 |
| 매트릭스 스키마 정합성 | `activity_duty_status` 등 5개 필드가 GOV-01에만 존재; 나머지 13종 누락 | 13종 전체에 5개 분류 필드 추가 (REVIEW_REQUIRED/UNVERIFIED/PENDING) |

---

## 2. governance RPC 실측 정정

### WO-008A 오류 사항

- 반환 항목 수: **16건으로 기술** → 실제 **332건**
- "governance DB는 45CM 개발 거버넌스 전용 — 산업 법령 SoT 아님" → **과잉 단정**

### WO-008B 정정 후 실측 기록

| 항목 | 실측값 |
|------|------|
| `get_active_items_for_scope('LEG', NULL)` 반환 항목 수 | 332건 |
| 산업안전·화학물질·MSDS 관련 용어 검색 | 0건 |
| 법령 조문·시행일·적용조건 조회 계약 | 미확정 |
| governance 스키마 전체 법령 유무 | 미확정 |
| `GOVERNANCE_SOURCE_OF_TRUTH.md` | NOT_FOUND (파일명 기준 검색; SoT 부재 증거 아님) |
| LEG_RUNTIME_URL | NOT_SET (research context) |

### 수정된 판정

```
GOVERNANCE_RPC_ACCESSIBLE              = YES
GOVERNANCE_RPC_ITEM_COUNT              = 332건
GOVERNANCE_RPC_INDUSTRIAL_SAFETY_TERMS = 0건
GOVERNANCE_SCHEMA_LAW_PRESENCE         = UNVERIFIED
LEGAL_RPC_CONTRACT_STATUS              = UNRESOLVED
LEGAL_RPC_ROUTE                        = LEGAL_RPC_CONTRACT_UNRESOLVED
```

---

## 3. 14종 법률 분류 스키마 정합화

### 변경 내용

`REF01_B8_14_LEGAL_RIGHTS_MATRIX.json` 13종(C026~C044 / GOV-01 제외)에 다음 5개 필드 추가:

```json
"activity_duty_status": "REVIEW_REQUIRED",
"applicability_status": "UNVERIFIED",
"prescribed_form_status": "UNVERIFIED",
"field_mandatory_status": "UNVERIFIED",
"legal_review_status": "PENDING"
```

### 검증 결과

| 항목 | 결과 |
|------|------|
| `activity_duty_status` 보유 서식 수 | 14/14 |
| `legal_review_status` 보유 서식 수 | 14/14 |
| JSON 유효성 | PASS |
| GOV-01 기존 분류 유지 | CONFIRMED — `ACTIVITY_DUTY_CONFIRMED_CONDITIONAL` + `SECONDARY_EVIDENCE_ONLY` |
| 13종 미확인 사실 추정 없음 | CONFIRMED — 전원 REVIEW_REQUIRED/UNVERIFIED |

### GOV-01 분류 확인

GOV-01은 WO-008A에서 설정된 분류 유지:
- `legal_duty_class`: `ACTIVITY_DUTY_CONFIRMED_CONDITIONAL`
- `activity_duty_status`: `SECONDARY_EVIDENCE_ONLY — 법 제24조 기록 의무 언급 (report 15 S1)`
- 공식 RPC 검증 결과가 아닌 2차 연구 문서 분류임 명시

---

## 4. 영수증 정정 (BASE HEAD)

| 항목 | 정정 전 | 정정 후 |
|------|--------|--------|
| WO-008 BASE_HEAD (WO-008 결과문서) | `84e8461a` (부분 SHA) | `84e8461af7e51139d1e165f484991434945f4d92` |
| WO-008 REMOTE_HEAD | `9864b9ac (WO-008 push 전)` | `6440d28700b01c9ce541dff459d159bac342a97f` (WO-008A 이후 최신) |

---

## 5. 변경 파일

| 파일 | 변경 내용 |
|------|---------|
| `evidence/legal-rights-008/REF01_B8_14_LEGAL_RIGHTS_MATRIX.json` | 14종 `rpc_content` 정정 (332건 반영). 13종 5개 분류 필드 추가. |
| `evidence/legal-rights-008/REF01_B8_14_LEGAL_RPC_TRACE.md` | §1.1 재정정: 332건 반영, governance 법령 유무 UNVERIFIED로 수정. 판정 블록 업데이트. 한계 §4 항목 2 수정. |
| `evidence/REF01-B8-WAVE2-LEGAL-RIGHTS-008A-RESULT.md` | 조회 결과 표 수정 (332건). RPC 판정 블록 수정. 주의 사항 추가. |
| `evidence/REF01-B8-WAVE2-LEGAL-RIGHTS-008-RESULT.md` | BASE_HEAD 전체 SHA 정정. REMOTE_HEAD 업데이트. |
| `evidence/REF01-B8-WAVE2-LEGAL-RIGHTS-008B-RESULT.md` | 본 정정 결과 문서 (신규) |

정규 JSON 14종·PDF 14종·DOCX 14종·공통 엔진·DB 스키마·행 변경 없음.

---

## 6. 최종 매트릭스 검증 결과

| 항목 | 값 |
|------|---|
| 대상 서식 수 | 14/14 |
| 법령 RPC 계약 미확정 | 14/14 |
| 법률 분류 5개 필드 보유 | 14/14 |
| GOV-01 조건부 활동의무 (2차 증거) | 1건 |
| 나머지 13종 REVIEW_REQUIRED | 13건 |
| 원본 파일 검사 완료 | 0/14 |
| 권리 확인 | 0/14 |
| 상업적 재배포 승인 | 0/14 |
| JSON 유효성 | PASS |

---

## 7. 상태

```
WO                                   = WO-REF01-060-B8-WAVE2-LEGAL-RIGHTS-EVIDENCE-008B
PARENT_WO                            = WO-REF01-060-B8-WAVE2-LEGAL-RIGHTS-EVIDENCE-008A
BASE_HEAD                            = 6440d28700b01c9ce541dff459d159bac342a97f
FORMS                                = 14/14
LEGAL_RPC_ROUTE                      = LEGAL_RPC_CONTRACT_UNRESOLVED
GOVERNANCE_RPC_ACCESSIBLE            = YES
GOVERNANCE_RPC_ITEM_COUNT            = 332건
GOVERNANCE_RPC_INDUSTRIAL_SAFETY_TERMS = 0건
GOVERNANCE_SCHEMA_LAW_PRESENCE       = UNVERIFIED
LEGAL_RPC_RESULTS                    = EVIDENCED=0 / REVIEW_REQUIRED=13 / CONDITIONAL=1
MATRIX_FIELD_CONSISTENCY             = PASS (14/14 5개 분류 필드 보유)
SOURCE_TRACE                         = EVIDENCED=0 / UNVERIFIED=14
RIGHTS_TRACE                         = SPECIFIC_PERMISSION=0 / UNVERIFIED=14
COMMERCIAL_REDISTRIBUTION_AUTHORIZED = NO
PRODUCTION_DB_WRITE                  = 0
CHANGED_FILES                        = 5 (evidence files only)
B8_CLOSED_FINAL                      = NO
PR_MERGE                             = BLOCKED
DEPLOY                               = BLOCKED
PUBLICATION                          = INTERNAL_POC_ONLY
NEXT_GATE                            = GPT_INDEPENDENT_LEGAL_RIGHTS_008B_REVIEW
```
