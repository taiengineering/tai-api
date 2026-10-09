---
wo: WO-REF01-060-B8-WAVE2-AUTO-QA-004
evidence_type: AUTO_QA_RESULT
status: AUTOMATED_QA_COMPLETE_GPT_REVIEW_PENDING
date: 2026-10-10
base_head: 9259e0b8dc8308ea51a1bc115fdfcae5b765bd22
engine_py_sha8: be4899da
engine_cjs_sha8: 375250c7
---

# REF01-B8-WAVE2-AUTO-QA-004-RESULT

WO-REF01-060-B8-WAVE2-AUTO-QA-004 B8 Wave2 자동화 QA 실행 결과.

## Preflight 결과

| 항목 | 결과 |
|------|------|
| BASE HEAD | 9259e0b8dc8308ea51a1bc115fdfcae5b765bd22 (PASS — expected SHA) |
| working tree clean (pre-run) | PASS |
| engine Python SHA8 (be4899da) | PASS — common_v1_engine.py |
| engine CJS SHA8 (375250c7) | PASS — common_v1_engine.cjs |
| B8 28개 출력 SHA256 | 28/28 MATCH (BUILD-003-RESULT.md 수록 값과 일치) |
| FROZEN 24개 SHA256 | 24/24 MATCH (batch_build.py FROZEN_SHA와 일치) |
| 기존 EVIDENCE-REPAIR-004 실행 여부 | 미실행 확인 — 이 WO가 대체 |
| BUILD-003 engine_py_sha8 오류 정정 | ad0777bf(batch_build.py) → be4899da(common_v1_engine.py) |

### BUILD-003 engine_py_sha8 정정 근거

BUILD-003 영수증에 `engine_py_sha8: ad0777bf`로 기록됐으나 이는 `batch_build.py`(실행기)의 SHA8이다.
"Python engine"의 정확한 식별 대상은 `common_v1_engine.py`(SHA256 첫 8자 = `be4899da...`)이다.
두 파일 모두 WO 기간 중 변경 없음 — 엔진 무결성은 유지됨. 기록 오류만 정정.

### design_gate_notes 불일치 고지

B8 14건 JSON 모두 `design_gate_notes`에 "GPT 검토 전 빌드 차단" 텍스트가 잔존하나
`design_gate_status = GPT_APPROVED_INTERNAL_POC_BUILD`로 BUILD-003에서 승인됨.
이 WO에서 JSON 편집은 금지됨(섹션 6) — 불일치 기록만 남김.

## 실행 환경

| 항목 | 값 |
|------|----|
| Python | 3.14.7 |
| pymupdf | 1.28.2 |
| python-docx | 1.2.0 |
| Pillow | 12.3.0 |
| LibreOffice | NOT_INSTALLED |
| 실행 스크립트 | docs/reference-forms/scripts/qa_004.py |
| 회귀 테스트 명령 | `pytest docs/reference-forms/scripts/test_common_engine.py -q` |
| 회귀 테스트 결과 | 375 passed, 5 warnings in 18.21s — FAIL=0 |

## QA 방법론 변경 고지

| 항목 | 값 |
|------|----|
| OWNER_MANUAL_QA | REPLACED_BY_AUTOMATED_QA (METHOD_CHANGE) |
| POLARIS_GUI_TEST | NOT_PERFORMED |
| AUTOMATED_PDF_LAYOUT | EXECUTED — PyMuPDF 1.28.2 |
| AUTOMATED_DOCX_STRUCTURAL | EXECUTED — python-docx 1.2.0 |
| AUTOMATED_DOCX_ROUNDTRIP | EXECUTED — python-docx 1.2.0 (python-only) |
| DOCX_LIBREOFFICE_RENDER | UNVERIFIED_LIBREOFFICE_NOT_INSTALLED |
| POLARIS_MACOS_COMPAT | UNVERIFIED — 별도 검증 필요 |
| GPT_VISUAL_REVIEW | PENDING |
| OWNER_APPROVAL | PENDING |

## 14-form QA 매트릭스

