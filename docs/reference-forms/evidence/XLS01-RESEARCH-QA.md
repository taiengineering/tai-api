---
wo: WO-REF01-XLS01-SCOPE-AUDIT-001
date: 2026-10-11
status: EVIDENCE_COLLECTED
publication: NOT_FOR_PUBLICATION
---

# XLS01 조사 QA 증거

WO-REF01-XLS01-SCOPE-AUDIT-001 조사 완결성 및 근거 검증.

---

## 1. 조사 건수 요약

| 항목 | 수량 |
|------|------|
| 조사 대상 (인벤토리 전체) | 189 |
| 조사 완료 | 189 |
| 미조사 | 0 |
| CSV 행 수 (헤더 제외) | 189 |

---

## 2. 근거 확인율

### 조사 근거 유형

| 근거 유형 | 건수 |
|---------|------|
| JSON 섹션 구조 직접 확인 | 약 115 (BUILT 서식) |
| 인벤토리 + 중복판정 문서 확인 | 74 (NOT_BUILT/OFFICIAL/NON_FORM) |
| JSON 없음(LEGACY/NON_FORM/OFFICIAL) | 약 25 |

### JSON 섹션 확인 방법

- `common_v1_engine` JSON의 `sections[]` 배열에서 `type`, `columns[]` 직접 열람
- `repeat_table` 섹션의 `columns[].label` 목록 추출
- `freeform_area`, `approval`, `basic_info`, `labeled_grid`, `text_flow` 구분

### 미확인 사항

| 항목 | 내용 |
|------|------|
| 계산식 법령 기준 | REF-C029 빈도×강도 배점표 등 법령 근거 미확인 |
| 수치 집계 상한 | CHW-03 재고량 단위(kg/L/개) 미확인 |
| REF-C002 구조 | LEGACY_OUTPUT_ONLY. JSON 미존재. 서식 구조 미확인 |
| REF-C012 구조 | LEGACY_OUTPUT_ONLY. gen_c012_pdf.py 별도 엔진. JSON 구조 다름 |
| REF-C072 | NEEDS_REVIEW 상태 유지. 조사 보류 |
| B15 8건 PDF/DOCX SHA | JSON 존재 확인. 출력물 SHA 미조회 |
| WORD_INTERACTIVE_QA | 모든 서식 UNVERIFIED |

---

## 3. JSON·인벤토리 연결 검증

### BUILT 서식 JSON 매핑 확인 (표본)

| research_id | JSON 파일 | 확인 |
|-------------|---------|------|
| CHW-01 | chw-01_v1.json | VERIFIED |
| CHW-02 | chw-02_v1.json | VERIFIED |
| CHW-03 | chw-03_v1.json | VERIFIED |
| GOV-09 | gov-09_v1.json | VERIFIED |
| P-09 | p-09_v1.json | VERIFIED |
| P-20 | p-20_v1.json | VERIFIED |
| P-26 | p-26_v1.json | VERIFIED |
| REF-C004 | c004_v1.json | VERIFIED |
| REF-C007 | c007_v1.json | VERIFIED |
| REF-C016 | c016_v1.json | VERIFIED |
| REF-C029 | c029_v1.json | VERIFIED |
| REF-C039 | c039_v1.json | VERIFIED |
| REF-C040 | c040_v1.json | VERIFIED |
| REF-C071 | c071_v1.json | VERIFIED |
| RP-01 | rp-01_v1.json | VERIFIED |
| RP-07 | rp-07_v1.json | VERIFIED |
| RP-08 | rp-08_v1.json | VERIFIED |
| RP-22 | rp-22_v1.json | VERIFIED |

### B15 인벤토리 미반영 8건 JSON 존재 확인

