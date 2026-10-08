---
title: WO-055 REF-C002 DOCX 실사용 QA 보고서
version: 1.0
date: 2026-10-09
status: PARTIAL_PASS — GUI 항목 UNVERIFIED
base_commit: 12ee9e39ea824dd3ce60e5ce22ee04005608e5b9
---

# WO-055 REF-C002 DOCX 실사용 QA 보고서

## 검증 환경

| 항목 | 값 |
|------|-----|
| 기준 커밋 | `12ee9e39ea824dd3ce60e5ce22ee04005608e5b9` |
| 검증 도구 | Python 3 (zipfile + xml.etree.ElementTree — DOCX XML 직접 파싱) |
| 대상 파일 | `TAI-FORM-C002-blank.docx`, `TAI-FORM-C002-example.docx` |
| DOCX 생성기 | `gen_c002_docx.cjs` (node.js, docx 9.9.0) |
| GUI 환경 | 없음 (CLI 환경) — GUI 필요 항목 UNVERIFIED |

---

## 1. 파일 구조 및 XML 유효성

| 항목 | 확인 결과 | 판정 |
|------|----------|------|
| OOXML ZIP 구조 (word/document.xml, styles, footer 등) | 정상 | PASS |
| blank.docx 열기 오류 없음 | ZIP 파싱 성공 | PASS |
| example.docx 열기 오류 없음 | ZIP 파싱 성공 | PASS |
| Word XML 네임스페이스 정합 | 표준 OOXML | PASS |

---

## 2. 메타데이터

| 필드 | 값 | 판정 |
|------|-----|------|
| title | `안전보건 목표 및 추진계획서` | PASS |
| creator | `TAI` | PASS |
| description | `산업안전보건 실무서식` | PASS |
| blank / example 동일 | 동일 | PASS |

---

## 3. 페이지 설정

| 항목 | 설정값 | 기준 | 판정 |
|------|--------|------|------|
| 페이지 크기 | 210.0mm × 297.0mm | A4 | PASS |
| 상단 여백 | 20.0mm | 20mm | PASS |
| 하단 여백 | 20.0mm | 20mm | PASS |
| 좌측 여백 | 20.0mm | 20mm | PASS |
| 우측 여백 | 20.0mm | 20mm | PASS |

---

## 4. 섹션별 테이블 구조

### Table[0] — 제목

| 항목 | 값 | 판정 |
|------|-----|------|
| 구성 | 1행 × 1열 | PASS |
| 전체 폭 | 170.0mm | PASS |
| 행 높이 | 14.0mm (hRule=auto) | PASS |
| 텍스트 | `안전보건 목표 및 추진계획서` | PASS |

### Table[1] — 결재란

| 항목 | 값 | 판정 |
|------|-----|------|
| 외부 구조 | 1행 × 2열 (빈 셀 80mm + 중첩 테이블 90mm) | PASS |
| 내부 중첩 테이블 행 수 | 2행 (레이블행 7mm + 서명행 15mm) | PASS |
| 레이블 셀 폭 | 30.0mm × 3 (작성/검토/승인) | PASS |
| 서명행 높이 | 15.0mm | PASS |

### Table[2] — 기본정보

| 항목 | 값 | 판정 |
|------|-----|------|
| 구성 | 2행 × 2열 | PASS |
| 전체 폭 | 170.0mm | PASS |
| 행 높이 | 8.0mm (hRule=auto) × 2 | PASS |
| 필드 확인 | 사업장명/작성일/적용연도/문서번호 | PASS |

### Table[3] — 전사목표

| 항목 | 값 | 판정 |
|------|-----|------|
| 구성 | 2행 × 1열 | PASS |
| 레이블행 높이 | 7.0mm (hRule=auto) | PASS |
| 내용행 높이 | **22.0mm** (hRule=auto) | PASS* |
| 레이블 텍스트 | `전사 목표` | PASS |

