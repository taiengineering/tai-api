---
wo: WO-REF01-060-B17-REUSE-CONDITIONAL-RESOLUTION-001
date: 2026-10-11
status: SHARED_TEMPLATE_DISTINCT_CONFIRMED
publication: NOT_FOR_PUBLICATION
---

# B17 조건부 재사용 2건 판정 QA 증거

WO-REF01-060-B17-REUSE-CONDITIONAL-RESOLUTION-001 결과 증거 문서.
대상: REUSE_CONDITIONAL 2건(PRA-22-04, REF-C025) → SHARED_TEMPLATE_DISTINCT 전환.
신규 JSON/PDF/DOCX 생성 없음. DB 변경 없음.

---

## 1. 업무 목적·작업 트리거 비교

### 1-A. PRA-22-04 vs CHW-04

| 항목 | PRA-22-04 | CHW-04 |
|------|-----------|--------|
| 제목 | 화학물질 파손·누출품 격리 및 재고조정 승인서 | 화학물질 이상품 격리·처리 기록 |
| 유형 | FORM | REGISTER |
| 작업 트리거 | 손상·누출품 발견 → 재고조정 승인 요청 | 이상품 발생 시 격리 및 처리 |
| 핵심 업무 목적 | 재고조정 승인 결재 | 격리·처리 이력 추적 |
| 출력물 성격 | 승인 건별 단일 서식 | 다건 반복 대장 |
| 서식 구조 | FORM (건별 결재) | REGISTER (반복 기록표) |

### 1-B. REF-C025 vs REF-C012

| 항목 | REF-C025 | REF-C012 |
|------|----------|----------|
| 제목 | 위험작업 허가서 | 안전작업 허가서 |
| 유형 | FORM | FORM |
| 작업 트리거 | 위험작업 개시 전 허가 | 특별 작업 허가 신청 |
| 핵심 업무 목적 | 위험작업유형 구분 + 격리·방호 + 종료확인 | 작업 신청·허가 결재 |
| 엔진 | 미제작 | gen_c012_pdf.py / gen_c012_docx.cjs |
| _v1.json 등록 | 없음 (NOT_BUILT) | 없음 (c012_fields.json 별도 스키마) |

---

## 2. 제안 필드 vs 기존 입력항목 매트릭스

### 2-A. PRA-22-04 vs CHW-04

CHW-04 실제 구현 섹션:
- S01 basic_info: 사업장명, 담당자 (2 fields)
- S02 repeat_table (8 cols): 발생일, 화학물질명, 이상내용, 격리장소, 처리방법, 처리일, 처리자, 확인(입력)

| PRA-22-04 제안 필드 | CHW-04 대응 항목 | 커버리지 |
|--------------------|----------------|---------|
| 화학물질명·파손·누출 내용 | F02_CHEM, F03_ISSUE | PRESENT |
| 격리장소 | F04_LOC | PRESENT |
| 처리방법 | F05_METHOD | PRESENT |
| 재고조정 대상 및 조정 내용 | (없음) | MISSING |
| 재고조정 승인 대상 건 식별 | (없음) | MISSING |
| 재고조정 승인자 | (없음) | MISSING |
| 승인 여부 및 승인 시점 | (없음) | MISSING |
| 결재 서명란 (승인) | (approval 섹션 없음) | MISSING |

CHW-04에는 approval 섹션이 존재하지 않는다.
`확인(입력)` 열(F08_CONFIRM)은 자유기재 입력란으로, 정식 재고조정 승인 결재와 동일하게 간주할 수 없다.

**직접 재사용 불가 사유:** 재고조정 승인에 필요한 승인자·승인 내용·결재 서명 구조가 CHW-04에 독립 입력항목으로 존재하지 않는다.

### 2-B. REF-C025 vs REF-C012

REF-C012 실제 구현 섹션 (c012_fields.json):
- approval: 신청(AP01), 허가(AP02)
- labeled_grid: 작업종류, 신청부서, 직책, 성명, 허가요청기간, 작업장소, 장비투입, 작업인원
- freeform: 작업내용, 안전조치 사항

| REF-C025 제안 필드 | REF-C012 대응 항목 | 커버리지 |
|-------------------|-----------------|---------|
| 작업 식별(번호/제목) | (labeled_grid 내 작업종류 간접) | PARTIAL |
| 위험작업 유형 상세 구분 | (없음) | MISSING |
| 장소/시간 | 작업장소, 허가요청기간 | PRESENT |
| 사전 위험확인 결과 | (없음) | MISSING |
| 격리·방호 실시 내역 | (없음) | MISSING |
| 승인 | AP02 허가 | PRESENT |
| 작업 종료확인 | (없음) | MISSING |

