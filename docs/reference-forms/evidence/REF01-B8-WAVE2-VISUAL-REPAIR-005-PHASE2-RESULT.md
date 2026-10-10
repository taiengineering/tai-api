---
wo: WO-REF01-060-B8-WAVE2-VISUAL-REPAIR-005-PHASE2-CANONICAL-006
evidence_type: PHASE2_CANONICAL_REPLACEMENT_RESULT
status: CANDIDATE_READY_GPT_REVIEW_PENDING
date: 2026-10-10
base_head: 448c6f37a1e11504244d13446f48d450a1cc6bb1
engine_py_sha8: be4899da
engine_cjs_sha8: 375250c7
---

# REF01-B8-WAVE2-VISUAL-REPAIR-005-PHASE2-RESULT

WO-REF01-060-B8-WAVE2-VISUAL-REPAIR-005-PHASE2-CANONICAL-006 Phase 2 정식 교체 결과.  
C031/C043/C044 정규 JSON·PDF·DOCX 9건 원자적 교체, 회귀 C1310 음성→합성 픽스처 이전, C1310 양성 케이스 3건 추가, C1309 레이블 단언 갱신.

## Preflight 결과

| 항목 | 결과 |
|------|------|
| BASE HEAD | 448c6f37a1e11504244d13446f48d450a1cc6bb1 PASS |
| working tree clean (pre-run) | PASS |
| ENGINE PY SHA8 | be4899da MATCH |
| ENGINE CJS SHA8 | 375250c7 MATCH |
| 기존 6개 정규 SHA256 (pre) | 6/6 MATCH |
| 후보 JSON 3건 메타 검증 | REVIEW_ONLY_NOT_CANONICAL 확인 |

## 교체 내역 (9건)

### C031

| 파일 | 이전 SHA256[:16] | 이후 SHA256[:16] |
|------|----------------|----------------|
| `scripts/c031_v1.json` | `ddf20f4ad82d94cc` | `ea9c00d54af988e8` |
| `output/TAI-FORM-C031-blank.pdf` | `b12cd430e64f0938` | `dcd52a9f204cbc06` |
| `output/TAI-FORM-C031-blank.docx` | `2f0e8d4431e816f5` | `bd2c2d35f7643737` |

변경 사항:
- S01.F06 레이블: `"사용 교육자료(명칭·버전)"` → `"교육자료·버전"`
- S01.F07 레이블: `"출석 증빙 종류·보관 위치"` → `"출석증빙·보관"`
- S04 text_flow 섹션 추가 (입력 안내문)
- `_meta.design_gate_notes` 갱신: "내부 POC 후보 검토 통과, 법률·권리·외부공개 검토는 별도 대기."
- `candidate_for_review`, `candidate_status` 필드 제거 (정규 파일)

### C043

| 파일 | 이전 SHA256[:16] | 이후 SHA256[:16] |
|------|----------------|----------------|
| `scripts/c043_v1.json` | `0fe94d508ceda3d2` | `454ed11fb6f4d70b` |
| `output/TAI-FORM-C043-blank.pdf` | `27554037428 5c881` | `13334054dc1b1c9a` |
| `output/TAI-FORM-C043-blank.docx` | `f19ff42ab7e915a0` | `b0e9f95f3e29ec9b` |

변경 사항:
- S01.F05 레이블: `"훈련 참여자/명단 참조"` → `"참여/명단참조"`
- `_meta.design_gate_notes` 갱신
- `candidate_for_review`, `candidate_status` 필드 제거

### C044

| 파일 | 이전 SHA256[:16] | 이후 SHA256[:16] |
|------|----------------|----------------|
| `scripts/c044_v1.json` | `3a789037d6db4cf1` | `9c7dacfa9ad4622e` |
| `output/TAI-FORM-C044-blank.pdf` | `e7dc0b22ab666ff5` | `6b4f51a5d40da64f` |
| `output/TAI-FORM-C044-blank.docx` | `d08e8fae4e75e13b` | `c1e3da22c8ef6ec1` |

변경 사항:
- S01.F01 레이블: `"화학물질/제품명"` → `"물질명/제품명"`
- S01.F04 레이블: `"작업대상 또는 적용 작업"` → `"대상·적용 작업"`
- `_meta.design_gate_notes` 갱신
- `candidate_for_review`, `candidate_status` 필드 제거

## Phase 2 검증 결과

### 경계 충돌 (phase2_qa_matrix.json)

