---
title: WO-054 PATCH-2 QA 보고서 — 페이지 분할 개선
version: PATCH-2
date: 2026-10-09
status: PASS
---

# WO-054 PATCH-2 QA 보고서

## PATCH-2 변경 요약

| 항목 | PATCH-1 값 | PATCH-2 값 | 절약 |
|------|-----------|-----------|------|
| 결재란 레이블 행 높이 | None (자동 ≈10.6mm) | 7mm | ≈3.6mm |
| ROW_H_INFO (기본정보 행) | 8mm | 7mm | 2mm (×2행) |
| ROW_H_GOAL (전사목표 내용) | 22mm | 15mm | 7mm |
| 결재란↔기본정보 간격 | 1mm | 0mm (제거) | 1mm |
| 기본정보↔전사목표 간격 | 1mm | 1mm | — |
| 전사목표↔추진계획표 간격 | 2mm | 1mm | 1mm |
| **총 절약** | | | **≈14.6mm** |

## 페이지 분할 정책

- 10행 이하: 1페이지 전체 수용 (orphan 없음)
- 초과 행: ReportLab 기본 split (`repeatRows=1`) 사용
- 빈 행 최소 높이: ROW_H_PLAN = 14mm (ROWHEIGHT 강제)
- 별도 orphan-control 알고리즘 없음 — 레이아웃 압축으로 구조적 예방

## 테스트 케이스별 결과

### P2-QA-01: blank (기본 5행)
- **결과**: PASS
- 페이지 수: 1
- 데이터 행: 5 (빈 행)
- 표 머리글 반복: N/A (1페이지)
- 불필요한 빈 페이지: 없음

### P2-QA-02: example (10행)
- **결과**: PASS
- 페이지 수: 1
- 데이터 행 (1페이지): 10
- 이전 PATCH-1 상태: 9행 + orphan 1행 (2페이지)
- PATCH-2 후: 10행 전체가 1페이지에 수용됨
- 표 머리글 반복: N/A (1페이지)

### P2-QA-03: multipage (18행)
- **결과**: PASS
- 페이지 수: 2
- 데이터 행 (1페이지): 10
- 데이터 행 (2페이지): 8 + 표 머리글 반복 PASS
- 페이지 번호: 1/2, 2/2 ✓
- 불필요한 빈 페이지: 없음

### P2-QA-04: longpage (30행)
- **결과**: PASS
- 페이지 수: 3
- 데이터 행 (1페이지): 10
- 데이터 행 (2페이지): 16 + 표 머리글 반복 PASS
- 데이터 행 (3페이지): 4 + 표 머리글 반복 PASS
- 페이지 번호: 1/3, 2/3, 3/3 ✓
- 불필요한 빈 페이지: 없음

### P2-QA-05: 빈 행 물리 높이 ≥ 14mm
- **결과**: PASS
- ROW_H_PLAN = 14mm, ROWHEIGHT TableStyle 적용
- blank 렌더 이미지에서 빈 행 높이 14mm 이상 시각 확인

### P2-QA-06: 폰트 크기 변경 없음
- **결과**: PASS
- 모든 폰트 크기 PATCH-1 동일 유지 (S_TITLE=16, S_HDR/S_BODY=10, S_SMALL=8)
- 행 높이 조정 = 여백/간격만 변경, 폰트 미영향

### P2-QA-07: 표 머리글 반복 (repeatRows=1)
- **결과**: PASS
- multipage 2페이지, longpage 2/3페이지 모두 "목표·세부 추진계획" 열 헤더 확인

### P2-QA-08: 페이지 번호 (N / 전체)
- **결과**: PASS
- NumberedCanvas 유지, 모든 페이지 하단 중앙 "N / 전체" 형식

### P2-QA-09: 기존 필드/디자인/메타데이터 유지
- **결과**: PASS
- 제목 전폭, 결재란 우측 하단, 기본정보 2행, 6열 구성 모두 PATCH-1과 동일
- PDF 메타데이터: title/author/subject PATCH-1 동일

### P2-QA-10: DOCX 편집 게이트
- **결과**: UNVERIFIED (PATCH-2 범위 외)
- DOCX는 PATCH-2 코드 변경 없음 (gen_c002_docx.cjs 미수정)
- PATCH-1 DOCX 편집 테스트 상태 그대로 (QA-08 UNVERIFIED)

## 산출물 목록

| 파일 | 크기 | 페이지 |
|------|------|--------|
| `output/TAI-FORM-C002-blank.pdf` | 50KB | 1 |
| `output/TAI-FORM-C002-example.pdf` | 70KB | 1 |
| `output/TAI-FORM-C002-multipage.pdf` | 78KB | 2 |
| `output/TAI-FORM-C002-longpage.pdf` | 89KB | 3 |

## 렌더 증거 (qa/pages/p2_*)

| 파일명 | 내용 |
|--------|------|
| `p2_blank-1.png` | 빈 서식 1페이지 |
| `p2_example-1.png` | 10행 예시 단일 페이지 |
| `p2_multipage-1.png` | 18행 1/2페이지 (10행) |
| `p2_multipage-2.png` | 18행 2/2페이지 (8행 + 헤더) |
| `p2_longpage-1.png` | 30행 1/3페이지 (10행) |
| `p2_longpage-2.png` | 30행 2/3페이지 (16행 + 헤더) |
| `p2_longpage-3.png` | 30행 3/3페이지 (4행 + 헤더) |

## 판정

| 항목 | 판정 |
|------|------|
| 10행 example 1페이지 수용 | PASS |
| orphan 1행 현상 해소 | PASS |
| 빈 행 ≥ 14mm | PASS |
| 폰트 크기 변경 없음 | PASS |
| 표 머리글 반복 | PASS |
| 페이지 번호 | PASS |
| 불필요한 빈 페이지 없음 | PASS |
| DOCX 편집 게이트 | UNVERIFIED |

**PATCH-2 종합: PASS (DOCX 편집 게이트 별도)**
