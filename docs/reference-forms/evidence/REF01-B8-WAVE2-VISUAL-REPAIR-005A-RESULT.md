---
wo: WO-REF01-060-B8-WAVE2-VISUAL-REPAIR-005A
evidence_type: VISUAL_REPAIR_PHASE1_SUPPLEMENT_RESULT
status: CANDIDATE_READY_GPT_REVIEW_PENDING
date: 2026-10-10
base_head: 087b3ec3ff4a25c8a0eb3d82b6543ebde3d8b5be
engine_py_sha8: be4899da
engine_cjs_sha8: 375250c7
---

# REF01-B8-WAVE2-VISUAL-REPAIR-005A-RESULT

WO-REF01-060-B8-WAVE2-VISUAL-REPAIR-005A Phase 1 보완 결과.  
3건 의미 축소 레이블 재교정, DOCX 라운드트립 freeform_area 포함 완전화.

## Preflight 결과

| 항목 | 결과 |
|------|------|
| BASE HEAD | 087b3ec3ff4a25c8a0eb3d82b6543ebde3d8b5be PASS |
| working tree clean (pre-run) | PASS |
| ENGINE PY SHA8 | be4899da MATCH |
| ENGINE CJS SHA8 | 375250c7 MATCH |
| B8 28개 출력 SHA256 | 28/28 MATCH — 출력 불변 |
| FROZEN 24개 SHA256 | 24/24 MATCH — 불변 |
| 기존 11건 B8 JSON | NO_CHANGE |

## 1. 레이블 재교정 (005 → 005A)

### 배경 — 물리적 폭 제약

`build_basic_info()` 셀 유효 텍스트 폭 = (170/2 − 2×3)mm = 79mm = **223.90pt** (NanumGothic 10pt).  
레이블 + `": ____________________________"` 합산폭이 이 값을 초과하면 래핑 → 테두리 충돌 재발.

### 변경 레이블 표 (005 대비)

| 폼 | 섹션.필드 | 005 후보 | 005A 후보 | 005A 합산폭 | 비고 |
|----|----------|---------|---------|-----------|------|
| C031 | S01.F07 | "증빙종류·보관" | **"출석증빙·보관"** | 217.73pt ✓ | 출석(출석증빙) 보존; "위치"는 물리적 한계로 추가 불가 (보관처/위치 최소 227pt) |
| C043 | S01.F05 | "참여자/명단" | **"참여/명단참조"** | 218.58pt ✓ | 명단참조 복원; 참여자(7자)는 모든 조합에서 228pt 이상 → 불가 |
| C044 | S01.F04 | "적용 작업대상" | **"대상·적용 작업"** | 220.53pt ✓ | 작업대상·적용작업 두 개념 구분·점 분리 유지 |

### 미변경 레이블 (GPT 미지적)

| 폼 | 섹션.필드 | 레이블 | 폭 |
|----|----------|--------|-----|
| C031 | S01.F06 | "교육자료·버전" | 217.73pt ✓ |
| C044 | S01.F01 | "물질명/제품명" | 219.34pt ✓ |

### 물리적 한계 고지 (C031 F07 / C043 F05)

NanumGothic 10pt에서 한글 1자 ≈ 9.4pt. 아래 한계로 인해 더 긴 표현은 달성 불가:

| 폼.필드 | 이상적 레이블 예 | 합산폭 | 결론 |
|--------|------------|-------|------|
| C031.F07 | "출석증빙·보관처" | 227.13pt | OVER +3.2pt — 불가 |
| C031.F07 | "출석증빙·보관위치" | 237.13pt | OVER +13.2pt — 불가 |
| C043.F05 | "참여자/명단참조" | 227.98pt | OVER +4.1pt — 불가 |
| C043.F05 | "훈련참여/명단참조" | 237.38pt | OVER +13.5pt — 불가 |

"출석증빙·보관": "출석증빙"(attendance evidence)으로 출석 맥락 명확, "보관" 기재 공간 제공.  
"참여/명단참조": "명단참조"(list reference) 복원, "참여" 는 문맥상 훈련 참여자 지칭.

## 2. DOCX 라운드트립 완전화

### 005 vs 005A 마커 범위

| 섹션 유형 | 005 | 005A |
|---------|-----|------|
| basic_info | ✓ | ✓ |
| repeat_table | ✓ | ✓ |
| freeform_area | ✗ | **✓ (신규 추가)** |

### 폼별 freeform_area 섹션

| 폼 | 섹션 ID | 레이블 | DOCX 테이블 |
|----|--------|--------|-----------|
| C031 | S02 | "교육 내용 요약" | T2 (1col × 2rows) |
| C043 | S02 | "훈련 시나리오 개요" | T2 (1col × 2rows) |
| C043 | S03 | "대응단계별 실시 내용" | T3 (1col × 2rows) |
| C044 | S02 | "주지 핵심 위험정보 요약" | T2 (1col × 2rows) |
| C044 | S04 | "후속조치 내용 및 확인" | T4 (1col × 2rows) |

freeform 주입: `tbl.rows[1].cells[0].paragraphs[-1].add_run(marker)` (row[0]=헤더, row[1]=내용)