| 형식 ID | A PDF 레이아웃 | B DOCX 구조 | C 라운드트립 | 비고 |
|---------|--------------|------------|------------|------|
| C026 | PASS (labels=12/12, 1p, 595×842pt, Hangul OK) | PASS (1/1 table, 210×297mm portrait) | PASS (28/28 markers) | |
| C027 | PASS (labels=10/10, 1p, 595×842pt, Hangul OK) | PASS (1/1 table, 210×297mm portrait) | PASS (22/22 markers) | |
| C028 | PASS (labels=10/10, 1p, 595×842pt, Hangul OK) | PASS (1/1 table, 210×297mm portrait) | PASS (22/22 markers) | |
| C029 | PASS (labels=11/11, 1p, 595×842pt, Hangul OK) | PASS (1/1 table, 210×297mm portrait) | PASS (25/25 markers) | |
| C031 | PASS (labels=13/13, 1p, 595×842pt, Hangul OK) | PASS (1/1 table, 210×297mm portrait) | PASS (23/23 markers) | |
| C033 | PASS (labels=10/10, 1p, 595×842pt, Hangul OK) | PASS (1/1 table, 210×297mm portrait) | PASS (22/22 markers) | |
| C037 | PASS (labels=10/10, 1p, 842×595pt, landscape, Hangul OK) | PASS (1/1 table, 297×210mm landscape) | PASS (26/26 markers) | landscape 2/2 |
| C039 | PASS (labels=12/12, 1p, 842×595pt, landscape, Hangul OK) | PASS (1/1 table, 297×210mm landscape) | PASS (30/30 markers) | landscape 2/2 |
| C040 | PASS (labels=9/9, 1p, 595×842pt, Hangul OK) | PASS (1/1 table, 210×297mm portrait) | PASS (23/23 markers) | |
| C041 | PASS (labels=9/9, 1p, 595×842pt, Hangul OK) | PASS (1/1 table, 210×297mm portrait) | PASS (19/19 markers) | |
| C042 | PASS (labels=9/9, 1p, 595×842pt, Hangul OK) | PASS (1/1 table, 210×297mm portrait) | PASS (19/19 markers) | |
| C043 | PASS (labels=12/12, 1p, 595×842pt, Hangul OK) | PASS (1/1 table, 210×297mm portrait) | PASS (22/22 markers) | |
| C044 | PASS (labels=11/11, 1p, 595×842pt, Hangul OK) | PASS (1/1 table, 210×297mm portrait) | PASS (21/21 markers) | |
| GOV-01 | PASS (labels=12/12, 1p, 595×842pt, Hangul OK) | PASS (1/1 table, 210×297mm portrait) | PASS (24/24 markers) | |

**섹션 A 합계:** 14/14 PASS — PDF 구조·사이즈·방향·라벨·Hangul 전원 정상  
**섹션 B 합계:** 14/14 PASS (LibreOffice 렌더 UNVERIFIED)  
**섹션 C 합계:** 14/14 PASS (LibreOffice 렌더 UNVERIFIED; Polaris GUI UNVERIFIED)

## 섹션 A 상세 — PDF 레이아웃

- **검사 도구:** PyMuPDF 1.28.2 (`import pymupdf`)
- **명령:** `python3 docs/reference-forms/scripts/qa_004.py`
- **기준:** 유효 PDF, 1 page, A4(portrait=595×842pt / landscape=842×595pt), 방향 일치
- **라벨 추출:** JSON 섹션별 labels를 normalise 후 PDF 텍스트와 3자 부분 매칭
- **폰트/Hangul:** 모든 14건에서 한글 텍스트 추출 가능 (tofu 없음)
- **bbox 검사:** 페이지 경계 ±30pt 이탈 텍스트 없음, FONT_TOO_SMALL(4pt 이하) 없음
- **PNG 증거:** 150 DPI 래스터라이즈, `docs/reference-forms/evidence/qa-004/A_{CODE}_pdf_page1.png` 14건

## 섹션 B 상세 — DOCX 구조 파싱

- **검사 도구:** python-docx 1.2.0, zipfile(내장)
- **DOCX 구조:** T0=제목(1col) | T1=basic_info(2col) | T2+=freeform(1col)/repeat_table(>2col)
- **검사 항목:** ZIP 정상, word/document.xml 존재, 페이지 방향, repeat_table 컬럼 수, 헤더 라벨
- **LibreOffice 렌더:** UNVERIFIED_LIBREOFFICE_NOT_INSTALLED — Polaris/macOS 호환성 미검증

## 섹션 C 상세 — DOCX 라운드트립

- **마커 방식:** `MARKER_PREFIX = "TAI_QA_004_"` + 섹션/필드 식별자
- **주입 대상:** basic_info 전 필드(T1 매핑), repeat_table 데이터행 1–3(>2col 테이블), freeform_area 내용행(1col 테이블)
- **격리:** `/tmp` 복사본만 사용 — `docs/reference-forms/output/` 미수정
- **저장·재개·검증:** python-docx save → Document() 재개 → 전체 텍스트 마커 검색
- **마커 보존:** 전 14건 0 loss (마커 손실 없음)
- **LibreOffice 라운드트립:** UNVERIFIED_LIBREOFFICE_NOT_INSTALLED

