# REF01-059 대표 검증 후보 (유형별)
Date: 2026-10-09
WO: WO-REF01-059
Phase: A — Read-Only 조사 산출물
Source SoT: WO-052 corrected 189-row proposal
DB mutations: 0

---

## 선정 기준

1. SSV 항목 우선 (SOURCE_STRUCTURE_VERIFIED)
2. 엔진 재사용성 높은 것
3. 블로커 없는 것
4. RESEARCH_REPORT_ONLY 항목은 원본 확보 조건부 후보

---

## 참고: 구현 완료 항목

이미 완료된 항목. 재구현 불필요. 유형 대표 참고용으로만 기재.

| research_id | source_title | primary_type | obs_count | engine_coverage | status |
|---|---|---|---|---|---|
| REF-C002 | 안전보건활동 목표/세부 추진계획 | PLAN | 10 | SUPPORTED | 구현 완료 |
| REF-C012 | 안전작업 허가서 | FORM | 11 | SUPPORTED | 구현 완료 |

---

## 유형별 대표 검증 후보

### PLAN

| research_id | source_title | primary_type | confidence | obs_count | engine_coverage | selection_basis | blockers |
|---|---|---|---|---|---|---|---|
| REF-C014 | 재해 감소대책 수립 및 실행 계획서 작성 서식 | PLAN | SOURCE_STRUCTURE_VERIFIED | 10 | SUPPORTED | SSV; obs=10; REF-C002와 유사 패턴; PLAN 패턴 재사용 가능; non-provisional | 없음 |
| REF-C016 | 연간 안전보건교육 수립 서식 | PLAN | SOURCE_STRUCTURE_VERIFIED | 10 | SUPPORTED | SSV; obs=10; 교육계획 구조; basic_info+repeat_table 조합 가능; non-provisional | 없음 |

권장: REF-C014 (재해 감소대책, REF-C002 패턴 확장 검증에 적합)

---

### FORM

| research_id | source_title | primary_type | confidence | obs_count | engine_coverage | selection_basis | blockers |
|---|---|---|---|---|---|---|---|
| REF-C001 | 안전보건경영방침 | FORM | SOURCE_STRUCTURE_VERIFIED | 3 | SUPPORTED | SSV; obs=3; 단순 서식; approval+labeled_grid 패턴; non-provisional | 없음 |
| REF-C009 | 안전보건 전문인력 등 배치표 및 담당업무 | REGISTER | SOURCE_STRUCTURE_VERIFIED | 8 | SUPPORTED | SSV; obs=8; PROVISIONAL; 법정 직위 4종 ROW_LABEL; labeled_grid+repeat_table 가능 | PROVISIONAL; gpt_review=Y 미완 |

권장: REF-C001 (관찰 필드 3개로 단순. FORM 패턴 최소 검증에 적합.)

---

### REGISTER

| research_id | source_title | primary_type | confidence | obs_count | engine_coverage | selection_basis | blockers |
|---|---|---|---|---|---|---|---|
| REF-C003 | 위험기계·기구·설비 목록 작성 서식 | REGISTER | SOURCE_STRUCTURE_VERIFIED | 9 | SUPPORTED | SSV; obs=9; 설비 목록 레지스터; labeled_grid+repeat_table 조합; non-provisional | 없음 |
| REF-C004 | 유해·위험물질 목록 작성 서식 | REGISTER | SOURCE_STRUCTURE_VERIFIED | 14 | SUPPORTED | SSV; obs=14; 물질 목록 레지스터; 필드 수 가장 많음; non-provisional | 없음 |
| REF-C005 | 작업별 위험과관리 대장 | REGISTER | SOURCE_STRUCTURE_VERIFIED | 9 | SUPPORTED | SSV; obs=9; 작업 위험 관리 대장; non-provisional | 없음 |

권장: REF-C003 (obs=9, 블로커 없음, REGISTER 패턴 1차 검증에 적합)

---

### RECORD

SSV 항목 없음. RESEARCH_REPORT_ONLY만 존재.

| research_id | source_title | primary_type | confidence | obs_count | engine_coverage | selection_basis | blockers |
|---|---|---|---|---|---|---|---|
| GOV-01 | 산업안전보건위원회 회의록 | RECORD | RESEARCH_REPORT_ONLY | 0 | UNVERIFIED | 회의록은 일반적 헤더+참석자+안건+결의 구조. labeled_grid+repeat_table로 기본 구조 표현 가능. | 원본 확보 필요. obs=0. |
| REF-C024 | 안전보건교육일지 서식(엑셀, 한글) | RECORD | RESEARCH_REPORT_ONLY | 0 | UNVERIFIED | 교육일지는 헤더+참석자 목록 구조. repeat_table로 표현 가능. | 원본 확보 필요. obs=0. |

권장: GOV-01 (회의록 — 범용성 높은 RECORD 유형) 또는 REF-C024 (교육일지).
조건: 원본 구조 확인 후 판정. 현재 UNVERIFIED.

---

### CHECKLIST

SSV 항목 없음. RESEARCH_REPORT_ONLY만 존재.