### 마커 수 정정

| 폼 | 005 (기록 오류) | 005 (JSON 실제) | 005A (JSON) | 증가 |
|----|-------------|--------------|------------|------|
| C031 | 22 | 22 | 23 | +1 (S02 freeform) |
| C043 | 22 (오기) | 20 | 22 | +2 (S02+S03 freeform) |
| C044 | 21 (오기) | 19 | 21 | +2 (S02+S04 freeform) |

## 3. 후보 검증 결과

### 경계 충돌 탐지

| 폼 | 원본 충돌 | 005A 후보 충돌 | 결과 |
|----|---------|------------|------|
| C031 | 8 | 0 | DEFECT_RESOLVED |
| C043 | 4 | 0 | DEFECT_RESOLVED |
| C044 | 7 | 0 | DEFECT_RESOLVED |

### 후보 PDF 검증

| 폼 | 페이지 수 | 방향 | 레이블 수 | 경계 충돌 |
|----|---------|------|---------|---------|
| C031 | 1p | portrait | 13/13 | 0 |
| C043 | 1p | portrait | 12/12 | 0 |
| C044 | 1p | portrait | 11/11 | 0 |

### 후보 DOCX 라운드트립 (전 입력영역 포함)

| 폼 | 마커 총수 | 마커 보존 | 상태 |
|----|---------|---------|------|
| C031 | 23 | 23/23 | PASS |
| C043 | 22 | 22/22 | PASS |
| C044 | 21 | 21/21 | PASS |

LibreOffice DOCX 렌더: UNVERIFIED_LIBREOFFICE_NOT_INSTALLED

## 4. 회귀 테스트

```
pytest docs/reference-forms/scripts/test_common_engine.py -q
382 passed, 5 warnings in 18.57s   FAIL=0
```

(375 기존 + 7 C1310 신규 — 005A에서 test_common_engine.py 변경 없음)

## 5. 증거 파일 (005A 갱신분)

| 파일 | 설명 |
|------|------|
| `evidence/visual-repair-005/CAND_C031_pdf_page1.png` | C031 005A 후보 PDF 150dpi |
| `evidence/visual-repair-005/CAND_C043_pdf_page1.png` | C043 005A 후보 PDF 150dpi |
| `evidence/visual-repair-005/CAND_C044_pdf_page1.png` | C044 005A 후보 PDF 150dpi |
| `evidence/visual-repair-005/c031_candidate_v1.json` | C031 005A 후보 JSON (REVIEW_ONLY) |
| `evidence/visual-repair-005/c043_candidate_v1.json` | C043 005A 후보 JSON (REVIEW_ONLY) |
| `evidence/visual-repair-005/c044_candidate_v1.json` | C044 005A 후보 JSON (REVIEW_ONLY) |
| `evidence/visual-repair-005/qa_matrix_005.json` | 005A QA 결과 (마커 수 정정) |

## 6. 불변 확인

```
ORIGINAL_OUTPUT_28_SHA = 28/28 MATCH (변경 없음)
FROZEN_24_SHA          = 24/24 MATCH
COMMON_ENGINE_SHA      = PY be4899da MATCH / CJS 375250c7 MATCH
OLD_11_B8_SPECS        = NO_CHANGE
PRODUCTION_DB_WRITE    = 0
```

## 7. 상태

```
WO                   = WO-REF01-060-B8-WAVE2-VISUAL-REPAIR-005A
BASE_HEAD            = 087b3ec3ff4a25c8a0eb3d82b6543ebde3d8b5be
LABEL_SEMANTICS      = C031.F07 출석증빙·보관(217.73pt) / C043.F05 참여/명단참조(218.58pt)
                       / C044.F04 대상·적용 작업(220.53pt) — 물리적 최장 보존 확인
DOCX_COVERAGE        = basic_info + repeat_table + freeform_area 전 입력영역
C031_CANDIDATE       = PASS (cand_collisions=0, roundtrip=23/23) — GPT 시각 검토 대기
C043_CANDIDATE       = PASS (cand_collisions=0, roundtrip=22/22) — GPT 시각 검토 대기
C044_CANDIDATE       = PASS (cand_collisions=0, roundtrip=21/21) — GPT 시각 검토 대기
DOCX_BLANK_RENDER    = UNVERIFIED_LIBREOFFICE_NOT_INSTALLED
DOCX_EDITED_RENDER   = UNVERIFIED_LIBREOFFICE_NOT_INSTALLED
REGRESSION           = 382 passed FAIL=0
ORIGINAL_OUTPUT_28   = 28/28 MATCH
FROZEN_24            = 24/24 MATCH
COMMON_ENGINE        = PY/CJS MATCH
OLD_11_B8_SPECS      = NO_CHANGE
PRODUCTION_DB_WRITE  = 0
PR_MERGE             = BLOCKED
DEPLOY               = BLOCKED
PUBLICATION          = INTERNAL_POC_ONLY
NEXT_GATE            = GPT_CANDIDATE_REVIEW
PHASE_2              = NOT_AUTHORIZED (canonical output replacement requires GPT review + Owner authorization)
```
