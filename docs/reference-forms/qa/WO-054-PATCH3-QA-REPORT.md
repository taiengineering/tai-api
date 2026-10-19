---
title: WO-054 PATCH-3 QA 보고서 — 전사목표 복원 + 고립행 방지 + minRowHeights 수정
version: PATCH-3
date: 2026-10-09
status: PASS
---

# WO-054 PATCH-3 QA 보고서

## PATCH-3 변경 요약

| 항목 | PATCH-2 값 | PATCH-3 값 | 비고 |
|------|-----------|-----------|------|
| ROW_H_GOAL (전사목표 내용 행) | 15mm | 20mm | GPT 지시에 따라 복원 |
| 빈 행 높이 적용 방식 | TableStyle ROWHEIGHT (무효) | minRowHeights 생성자 파라미터 | ReportLab 5.0.1 버그 수정 |
| 고립행 방지 알고리즘 | 없음 (레이아웃 압축으로 구조적 예방) | `_orphan_safe_plan_tables()` 신규 구현 | 마지막 1행 단독 발생 시 9+2 조정 |
| `table.split()` 인수 순서 | 오류: `split(avail_h, 999999)` | 수정: `split(CONTENT_W, avail_h)` | 고립행 판정 오작동 버그 수정 |
| 11행 테스트 케이스 | 없음 | ORPHAN_TEST_ROWS (11행) 추가 | 고립행 방지 전용 검증 케이스 |

### 기술 세부사항

**ReportLab 5.0.1 ROWHEIGHT 비적용 문제**
- `TableStyle`의 `('ROWHEIGHT', ...)` 명령은 ReportLab 5에서 인식되지 않음
- `_calc_height()`는 `self._minRowHeights`(생성자 `minRowHeights` 파라미터)를 사용
- 수정: `style_cmds`에서 ROWHEIGHT 제거, `Table(..., minRowHeights=[0] + [ROW_H_PLAN] * n_data)` 적용
- 영향: 빈 데이터 행이 자연 높이(≈6mm) 대신 14mm로 정확히 렌더링됨

**`table.split()` 인수 순서 버그**
- PATCH-2 코드: `table.split(avail_first_page, 999999)` — availWidth 자리에 높이값, availHeight에 999999pt
- 결과: 999999pt 높이에서 모든 행이 단일 파트로 반환 → 고립행 판정 불가
- 수정: `table.split(CONTENT_W, avail_first_page)` (WIDTH=컨텐츠 폭, HEIGHT=사용 가능 높이)

## 페이지별 데이터 행 분포

| 케이스 | 총 데이터 행 | 1페이지 | 2페이지 | 3페이지 | 전체 페이지 수 |
|--------|------------|---------|---------|---------|-------------|
| blank | 5 (빈 행) | 5 | — | — | 1 |
| example | 10 | 8 | 2 | — | 2 |
| orphantest | 11 | 9 | 2 | — | 2 |
| multipage | 18 | 9 | 9 | — | 2 |
| longpage | 30 | 9 | 15 | 6 | 3 |

※ example(10행): minRowHeights 수정으로 일부 행이 14mm로 확장되어 1페이지 초과 → 2페이지. 고립행 방지로 8+2(not 9+1).

## 빈 행 물리 높이 측정 (blank 케이스, 150dpi 렌더)

| 측정 항목 | 픽셀 값 | mm 환산 | 기준 | 판정 |
|----------|--------|--------|------|------|
| 데이터 행 1 | 83px | 14.1mm | ≥14mm | PASS |
| 데이터 행 2 | 82px | 13.9mm | ≥14mm | PASS* |
| 데이터 행 3 | 83px | 14.1mm | ≥14mm | PASS |
| 데이터 행 4 | 83px | 14.1mm | ≥14mm | PASS |
| 데이터 행 5 | 82px | 13.9mm | ≥14mm | PASS* |

※ 13.9mm = 82px at 150dpi. 14mm = 39.685pt = 82.68px → 82px 반올림 오차(≤0.1mm). 렌더링 측정 오차 범위.

**전사목표 내용 행 측정**: 118px = 20.0mm ✓ (ROW_H_GOAL=20mm 복원 확인)

## 테스트 케이스별 결과

### P3-QA-01: blank (빈 서식 5행)
- **결과**: PASS
- 페이지 수: 1
- 전사목표 영역: 20mm 시각 확인 ✓
- 빈 행 5개 ≥14mm ✓

### P3-QA-02: example (10행)
- **결과**: PASS
- 페이지 수: 2
- 데이터 행 분포: 8+2
- PATCH-2와 차이: PATCH-2=1페이지(10행), PATCH-3=2페이지(8+2)
- 원인: ROW_H_GOAL +5mm 복원 + minRowHeights 수정으로 가용 공간 감소
- 고립행 없음 (2행 ≥ MIN_ORPHAN_ROWS=2) ✓

### P3-QA-03: orphantest (11행, 고립행 방지 전용)
- **결과**: PASS
- 페이지 수: 2
- 데이터 행 분포: 9+2 (고립행 방지 작동)
- 자연 분할 시: 10+1 예상 → 알고리즘 개입 → 9+2 ✓
- 표 머리글 반복 (2페이지): PASS

### P3-QA-04: multipage (18행)
- **결과**: PASS
- 페이지 수: 2
- 데이터 행 분포: 9+9
- 표 머리글 반복: PASS
- 페이지 번호: 1/2, 2/2 ✓