※ DOCX ROW_H_GOAL=22mm, PDF PATCH-3 ROW_H_GOAL=20mm → 2mm 차이 (후술)

### Table[4] — 추진계획표

| 항목 | blank | example | 판정 |
|------|-------|---------|------|
| 행 수 (헤더 포함) | 6행 (1+5) | 11행 (1+10) | PASS |
| 열 수 | 6 | 6 | PASS |
| 전체 폭 | 170.0mm | 170.0mm | PASS |
| 열 너비 (F05~F10) | 56/26/22/26/22/18mm | 동일 | PASS |
| 헤더행 반복 (`w:tblHeader`) | ✓ | ✓ | PASS |
| 헤더행 높이 | 8.0mm (hRule=auto) | 동일 | PASS |
| 데이터행 높이 | 14.0mm (hRule=auto) × 5 | 14.0mm × 10 | PASS |
| hRule=auto (AT_LEAST) | ✓ | ✓ | PASS |

---

## 5. 폰트 및 텍스트 스타일

| 항목 | 값 | 판정 |
|------|-----|------|
| 헤더행 폰트 | NanumGothic | PASS |
| 헤더행 bold | yes | PASS |
| 헤더행 글자 크기 | sz=20 (10pt) | PASS |
| 데이터행 폰트 | NanumGothic | PASS |
| 데이터행 글자 크기 | sz=20 (10pt) | PASS |
| 폰트 임베딩 | 없음 (시스템 폰트 참조) | NOTED* |

※ NanumGothic이 없는 시스템에서 대체 폰트 사용 → 표시 차이 가능 (GUI 미확인)

---

## 6. 테두리 및 셀 스타일

| 항목 | 값 | 판정 |
|------|-----|------|
| 헤더 셀 테두리 | SINGLE, size=4, color=000000 | PASS |
| 헤더 배경 | E8E8E8 | PASS |
| 데이터행 배경 | ffffff (홀수) / F5F5F5 (짝수 교대) | PASS |
| 셀 여백 | top/bottom/left/right = 3mm | PASS |

---

## 7. Footer (페이지 번호)

| 항목 | 값 | 판정 |
|------|-----|------|
| 필드 타입 | PAGE / NUMPAGES (OOXML 표준) | PASS |
| 형식 | `{PAGE} / {NUMPAGES}` | PASS |
| 정렬 | center | PASS |
| 폰트 | NanumGothic, sz=16 (8pt) | PASS |

---

## 8. hRule=auto 셀 확장 특성

`hRule=auto`는 Word OOXML에서 "AT_LEAST" 동작:
- 지정 높이를 최솟값으로 하고, 내용이 많으면 자동 확장
- 긴 한글 텍스트 입력 시 셀이 자동으로 높아지는 동작 **구조적으로 보장**
- 실제 Word/Hangul 렌더링에서의 동작은 GUI 미확인 → UNVERIFIED

---

## 9. PDF ↔ DOCX 구조적 차이

| 항목 | PDF (PATCH-3) | DOCX | 비고 |
|------|--------------|------|------|
| ROW_H_GOAL (전사목표) | 20mm | **22mm** | DOCX가 2mm 더 큼 |
| ROW_H_INFO (기본정보) | 7mm | **8mm** | DOCX가 1mm 더 큼 |
| 결재란 레이아웃 | 단일 테이블 내 우측 배치 | 중첩 테이블 구조 | 동등 기능 |
| 페이지 분할 | ReportLab `_orphan_safe_plan_tables()` 알고리즘 | Word/Hangul 자동 처리 | DOCX는 orphan 알고리즘 없음 |
| 표 머리글 반복 | ReportLab `repeatRows=1` | OOXML `w:tblHeader` | 동등 기능, 표준 방식 |
| 페이지 번호 | ReportLab NumberedCanvas | OOXML PAGE/NUMPAGES 필드 | 동등 기능, 표준 방식 |
| 폰트 처리 | NanumGothic.ttc 임베딩 | 시스템 폰트 참조 | DOCX 대체 폰트 위험 |
| 고립행 방지 | ✓ (알고리즘 구현) | N/A (Word 자동 처리) | DOCX는 Word 렌더러에 위임 |