안전조치 사항 freeform(min_height_mm=30)이 존재하나, 이를 근거로 격리·방호와 종료확인 항목이 모두 충족됐다고 판단하지 않는다.

**직접 재사용 불가 사유:** 위험작업유형 구분, 사전위험확인 결과, 격리·방호 실시 내역, 작업종료확인이 독립 입력항목으로 존재하지 않는다.

---

## 3. CHW-04 직접 재사용이 불가능한 이유

1. CHW-04는 REGISTER 유형 — 다건 반복 기록 대장이며, PRA-22-04는 건별 단일 승인 FORM
2. CHW-04에 approval 섹션(결재란) 없음
3. 재고조정 승인자, 승인 내용, 승인 시점을 기재할 독립 입력란 없음
4. 재고조정 승인과 격리·처리 기록은 업무 단계가 다름 — 격리는 현장, 승인은 별도 결재 단계

---

## 4. REF-C012 공통 엔진 호출 경로

REF-C012는 통합 batch_build.py에 등록되지 않았으나, 전용 생성기가 공통 엔진을 직접 호출한다.

```
gen_c012_pdf.py   → import common_v1_engine as eng → eng.generate(c012_fields.json, ...)
gen_c012_docx.cjs → const engine = require('./common_v1_engine.cjs') → engine.generate(...)
```

batch_build.py 주석(line 59):
```
# c012: legacy c012_fields.json schema — not common_v1 batch-compatible
```

따라서:
- 공통 엔진 사용: YES
- 통합 배치 등록: NO (c012_fields.json 스키마 구조가 _v1.json 표준과 다름)

B14 기존 판정 메모의 `common-v1 미전환으로 유지보수 불가`는 부정확하다.
엔진은 공유됐으나 배치 등록 방식이 다른 것이다.

---

## 5. REF-C025 필드 부족 항목 요약

| 부족 항목 | 직접 추가 가능 여부 | 비고 |
|----------|-----------------|------|
| 위험작업 유형 상세 구분 | 별도 설계 필요 | labeled_grid 추가 |
| 사전 위험확인 결과 | 별도 설계 필요 | labeled_grid 추가 |
| 격리·방호 실시 내역 | 별도 설계 필요 | labeled_grid 추가 |
| 작업 종료확인 | 별도 설계 필요 | labeled_grid 또는 approval 추가 |

이번 단계에서 구현하지 않는다.

---

## 6. 판정 전후 B14 중복 수량

| 판정 | B14 확정 | B17 교정 후 |
|------|---------|-----------|
| REUSE_EXISTING | 25 | 25 |
| REUSE_CONDITIONAL | 2 | 0 |
| NEW_BUILD_REQUIRED | 7 | 7 |
| SHARED_TEMPLATE_DISTINCT | 1 | 3 |
| NON_FORM_REFERENCE | 5 | 5 |
| LEGAL_OR_RIGHTS_REVIEW | 2 | 2 |
| **합계** | **42** | **42** |

---

## 7. 향후 구현 시 공통 재사용 범위

### PRA-22-04

- CHW-04의 격리·처리 기록 구조 (basic_info + repeat_table) 참조
- 재고조정 승인에 필요한 입력 구조만 별도 정의 (approval 섹션 신설 필수)
- 공통 엔진(common_v1_engine) 재사용
- 격리기록(CHW-04)과 승인기록(PRA-22-04) 간 식별 관계 별도 설계 필요
- 동일 데이터를 복사하여 두 서식에 중복 관리하는 구조 금지

### REF-C025

- REF-C012의 labeled_grid(기본 작업정보), approval(신청/허가) 구조 참조
- gen_c012_pdf.py / gen_c012_docx.cjs의 엔진 호출 패턴 재사용
- c012_fields.json과 유사한 별도 c025_fields.json 정의 또는 _v1.json 표준 등록 방식 중 선택
- REF-C012 원본 구조를 임의로 변형하지 않음
- 위험작업유형 구분, 사전위험확인, 격리·방호, 종료확인을 독립 입력항목으로 추가

---

## 8. 기존 서식 수정·신규 출력물 생성 없음 확인

| 항목 | 확인 결과 |
|------|---------|
| CHW-04 JSON 수정 | 없음 |
| REF-C012 JSON(c012_fields.json) 수정 | 없음 |
| 신규 PDF 생성 | 0 |
| 신규 DOCX 생성 | 0 |
| output/ 파일 수 | 292 (불변) |
| 공통 엔진 SHA | py=be4899da / cjs=375250c7 / docx=3c117e8b (불변) |
| batch_build.py 수정 | 없음 |
| DB WRITE | 0 |

변경된 파일: B14-DEDUP-DECISIONS.md, B14-189-INVENTORY.csv, B17-REUSE-RESOLUTION-QA.md (신규) — 3건 한정.