## 증거 파일 목록

| 파일 | 크기 | 설명 |
|------|------|------|
| `evidence/qa-004/A_C026_pdf_page1.png` | 92KB | C026 PDF 원본 1페이지 |
| `evidence/qa-004/A_C027_pdf_page1.png` | 65KB | C027 PDF 원본 1페이지 |
| `evidence/qa-004/A_C028_pdf_page1.png` | 66KB | C028 PDF 원본 1페이지 |
| `evidence/qa-004/A_C029_pdf_page1.png` | 78KB | C029 PDF 원본 1페이지 |
| `evidence/qa-004/A_C031_pdf_page1.png` | 51KB | C031 PDF 원본 1페이지 |
| `evidence/qa-004/A_C033_pdf_page1.png` | 67KB | C033 PDF 원본 1페이지 |
| `evidence/qa-004/A_C037_pdf_page1.png` | 50KB | C037 PDF 원본 1페이지 (landscape) |
| `evidence/qa-004/A_C039_pdf_page1.png` | 57KB | C039 PDF 원본 1페이지 (landscape) |
| `evidence/qa-004/A_C040_pdf_page1.png` | 47KB | C040 PDF 원본 1페이지 |
| `evidence/qa-004/A_C041_pdf_page1.png` | 65KB | C041 PDF 원본 1페이지 |
| `evidence/qa-004/A_C042_pdf_page1.png` | 66KB | C042 PDF 원본 1페이지 |
| `evidence/qa-004/A_C043_pdf_page1.png` | 50KB | C043 PDF 원본 1페이지 |
| `evidence/qa-004/A_C044_pdf_page1.png` | 53KB | C044 PDF 원본 1페이지 |
| `evidence/qa-004/A_GOV-01_pdf_page1.png` | 52KB | GOV-01 PDF 원본 1페이지 |
| `evidence/qa-004/qa_matrix.json` | 14KB | 기계가독 QA 결과 전체 |

## 출력물 변경 없음 확인

```
EXISTING_OUTPUT_CHANGES = 0
COMMON_ENGINE_CHANGES   = 0
JSON_SPEC_CHANGES       = 0
FROZEN_SHA_24_MATCH     = 24/24
B8_SHA_28_MATCH         = 28/28
```

## 리스크 분류

| 항목 | 분류 | 내용 |
|------|------|------|
| PDF 레이아웃 | NON-BLOCKING | 14/14 PASS |
| DOCX 구조 | NON-BLOCKING | 14/14 PASS |
| DOCX 라운드트립 (python) | NON-BLOCKING | 14/14 PASS |
| LibreOffice DOCX 렌더 | UNVERIFIED | 환경 미설치 — 별도 검증 필요 |
| Polaris macOS GUI | UNVERIFIED | 미수행 — 방법론 변경으로 대체 |
| Hangul 폰트 | NON-BLOCKING | 모든 PDF 한글 추출 정상 |

## 상태

```
BASE_HEAD               = 9259e0b8dc8308ea51a1bc115fdfcae5b765bd22
EXISTING_OUTPUT_SHA     = 28/28 MATCH
FROZEN_SHA              = 24/24 MATCH
ENGINE_SHA              = Python be4899da MATCH / CJS 375250c7 MATCH
REGRESSION              = 375 passed FAIL=0
PDF_LAYOUT              = 14/14 PASS
DOCX_BLANK_RENDER       = 14/14 PASS (LibreOffice UNVERIFIED)
DOCX_EDIT_SAVE_REOPEN   = 14/14 PASS (LibreOffice UNVERIFIED)
EDITED_DOCX_RENDER      = UNVERIFIED_LIBREOFFICE_NOT_INSTALLED
OWNER_MANUAL_QA         = REPLACED_BY_AUTOMATED_QA (METHOD_CHANGE)
POLARIS_GUI             = NOT_PERFORMED
GPT_VISUAL_REVIEW       = PENDING
OWNER_APPROVAL          = PENDING
PR_MERGE                = BLOCKED
DEPLOY                  = BLOCKED
PUBLICATION             = INTERNAL_POC_ONLY
B8_CLOSED_FINAL         = NO
LEGAL_REVIEW            = PENDING
RIGHTS                  = UNVERIFIED
```
