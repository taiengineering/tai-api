---
wo: WO-REF01-060-B8-WAVE2-VISUAL-REPAIR-005
evidence_type: VISUAL_REPAIR_PHASE1_RESULT
status: CANDIDATE_READY_GPT_REVIEW_PENDING
date: 2026-10-10
base_head: 60a7e6d9c75c0bb162e93bbc49a32889805964db
engine_py_sha8: be4899da
engine_cjs_sha8: 375250c7
---

# REF01-B8-WAVE2-VISUAL-REPAIR-005-RESULT

WO-REF01-060-B8-WAVE2-VISUAL-REPAIR-005 Phase 1 결과.  
3건 시각 결함 근본 원인 분석, JSON 후보 교정 설계, 후보 PDF/DOCX 생성(temp), 충돌 감지 QA 강화.

## Preflight 결과

| 항목 | 결과 |
|------|------|
| BASE HEAD | 60a7e6d9c75c0bb162e93bbc49a32889805964db PASS |
| working tree clean (pre-run) | PASS |
| ENGINE PY SHA8 | be4899da MATCH |
| ENGINE CJS SHA8 | 375250c7 MATCH |
| B8 28개 출력 SHA256 | 28/28 MATCH — 출력 불변 |
| FROZEN 24개 SHA256 | 24/24 MATCH — 불변 |
| 기존 11건 B8 JSON | NO_CHANGE — C031/C043/C044만 후보 JSON 별도 생성 |

## 1. 근본 원인 분석

### 엔진 레이아웃 상수 (common_v1_engine.py)

| 상수 | 값 | 위치 |
|------|----|------|
| `ROW_H_INFO` | 7mm = 19.84pt | line 53 |
| `CELL_PAD` | 3mm = 8.50pt | line 52 |
| `CONTENT_W` | 170mm = 481.9pt | line 51 |
| basic_info 셀 반폭 | 85mm = 240.9pt | build_basic_info() line 330 |
| 사용 가능 텍스트 너비 | 79mm = 223.9pt | 셀 반폭 − 2×CELL_PAD |

### build_basic_info() 핵심 코드 (line 327–340)

```python
def build_basic_info(section, content_w=None):
    cw   = content_w if content_w is not None else CONTENT_W
    flds = section['fields']
    half = cw / 2
    rows = []
    for i in range(0, len(flds), 2):
        left  = flds[i]   if i     < len(flds) else None
        right = flds[i+1] if i+1 < len(flds) else None
        rows.append([
            P(f"{left['label']}: ____________________________")  if left  else '',
            P(f"{right['label']}: ____________________________") if right else '',
        ])
    return Table(rows, colWidths=[half, half],
                 rowHeights=[ROW_H_INFO]*len(rows), style=ts())  # ← 고정 7mm
```

**핵심 문제:**
- `rowHeights=[ROW_H_INFO]*len(rows)` — JSON에서 재정의 불가한 고정 7mm
- `labeled_grid`는 `section.get('row_height_mm', 7)` JSON 오버라이드 지원, `basic_info`는 미지원
- S_BODY 스타일: size=10pt, leading=14pt
- 레이블 + ": ____________________________" 텍스트가 223.9pt 초과 → ReportLab 두 번째 줄로 래핑
- 두 번째 줄 bbox가 셀 하단 경계(border)를 가로지름 → 시각적 충돌

### 확인된 텍스트 폭 초과 (NanumGothic 10pt)

| 폼 | 필드 | 레이블 | 실제 폭 | 초과 |
|----|------|--------|---------|------|
| C031 | F06 | "사용 교육자료(명칭·버전)" | 265pt | +41pt |
| C031 | F07 | "출석 증빙 종류·보관 위치" | 264pt | +40pt |
| C043 | F05 | "훈련 참여자/명단 참조" | 252pt | +28pt |
| C044 | F01 | "화학물질/제품명" | 228pt | +4pt |
| C044 | F04 | "작업대상 또는 적용 작업" | 261pt | +37pt |

**JSON 단독 수정 가능 여부:** YES — 레이블 단축으로 해결 가능. ENGINE_CHANGE_REQUESTED 불필요.

