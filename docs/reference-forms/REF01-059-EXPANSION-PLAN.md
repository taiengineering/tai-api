# REF01-059 단계별 확장 계획
Date: 2026-10-09
WO: WO-REF01-059
Phase: A — Read-Only 조사 산출물 (구현 지침 아님)
Source SoT: WO-052 corrected 189-row proposal; Coverage Matrix REF01-059-189-COVERAGE-MATRIX.md
DB mutations: 0

---

## 1. 전제 조건

- 이 문서는 Phase A 조사 결과 기반 제안임. 구현 승인 아님.
- Phase B 착수 전 GPT 승인 및 Owner 승인 필요.
- 기존 구현(REF-C002, REF-C012) 회귀 보호 유지 필수.
- RESEARCH_REPORT_ONLY 항목은 원본 확보 없이 구현 착수 금지.
- 코드 변경은 별도 WO 발행 후 실행.

---

## 2. 단계별 흐름 제안

```
Phase B-1 (SUPPORTED, 블로커 없음)
  PLAN: REF-C014, REF-C016
  FORM: REF-C001
  REGISTER: REF-C003, REF-C004, REF-C005

Phase B-2 (PARTIAL, SSV 근거)
  REPORT: REF-C015, REF-C013
  EVALUATION: REF-C008 (score_total_row 결정 후)

Phase B-3 (PARTIAL, 블록 결정 필요)
  CHECKLIST: checkbox_row 구현 결정 후
  RECORD: 원본 확보 후

Phase B-4 (UNVERIFIED, 원본 확보 필요)
  REFERENCE: 별도 원본 수집 WO
  RRO 항목들: 유형별 원본 확보 후 재분류

Phase B-5 (UNSUPPORTED)
  WORKFLOW_DIAGRAM: diagram_block 신규 WO 발행
```

---

## 3. 유형별 우선순위 테이블

| type | ssv_count | engine_ready_count | unverified_count | priority_basis |
|---|---|---|---|---|
| PLAN | 3 (C002완료/C014/C016) | 3 | 16 RRO | SSV 3개 SUPPORTED. C002 구현 완료. C014/C016 즉시 착수 가능. 최우선. |
| REGISTER | 3 (C003/C004/C005) | 3 | 32 RRO | SSV 3개 SUPPORTED. 블로커 없음. 우선. |
| FORM | 2 (C001/C012완료) | 2 | 24 RRO | SSV 2개 SUPPORTED (C012 완료). C001 즉시 착수 가능. 우선. |
| REPORT | 2 (C013/C015) | 0 (PARTIAL) | 12 RRO | SSV 2개 PARTIAL. labeled_grid+freeform_area 가능. 중간. |
| EVALUATION | 2 (C008/C011) | 0 (PARTIAL) | 10 RRO | SSV 2개 PARTIAL. score_total_row 결정 보류 중. 중간. |
| RECORD | 0 | 0 (PARTIAL) | 33 RRO | SSV 없음. 원본 확보 후 구조 파악 필요. 하위. |
| CHECKLIST | 0 | 0 (PARTIAL) | 39 RRO | SSV 없음. checkbox_row 블록 결정 선행 필요. 하위. |
| REFERENCE | 0 | 0 (UNVERIFIED) | 10 RRO | SSV 없음. 구조 미확인. 원본 확보 WO 필요. 최하위. |
| WORKFLOW_DIAGRAM | 1 (C010, HOLD) | 0 (UNSUPPORTED) | 0 | diagram_block 신규 WO. 별도 트랙. |

---

## 4. 선행 조건 목록

| 조건 | 관련 유형 | 상태 |
|---|---|---|
| GPT Phase A 보고서 독립 검증 | 전체 | 미착수 |
| REF-C014 원본 필드 GPT 승인 | PLAN | 미착수 |
| REF-C016 원본 필드 GPT 승인 | PLAN | 미착수 |
| REF-C001 원본 필드 GPT 승인 | FORM | 미착수 |
| REF-C003/C004/C005 원본 필드 GPT 승인 | REGISTER | 미착수 |
| REF-C008 score_total_row 없이 텍스트 대체 허용 여부 결정 | EVALUATION | 미결 |
| REF-C011 score_total_row 없이 텍스트 대체 허용 여부 결정 | EVALUATION | 미결 |
| checkbox_row 블록 구현 여부 결정 | CHECKLIST | 미결 |
| signature_line 블록 구현 여부 결정 | RECORD | 미결 |
| RECORD 유형 원본 확보 (GOV-01 등) | RECORD | 미착수 |
| REFERENCE 유형 원본 확보 WO 발행 | REFERENCE | 미착수 |
| diagram_block 신규 WO 발행 | WORKFLOW_DIAGRAM | 미착수 |

---

## 5. 잔여 블로커

| blocker_id | 설명 | 영향 유형 | 해결 경로 |
|---|---|---|---|
| BLK-01 | RESEARCH_REPORT_ONLY 173건 원본 미확인 | 전체 유형 | 원본 수집 WO 발행 |
| BLK-02 | REF-C006 obs=0 HOLD | EVALUATION | 원본 접근 확보 후 관찰 |
| BLK-03 | REF-C010 UNSUPPORTED (diagram_block 없음) | WORKFLOW_DIAGRAM | diagram_block 신규 WO |
| BLK-04 | checkbox_row 구현 결정 보류 | CHECKLIST | GPT/Owner 결정 |
| BLK-05 | score_total_row 구현 결정 보류 | EVALUATION | GPT/Owner 결정 |
| BLK-06 | signature_line 구현 결정 보류 | RECORD | GPT/Owner 결정 |
| BLK-07 | REF-C007 PROVISIONAL PLAN (gpt_review=Y) | PLAN | GPT 검토 완료 후 확정 |
| BLK-08 | REF-C009 PROVISIONAL REGISTER (gpt_review=Y) | REGISTER | GPT 검토 완료 후 확정 |