| 폼 | 원본 충돌 | 신규 충돌 | 결과 |
|----|---------|---------|------|
| C031 | 8 | 0 | DEFECT_RESOLVED |
| C043 | 4 | 0 | DEFECT_RESOLVED |
| C044 | 7 | 0 | DEFECT_RESOLVED |

### 신규 정규 PDF

| 폼 | 페이지 | 방향 | 레이블 | 충돌 |
|----|------|------|------|------|
| C031 | 1p | portrait | 13/13 | 0 |
| C043 | 1p | portrait | 12/12 | 0 |
| C044 | 1p | portrait | 11/11 | 0 |

### 신규 정규 DOCX 라운드트립

| 폼 | 마커 총수 | 보존 | 상태 |
|----|---------|------|------|
| C031 | 23 | 23/23 | PASS |
| C043 | 22 | 22/22 | PASS |
| C044 | 21 | 21/21 | PASS |

LibreOffice DOCX 렌더: UNVERIFIED_LIBREOFFICE_NOT_INSTALLED

## QA-004 전체 재검증

```
14/14 A-PDF PASS (레이블 100%)
14/14 B-DOCX PASS
14/14 C-ROUNDTRIP PASS
```

## 회귀 테스트

```
pytest docs/reference-forms/scripts/test_common_engine.py -q
385 passed, 5 warnings in 19.15s   FAIL=0
```

총 385건 (이전 382건 + 신규 3건):
- C1310_11: C031 신규 정규 PDF 0충돌 양성
- C1310_12: C043 신규 정규 PDF 0충돌 양성
- C1310_13: C044 신규 정규 PDF 0충돌 양성

C1309_07/09/10 레이블 단언 갱신:
- C1309_07: `'출석 증빙'` → `'출석증빙'`
- C1309_09: `'참여자'` → `'참여'`
- C1309_10: `'작업대상'` → `'적용 작업'`

C1310_01/02/03/06: 합성 결함 픽스처(`_make_defect_pdf`) 이전 완료 — 정규 출력 불변성 유지.

## 증거 파일

| 파일 | 설명 |
|------|------|
| `evidence/visual-repair-005/phase2_sha_manifest.json` | 교체 전후 SHA256 전체 |
| `evidence/visual-repair-005/phase2_qa_matrix.json` | Phase 2 QA 결과 |
| `evidence/visual-repair-005/NEW_C031_pdf_page1.png` | C031 신규 정규 PDF 150dpi |
| `evidence/visual-repair-005/NEW_C043_pdf_page1.png` | C043 신규 정규 PDF 150dpi |
| `evidence/visual-repair-005/NEW_C044_pdf_page1.png` | C044 신규 정규 PDF 150dpi |
| `evidence/qa-004/qa_matrix.json` | B8 14폼 전수 재검증 결과 |

## 불변 확인

```
FROZEN_24_SHA              = 24/24 MATCH (이전 세션 기록)
COMMON_ENGINE_SHA          = PY be4899da / CJS 375250c7 MATCH
NON_TARGET_11_B8_SPECS     = NO_CHANGE (C031/C043/C044 외 11건)
PRODUCTION_DB_WRITE        = 0
```

## 상태

```
WO                         = WO-REF01-060-B8-WAVE2-VISUAL-REPAIR-005-PHASE2-CANONICAL-006
BASE_HEAD                  = 448c6f37a1e11504244d13446f48d450a1cc6bb1
CANONICAL_REPLACE_9FILES   = DONE (3 JSON + 3 PDF + 3 DOCX)
C1310_NEGATIVE_FIXTURE     = SYNTHETIC (합성 결함 픽스처 이전)
C1310_POSITIVE_NEW         = 3건 추가 (C031/C043/C044)
C1309_LABEL_ASSERT_UPDATE  = 3건 갱신 (07/09/10)
REGRESSION                 = 385 passed FAIL=0
QA_004_14FORMS             = 14/14 PASS
DOCX_BLANK_RENDER          = UNVERIFIED_LIBREOFFICE_NOT_INSTALLED
DOCX_EDITED_RENDER         = UNVERIFIED_LIBREOFFICE_NOT_INSTALLED
PR_MERGE                   = PENDING_GPT_REVIEW
DEPLOY                     = BLOCKED
PUBLICATION                = INTERNAL_POC_ONLY
NEXT_GATE                  = GPT_INDEPENDENT_VERIFICATION
```
