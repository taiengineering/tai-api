---
doc_id: TAI-DESIGN-C012-V0.2
title: REF-C012 안전작업 허가서 — 필드·레이아웃 설계서
version: 0.2-DRAFT
status: PHASE_B_R1_DRAFT — GPT 독립검증 대기
date: 2026-10-09
branch: docs/tai-reference-forms-charter-obj-20261008
scope: REF-C012 단독 서식 설계. 공통 디자인 규격은 COMMON-DESIGN-SPEC-053.md 참조.
source_evidence: WO-058 Phase A — 11개 관찰 필드 NATIVE_HWP_BODYTEXT_LABEL (FIELDS_UNVERIFIED)
form_type: FORM
supersedes: TAI-DESIGN-C012-V0.1
change_reason: B-R1 GPT 지적 반영 — 결재 2역할(검토 제거), N01/N02 기본 서식 제외, source 상태 수정
---

# REF-C012 안전작업 허가서 — 필드·레이아웃 설계서 v0.2

## 0. 문서 목적

REF-C012 원본에서 확인된 필드와 TAI가 신규 제안하는 필드를 구분한다.
Phase A 조사 결과를 입력으로, Phase C 생성기 구현 전 GPT 검토를 위한 설계 명세서를 작성한다.

---

## 1. 원본 증거 요약

| 항목 | 내용 |
|---|---|
| 원본 코드 | REF-C012 |
| 원본 제목 | 안전작업 허가서 |
| 출처 | KOSHA (산업안전보건공단) |
| 증거 신뢰도 | PAGE_ENUMERATED (출처 보고서 03) |
| 원본 증거 방식 | NATIVE_HWP_BODYTEXT_LABEL |
| 표 구조 확인 | NOT_VERIFIED (NATIVE_PARAGRAPH_ONLY 한계) |
| 법적 필수성 | LEGAL_REVIEW_PENDING — 확정 금지 |
| WO 번호 | WO-058 Phase A |
| 서식 유형 | FORM |
| observed_fields | 11개 |
| validation_blockers | SOURCE_FIELDS_UNVERIFIED / LEGAL_REVIEW_PENDING / RIGHTS_UNVERIFIED |

---

## 2. 원본 필드 목록 (11개, NATIVE_HWP_BODYTEXT_LABEL)

모든 필드의 source = `NATIVE_HWP_BODYTEXT_LABEL` (HWP 본문 텍스트에서 관찰된 레이블).
표 구조·셀 병합 방식·법적 필수 여부는 SOURCE_FIELDS_UNVERIFIED 상태이므로 미확정.

| # | 필드 ID | 원본 텍스트 | 설계 배치 | source | 법적 필수 |
|---|---|---|---|---|---|
| OF-01 | F01 | 작업종류        | 기본정보 그리드 행1 좌 | NATIVE_HWP_BODYTEXT_LABEL | 미확정 |
| OF-02 | F02 | 신청부서(업체명) | 기본정보 그리드 행1 우 | NATIVE_HWP_BODYTEXT_LABEL | 미확정 |
| OF-03 | F03 | 직책            | 기본정보 그리드 행2 좌 | NATIVE_HWP_BODYTEXT_LABEL | 미확정 |
| OF-04 | F04 | 성명(서명)       | 기본정보 그리드 행2 우 | NATIVE_HWP_BODYTEXT_LABEL | 미확정 |
| OF-05 | F05 | 허가요청기간     | 기본정보 그리드 행3 좌 | NATIVE_HWP_BODYTEXT_LABEL | 미확정 |
| OF-06 | F06 | 작업장소         | 기본정보 그리드 행3 우 | NATIVE_HWP_BODYTEXT_LABEL | 미확정 |
| OF-07 | F07 | 장비투입         | 기본정보 그리드 행4 좌 | NATIVE_HWP_BODYTEXT_LABEL | 미확정 |
| OF-08 | F08 | 작업인원         | 기본정보 그리드 행4 우 | NATIVE_HWP_BODYTEXT_LABEL | 미확정 |
| OF-09 | F09 | 작업내용         | 작업내용 자유 기재란 (전체 너비) | NATIVE_HWP_BODYTEXT_LABEL | 미확정 |
| OF-10 | F10 | 안전조치 사항    | 안전조치 자유 기재란 (전체 너비) | NATIVE_HWP_BODYTEXT_LABEL | 미확정 |
| OF-11 | AP02 | 허가자 성명     | 결재란 "허가" 칸 매핑 | NATIVE_HWP_BODYTEXT_LABEL | 미확정 |

**주의**: OF-04(성명/서명)는 신청인 데이터 기재란(작업기본정보 그리드 내). AP01(신청)은 결재 서명란. 동일 인물이 서로 다른 목적으로 사용 — 중복 아님.

---

## 3. TAI 신규 제안 필드 (TAI_NEW_PROPOSAL) — 기본 서식 제외 결정

**D05 결정**: 기본 서식에는 원본 관찰 필드만 포함. TAI 신규 제안 필드는 구현 단계에서 별도 확장판으로 제공.

| # | 제안 필드명 | 제안 이유 | 기본 서식 포함 여부 | 비고 |
|---|---|---|---|---|
| N01 | 허가번호 | 내부 문서 관리 | **제외** | 구현 단계 확장판에서 검토 |
| N02 | 작성일   | 문서 이력 관리 | **제외** | 구현 단계 확장판에서 검토 |

