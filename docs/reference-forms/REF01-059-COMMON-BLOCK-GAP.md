# REF01-059 공통 블록 Gap 분석
Date: 2026-10-09
WO: WO-REF01-059
Phase: A — Read-Only 조사 산출물
Source SoT: WO-052 corrected 189-row proposal; WO-049 observed_fields
DB mutations: 0

---

## 1. 현재 구현된 5개 공통 블록

| 블록명 | 설명 | 구현 상태 |
|---|---|---|
| approval | 결재란 (N열, 헤더+서명 행) | 구현 완료 |
| basic_info | 2열 기본정보 (레이블+값 쌍) | 구현 완료 |
| labeled_grid | 레이블 그리드 (행별 2셀 레이블+값) | 구현 완료 |
| freeform_area | 자유 기재 영역 (제목+빈 내용 영역) | 구현 완료 |
| repeat_table | 반복 테이블 (고정 열, N개 행) | 구현 완료 |

공통 내장 기능: 제목행, 페이지 번호, 여백, 폰트

검증된 조합 패턴:
- PLAN: approval + basic_info + freeform_area + repeat_table (REF-C002 검증)
- FORM: approval + labeled_grid + freeform_area (REF-C012 검증)

---

## 2. 유형별 Gap 테이블

| type | current_blocks_applicable | missing_capability | gap_description | impact_count |
|---|---|---|---|---|
| PLAN | approval, basic_info, freeform_area, repeat_table | 없음 | 기존 블록 조합으로 충분. REF-C002 패턴 재사용 가능. | SSV=3 (C002/C014/C016) |
| FORM (단순) | approval, labeled_grid, freeform_area | 없음 | REF-C012 패턴 재사용 가능. | SSV=2 (C001/C012) |
| REGISTER | labeled_grid, repeat_table, approval | 없음 | 헤더(labeled_grid)+반복항목(repeat_table) 조합 가능. | SSV=3 (C003/C004/C005) |
| FORM (복잡/PROVISIONAL) | repeat_table | PROVISIONAL 구조 미확인 | REF-C007: CATEGORY_LABEL+ROW_LABEL 구조. 중첩 카테고리 표현 한계. | SSV=1 (C007) |
| EVALUATION | repeat_table, freeform_area | score_total_row | 합계/소계 자동계산 불가. 텍스트 수동 입력 대체 가능하나 자동화 불가. | SSV=2 (C008/C011) |
| REPORT | labeled_grid, freeform_area | 없음 (단순) | labeled_grid+freeform_area 조합 가능. 일부 복잡 보고서는 중첩 섹션 한계. | SSV=2 (C013/C015) |
| RECORD | labeled_grid, repeat_table, approval | signature_line (선택) | 서명 라인을 approval 블록으로 대체 가능하나, 단독 서명 행이 필요한 경우 별도 블록 필요. | SSV=0; RRO=33 |
| CHECKLIST | repeat_table | checkbox_row | 행별 체크박스(적합/부적합/해당없음) 컬럼 필요. repeat_table 텍스트 대체(○/×/N/A)는 가능하나 시각적 체크박스 기호 렌더링 한계. | SSV=0; RRO=39 |
| REFERENCE | (미확인) | 없음 (조사 필요) | 전체 RESEARCH_REPORT_ONLY. 구조 파악 후 판정 필요. | SSV=0; RRO=10 |
| WORKFLOW_DIAGRAM | 없음 | diagram_block | 흐름도/다이어그램 렌더링 불가. 기존 5개 블록 중 해당 없음. | SSV=1 (C010) |

---

## 3. 신규 블록 후보 목록

> 참고: 이 목록은 조사 기반 후보 목록임. 구현 승인 아님. GPT 검토 및 Owner 승인 필요.

### 후보 A: checkbox_row

- 설명: 행별 체크박스 컬럼 (적합/부적합/해당없음 또는 O/X/NA)
- 트리거 유형: CHECKLIST (39건)
- 현재 대체 방법: repeat_table에 텍스트 심볼(○/×/N/A) 입력
- 대체 방법 한계: 시각적 체크박스 기호 렌더링 불가. DOCX에서 체크박스 필드 미지원.
- 영향 범위: CHECKLIST 39건 (모두 RESEARCH_REPORT_ONLY이므로 구조 확인 필요)

### 후보 B: score_total_row

- 설명: 합계/소계 자동계산 행 (배점 합계, 점수 소계)
- 트리거 유형: EVALUATION (12건)
- 현재 대체 방법: freeform_area에 수동 합계 텍스트 입력
- 대체 방법 한계: 배점 자동계산 불가. 수기 작성 시 오류 가능.
- 영향 범위: REF-C008 (10 obs), REF-C011 (17 obs) 및 RESEARCH_REPORT_ONLY 평가표

### 후보 C: signature_line

- 설명: 단독 서명 라인 블록 (서명인+날짜 1행)
- 트리거 유형: RECORD 일부 (서명/확인 영역)
- 현재 대체 방법: approval 블록 (복수 서명) 또는 freeform_area (자유 기재)
- 대체 방법 한계: approval은 복수 결재 구조 전용. 단독 서명 행은 구조 과잉. freeform_area는 구조 부족.
- 영향 범위: RECORD 33건 (모두 RESEARCH_REPORT_ONLY이므로 구조 확인 후 판단 필요)

### 후보 D: diagram_block

- 설명: 흐름도/다이어그램 렌더링 블록
- 트리거 유형: WORKFLOW_DIAGRAM (1건, REF-C010)
- 현재 대체 방법: 없음. 기존 5개 블록 중 해당 없음.
- 대체 방법 한계: DOCX에서 다이어그램 렌더링은 이미지 삽입 또는 외부 도구 필요.
- 영향 범위: REF-C010 (1건). 단독 유형.

---

## 4. 기존 블록 조합으로 해결 가능한 항목

이미 SUPPORTED 판정된 항목은 신규 블록 불필요. 중복 제안 방지를 위해 목록 기재.

| type | 해결 방법 | 해당 항목 |
|---|---|---|
| PLAN | approval + basic_info + freeform_area + repeat_table | REF-C002, C014, C016 |
| FORM (단순) | approval + labeled_grid + freeform_area | REF-C001, C012 |
| REGISTER | labeled_grid + repeat_table | REF-C003, C004, C005, C009 |
| REPORT (단순) | labeled_grid + freeform_area | REF-C013, C015 (PARTIAL이지만 기본 구조는 가능) |
| EVALUATION (기준 텍스트) | freeform_area + repeat_table | REF-C008 평가 기준 텍스트 섹션 |

---

## 5. 잔여 블로커

| blocker | 설명 | 영향 |
|---|---|---|
| RESEARCH_REPORT_ONLY 173건 | 원본 구조 미확인. 실제 Gap 판정 불가. | 유형별 PARTIAL/SUPPORTED 최종 판정 보류. |
| REF-C006 obs=0 HOLD | 빈도×강도법 구조 미확인. | EVALUATION Gap 판정 보류. |
| REF-C010 obs=0 HOLD | 다이어그램 24노드 구조. | UNSUPPORTED 확정. diagram_block 필요. |
| checkbox_row 결정 보류 | 텍스트 대체 허용 여부 미결정. | CHECKLIST 39건 PARTIAL 유지. |
| score_total_row 결정 보류 | 자동계산 요구 수준 미결정. | EVALUATION 12건 PARTIAL 유지. |