## 2. 후보 JSON 교정 설계

### 교정 원칙

- 레이블 단축: 원래 의미가 서식 내에서 인간이 읽고 기입할 수 있도록 보존
- 필드 ID 보존: 기존 모든 ID 유지
- 기존 B8 JSON 파일 미수정: 후보 JSON은 `evidence/visual-repair-005/`에만 저장
- JSON 이외 변경 없음

### 후보 레이블 변경 표

| 폼 | 섹션.필드 | 기존 레이블 | 후보 레이블 | 실측 폭 변화 | 의미 보존 |
|----|----------|------------|------------|------------|---------|
| C031 | S01.F06 | "사용 교육자료(명칭·버전)" (265pt) | "교육자료·버전" (218pt) | −47pt → OK | 자료명·버전 양면 유지 |
| C031 | S01.F07 | "출석 증빙 종류·보관 위치" (264pt) | "증빙종류·보관" (218pt) | −46pt → OK | 증빙 종류·보관처 양면 유지 |
| C043 | S01.F05 | "훈련 참여자/명단 참조" (252pt) | "참여자/명단" (209pt) | −43pt → OK | 참여자/명단 참조 유지 |
| C044 | S01.F01 | "화학물질/제품명" (228pt) | "물질명/제품명" (219pt) | −9pt → OK | 물질명/제품명 양면 유지 |
| C044 | S01.F04 | "작업대상 또는 적용 작업" (261pt) | "적용 작업대상" (218pt) | −43pt → OK | 적용 작업대상 유지 |

후보 JSON 파일: `evidence/visual-repair-005/{c031,c043,c044}_candidate_v1.json`  
(status: `REVIEW_ONLY_NOT_CANONICAL` — 정규 출력 미포함)

## 3. 후보 검증 결과 (temp 전용, output/ 미수정)

### 경계 충돌 탐지 (border collision guard)

탐지 알고리즘: `qa_004.py::detect_border_collisions()` — PyMuPDF `get_drawings()` 수평선 + `get_text("words")` bbox 교차 판정 (tolerance=1pt)

| 폼 | 원본 충돌 수 | 후보 충돌 수 | 결과 |
|----|------------|------------|------|
| C031 | 8 | 0 | DEFECT_RESOLVED |
| C043 | 4 | 0 | DEFECT_RESOLVED |
| C044 | 7 | 0 | DEFECT_RESOLVED |

### 후보 PDF 검증

| 폼 | 페이지 수 | 방향 | 레이블 수 | 경계 충돌 |
|----|---------|------|---------|---------|
| C031 | 1p | portrait | 13/13 | 0 |
| C043 | 1p | portrait | 12/12 | 0 |
| C044 | 1p | portrait | 11/11 | 0 |

### 후보 DOCX 라운드트립

| 폼 | 마커 총수 | 마커 보존 | 상태 |
|----|---------|---------|------|
| C031 | 22 | 22/22 | PASS |
| C043 | 22 | 22/22 | PASS |
| C044 | 21 | 21/21 | PASS |

LibreOffice DOCX 렌더: UNVERIFIED_LIBREOFFICE_NOT_INSTALLED

## 4. QA 강화 — 경계 충돌 가드

### qa_004.py 업데이트

- `detect_border_collisions(pdf_path, tolerance=1.0)` 함수 추가 (WO-005 근거 주석)
- `qa_pdf()` 내 호출: `border_collisions` 카운트를 결과에 포함, 0 초과 시 HOLD
- qa_matrix.json 업데이트: C031(8)/C043(4)/C044(7) border_collisions 기록, A_PDF→HOLD

### 기존 충돌 부재 확인 (C031/C043/C044 제외 11건)

```
C026 clean (0) | C027 clean (0) | C028 clean (0) | C029 clean (0)
C033 clean (0) | C037 clean (0) | C039 clean (0) | C040 clean (0)
C041 clean (0) | C042 clean (0) | GOV-01 clean (0)
```

### test_common_engine.py — C1310 추가 (7건)

