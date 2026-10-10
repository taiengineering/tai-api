---
wo: WO-054
title: REF-C002 PDF/DOCX 시제품 QA 보고서
form: TAI-FORM-C002
version: 0.1-DRAFT
date: 2026-10-09
status: EVIDENCE_READY
verifier: Claude Code (증거수집 전담)
independent_verification: GPT (독립검증 미완료)
---

# WO-054 QA 보고서 — REF-C002 시제품

## 생성 파일 경로

| 파일 | 크기 | 비고 |
|------|------|------|
| `output/TAI-FORM-C002-blank.pdf` | 50 KB (51583 bytes) | 빈 서식, 1페이지 |
| `output/TAI-FORM-C002-example.pdf` | 70 KB (71496 bytes) | 예시 데이터 10행, 1페이지 |
| `output/TAI-FORM-C002-multipage.pdf` | 78 KB (79533 bytes) | 18행, 2페이지 (표 헤더 반복 검증용) |
| `output/TAI-FORM-C002-blank.docx` | 11.6 KB (11908 bytes) | 빈 서식 |
| `output/TAI-FORM-C002-example.docx` | 12.4 KB (12666 bytes) | 예시 데이터 10행 |

## 실행 명령

```bash
# 의존성 설치 (최초 1회)
cd docs/reference-forms/scripts
npm install

# DOCX 생성
node gen_c002_docx.cjs all

# PDF 생성 (NanumGothic.ttc 필요)
python3 gen_c002_pdf.py all

# 또는 통합 실행
npm run gen-all
```

## 폰트 증거

| 항목 | 값 |
|------|-----|
| 파일 | NanumGothic.ttc |
| 라이선스 | SIL OFL 1.1 |
| 경로 (macOS MobileAsset) | `/System/Library/AssetsV2/com_apple_MobileAsset_Font8/7a0b5c0f3c1d41c4c52a33343496c9c65ad52c50.asset/AssetData/NanumGothic.ttc` |
| SHA256 | `7cbdb4c1e62a22e08a38e76b257d9bf361a295d9efb98c5a5fa9316452614bd0` |
| Git 포함 여부 | 미포함 (FONT_TTC 환경 변수로 재지정 가능) |
| subfontIndex 0 | NanumGothic Regular |
| subfontIndex 1 | NanumGothicBold |

PDF 폰트 임베딩 (`pdffonts TAI-FORM-C002-blank.pdf`):
```
name                      type       emb sub uni
AAAAAA+NanumGothicBold-1  TrueType   yes yes yes
AAAAAA+NanumGothic-0      TrueType   yes yes yes
```

## QA 결과

### QA-01: 빈 서식 사용성

**목적**: 사용자가 인쇄 후 손으로 작성 가능한지 확인  
**상태**: PASS  
**증거**: `pages/blank_pdf_p1.png`  
**관찰**:
- 제목 "안전보건 목표 및 추진계획서" 중앙 배치 확인
- 결재란 (작성/검토/승인) 3칸 오른쪽 배치 확인
- 사업장명 / 작성일 / 적용 연도 / 문서번호 기본정보 행 확인
- 전사 목표 입력 공란 (22mm 높이) 확인
- 계획 표 5행 (기본값 `default_row_count: 5`) 빈 행 확인
- 페이지 번호 "1 / 1" 하단 중앙 확인

---

### QA-02: 예시 데이터 입력