| research_id | source_title | primary_type | confidence | obs_count | engine_coverage | selection_basis | blockers |
|---|---|---|---|---|---|---|---|
| REF-C021 | 지게차 정기점검표 | CHECKLIST | RESEARCH_REPORT_ONLY | 0 | UNVERIFIED | 정기점검표 = 체크 항목 목록. repeat_table 구조 가능. | 원본 확보 필요. obs=0. checkbox_row 결정 보류. |
| REF-C027 | 체크리스트형 위험성평가표 | CHECKLIST | RESEARCH_REPORT_ONLY | 0 | UNVERIFIED | 명칭에 "체크리스트" 명시. CHECKLIST 패턴 대표 후보. | 원본 확보 필요. obs=0. checkbox_row 결정 보류. |

권장: REF-C027 (체크리스트형 위험성평가표 — 유형명 명시적).
조건: checkbox_row 구현 결정 선행 필요. 현재 PARTIAL 한계 존재.

---

### EVALUATION

| research_id | source_title | primary_type | confidence | obs_count | engine_coverage | selection_basis | blockers |
|---|---|---|---|---|---|---|---|
| REF-C008 | 안전보건 전문이력 평가 기준 및 평가표 | EVALUATION | SOURCE_STRUCTURE_VERIFIED | 10 | PARTIAL | SSV; obs=10; EVALUATION_CRITERION(양호/보통/미흡)+COLUMN_HEADER 구조 확인; non-provisional | 합계 자동계산 불가. score_total_row 미구현. |
| REF-C011 | 도급·용역·위탁 업체 안전보건 수준 평가 | EVALUATION | SOURCE_STRUCTURE_VERIFIED | 17 | PARTIAL | SSV; obs=17; 대규모 평가표; 필드 수 가장 많음; non-provisional | 합계 자동계산 불가. score_total_row 미구현. |

권장: REF-C008 (obs=10, 구조 간결, score_total_row 없이 텍스트 대체 가능 여부 검증에 적합)

---

### REPORT

| research_id | source_title | primary_type | confidence | obs_count | engine_coverage | selection_basis | blockers |
|---|---|---|---|---|---|---|---|
| REF-C013 | 사고조사 보고서 서식 | REPORT | SOURCE_STRUCTURE_VERIFIED | 15 | PARTIAL | SSV; obs=15; 사고조사 보고서; labeled_grid+freeform_area 조합; non-provisional | 중첩 섹션 구조 일부 한계. |
| REF-C015 | 아차사고 보고서 서식 | REPORT | SOURCE_STRUCTURE_VERIFIED | 7 | PARTIAL | SSV; obs=7; 단순 보고서; obs 수 적어 구조 단순; non-provisional | 없음 |

권장: REF-C015 (obs=7, 단순 구조, REPORT 패턴 1차 검증에 적합)

---

### REFERENCE

SSV 항목 없음. 전체 10건 RESEARCH_REPORT_ONLY.

| research_id | source_title | primary_type | confidence | obs_count | engine_coverage | selection_basis | blockers |
|---|---|---|---|---|---|---|---|
| REF-C034 | 사고 비상대응 절차서 | REFERENCE | RESEARCH_REPORT_ONLY | 0 | UNVERIFIED | 절차서 = 지침/설명 문서. freeform_area 조합 가능 추정. | 원본 확보 필수. 구조 미확인. |
| REF-C018 | 안전보건관리담당자의 업무 | REFERENCE | RESEARCH_REPORT_ONLY | 0 | UNVERIFIED | 직무 정의 문서. REFERENCE 유형 단순 텍스트 구조 추정. | 원본 확보 필수. 구조 미확인. |

권장: 원본 확보 없이 후보 선정 불가. 별도 원본 수집 WO 발행 필요.

---

### WORKFLOW_DIAGRAM

| research_id | source_title | primary_type | confidence | obs_count | engine_coverage | selection_basis | blockers |
|---|---|---|---|---|---|---|---|
| REF-C010 | 사고 발생 대응 시나리오(처리 흐름도) | WORKFLOW_DIAGRAM | SOURCE_STRUCTURE_VERIFIED | 0 | UNSUPPORTED | SSV (WO-050 시각 확인); 24노드 흐름도; 유일한 WORKFLOW_DIAGRAM 항목 | diagram_block 미구현. UNSUPPORTED 확정. 별도 WO 필요. |

권장: 구현 불가. diagram_block 신규 WO 발행 후 재검토.

---

## 선정 요약

| primary_type | 권장 research_id | 조건 |
|---|---|---|
| PLAN | REF-C014 | 없음. 즉시 착수 가능. |
| FORM | REF-C001 | 없음. 즉시 착수 가능. |
| REGISTER | REF-C003 | 없음. 즉시 착수 가능. |
| RECORD | GOV-01 | 원본 확보 필요. |
| CHECKLIST | REF-C027 | checkbox_row 결정 필요. |
| EVALUATION | REF-C008 | score_total_row 없이 텍스트 대체 허용 여부 결정 필요. |
| REPORT | REF-C015 | 없음. 즉시 착수 가능. |
| REFERENCE | 미정 | 원본 확보 WO 발행 필요. |
| WORKFLOW_DIAGRAM | REF-C010 | diagram_block 신규 WO 필요. BLOCKED. |