---

## 10. GUI 필요 항목 (UNVERIFIED)

| 항목 | 이유 |
|------|------|
| Word/Hangul에서 파일 열기 | GUI 환경 없음 |
| 사업장명·작성일·전사목표 직접 편집 | GUI 필요 |
| 계획표 행 추가/삭제 | GUI 필요 |
| 긴 한글 입력 시 셀 자동 확장 실측 | GUI 필요 |
| 다중 페이지 표 머리글 반복 렌더링 | GUI 필요 |
| PDF 출력 시 기준 PDF와 비교 | GUI + 인쇄 필요 |
| NanumGothic 없는 시스템 폰트 대체 표시 | 별도 시스템 필요 |
| 저장 후 재열기 정합성 | GUI 필요 |

---

## 11. 발견된 잠재적 문제점

### ISSUE-D01: ROW_H_GOAL DOCX/PDF 불일치 (22mm vs 20mm)

- **현상**: DOCX `ROW_H_GOAL = mm(22)`, PDF `ROW_H_GOAL = 20mm`
- **원인**: PATCH-2/3에서 PDF만 수정, DOCX 미수정
- **영향**: 전사목표 입력 영역이 DOCX에서 2mm 더 넓음 — 사용성에 유리하나 불일치
- **심각도**: MINOR (기능 차이 없음, 미관 차이)
- **권고**: 향후 통일 시 PDF를 22mm로 올리거나 DOCX를 20mm로 내릴 것 — 이번 WO-055 범위 외

### ISSUE-D02: ROW_H_INFO DOCX/PDF 불일치 (8mm vs 7mm)

- **현상**: DOCX `ROW_H_INFO = mm(8)`, PDF `ROW_H_INFO = 7mm`
- **원인**: PATCH-2에서 PDF만 기본정보 행 7mm로 압축
- **영향**: 기본정보 2행의 높이가 DOCX와 PDF 간 다름 — 2mm 합산 차이
- **심각도**: MINOR
- **권고**: WO-055 범위 외 — 별도 검토 가능

### ISSUE-D03: DOCX 고립행 알고리즘 없음

- **현상**: DOCX에는 `_orphan_safe_plan_tables()` 없음, Word/Hangul 페이지 분할 전적으로 의존
- **영향**: 데이터 행이 많을 때 Word가 마지막 1행을 고립시킬 수 있음
- **심각도**: MINOR (Word 기본 동작, 사용자 수동 조정 가능)
- **권고**: DOCX 용도(편집·배포)에서는 수용 가능 — GUI 검증 시 확인 권장

---

## 12. 판정 요약

| 항목 | 판정 |
|------|------|
| DOCX 파일 구조 유효성 | PASS |
| 메타데이터 | PASS |
| 페이지 설정 (A4, 여백) | PASS |
| 제목/결재란/기본정보/전사목표 구조 | PASS |
| 추진계획표 열 너비·행 높이·헤더 반복 XML | PASS |
| 폰트 (NanumGothic, sz=20, bold) | PASS |
| Footer PAGE/NUMPAGES 필드 | PASS |
| hRule=auto 셀 자동 확장 구조 | PASS |
| GUI 편집·렌더링·인쇄 | UNVERIFIED |
| ROW_H_GOAL/INFO DOCX↔PDF 일치 | MINOR 불일치 (NOTED) |

**WO-055 종합: PARTIAL_PASS**
- 구조 검증 전 항목 PASS
- GUI 실사용 항목 전체 UNVERIFIED (CLI 환경 한계)
- ISSUE-D01/D02/D03 발견, 모두 MINOR — 이번 범위 내 수정 대상 아님
