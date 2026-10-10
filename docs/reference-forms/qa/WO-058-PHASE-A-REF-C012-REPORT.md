# WO-058 Phase A — REF-C012 안전작업허가서 READ ONLY 조사 보고서

Date: 2026-10-09
Goal: G-muzv7o29-b4a5ab
Branch: docs/tai-reference-forms-charter-obj-20261008
Head: 3711c153
Status: PHASE_A_COMPLETE — GPT 독립검증 대기

---

## 1. DB 조회 결과 (project_ref: vwlahtguyggrhvslabax)

`public.ref_form_research_items WHERE research_id = 'REF-C012'` 결과: **1행**

| 항목 | 값 |
|---|---|
| research_id | REF-C012 |
| source_title | 안전작업 허가서 |
| source_evidence | PAGE_ENUMERATED |
| source_fields_status | FIELDS_UNVERIFIED |
| legal_review_status | PENDING |
| reuse_rights_status | RIGHTS_UNVERIFIED |
| disposition | INDEPENDENT_CANDIDATE |
| review_status | IN_PROGRESS |
| artifact_type | null (미분류) |
| canonical_title | null |
| practitioner_role | null |
| proposed_fields | [] (비어있음) |
| source_url | null |
| validation_blockers | SOURCE_FIELDS_UNVERIFIED, LEGAL_REVIEW_PENDING, RIGHTS_UNVERIFIED |

---

## 2. 원본 관찰 필드 (observed_fields 11개)

모두 source_section="안전작업허가서 활용 서식", verification=NATIVE_HWP_BODYTEXT_LABEL, requiredness=UNVERIFIED.

| # | 필드명 | 비고 |
|---|---|---|
| OF-01 | 작업종류 | — |
| OF-02 | 신청부서(업체명) | 자사 부서 or 도급업체 모두 포함 추정 |
| OF-03 | 직책 | 신청자 직책 |
| OF-04 | 성명(서명) | 신청자 서명 |
| OF-05 | 허가요청기간 | 날짜/시간 범위 |
| OF-06 | 작업내용 | 서술형 |
| OF-07 | 작업장소 | — |
| OF-08 | 장비투입 | — |
| OF-09 | 작업인원 | 인원 수 or 명단 |
| OF-10 | 안전조치 사항 | 서술형 or 체크리스트 — 구조 미확인 |
| OF-11 | 허가자 성명 | 결재자 서명 영역 — 결재란과 중복 가능성 있음 |

**주의**: 11개 필드는 HWP 단락 텍스트에서만 확인. 표 구조·셀 병합·섹션 경계·그룹핑 방식은 NATIVE_PARAGRAPH_ONLY 한계로 미확인.

---

## 3. 통합 연구 레지스터 컨텍스트

| 항목 | 값 |
|---|---|
| KOSHA 분류 | KOSHA_LIST |
| 공개 유형 | PUBLIC_EXAMPLE |
| 출처 보고서 | OBJ-REF-01-KOSHA-24-FORMS-SOURCE-03 (source_report 03) |
| 원본 증거 상태 | PAGE_ENUMERATED |
| 법령 검토 | PENDING |

**관련 서식**: REF-C025 "위험작업 허가서" (WORKFLOW_DRAFT / TAI_CANDIDATE / source_report 09) — 별도 후보. 동일 허가 패턴이나 TAI 제안분으로 별도 처리 필요.

---

## 4. LEG 조회 결과 (project_ref: wrfcedzgdrfupenzqhur)

### 4.1 법령 텍스트 일치 결과

**산업안전보건법 시행규칙 제50조** (공정안전보고서의 세부 내용 등):

> 3. 안전운전계획
>   다. **안전작업허가**

- 맥락: 공정안전보고서(PSM) 안전운전계획의 7개 하위 항목 중 하나.
- 적용 범위: 공정안전관리대상 사업장 (고압가스·유해화학물질 일정 수량 이상 취급).
- 서식 필드 요건: 법령 문언에 서식 구체 항목 명시 없음. "안전작업허가" 계획 수립 의무만 기재.

### 4.2 legal_runtime_obligation_norm 조회

`action ILIKE '%작업허가%'` 결과: **0행**

→ 안전작업허가 관련 의무 norm이 아직 추출·등록되지 않은 상태.

### 4.3 LEG 판정

| 구분 | 내용 |
|---|---|
| 직접 법령 근거 | 산업안전보건법 시행규칙 제50조 3호 다목 — PSM 사업장 한정 |
| 일반 사업장 의무 | 확인 불가 (LEG DB에서 비PSM 적용 근거 미발견) |
| 필드 수준 법령 필수성 | LEGAL_REVIEW_PENDING — 확정 금지 |
| norm_atom 등록 여부 | 미등록 |

**UNVERIFIED**: PSM 외 일반 위험작업에 대한 안전작업허가서 작성 의무 여부 별도 LEG 검토 필요.

---

## 5. 기존 생성기 재사용 후보

### 5.1 gen_c002_pdf.py 재사용 가능

| 구성요소 | 재사용 방식 |
|---|---|
| `register_fonts()` | 그대로 사용 |
| `NumberedCanvas` | 그대로 사용 (N / 전체 하단 페이지 번호) |
| `C_BLACK`, `C_HEADER_BG`, `C_ALT_BG`, `C_GRAY_TEXT` | 그대로 사용 |
| `ROW_H_INFO=7mm`, `ROW_H_SIGN=15mm` | 동일 기준 적용 |
| `build_approval()` | 90mm 3셀 패턴 — 결재란 구조 확정 후 재사용 |
| `_BASE` + `ts()` | 그대로 사용 |
| `SimpleDocTemplate` A4/20mm 설정 | 그대로 사용 |
| `CELL_PAD=3mm` | 그대로 사용 |

