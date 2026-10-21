# WO-TAI-DOC-UNIFICATION-9-LINK-PREFLIGHT-001 — 등록 전 점검 증거

**작성일**: 2026-10-21  
**작업 유형**: READ-ONLY — 등록 사전 점검  
**기준**: GPT 9쌍 RELATED_FORM 권고안 (WO-TAI-DOC-UNIFICATION-LEG-9-001-IV-CORRECTION R1 기준)

---

## 1. unified_document_link 컬럼 구조 확인

| 컬럼 | 타입 | 비고 |
|------|------|------|
| id | uuid | PK |
| saas_catalog_id | uuid | document_forms.id |
| reference_form_id | uuid | reference_form_content.form_id |
| relation_type | text | RELATED_FORM 등 |
| review_state | text | fn_udl_transition 상태 |
| evidence_note | text | 증거 메모 |
| reviewed_by | text | |
| reviewed_at | timestamptz | |
| owner_approval_ref | text | |
| version | integer | |
| created_at | timestamptz | |
| updated_at | timestamptz | |

Unique constraint: `(saas_catalog_id, reference_form_id)` 쌍.

---

## 2. SaaS 문서 존재·활성 확인

| doc_id | doc_name | saas_catalog_id (UUID) | is_active |
|--------|----------|----------------------|----------|
| DOC-OSH-058 | 산업안전보건위원회 회의록 | `d46d90b7-385d-45ef-8341-219837320ecf` | ✓ |
| DOC-OSH-045 | 보호구 지급대장 | `e39677b4-fb23-4b50-bde9-cd5b57a079fe` | ✓ |
| DOC-OSH-047 | 밀폐공간 작업허가서 | `877eabe7-a6fc-4d6d-8808-67f9c96dda93` | ✓ |
| DOC-CON-011 | 안전보건협의체 회의록(건설) | `ccc67e35-621e-4318-8537-7166b6acb9b8` | ✓ |
| DOC-OSH-037 | 안전보건교육 실시기록부 | `ed047fe4-4a0c-443f-9159-b1be0318f779` | ✓ |
| DOC-CON-041 | 작업중지 및 재개 기록 | `d03cb25e-fa5e-4dfe-abb5-656aa06cd430` | ✓ |
| DOC-OSH-006 | 안전보건교육일지 | `1f79fada-efed-437d-b472-7a074b8a6eb6` | ✓ |
| DOC-OSH-049 | 작업허가서(위험작업) | `6d5a54e5-679c-4c86-b5d0-355702f8c559` | ✓ |
| DOC-OSH-015 | 안전보건협의체회의록 | `9cf424e7-ff2a-4720-8d0c-0df5a89dba7b` | ✓ |

전 9개 문서 is_active=true 확인.

---

## 3. 참고서식 존재 확인

| slug | form_id (UUID) | title |
|------|---------------|-------|
| ref-gov-01 | `984d3675-cd74-4b65-981e-3484c2d705c8` | 산업안전보건위원회 회의록 |
| ref-c023 | `71a815f3-d493-4557-a0e4-48d97e00552d` | 안전보호구 지급대장 |
| ref-conf-01 | `ac41001e-b679-4b8f-ae62-749dd69fc1fa` | 밀폐공간 출입·작업허가서 |
| ref-gov-06 | `58ba7434-3468-46ab-bd10-bd9af979b737` | 안전보건협의체 회의록(도급사업) |
| ref-c031 | `ee664e1a-a543-4ced-b3bf-297e5b5c9f20` | 안전보건교육 실시일지 |
| ref-p-14 | `5e1d0cf5-9e55-4db8-9e03-32823b427776` | 작업중지·재개 승인기록 |
| ref-c025 | `85f0d094-7a1e-457e-a689-6f9890038ebc` | 위험작업 허가서 |

전 7개 참고서식 존재 확인.

---

## 4. unified_document_link 기존 등록 여부

9쌍 전부 쿼리 결과: **0건** — 중복 없음. 신규 PROPOSED 등록 가능.

---

## 5. 9쌍 등록 가능 여부 표 (Owner 결정용)

| # | SaaS 문서 | 참고서식 | 권고 관계 | SaaS 활성 | Ref 존재 | 기존 링크 | 등록 가능 | 비고 |
|---|----------|---------|---------|---------|---------|---------|---------|------|
| 1 | DOC-OSH-058 위원회 회의록 | ref-gov-01 | RELATED_FORM | ✓ | ✓ | 없음 | **READY** | 시행령 제37조④ 4항목 중 기타 토의사항 독립 필드 미확정 |
| 2 | DOC-OSH-045 보호구 지급대장 | ref-c023 | RELATED_FORM | ✓ | ✓ | 없음 | **READY** | law_ref 정정 완료. 지급대장 보존 의무 근거 별도 확인 필요. |
| 3 | DOC-OSH-047 밀폐공간 작업허가서 | ref-conf-01 | RELATED_FORM | ✓ | ✓ | 없음 | **READY** | 제619조② 6항목 중 감시인·보호구 종류 SaaS 미확인 |
| 4 | DOC-CON-011 건설 협의체 회의록 | ref-gov-06 | RELATED_FORM | ✓ | ✓ | 없음 | **READY** | ref-gov-06 다중매핑(Pair 9와 공유). 건설 특화형으로 별도 등록. |
| 5 | DOC-OSH-037 교육 실시기록부 | ref-c031 | RELATED_FORM | ✓ | ✓ | 없음 | **READY** | ref-c031 다중매핑(Pair 7과 공유). 간략 기록부. 서명·강사 없음. |
| 6 | DOC-CON-041 작업중지·재개 기록 | ref-p-14 | RELATED_FORM | ✓ | ✓ | 없음 | **READY** | 재개 승인자 서명 법정 의무 미확정. 구조 차이 기록. |
| 7 | DOC-OSH-006 안전보건교육일지 | ref-c031 | RELATED_FORM | ✓ | ✓ | 없음 | **READY** | ref-c031 다중매핑. DOC-OSH-006이 서명 포함으로 Ref에 더 근접. |
| 8 | DOC-OSH-049 작업허가서(위험작업) | ref-c025 | RELATED_FORM | ✓ | ✓ | 없음 | **READY** | 목적·구조 가장 높은 일치. 결재 단계 수 차이. |
| 9 | DOC-OSH-015 일반 협의체 회의록 | ref-gov-06 | RELATED_FORM | ✓ | ✓ | 없음 | **READY** | ref-gov-06 다중매핑(Pair 4와 공유). 일반 도급사업 맥락에 더 근접. |

