---
wo: WO-054
patch: PATCH-1
title: REF-C002 시제품 레이아웃 보완 QA 보고서
base_commit: ecb9ab1093f19eb2f0cdeb0c425d49004c05e5b1
version: 0.1-DRAFT
date: 2026-10-09
status: EVIDENCE_READY
verifier: Claude Code (증거수집 전담)
independent_verification: GPT (독립검증 미완료)
---

# WO-054 PATCH-1 QA 보고서

## 변경 요약 (GPT CONDITIONAL FAIL 대응)

| 항목 | 변경 전 | 변경 후 |
|------|---------|---------|
| 제목 위치 | 80mm (좌), 결재란 90mm (우) 같은 행 | 170mm 전체 너비 단독 행 |
| 결재란 위치 | 제목 오른쪽 | 제목 아래 오른쪽 (80mm 공백 + 90mm) |
| 기본정보 | 1행 (사업장명55+작성일70+적용연도+문서번호45mm) | 2행 (사업장명85+작성일85 / 적용연도85+문서번호85mm) |
| F08 담당부서 열 너비 | 20mm | 26mm (+6mm) |
| 빈 행 높이 (ROW_H_PLAN) | 12mm | 14mm |
| F05 열 너비 | 58mm | 56mm (-2mm) |
| F06 열 너비 | 28mm | 26mm (-2mm) |
| F07 열 너비 | 24mm | 22mm (-2mm) |
| 열 너비 합계 | 170mm | 170mm (유지) |

## 변경 파일

| 파일 | 변경 내용 |
|------|----------|
| `scripts/gen_c002_pdf.py` | build_title_approval → build_title + build_approval 분리; build_basic_info 2행; COL_WIDTHS_MM, ROW_H_PLAN |
| `scripts/gen_c002_docx.cjs` | buildTitleApproval → buildTitle + buildApproval 분리; buildBasicInfo 2행; COL_W, ROW_H_PLAN |
| `scripts/c002_fields.json` | column width_mm 업데이트 (F05~F08), min_row_height_mm 12→14 |

## QA 확인 결과

### P1-QA-01: 제목 전체 너비 배치
**상태**: PASS  
**증거**: `pages/p1_blank-1.png`  
**관찰**: "안전보건 목표 및 추진계획서" A4 170mm 전체 너비 박스, 중앙 배치 ✓

### P1-QA-02: 결재란 아래 우측 배치
**상태**: PASS  
**증거**: `pages/p1_blank-1.png`  
**관찰**: (작성/검토/승인) 결재란이 제목 아래 행에 우측 90mm 공간에 독립 배치 ✓. 좌 80mm 공백 ✓

### P1-QA-03: 기본정보 2행 구성
**상태**: PASS  
**증거**: `pages/p1_blank-1.png`  
**관찰**:
- 1행: "사업장명: ___" (85mm) | "작성일: ______년 ______월 ______일" (85mm)
- 2행: "적용 연도: ______년" (85mm) | "문서번호: ___" (85mm)
- 작성일 "일"이 다음 줄로 넘어가는 문제 없음 ✓
- 각 필드 입력 공간 충분 ✓

### P1-QA-04: 담당부서 한글 줄바꿈 해소
**상태**: PASS  
**증거**: `pages/p1_example-1.png`, `pages/p1_multi-2.png`  
**관찰**:
- "안전관리팀" (5자) — 단일 행 표시 ✓ (이전: 줄바꿈)
- "환경안전팀", "공사관리팀", "경영지원팀" (5자 부서명) — 모두 줄바꿈 없음 ✓

### P1-QA-05: 빈 행 높이 (손글씨 공간)
**상태**: PASS  
**증거**: `pages/p1_blank-1.png`  
**관찰**: 빈 계획표 행 높이 14mm → 이전 12mm 대비 넓어진 쓰기 공간 시각 확인 ✓

### P1-QA-06: 표 헤더 반복 유지
**상태**: PASS  
**증거**: `pages/p1_example-2.png`, `pages/p1_multi-2.png`  
**관찰**: 2페이지 상단에 (목표·세부 추진계획 / 추진일정 / 성과지표 / 담당부서 / 예산(만원) / 달성률) 헤더 반복 ✓

### P1-QA-07: 잘린 글자 없음
**상태**: PASS  
**증거**: `pages/p1_example-1.png`, `pages/p1_multi-2.png`  
**관찰**: 모든 셀 내 한국어 텍스트 클리핑 없음 ✓. F05 "추락·낙하 예방 설비 점검" 56mm 셀 정상 wrap ✓

### P1-QA-08: 페이지 번호
**상태**: PASS  
**증거**: 전 페이지 하단  
**관찰**: 빈 서식 "1 / 1", 예시 "1 / 2", "2 / 2", 다중페이지 "1 / 2", "2 / 2" 모두 정상 ✓

### P1-QA-09: PDF/DOCX 필드 패리티 유지
**상태**: PASS  
**증거**: gen_c002_pdf.py + gen_c002_docx.cjs 모두 동일 c002_fields.json 참조; COL_WIDTHS_MM/COL_W 동일값  
**관찰**: 6열 너비 [56,26,22,26,22,18]mm 양 포맷 일치 ✓

### P1-QA-10: 메타데이터 유지
**상태**: PASS (이전 검증 기준 재확인 — 코드 변경 없음)  
**관찰**: 메타데이터 생성 로직 변경 없음. 이전 QA-06/07 PASS 유지

## 페이지 분량 변화

| 파일 | PATCH-1 전 | PATCH-1 후 | 원인 |
|------|-----------|-----------|------|
| blank.pdf (5행) | 1페이지 | 1페이지 | 변화 없음 |
| example.pdf (10행) | 1페이지 | 2페이지 | 레이아웃 비표 영역 +22mm (제목행 분리 +14mm + 기본정보 2행 +8mm) |
| multipage.pdf (18행) | 2페이지 | 2페이지 | 변화 없음 |

**판단**: 빈 서식(주 배포본)은 1페이지 유지. example 2페이지는 레이아웃 개선의 직접 결과이며 실사용 범위(행 추가 시 페이지 넘김)에 해당.

## 미결 항목 (이전 동일)

| 항목 | 상태 |
|------|------|
| DOCX 편집가능성 | UNVERIFIED (Word/한글 수동 테스트 필요) |
| DOCX F09 2줄 헤더 | UNVERIFIED |
| DOCX tableHeader 반복 | UNVERIFIED |

## 독립검증 요청

- 브랜치: `docs/tai-reference-forms-charter-obj-20261008`
- 커밋: PATCH-1 커밋 SHA (이 보고서와 함께 커밋 예정)
- 검증 항목: P1-QA-01~10, 페이지 분량 판단 적절성, DOCX buildTitle/buildApproval 구조
