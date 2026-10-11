---
title: WO-057B DOCX 제목·결재란 Google Docs 호환성 후보 QA 보고서
version: 1.0
date: 2026-10-09
status: PHASE3_BLOCKED — Phase 1+2 PASS / Phase 3 (실제 Google Docs 검증) 미실행
goal: G-muzta7bb-b4a5ab
base_commit: 6067d927c2
---

# WO-057B DOCX 제목·결재란 호환성 후보 QA 보고서

## 기준 파일 해시 (변경 없음 확인)

| 파일 | MD5 |
|------|-----|
| `TAI-FORM-C002-blank.docx` (baseline) | `b2deda161c7204919d932102f4018858` |
| `TAI-FORM-C002-blank.pdf` (baseline) | `dbe073b2a627c592c7083a38b4ad5d69` |

---

## Phase 1 — 근본 원인 확인

### 현상

GPT 분석: Google Docs 변환 시 제목(170mm, 1셀)과 결재란(170mm, 2셀)이 하나의 2행×2열 테이블로 병합됨.

### OOXML 원인

`word/document.xml` body 직속 자식 요소 순서 (baseline):

```
[0] w:tbl  (170mm — 제목)
[1] w:tbl  (170mm — 결재란 외부 래퍼)     ← 인접, 사이에 w:p 없음
[2] w:p    (spacer — before/after=80)
[3] w:tbl  (170mm — 기본정보)
...
```

**OOXML 표준**: 인접한 두 `w:tbl` 사이에 `w:p`가 없으면 일부 구현체가 하나의 테이블로 해석. Google Docs 변환기가 이 경우에 해당.

**추가 구조적 취약점 (baseline)**:
- 결재란이 170mm noBorder 외부 테이블 + 90mm 중첩 내부 테이블로 구성
- noBorder 셀이 있는 외부 테이블 + 중첩 테이블 구조는 비표준 구현체에서 추가 문제 유발 가능

---

## Phase 2 — 수정 후보 비교

### 후보 요약

| 속성 | Baseline | Candidate A | Candidate B |
|------|---------|-------------|-------------|
| 제목↔결재란 분리 단락 | 없음 | **있음** (before=0, after=0) | **있음** (before=0, after=0) |
| 결재란 구조 | 170mm noBorder 래퍼 + 90mm 중첩 | 170mm noBorder 래퍼 + 90mm 중첩 | **90mm 독립 테이블 (jc=right)** |
| 전체 테이블 수 | 6 | 6 | **5** |
| 중첩 테이블 | YES | YES | **NO** |
| noBorder 셀 | 2개 | 2개 | **0개** |
| 분리 단락 XML | — | `<w:spacing before=0 after=0/>` | `<w:spacing before=0 after=0/>` |
| 결재란 정렬 | 래퍼 내 우측 셀 위치 | 래퍼 내 우측 셀 위치 | `<w:jc w:val="right"/>` |

### Candidate A 분석

- **수정 범위**: `buildDoc()` children에 `spacer0()` 1개 삽입 (1행 변경)
- **효과**: 인접 테이블 병합 방지 → 제목/결재란이 별도 테이블로 유지
- **잔여 위험**: 170mm noBorder 래퍼 + 90mm 중첩 구조 유지 → 일부 구현체에서 빈 noBorder 셀 처리 불일치 가능

### Candidate B 분석

- **수정 범위**: `buildApproval()` 함수 교체 + `buildDoc()`에 `spacer0()` 삽입
- **효과**: 인접 테이블 병합 방지 + 중첩 테이블 제거 + noBorder 셀 제거
- **구조**: 90mm 독립 테이블 + `w:jc="right"` 표준 정렬
- **잔여 위험**: `w:jc="right"` 정렬이 Google Docs에서 정확히 90mm 오른쪽 정렬로 렌더링되는지 실측 필요

---

## Phase 3 — Google Docs 실제 임포트

**상태: 미실행 (BLOCKED)**

- CLI 환경에서 Google Docs API 접근 불가
- Google Drive MCP 도구 미인증 상태
- Phase 3는 실제 Google Docs 임포트 결과 기반 최종 후보 선택이 필요 → GPT 또는 Owner 직접 수행 필요

---

## OOXML 구조 검증 요약 (Phase 2 범위)

| 항목 | Candidate A | Candidate B | 판정 |
|------|------------|------------|------|
| 분리 단락 존재 | ✓ | ✓ | PASS |
| 분리 단락 간격 0 (시각적 영향 최소) | ✓ (before=0, after=0) | ✓ (before=0, after=0) | PASS |
| 기본 필드 유지 (제목/결재란/기본정보/전사목표/계획표) | ✓ | ✓ | PASS |
| 행 높이 계약 (atLeast) | ✓ (13행) | ✓ (13행) | PASS |
| A4 페이지 설정 | ✓ | ✓ | PASS |
| baseline DOCX/PDF 미변경 | ✓ | ✓ | PASS |
| 실제 Google Docs 렌더링 검증 | UNVERIFIED | UNVERIFIED | BLOCKED |

---

## 권고

**Candidate B 구조적 우위**: 중첩 테이블과 noBorder 셀을 제거해 비표준 구현체 대응에 더 유리. 단, Google Docs에서 `w:jc="right"` 90mm 테이블이 시각적으로 올바르게 렌더링되는지 실측 필요.

**최종 선택**: Phase 3 실제 Google Docs 임포트 결과로 GPT가 판정.

---

## 산출물

| 파일 | 용도 |
|------|------|
| `output/TAI-FORM-C002-blank-CandidateA.docx` | 분리 단락만 추가 (중첩 구조 유지) |
| `output/TAI-FORM-C002-blank-CandidateB.docx` | 분리 단락 + 90mm 독립 right-align 테이블 |
| `scripts/gen_c002_docx_candidate.cjs` | 후보 생성기 (QA 전용, 프로덕션 아님) |
| `qa/WO-057B-CANDIDATE-QA-REPORT.md` | 본 보고서 |
