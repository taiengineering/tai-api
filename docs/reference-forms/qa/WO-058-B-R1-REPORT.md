# WO-058 Phase B-R1 — GPT 지적사항 수정 보고서

Date: 2026-10-09
Goal: G-muzv7o29-b4a5ab
Branch: docs/tai-reference-forms-charter-obj-20261008
Status: PHASE_B_R1_COMPLETE — GPT 독립검증 대기
Supersedes: WO-058-PHASE-B-REPORT.md

---

## 0. B-R1 수정 배경

Phase B GPT 독립검증에서 CONDITIONAL FAIL 판정을 받았다. 지적 항목:

| 지적 항목 | Phase B 결함 | B-R1 수정 내용 |
|---|---|---|
| V02 FAIL | 결재 3역할(신청/검토/허가) — 원본 미관찰 "검토" 포함 | 2역할(신청/허가)로 수정 |
| D05 위반 | N01/N02 신규 제안 필드를 기본 서식에 포함 | 기본 서식에서 제외 |
| source 과장 | `SOURCE_VERIFIED` 사용 — 실제 증거 수준 초과 | 전체 `NATIVE_HWP_BODYTEXT_LABEL`로 수정 |
| GAP 불완전 | 공통 assembler 설계 누락 | COMMON-ENGINE-SCHEMA-058.md 신규 작성 |
| Goal ID 불일치 | 작업지시서 헤더에 구 Goal ID `G-muzta7bb-b4a5ab` 기재 | 아래 섹션 1에서 해명 |

---

## 1. Goal ID 해명

| 항목 | 값 |
|---|---|
| **현재 활성 Goal** | `G-muzv7o29-b4a5ab` — WO-058 전체(Phase A/B/C) 담당 |
| **구 Goal** | `G-muzta7bb-b4a5ab` — WO-056 목표, CLOSED PASSED |
| **B-R1 작업지시서 헤더 오기** | WO-058 B-R1 작업지시서에 구 Goal ID가 기재됨 — GPT 작성 오류로 확인 |
| **영향** | 실제 수행 작업은 `G-muzv7o29-b4a5ab` 하에서 진행됨. 오기이므로 수정 대상 없음 |

이 보고서 및 모든 B-R1 산출물의 Goal = `G-muzv7o29-b4a5ab`.

---

## 2. 수정 산출물 목록

| 파일 | 유형 | 변경 내용 |
|---|---|---|
| `scripts/c012_fields.json` | 필드 명세 JSON | **수정** — 2역할 결재, N01/N02 제거, source 수정, common-v1 스키마 |
| `design/REF-C012-FIELD-SPEC-058.md` | 설계 명세서 | **v0.2 수정** — 동일 수정 반영 + 레이아웃 다이어그램 수정 |
| `design/COMMON-ENGINE-SCHEMA-058.md` | 공통 엔진 스키마 설계 | **신규** — 5 블록 타입 정의, C002/C012 비교, GAP 재정의 |
| `qa/WO-058-B-R1-REPORT.md` | 이 보고서 | **신규** |

**변경 없음**: gen_c002_pdf.py, gen_c002_docx.cjs, c002_fields.json, WO-058-PHASE-B-REPORT.md (SUPERSEDED 상태로 보존), WO-058-PHASE-A-REF-C012-REPORT.md.

---

## 3. c012_fields.json 수정 상세

### 3.1 결재 역할 수정 (V02 FAIL 해소)

```
Before (Phase B):  "fields": [AP01 신청, AP02 검토, AP03 허가]  // 3역할
After  (B-R1):     "fields": [AP01 신청, AP02 허가]             // 2역할
```

검토(AP02_OLD) 제거 근거: 원본 NATIVE_HWP_BODYTEXT_LABEL에서 "검토" 레이블 미관찰.
허가(AP03→AP02) ID 재부여: 3역할 기준 AP03 → 2역할 기준 AP02.

### 3.2 N01/N02 기본 서식 제외 (D05 위반 해소)

`basic_info` 섹션 전체 제거. 기본 서식에는 원본 관찰 필드(F01~F10, AP01~AP02)만 포함.
N01/N02는 구현 단계 확장판에서 별도 검토.

### 3.3 source 상태 수정 (과장 해소)

```
Before: "source": "SOURCE_VERIFIED"     // 표 구조까지 확인된 수준 — 부정확
After:  "source": "NATIVE_HWP_BODYTEXT_LABEL"  // 실제 증거 수준
```

모든 필드 (F01~F10, AP01~AP02)에 동일 적용.

### 3.4 스키마 구조 변경 (common-v1 적용)

```
Before (Phase B): 플랫 구조 {document, approval, basic_info, sections...}
After  (B-R1):    sections 배열 통합 [{type:approval}, {type:labeled_grid}, {type:freeform_area}, ...]
```

---