**RELATED_FORM 의미 한계**: 두 서식이 관련된 업무에서 사용됨을 나타냄. 동일 문서 확정·법정 적합성 인증·문서 병합을 의미하지 않음.

---

## 6. 다중 매핑 처리 지침

### ref-c031 → Pair 5 (DOC-OSH-037) + Pair 7 (DOC-OSH-006)

| 쌍 | 우선순위 | 근거 |
|---|---------|------|
| DOC-OSH-006 ↔ ref-c031 | 우선 | 6필드 + 서명 포함. Ref에 더 근접. |
| DOC-OSH-037 ↔ ref-c031 | 보조 | 4필드, 서명 없음. 간략 기록부로 별도 연결. |

두 쌍 모두 `(saas_catalog_id, reference_form_id)` unique constraint 충족. 동시 등록 가능.

### ref-gov-06 → Pair 4 (DOC-CON-011) + Pair 9 (DOC-OSH-015)

| 쌍 | 우선순위 | 근거 |
|---|---------|------|
| DOC-OSH-015 ↔ ref-gov-06 | 우선 | 일반 도급사업 맥락 근접. Ref 제목·범위 일치. |
| DOC-CON-011 ↔ ref-gov-06 | 보조 | 건설 특화형. 순회점검 등 건설 고유 항목 포함. |

두 쌍 모두 동시 등록 가능. 원본 문서 유지.

---

## 7. evidence_note 초안 (각 쌍)

PROPOSED 등록 시 `evidence_note` 필드에 사용할 문구 초안:

| # | evidence_note 초안 |
|---|-------------------|
| 1 | "시행령 제37조④ 4항목 구조 일치(일시·장소·출석·의결). 기타토의사항 독립필드 미확정. RELATED_FORM. LEG-9-R1 Pair1." |
| 2 | "안전보건기준규칙 제32조 보호구 지급·착용 의무 공통 근거. 반납일·서명 구조 차이. RELATED_FORM. LEG-9-R1 Pair2." |
| 3 | "제619조② 작업허가 확인사항 공통 근거. 감시인·보호구종류·결재3단 차이. RELATED_FORM. LEG-9-R1 Pair3." |
| 4 | "시행규칙 제79조 도급협의체. 건설 특화형(순회점검·연락·대피). ref-gov-06 건설 적용. RELATED_FORM. LEG-9-R1 Pair4." |
| 5 | "산안법 제29조 교육 기록. 간략 실시기록부. 서명·강사·장소 없음. ref-c031 보조 매핑. RELATED_FORM. LEG-9-R1 Pair5." |
| 6 | "산안법 제52조 작업중지 절차 공통 근거. 재개승인자 서명 구조 차이. RELATED_FORM. LEG-9-R1 Pair6." |
| 7 | "산안법 제29조 교육 기록. 서명·참석자 포함. ref-c031 우선 매핑. RELATED_FORM. LEG-9-R1 Pair7." |
| 8 | "산안법 제38조 위험작업 허가. 위험확인→조치→승인→종료 구조 일치. 결재단계 차이. RELATED_FORM. LEG-9-R1 Pair8." |
| 9 | "시행규칙 제79조 도급협의체 일반형. 일반 도급사업 맥락 근접. ref-gov-06 우선 매핑. RELATED_FORM. LEG-9-R1 Pair9." |

---

## 8. 종료 보고

```
WO = WO-TAI-DOC-UNIFICATION-9-LINK-PREFLIGHT-001

TARGET_PAIRS       = 9
RECOMMENDED_RELATION = RELATED_FORM

SAAS_DOCS_ACTIVE   = 9/9
REF_FORMS_EXIST    = 7/7 (고유 Ref 7개)
EXISTING_LINKS     = 0  (중복 없음)
READY_TO_PROPOSE   = 9
BLOCKED_PAIRS      = 0
DUPLICATE_PAIRS    = 0

MULTI_MAPPING_REF  = 2 (ref-c031: Pair5+7, ref-gov-06: Pair4+9)
PRIORITY_ORDER     = DOC-OSH-006 우선/DOC-OSH-015 우선 (각 Ref별)

OWNER_APPROVAL     = PENDING
PRODUCTION_WRITE   = 0
NEW_DEVELOPMENT    = 0

RESULT = READY_FOR_OWNER_DECISION
```

---

**조회 소스 식별자**:
- document_forms: vwlahtguyggrhvslabax 2026-10-21 조회 (9행)
- reference_form_slug_registry + reference_form_content: vwlahtguyggrhvslabax 2026-10-21 조회 (7행)
- unified_document_link: vwlahtguyggrhvslabax 2026-10-21 조회 (9쌍 기존 링크 0건)
- 기준 커밋: d7521e05 (LEG-drift 증거 직전)