| research_id | JSON 파일 | 인벤토리 production_status | 충돌 |
|-------------|---------|--------------------------|------|
| PRA-22-02 | pra-22-02_v1.json | NOT_BUILT | YES (B15 미등록) |
| PRA-22-06 | pra-22-06_v1.json | NOT_BUILT | YES (B15 미등록) |
| PRA-22-08 | pra-22-08_v1.json | NOT_BUILT | YES (B15 미등록) |
| PRA-22-09 | pra-22-09_v1.json | NOT_BUILT | YES (B15 미등록) |
| PRA-22-10 | pra-22-10_v1.json | NOT_BUILT | YES (B15 미등록) |
| REF-C022 | c022_v1.json | NOT_BUILT | YES (B15 미등록) |
| REF-C023 | c023_v1.json | NOT_BUILT | YES (B15 미등록) |
| REF-C067 | c067_v1.json | NOT_BUILT | YES (B15 미등록) |

이 8건의 인벤토리 갱신은 이번 WO 범위 외. 별도 WO 발행 필요.

---

## 4. 기존 파일 불변 증거

이번 조사에서 기존 파일 변경 없음.

```
변경된 파일:
  docs/reference-forms/evidence/XLS01-189-SUITABILITY-EVIDENCE.csv  (신규)
  docs/reference-forms/evidence/XLS01-CANDIDATE-GROUPS.md            (신규)
  docs/reference-forms/evidence/XLS01-RESEARCH-QA.md                 (신규)

기존 파일 변경:
  scripts/*.json     → 0건
  output/*.pdf       → 0건
  output/*.docx      → 0건
  evidence/B14-189-INVENTORY.csv → 0건
  common_v1_engine.py → 0건
  batch_build.py      → 0건
```

---

## 5. 미확인·충돌 목록

| 항목 | 유형 | 내용 |
|------|------|------|
| B15 인벤토리 미등록 | 충돌 | 8건 JSON 존재하나 NOT_BUILT 상태. 인벤토리 갱신 WO 필요 |
| REF-C029 계산식 기준 | 미확인 | 빈도·강도 배점 법령 참조 필요. 임의 확정 금지 |
| REF-C007 연도 컬럼 | 미확인 | 2021·2022 컬럼명만 확인. 실제 연도 범위 미결정 |
| REF-C071 계산 | 조건부 확인 | 대상인원-실시인원=미수검자 계산 논리 확인. 법령 필수항목 아님 |
| REF-C004 수량 단위 | 미확인 | 화학물질별 단위 이질적. 합산 방법 미결정 |
| CHW-03 재고 계산 | 확인 | 차이수량=장부-실사 컬럼 명시. 계산 논리 명확 |
| REF-C072 | 상태 불명 | NEEDS_REVIEW 유지. Excel 조사 보류 |
| WORD_INTERACTIVE_QA | 전체 미확인 | 모든 DOCX Word 실제 입력 검증 미수행 |

---

## 6. 조사 범위 통계

| 구분 | 건수 |
|------|------|
| NON_FORM (NON_FORM_REFERENCE + OFFICIAL + LEGAL) | 24 |
| REUSE_EXISTING (대표 서식 재사용) | 25 |
| SINGLE_EVENT / DOC_PDF_ONLY 예비 | 약 45 |
| CHECKLIST / DAILY_LOG 예비 | 약 25 |
| Excel 후보 예비 (A~E 그룹) | 약 55 |
| CONDITIONAL (판정 보류) | 13 |
| B15 미등록 (조사 포함) | 8 |
| NEEDS_REVIEW | 1 |
| LEGACY_OUTPUT_ONLY | 2 |

※ 예비 분류는 GPT 최종 판정 전 참고값. xlsx_suitability_raw = 전체 GPT_REVIEW_REQUIRED.

---

## 7. 다음 단계 (XLS02)

GPT가 다음을 판정한다:

1. 189건 각각에 대한 최종 xlsx_suitability 확정
   (XLSX_REQUIRED / XLSX_RECOMMENDED / XLSX_CONDITIONAL / DOC_PDF_ONLY / REUSE_EXISTING / NOT_APPLICABLE)
2. REUSE_EXISTING 25건의 대표 서식 Excel 결과 연동 방식
3. 공통 워크북 그룹 확정 여부
4. B15 8건 미등록 대응 방향
5. 최종 제작 대상 목록 + 수량

Owner 승인 전 샘플 제작 시작 금지.