**목적**: 한국어 텍스트 10행이 정상 렌더링되는지 확인  
**상태**: PASS  
**증거**: `pages/example_pdf-1.png`  
**관찰**:
- 10행 예시 데이터 (안전보건 교육 실시, 위험성평가 등) 모두 표시
- 한국어 텍스트 깨짐 없음
- F05 (목표·세부 추진계획) 셀 내 텍스트 정상 wrap
- F09 예산 열 숫자값 우정렬 확인
- 짝수 행 ALT_BG (#F5F5F5) 배경색 확인

---

### QA-03: 표 헤더 반복 (다중 페이지)

**목적**: 2페이지 이상 시 표 헤더가 반복되는지 확인  
**상태**: PASS  
**증거**: `pages/multi-1.png`, `pages/multi-2.png`  
**관찰**:
- multipage (18행) PDF: 1페이지 "1 / 2", 2페이지 "2 / 2" 확인
- 2페이지 상단에 표 헤더 행 (목표·세부 추진계획 / 추진일정 / 성과지표 / 담당부서 / 예산(만원) / 달성률) 반복 확인
- ReportLab `Table(..., repeatRows=1)` 동작 VERIFIED

---

### QA-04: F06 추진일정 2줄 텍스트

**목적**: "연 2회\n(3월·9월)" 같은 줄바꿈 텍스트가 셀 내 정상 표시되는지 확인  
**상태**: PASS  
**증거**: `pages/example_pdf-1.png` — 첫 번째 행 F06 셀  
**관찰**:
- EXAMPLE_ROWS 첫 행 F06 = "연 2회\n(3월·9월)" — Python 줄바꿈 \n이 Paragraph로 처리됨
- 셀 높이 12mm(ROW_H_PLAN)에서 2줄 수용 확인

---

### QA-05: F09 "예산\n(만원)" 헤더 2줄

**목적**: F09 헤더가 22mm 칸 내에 "예산" + "(만원)" 2줄로 표시되는지 확인  
**상태**: PASS  
**증거**: `pages/example_pdf-1.png` — 헤더 행 F09 열  
**관찰**:
- c002_fields.json의 `"label": "예산\n(만원)"` → PDF에서 2줄 렌더링 확인
- DOCX에서는 TextRun `break: 1`로 처리 (UNVERIFIED — Word/한글 미확인)

---

### QA-06: PDF 메타데이터

**목적**: PDF 내부 메타데이터가 TAI 명세에 맞는지 확인  
**상태**: PASS  
**증거**: `pdfinfo TAI-FORM-C002-blank.pdf` 실행 결과  

| 필드 | 기대값 | 실제값 |
|------|--------|--------|
| Title | 안전보건 목표 및 추진계획서 | 안전보건 목표 및 추진계획서 ✓ |
| Subject | 산업안전보건 실무서식 | 산업안전보건 실무서식 ✓ |
| Author | TAI | TAI ✓ |
| Creator | TAI | TAI ✓ |
| Producer | TAI Document Pipeline v1 | TAI Document Pipeline v1 ✓ |
| Pages | 1 | 1 ✓ |
| Page size | A4 | 595.276 × 841.89 pts (A4) ✓ |

---

### QA-07: DOCX 메타데이터

**목적**: DOCX core.xml 메타데이터가 명세에 맞는지 확인  
**상태**: PASS  
**증거**: `zipfile` 로 `docProps/core.xml` 직접 추출  

| 필드 | 기대값 | 실제값 |
|------|--------|--------|
| dc:title | 안전보건 목표 및 추진계획서 | 안전보건 목표 및 추진계획서 ✓ |
| dc:creator | TAI | TAI ✓ |
| dc:description | 산업안전보건 실무서식 | 산업안전보건 실무서식 ✓ |
| cp:lastModifiedBy | TAI Document Pipeline v1 | TAI Document Pipeline v1 ✓ |

---

### QA-08: DOCX 편집 가능성

**목적**: Word 또는 한글에서 DOCX 파일을 열어 내용 편집 가능한지 확인  
**상태**: UNVERIFIED  
**사유**: 이 환경에서 Word/한글 GUI 실행 불가. DOCX 구조는 npm docx 9.9.0 정상 빌드(Exit 0) 및 core.xml 메타데이터 확인. 실제 편집 테스트는 수동 QA 필요.

---

### QA-09: PDF/DOCX 필드 패리티

**목적**: 단일 JSON 소스(c002_fields.json)에서 양 포맷이 동일 필드 구성을 갖는지 확인  
**상태**: PASS  
**증거**: gen_c002_pdf.py + gen_c002_docx.cjs 모두 `c002_fields.json` 단일 소스 참조  
**관찰**:
- 문서 제목, 결재 필드, 기본정보 필드, 전사목표, 계획 표 6컬럼 — 양 포맷 동일
- 열 너비 [58, 28, 24, 20, 22, 18]mm — 양 포맷 동일 (`COL_WIDTHS` / `COL_W`)
- 헤더 레이블 (F05~F10) — 양 포맷 동일
- 정렬 (left/center/right) — 양 포맷 동일

---

### QA-10: 한국어 텍스트 wrap (장문 셀)

**목적**: F05(58mm) 셀 내 장문 한국어가 잘리지 않고 wrap되는지 확인  
**상태**: PASS  
**증거**: `pages/example_pdf-1.png`  
**관찰**:
- "안전보건 교육 실시 (신규·정기)" (18자 + 괄호) — 58mm 셀 내 정상 표시
- "근골격계 부담작업 유해요인 조사" (다중페이지 추가 행) — 정상 wrap
- 텍스트 클리핑(잘림) 없음 확인

---

## 미결 항목

| 항목 | 상태 | 내용 |
|------|------|------|
| QA-08 DOCX 편집 | UNVERIFIED | Word/한글 수동 테스트 필요 |
| F09 DOCX 2줄 헤더 | UNVERIFIED | DOCX에서 "예산/(만원)" 2줄 표시 수동 확인 필요 |
| DOCX tableHeader 반복 | UNVERIFIED | Word에서 페이지 넘김 시 헤더 반복 여부 수동 확인 필요 |

## 독립검증 요청

GPT 독립검증 항목:
1. gen_c002_pdf.py — NumberedCanvas 구조, column widths, font 등록 방식
2. gen_c002_docx.cjs — TableLayoutType.FIXED, PageNumber 사용, Footer 구조
3. c002_fields.json — 필드 구성이 REF-C002-FIELD-SPEC-053.md v0.2와 일치 여부
4. QA-01~QA-10 결과 판정 적절성
5. UNVERIFIED 3건에 대한 처리 방침