## 4. COMMON-ENGINE-SCHEMA-058.md 신규 작성 내용 요약

### 4.1 정의된 블록 타입 (5종)

| 블록 타입 | 설명 | 현재 구현 상태 |
|---|---|---|
| `title` | 문서 제목 행 | C002에서 구현됨 — 재사용 가능 |
| `approval` | 결재란 (N열 가변) | C002에서 구현됨 — JSON 레이블/칸수로 구동 |
| `labeled_grid` | 2열 그리드 기본정보 | **없음 — GAP-01 신규 빌더 필요** |
| `freeform_area` | 전체너비 자유 기재란 | C002 `corporate_goal` 파라미터화 필요 — **GAP-02** |
| `repeat_table` | 다중 행 반복 테이블 | C002에서 구현됨 — C002 전용 하드코딩 잔존 |

### 4.2 GAP-03 NONE 재확인

Phase B에서 GAP-03("approval 레이블 파라미터화")을 REQUIRED로 분류했으나, 실제 코드 확인 결과 `buildApproval(fields)` 이미 `f.label` JSON 값을 소비 → 코드 수정 불필요. **GAP-03 = NONE 유지.**

### 4.3 C002 + C012 동일 스키마 표현 가능 확인

| 블록 | C002 | C012 |
|---|---|---|
| `title` | O | O |
| `approval` | O (3역할) | O (2역할) |
| `labeled_grid` | X (없음) | O (F01~F08) |
| `freeform_area` | O (전사목표) | O (F09, F10) |
| `repeat_table` | O (계획표) | X (없음) |

두 서식 모두 `sections` 배열로 표현 가능 — common-v1 스키마 타당성 확인.

---

## 5. Phase B-R1 GAP 목록 (수정판)

| GAP ID | 분류 | 설명 | C012 필수 여부 |
|---|---|---|---|
| GAP-01 | 신규 빌더 | `labeled_grid` 빌더 (PDF + DOCX) | **REQUIRED** |
| GAP-02 | 파라미터화 | `freeform_area` 빌더 (PDF + DOCX) | **REQUIRED** |
| GAP-03 | — | NONE — 코드 수정 불필요 | — |
| GAP-04 | 선택 | `basic_info` 파라미터화 — C012 기본 서식에 basic_info 없으므로 불필요 | NOT REQUIRED |
| GAP-05 | 아키텍처 | assembler JSON-driven화 | NICE_TO_HAVE |
| GAP-06 | 인프라 | package.json 다중 서식 지원 | **REQUIRED** |
| GAP-07 | 인프라 | Python entry point 다중 서식 지원 | **REQUIRED** |

Phase C 최소 착수 조건: GAP-01, GAP-02, GAP-06, GAP-07 해소.

---

## 6. 3개 블로커 해소 방침 (V07 재확인)

| 블로커 | 현황 | Phase C (POC) 착수 가능 여부 |
|---|---|---|
| SOURCE_FIELDS_UNVERIFIED | 원본 HWP 표 구조 미확인 | **POC 착수 가능** — 표 구조 추정 기반 POC, 원본 확인 후 수정 허용 |
| LEGAL_REVIEW_PENDING | FIELD_REQUIRED 미확정 | **POC 착수 가능** — requiredness=UNVERIFIED 유지, 배포 금지 |
| RIGHTS_UNVERIFIED | 외부 배포 금지 | **POC 착수 가능** — 내부 POC 한정, 외부 배포 금지 조건 유지 |

GPT Phase B 판정과 동일: 3개 블로커 해소 없이 POC(내부 생성 테스트) 착수 가능. 외부 배포·법적 필수 확정은 블로커 해소 후.

---

## 7. Phase B-R1 검증 요청 항목 (GPT 독립검증용)

| # | 검증 항목 |
|---|---|
| R01 | c012_fields.json 결재 2역할(신청/허가) 수정이 D01 결정에 부합하는가? |
| R02 | N01/N02 기본 서식 제외가 D05 결정에 부합하는가? |
| R03 | 전체 필드 source = `NATIVE_HWP_BODYTEXT_LABEL` 수정이 실제 증거 수준에 적합한가? |
| R04 | common-v1 스키마 5개 블록 타입 정의가 C002와 C012를 모두 커버하는가? |
| R05 | GAP-03 = NONE 판단(approval 이미 JSON-driven)이 정확한가? |
| R06 | GAP-04가 C012 Phase C 착수에 NOT REQUIRED라는 판단이 정확한가? (C012 기본 서식에 basic_info 없음) |
| R07 | Goal ID 불일치 해명이 타당한가? (구 G-muzta7bb-b4a5ab = WO-056 CLOSED PASSED, 현재 활성 = G-muzv7o29-b4a5ab) |
| R08 | Phase C 최소 착수 조건(GAP-01/02/06/07 해소)이 완전한가? |
