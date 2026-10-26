---
title: WO-056 REF-C002 DOCX 최종 품질 검증 보고서
version: 1.0
date: 2026-10-09
status: PARTIAL_PASS — 구조 수정 PASS / GUI 실사용 UNVERIFIED
base_commit: b1965bfd9bc1180ec736e745b59eee7b0e5baaff
---

# WO-056 REF-C002 DOCX 최종 품질 검증 보고서

## 1. 수정 내역 (gen_c002_docx.cjs)

### 수정 1: `HeightRule.AT_LEAST` → `HeightRule.ATLEAST`

| 항목 | 내용 |
|------|------|
| 원인 | `HeightRule.AT_LEAST` = `undefined` (docx 9.9.0 키 오타) |
| 영향 | `w:hRule` 속성 미기록 → Word가 `val` 값 무시, 완전 auto 처리 |
| 수정 | `gen_c002_docx.cjs` 내 9개소 전체 `ATLEAST`로 교체 |
| 결과 | 모든 `w:trHeight`에 `w:hRule="atLeast"` 기록됨 |

### 수정 2: `ROW_H_GOAL` 22mm → 20mm

| 항목 | 내용 |
|------|------|
| 변경 | `const ROW_H_GOAL = mm(22)` → `mm(20)` |
| 이유 | WO-056 지시: PDF 기준 20mm와 통일 |
| 전사목표 내용 행 twips | 1247 → 1133 (20.0mm) |

### 수정 3: `ROW_H_INFO` 8mm → 7mm

| 항목 | 내용 |
|------|------|
| 변경 | `const ROW_H_INFO = mm(8)` → `mm(7)` |
| 이유 | WO-056 지시: PDF 기준 7mm와 통일 |
| 기본정보 2행 twips | 453 → 396 (7.0mm) |

---

## 2. `w:hRule="atLeast"` 기록 검증

모든 `w:trHeight` 원소에 `w:hRule="atLeast"` 기록 확인 (blank.docx 13건, example.docx 18건).

OOXML 의미: 지정 값을 최솟값으로 유지, 내용이 많으면 자동 확장 → **긴 텍스트 입력 시 셀 확장 보장**.

---

## 3. 행 높이 계약 검증 (blank.docx, 전수)

| 섹션 | twips | mm | hRule | 판정 |
|------|------|----|-------|------|
| 제목 | 793 | 14.0mm | atLeast | PASS |
| 결재란 레이블 | 396 | 7.0mm | atLeast | PASS |
| 결재란 서명 공간 | 850 | 15.0mm | atLeast | PASS |
| 기본정보 행1 | 396 | 7.0mm | atLeast | PASS |
| 기본정보 행2 | 396 | 7.0mm | atLeast | PASS |
| 전사목표 레이블 | 396 | 7.0mm | atLeast | PASS |
| 전사목표 내용 | 1133 | 20.0mm | atLeast | PASS |
| 계획표 헤더 | 453 | 8.0mm | atLeast | PASS |
| 계획표 데이터 행 ×5 | 793 | 14.0mm | atLeast | PASS |

---

## 4. PDF ↔ DOCX 정합성 (수정 후)

| 항목 | PDF (PATCH-3) | DOCX (WO-056) | 판정 |
|------|--------------|--------------|------|
| ROW_H_GOAL (전사목표 내용) | 20mm | **20mm** | PASS |
| ROW_H_INFO (기본정보 행) | 7mm | **7mm** | PASS |
| ROW_H_SIGN (결재란 서명) | 15mm | 15mm | PASS |
| ROW_H_PLAN (데이터 행 최소) | 14mm | 14mm | PASS |
| 계획표 열 너비 (F05~F10) | 56/26/22/26/22/18mm | 56/26/22/26/22/18mm | PASS |
| 페이지 크기 | A4 (210×297mm) | A4 (210×297mm) | PASS |
| 여백 | 20mm × 4 | 20mm × 4 | PASS |
| 폰트 | NanumGothic 임베딩 | NanumGothic 참조 | NOTED |
| 표 머리글 반복 | repeatRows=1 | w:tblHeader | PASS |
| 페이지 번호 | NumberedCanvas | PAGE/NUMPAGES 필드 | PASS |
| 고립행 방지 알고리즘 | _orphan_safe_plan_tables | Word 자동 처리 | NOTED |

---

## 5. GUI 필요 항목 (UNVERIFIED)

| 항목 | 상태 |
|------|------|
| Word/한글에서 파일 열기 및 정상 표시 | UNVERIFIED |
| 사업장명·작성일·전사목표 직접 입력 | UNVERIFIED |
| 계획표 5행→10행→18행 확장 | UNVERIFIED |
| 긴 한글 입력 시 atLeast 셀 확장 실측 | UNVERIFIED |
| 다중 페이지 표 머리글 반복 렌더링 | UNVERIFIED |
| 저장 후 재열기 정합성 | UNVERIFIED |
| PDF 출력 시 기준 PDF와 비교 | UNVERIFIED |
| NanumGothic 없는 시스템 폰트 대체 | UNVERIFIED |

---

## 6. 산출물

| 파일 | 크기 | 변경 |
|------|------|------|
| `output/TAI-FORM-C002-blank.docx` | 11.6KB | atLeast + ROW_H 수정 |
| `output/TAI-FORM-C002-example.docx` | 12.4KB | atLeast + ROW_H 수정 |
| `scripts/gen_c002_docx.cjs` | — | HeightRule 키 + 상수 수정 |

---

## 7. 판정 요약

| 항목 | 판정 |
|------|------|
| `w:hRule="atLeast"` 기록 (13/13행) | PASS |
| 행 높이 계약 (twips 전수) | PASS |
| ROW_H_GOAL PDF↔DOCX 통일 (20mm) | PASS |
| ROW_H_INFO PDF↔DOCX 통일 (7mm) | PASS |
| ISSUE-D01/D02 해소 | PASS |
| GUI 실사용 검증 | UNVERIFIED |

**WO-056 종합: PARTIAL_PASS**
- 구조 수정 및 XML 계약 전항목 PASS
- GUI 실사용 항목 UNVERIFIED (CLI 환경 한계)
