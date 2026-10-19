---
wo: WO-REF01-060-B8-WAVE2-VISUAL-REPAIR-005B
evidence_type: VISUAL_REPAIR_PHASE1_FINAL_RESULT
status: CANDIDATE_READY_GPT_REVIEW_PENDING
date: 2026-10-10
base_head: cab4fe23f1ee2051834eef493d937d1bdb2e7771
engine_py_sha8: be4899da
engine_cjs_sha8: 375250c7
---

# REF01-B8-WAVE2-VISUAL-REPAIR-005B-RESULT

WO-REF01-060-B8-WAVE2-VISUAL-REPAIR-005B Phase 1 최종 보완 결과.  
C031 입력 안내문(`text_flow`) 추가, 전체 후보 JSON 메타데이터 복원.

## Preflight 결과

| 항목 | 결과 |
|------|------|
| BASE HEAD | cab4fe23f1ee2051834eef493d937d1bdb2e7771 PASS |
| working tree clean (pre-run) | PASS |
| ENGINE PY SHA8 | be4899da MATCH |
| ENGINE CJS SHA8 | 375250c7 MATCH |
| B8 28개 출력 SHA256 | 28/28 MATCH — 출력 불변 |
| FROZEN 24개 SHA256 | 24/24 MATCH — 불변 |
| 기존 11건 B8 JSON | NO_CHANGE |

## 작업 1 — C031 입력 안내 (`text_flow`)

### 추가된 섹션

```json
{
  "id":   "S04",
  "type": "text_flow",
  "paragraphs": [
    {
      "id":    "P01",
      "text":  "【작성 안내】 출석증빙·보관란에는 출석 증빙의 종류(예: 참석자 서명부)와 실제 보관 위치를 함께 기재하십시오.",
      "align": "left"
    }
  ]
}
```

- 기존 S01~S03 섹션 및 필드 ID 보존
- F07 레이블 `출석증빙·보관` 유지
- 공통 엔진 변경 없음 (text_flow는 엔진 기존 지원 타입)

### 검증 결과

| 항목 | 결과 |
|------|------|
| C031 후보 PDF 페이지 수 | 1p (불변) |
| C031 후보 PDF 경계 충돌 | 0 |
| 안내문 in PDF | PRESENT (`작성 안내` 확인) |
| 안내문 in DOCX | PRESENT (`작성 안내` 확인) |

## 작업 2 — 후보 JSON 메타데이터 복원

### 추가된 `_meta` 항목 (3건 공통)

```json
{
  "candidate_for_review": "WO-REF01-060-B8-WAVE2-VISUAL-REPAIR-005B",
  "candidate_status":     "REVIEW_ONLY_NOT_CANONICAL"
}
```

기존 `legal_review_status`, `rights_status`, `publication_status` 등 법률·권리·공개 항목 변경 없음.

| 폼 | candidate_metadata |
|----|-------------------|
| C031 | PRESENT |
| C043 | PRESENT |
| C044 | PRESENT |

## 최종 후보 레이블 요약

| 폼 | 섹션.필드 | 원본 | 005B 후보 | 폭 |
|----|----------|------|---------|-----|
| C031 | S01.F06 | "사용 교육자료(명칭·버전)" | "교육자료·버전" | 217.73pt ✓ |
| C031 | S01.F07 | "출석 증빙 종류·보관 위치" | "출석증빙·보관" | 217.73pt ✓ |
| C043 | S01.F05 | "훈련 참여자/명단 참조" | "참여/명단참조" | 218.58pt ✓ |
| C044 | S01.F01 | "화학물질/제품명" | "물질명/제품명" | 219.34pt ✓ |
| C044 | S01.F04 | "작업대상 또는 적용 작업" | "대상·적용 작업" | 220.53pt ✓ |

## 검증 결과 (전체)

### 경계 충돌

| 폼 | 원본 충돌 | 후보 충돌 | 결과 |
|----|---------|---------|------|
| C031 | 8 | 0 | DEFECT_RESOLVED |
| C043 | 4 | 0 | DEFECT_RESOLVED |
| C044 | 7 | 0 | DEFECT_RESOLVED |

### 후보 PDF

| 폼 | 페이지 | 방향 | 레이블 | 충돌 |
|----|------|------|------|------|
| C031 | 1p | portrait | 13/13 | 0 |
| C043 | 1p | portrait | 12/12 | 0 |
| C044 | 1p | portrait | 11/11 | 0 |

### 후보 DOCX 라운드트립 (basic_info + repeat_table + freeform_area 전 영역)

| 폼 | 마커 총수 | 보존 | 상태 |
|----|---------|------|------|
| C031 | 23 | 23/23 | PASS |
| C043 | 22 | 22/22 | PASS |
| C044 | 21 | 21/21 | PASS |

LibreOffice DOCX 렌더: UNVERIFIED_LIBREOFFICE_NOT_INSTALLED

## 회귀 테스트

```
pytest docs/reference-forms/scripts/test_common_engine.py -q
382 passed, 5 warnings in 17.92s   FAIL=0
```

## 증거 파일 (005B 갱신분)

| 파일 | 설명 |
|------|------|
| `evidence/visual-repair-005/CAND_C031_pdf_page1.png` | C031 005B 후보 PDF 150dpi (안내문 포함) |
| `evidence/visual-repair-005/c031_candidate_v1.json` | C031 005B 후보 JSON (REVIEW_ONLY, text_flow S04 포함) |
| `evidence/visual-repair-005/c043_candidate_v1.json` | C043 005B 후보 JSON (메타데이터 복원) |
| `evidence/visual-repair-005/c044_candidate_v1.json` | C044 005B 후보 JSON (메타데이터 복원) |
| `evidence/visual-repair-005/qa_matrix_005.json` | 005B QA 결과 |

## 불변 확인

```
ORIGINAL_OUTPUT_28_SHA = 28/28 MATCH (변경 없음)
FROZEN_24_SHA          = 24/24 MATCH
COMMON_ENGINE_SHA      = PY be4899da MATCH / CJS 375250c7 MATCH
OLD_11_B8_SPECS        = NO_CHANGE
PRODUCTION_DB_WRITE    = 0
```

## 상태

```
WO                   = WO-REF01-060-B8-WAVE2-VISUAL-REPAIR-005B
BASE_HEAD            = cab4fe23f1ee2051834eef493d937d1bdb2e7771
C031_GUIDANCE        = text_flow S04 추가 / PDF+DOCX 존재 확인
CANDIDATE_METADATA   = 3건 PRESENT (REVIEW_ONLY_NOT_CANONICAL)
C031_CANDIDATE       = PASS (cand_collisions=0, roundtrip=23/23, guidance=PRESENT, 1p) — GPT 검토 대기
C043_CANDIDATE       = PASS (cand_collisions=0, roundtrip=22/22) — GPT 검토 대기
C044_CANDIDATE       = PASS (cand_collisions=0, roundtrip=21/21) — GPT 검토 대기
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
PHASE_2              = NOT_AUTHORIZED (Owner 승인 전 canonical output replacement 금지)
```