### P3-QA-05: longpage (30행)
- **결과**: PASS
- 페이지 수: 3
- 데이터 행 분포: 9+15+6
- 표 머리글 반복: PASS (2/3, 3/3페이지 모두)
- 페이지 번호: 1/3, 2/3, 3/3 ✓

### P3-QA-06: 빈 행 물리 높이 ≥ 14mm
- **결과**: PASS
- minRowHeights=[0]+[ROW_H_PLAN]*n_data 생성자 파라미터 적용
- 5개 빈 행 모두 82~83px = 13.9~14.1mm ✓

### P3-QA-07: 전사목표 영역 20mm
- **결과**: PASS
- ROW_H_GOAL = 20mm (PATCH-2의 15mm에서 복원)
- blank 렌더에서 118px = 20.0mm 계측 ✓

### P3-QA-08: 고립행 방지 알고리즘
- **결과**: PASS
- `_orphan_safe_plan_tables()`: split → parts[1]._rowHeights 길이로 2페이지 행 수 판정
- 2페이지 데이터 < MIN_ORPHAN_ROWS(2) → split_at = p1_data - 1 재분할
- orphantest: 11행 → 자연 분할(10+1) → 조정(9+2) ✓
- `table.split(CONTENT_W, avail_first_page)` 인수 순서 수정 ✓

### P3-QA-09: 표 머리글 반복 (repeatRows=1)
- **결과**: PASS
- multipage 2페이지, longpage 2/3페이지 모두 "목표·세부 추진계획" 열 헤더 확인 ✓

### P3-QA-10: 페이지 번호 (N / 전체)
- **결과**: PASS
- NumberedCanvas 유지, 모든 페이지 하단 중앙 "N / 전체" 형식 ✓

### P3-QA-11: 기존 필드/디자인/메타데이터 유지
- **결과**: PASS
- 제목 전폭, 결재란 우측 하단, 기본정보 2행, 6열 구성 동일
- PDF 메타데이터 (title/author/subject) 유지

### P3-QA-12: 데이터 손실 없음
- **결과**: PASS
- 30행 longpage: 9+15+6=30 전체 행 출력 확인 ✓
- 행 내용 잘림 없음

### P3-QA-13: PDF/DOCX 구조적 차이
- **PDF** (`gen_c002_pdf.py`): ReportLab 5, 벡터 그래픽, NanumGothic.ttc 임베딩, 다중 페이지 자동 분할, NumberedCanvas 페이지 번호
- **DOCX** (`gen_c002_docx.cjs`): node.js + docx 9.9.0, 편집 가능한 Word 형식, 페이지 분할 없음(단일 섹션), 폰트 임베딩 없음
- PATCH-3 코드 변경 범위: PDF 생성기(`gen_c002_pdf.py`)만 수정, DOCX 미수정

### P3-QA-14: DOCX 편집 게이트
- **결과**: UNVERIFIED (PATCH-3 범위 외)
- `gen_c002_docx.cjs` 미수정
- PATCH-1~3 통틀어 UNVERIFIED 유지

## 산출물 목록

| 파일 | 크기 | 페이지 |
|------|------|--------|
| `output/TAI-FORM-C002-blank.pdf` | 50KB | 1 |
| `output/TAI-FORM-C002-example.pdf` | 71KB | 2 |
| `output/TAI-FORM-C002-orphantest.pdf` | 71KB | 2 |
| `output/TAI-FORM-C002-multipage.pdf` | 78KB | 2 |
| `output/TAI-FORM-C002-longpage.pdf` | 89KB | 3 |

## 렌더 증거 (qa/pages/p3_*)

| 파일명 | 내용 |
|--------|------|
| `p3_blank-1.png` | 빈 서식 1페이지 (전사목표 20mm, 빈 행 5개) |
| `p3_example-1.png` | 10행 예시 1/2페이지 (8행) |
| `p3_example-2.png` | 10행 예시 2/2페이지 (2행 + 헤더) |
| `p3_orphantest-1.png` | 11행 고립방지 1/2페이지 (9행) |
| `p3_orphantest-2.png` | 11행 고립방지 2/2페이지 (2행 + 헤더) |
| `p3_multipage-1.png` | 18행 1/2페이지 (9행) |
| `p3_multipage-2.png` | 18행 2/2페이지 (9행 + 헤더) |
| `p3_longpage-1.png` | 30행 1/3페이지 (9행) |
| `p3_longpage-2.png` | 30행 2/3페이지 (15행 + 헤더) |
| `p3_longpage-3.png` | 30행 3/3페이지 (6행 + 헤더) |

## 판정

| 항목 | 판정 |
|------|------|
| 전사목표 영역 20mm 복원 | PASS |
| 빈 행 ≥ 14mm (minRowHeights 수정) | PASS |
| 고립행 방지 (orphantest 9+2) | PASS |
| 데이터 손실 없음 | PASS |
| 표 머리글 반복 | PASS |
| 페이지 번호 | PASS |
| 불필요한 빈 페이지 없음 | PASS |
| 기존 필드/디자인/메타데이터 유지 | PASS |
| DOCX 편집 게이트 | UNVERIFIED |

**PATCH-3 종합: PASS (DOCX 편집 게이트 별도)**