---

## 4. 결재란 설계 (D01 결정 반영)

**D01 결정**: 결재 역할은 신청자·허가자 2개. 검토 역할은 기본 서식에서 제거.

| 결재 ID | 레이블 | 원본 근거 | source |
|---|---|---|---|
| AP01 | 신청 | OF-04(성명/서명) — 신청인 서명 역할 | NATIVE_HWP_BODYTEXT_LABEL |
| AP02 | 허가 | OF-11(허가자 성명) — 허가자 서명 역할 | NATIVE_HWP_BODYTEXT_LABEL |

검토(AP02_OLD) 역할 제거 이유: 원본 NATIVE_HWP_BODYTEXT_LABEL에서 "검토" 레이블 미관찰.

---

## 5. 레이아웃 설계 (v0.2)

### 5.1 페이지 구성 (A4 세로, 170mm 본문 너비)

```
┌─────────────────────────────────────────────────────────────────┐
│      안전작업 허가서          │    신청    │    허가    (90mm)   │
├──────────────────────────────┴────────────┴─────────────────────┤
│  작업기본정보 섹션                                                │
│  작업종류: _______________  │  신청부서(업체명): ______________  │
│  직책: __________________ │  성명(서명): ____________________  │
│  허가요청기간: ___________  │  작업장소: _____________________  │
│  장비투입: _______________  │  작업인원: _____________________  │
├─────────────────────────────────────────────────────────────────┤
│  작업내용 (최소 20mm)                                            │
│  _______________________________________________________________  │
├─────────────────────────────────────────────────────────────────┤
│  안전조치 사항 (최소 30mm)                                        │
│  _______________________________________________________________  │
├─────────────────────────────────────────────────────────────────┤
│                     페이지 번호 N / 전체 (중앙)                   │
└─────────────────────────────────────────────────────────────────┘
```

v0.1 대비 변경:
- 결재란: 신청/검토/허가 3칸 → 신청/허가 2칸
- 기본 정보 행(허가번호/작성일) 제거

### 5.2 결재란 배치 (COMMON-DESIGN-SPEC § 4.3 준수)

- 위치: 문서 제목 우측 90mm (REF-C002 동일)
- 셀 구성: 신청(AP01) / 허가(AP02) — 2칸
- 구현: `buildApproval()` Candidate B 직접 재사용 (레이블만 교체, 칸 수만 다름)
- AP01 칸 너비: 45mm / AP02 칸 너비: 45mm (90mm ÷ 2)

### 5.3 작업기본정보 섹션 (F01–F08)

**레이아웃 유형: `labeled_grid`** — REF-C002에 없는 신규 유형.

- 섹션 레이블: "작업 기본 정보"
- 2열 그리드: 좌열 85mm / 우열 85mm
- 4행: [F01/F02], [F03/F04], [F05/F06], [F07/F08]
- 행 높이: 7mm (ROW_H_INFO)
- 셀: 라벨(Bold 10pt) + 기재란 (연회색 배경)

구현: 공통 엔진에 없음 → **GAP-01 신규 빌더 필요**.

### 5.4 작업내용 섹션 (F09)

**레이아웃 유형: `freeform_area`**

- 단일 전체 너비(170mm) 셀
- 최소 높이: 20mm
- 라벨 헤더 행 + 기재 공간 행 구조

구현: C002의 `buildCorporateGoal()` / `build_corporate_goal()` 파라미터화 재사용.

### 5.5 안전조치 사항 섹션 (F10)

`freeform_area` 동일, 최소 높이 30mm.

---

## 6. 스크립트 인터페이스 계획 (Phase C에서 구현)

| 파일 | 역할 | Phase |
|---|---|---|
| `scripts/c012_fields.json` | REF-C012 필드 명세 (SoT) — common-v1 스키마 | **B-R1 — 완료** |
| `scripts/gen_c012_pdf.py` | ReportLab PDF 생성기 | C |
| `scripts/gen_c012_docx.cjs` | npm docx DOCX 생성기 | C |

Phase C 생성기는 공통 엔진 GAP 해소 후 작성.

---

## 7. 잔여 OPEN 항목

| # | 항목 | 상태 |
|---|---|---|
| O01 | F03/F04 (직책/성명) — 신청자 1인 정보인가? 복수 가능? | UNRESOLVED |
| O02 | F07 장비투입 — 장비명 나열 vs 대수/종류 구분 | UNVERIFIED |
| O03 | 안전조치 사항 — 자유서술 외 체크리스트 행 추가 여부 | GPT 결정 대기 |
| O04 | 원본 표 구조 — 섹션 경계·셀 병합 방식 미확인 | SOURCE_FIELDS_UNVERIFIED |
| O05 | 법령 필수 필드 — PSM 외 일반 위험작업 LEG 검토 | LEGAL_REVIEW_PENDING |

---

## 8. 제약 사항 재확인

- 원본 KOSHA/MOEL 레이아웃·문구 복제 금지
- 법적 필수 여부(`FIELD_REQUIRED`) LEG 검토 전 확정 금지
- SOURCE_FIELDS_UNVERIFIED 상태: 원본 표 구조 임의 추정 금지
- RIGHTS_UNVERIFIED 상태: 외부 배포 금지
- Phase C 구현은 이 명세 GPT 독립검증 PASS 후 착수