### 5.2 gen_c002_docx.cjs 재사용 가능

| 구성요소 | 재사용 방식 |
|---|---|
| `border()`, `noBorder()`, `shading()` | 그대로 사용 |
| `hdrCell()`, `bodyCell()`, `emptyCell()` | 그대로 사용 |
| `buildApproval()` Candidate B | 90mm 독립 우측 정렬 테이블 — WO-057B 검증 완료 |
| `spacer0()`, `spacer()` | 그대로 사용 |
| `CONTENT_W=170mm`, `APPROVAL_W=90mm`, `ROW_H_SIGN=15mm` | 동일 기준 적용 |
| Footer `PageNumber` 설정 | 그대로 사용 |

### 5.3 REF-C002 전용 — 재사용 불가 (구조 다름)

| 구성요소 | 이유 |
|---|---|
| `c002_fields.json` | PLAN 유형 6열 계획테이블 특화 |
| `build_basic_info()` N01–N04 | 목표계획서 전용 레이아웃 |
| `build_corporate_goal()` | 전사목표 단일 셀 특화 |
| `build_plan_table()` / `_orphan_safe_plan_tables()` | 반복 행 계획테이블 전용 |
| `COL_WIDTHS` [56,26,22,26,22,18] | REF-C002 6열 전용 |

---

## 6. FORM 유형 설계 방향 (COMMON-DESIGN-SPEC 기준)

| 항목 | 기준 |
|---|---|
| 서식 유형 | **FORM** (허가서) |
| 레이아웃 패턴 | 헤더 → 기본정보 → 결재란 → 단계별 확인 섹션 |
| 용지 | A4 세로 (170mm 본문 너비) |
| 결재란 | 90mm, 우측 정렬 (COMMON-DESIGN-SPEC 확정) |

예상 섹션 구성 (안 — 설계 확정 아님):

```
┌─────────────────────────────────────────────────────────────────┐
│   안전작업 허가서          │ 작성 │ 검토 │ 승인 (90mm 우측) │
├─────────────────────────────────────────────────────────────────┤
│  작업기본정보: 작업종류 / 신청부서(업체명) / 직책 / 성명(서명)  │
│  허가요청기간 / 작업내용 / 작업장소 / 장비투입 / 작업인원       │
├─────────────────────────────────────────────────────────────────┤
│  안전조치 사항                                                    │
│  ________________________________________________________________│
├─────────────────────────────────────────────────────────────────┤
│  허가자 성명 / (서명)                                             │
└─────────────────────────────────────────────────────────────────┘
```

---

## 7. Phase B 설계를 위한 OPEN 항목

| # | 결정 항목 | 현재 상태 |
|---|---|---|
| D01 | 결재란 구성: 표준 3인(작성/검토/승인) vs 신청자/허가자 2인 | UNRESOLVED |
| D02 | 안전조치 사항: 자유 서술형 vs 체크리스트형 | UNRESOLVED |
| D03 | 허가자 성명(OF-11): 결재란 "승인"과 동일 처리 vs 별도 서명란 | UNVERIFIED (원본 구조 미확인) |
| D04 | 신청부서(업체명): 자사/도급업체 구분 라벨 방식 | UNRESOLVED |
| D05 | TAI 추가 제안 필드: 허가번호, 위험등급, 유효기간, 작업자 명단 테이블 포함 여부 | GPT 결정 필요 |
| D06 | 법령 범위: PSM 전용 vs 일반 위험작업 — 서식 사용 대상 범위 | LEG 검토 필요 |
| D07 | 작업기본정보 레이아웃: 1열 나열형 vs 2열 그리드형 | UNRESOLVED |
| D08 | JSON 필드 명세 파일 이름: `c012_fields.json` 신규 생성 | Phase B 실행 필요 |

---

## 8. 블로커 확인

| 블로커 | DB 상태 | 상세 |
|---|---|---|
| SOURCE_FIELDS_UNVERIFIED | CONFIRMED | 11개 필드 텍스트 확인만. 표 구조·섹션 경계 미확인. |
| LEGAL_REVIEW_PENDING | CONFIRMED | 법령 필수 필드 미확정. PSM 외 적용 범위 불명확. |
| RIGHTS_UNVERIFIED | CONFIRMED | KOSHA PUBLIC_EXAMPLE — 재사용 권리 미검증. |

**Phase B 착수 조건**: GPT가 위 3개 블로커를 인지한 상태에서 FORM 설계 방향(D01–D08)에 대한 결정을 내리고 c012_fields.json 명세를 승인한 후 Phase B 착수 가능. 블로커 해소 전까지 법령 필수 여부(`FIELD_REQUIRED`) 확정 금지.

---

## 9. 요약

| 조사 항목 | 결과 |
|---|---|
| DB REF-C012 행 수 | 1행 확인 |
| observed_fields | 11개 (NATIVE_HWP_BODYTEXT_LABEL, 전원 UNVERIFIED) |
| proposed_fields | 0개 (비어있음) |
| LEG 법령 근거 | 시행규칙 제50조 — PSM 안전운전계획 항목으로 언급 (서식 구체 항목 없음) |
| norm_atom 등록 | 미등록 |
| 재사용 가능 구조 | helpers 전체 + buildApproval Candidate B + NumberedCanvas + 색상 상수 |
| 재사용 불가 | c002_fields.json, build_plan_table, _orphan_safe_plan_tables, COL_WIDTHS |
| OPEN 설계 결정 | D01–D08 (8건) |
| Phase B 착수 조건 | GPT D01–D08 결정 + c012_fields.json 명세 승인 |