| 테스트 | 내용 | 결과 |
|--------|------|------|
| C1310_01 | C031 원본 충돌 ≥1 (부정 픽스처) | PASS |
| C1310_02 | C043 원본 충돌 ≥1 (부정 픽스처) | PASS |
| C1310_03 | C044 원본 충돌 ≥1 (부정 픽스처) | PASS |
| C1310_04 | C026 원본 충돌=0 (긍정 픽스처) | PASS |
| C1310_05 | C027 원본 충돌=0 (긍정 픽스처) | PASS |
| C1310_06 | C031 충돌 텍스트 = F06/F07 레이블 단어 | PASS |
| C1310_07 | 11개 비결함 B8 폼 전원 충돌=0 | PASS |

## 5. 회귀 테스트

```
pytest docs/reference-forms/scripts/test_common_engine.py -q
382 passed, 5 warnings in 19.08s   FAIL=0
```

(375 기존 + 7 C1310 신규)

## 6. 증거 파일

| 파일 | 설명 |
|------|------|
| `evidence/visual-repair-005/ORIG_C031_pdf_page1.png` | C031 원본 PDF 150dpi |
| `evidence/visual-repair-005/CAND_C031_pdf_page1.png` | C031 후보 PDF 150dpi |
| `evidence/visual-repair-005/ORIG_C043_pdf_page1.png` | C043 원본 PDF 150dpi |
| `evidence/visual-repair-005/CAND_C043_pdf_page1.png` | C043 후보 PDF 150dpi |
| `evidence/visual-repair-005/ORIG_C044_pdf_page1.png` | C044 원본 PDF 150dpi |
| `evidence/visual-repair-005/CAND_C044_pdf_page1.png` | C044 후보 PDF 150dpi |
| `evidence/visual-repair-005/c031_candidate_v1.json` | C031 후보 JSON (REVIEW_ONLY) |
| `evidence/visual-repair-005/c043_candidate_v1.json` | C043 후보 JSON (REVIEW_ONLY) |
| `evidence/visual-repair-005/c044_candidate_v1.json` | C044 후보 JSON (REVIEW_ONLY) |
| `evidence/visual-repair-005/qa_matrix_005.json` | 기계가독 후보 QA 결과 |

## 7. 불변 확인

```
ORIGINAL_OUTPUT_28_SHA = 28/28 MATCH (변경 없음)
FROZEN_24_SHA          = 24/24 MATCH
COMMON_ENGINE_SHA      = PY be4899da MATCH / CJS 375250c7 MATCH
OLD_11_B8_SPECS        = NO_CHANGE
PRODUCTION_DB_WRITE    = 0
```

## 8. 상태

```
WO                  = WO-REF01-060-B8-WAVE2-VISUAL-REPAIR-005
BASE_HEAD           = 60a7e6d9c75c0bb162e93bbc49a32889805964db
ROOT_CAUSE          = build_basic_info() ROW_H_INFO=7mm 고정 + 레이블 텍스트 223.9pt 초과 → 2행 래핑 → 하단 경계 충돌
C031_CANDIDATE      = PASS (cand_collisions=0, roundtrip=22/22) — GPT 시각 검토 대기
C043_CANDIDATE      = PASS (cand_collisions=0, roundtrip=22/22) — GPT 시각 검토 대기
C044_CANDIDATE      = PASS (cand_collisions=0, roundtrip=21/21) — GPT 시각 검토 대기
DOCX_BLANK_RENDER   = UNVERIFIED_LIBREOFFICE_NOT_INSTALLED
DOCX_EDITED_RENDER  = UNVERIFIED_LIBREOFFICE_NOT_INSTALLED
REGRESSION          = 382 passed FAIL=0
ORIGINAL_OUTPUT_28  = 28/28 MATCH
FROZEN_24           = 24/24 MATCH
COMMON_ENGINE       = PY/CJS MATCH
OLD_11_B8_SPECS     = NO_CHANGE
PRODUCTION_DB_WRITE = 0
PR_MERGE            = BLOCKED
DEPLOY              = BLOCKED
PUBLICATION         = INTERNAL_POC_ONLY
NEXT_GATE           = GPT_CANDIDATE_REVIEW
PHASE_2             = NOT_AUTHORIZED (canonical output replacement requires GPT review + Owner authorization)
```
