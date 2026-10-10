---
wo: WO-REF01-060-B8-WAVE2-FINAL-GATE-007A
evidence_type: FINAL_GATE_007A_SUPPLEMENT
status: EVIDENCE_COMPLETE_GPT_GATE_PENDING
date: 2026-10-10
base_head: 67ad5c639d8077ca00455de0e8833d172a436b2c
engine_py_sha8: be4899da
engine_cjs_sha8: 375250c7
---

# REF01-B8-WAVE2-FINAL-GATE-007A-RESULT

WO-REF01-060-B8-WAVE2-FINAL-GATE-007A 보완 결과.  
(A) SHA 기준 정합화 28/28 + 변조 감지 테스트  
(B) DOCX 시각검증 보완 — 짧은 현실 데이터 + 표 너비 분석 + 재렌더  
(C) 회귀 385 PASS / output SHA 불변

---

## A. SHA 기준 정합화

### 수정 내용 (`qa_004.py`)

BUILD-003 영수증에서 기준 SHA 읽기 후 C031/C043/C044를 Phase 2 매니페스트로 덮어씌움.

```python
# Override C031/C043/C044 with Phase 2 approved replacement SHAs (WO-006)
phase2_manifest = BASE.parent / "evidence" / "visual-repair-005" / "phase2_sha_manifest.json"
p2 = json.loads(phase2_manifest.read_text(encoding="utf-8"))
for cid in ("c031", "c043", "c044"):
    sha_from_receipt[f"{cid}_pdf"]  = p2["replacements"][cid]["pdf_new"]
    sha_from_receipt[f"{cid}_docx"] = p2["replacements"][cid]["docx_new"]
```

- BUILD-003 영수증 미변경
- phase2_sha_manifest.json 미변경
- 나머지 11종 기준값 유지

### 실행 결과

```
B8 OUTPUT SHA: 28/28 MATCH  FAIL=0
FROZEN SHA:    24/24 MATCH  FAIL=0
ENGINE PY:  be4899da  MATCH
ENGINE CJS: 375250c7  MATCH
```

### 변조 감지 테스트

```
C026 PDF에 바이트 추가(임시) → SHA 재검증
TAMPER_TEST: SHA 27/28 MATCH  FAIL=1
  ✗ C026_pdf: TAMPERED
TAMPER DETECTION: PASS
복원 후: C026_pdf SHA 8bc69c3c MATCH
```

실제 변조 시 FAIL 정상 감지. 복원 후 28/28 복귀 확인.

---

## B. DOCX 시각검증 보완

### 주입 데이터 (짧은 현실 업무 데이터)

| 필드 유형 | 주입 값 |
|---------|--------|
| 날짜/일자 | `2026-10-10` |
| 성명/작성자 | `홍길동` |
| 기타 | `검토완료` |

QA 마커(긴 문자열) 미사용. 표 행 높이 팽창 없음.

### 표 너비 분석

| 방향 | 표 너비(twips) | mm 환산 | A4 콘텐츠 폭 | 판정 |
|------|-------------|--------|-----------|------|
| portrait (12종) | 9637 | 169.9mm | ~170mm | 정상 (전폭 사용) |
| landscape (C037, C039) | 14570 | 256.8mm | ~257mm | 정상 (전폭 사용) |

**표 너비 정상** — QuickLook 썸네일에서 관찰된 "좁은 너비" 현상은 썸네일 렌더링 축소 아티팩트.  
실제 DOCX 표 너비는 A4 콘텐츠 폭 전체를 사용함.

### 우선 검증 결과 (C031·C043·C044·GOV-01)

| 폼 | 표 수 | 주입 필드 | 단락 수 | 렌더 |
|----|------|---------|--------|------|
| C031 | 4 | 12 | 6 | RENDERED |
| C043 | 5 | 10 | 5 | RENDERED |
| C044 | 5 | 9 | 5 | RENDERED |
| GOV-01 | 5 | 10 | 5 | RENDERED |

C031 text_flow S04 안내문 포함 (파라그래프 수 +1).

### 전체 14종 요약

| 폼 | 표 | 주입 | 단락 | 렌더 |
|----|---|------|------|------|
| C026 | 3 | 12 | 5 | RENDERED |
| C027 | 3 | 10 | 5 | RENDERED |
| C028 | 3 | 10 | 5 | RENDERED |
| C029 | 3 | 11 | 5 | RENDERED |
| C031 | 4 | 12 | 6 | RENDERED |
| C033 | 3 | 10 | 5 | RENDERED |
| C037 | 3 | 10 | 3 | RENDERED |
| C039 | 3 | 12 | 3 | RENDERED |
| C040 | 3 | 9 | 3 | RENDERED |
| C041 | 3 | 9 | 5 | RENDERED |
| C042 | 3 | 9 | 5 | RENDERED |
| C043 | 5 | 10 | 5 | RENDERED |
| C044 | 5 | 9 | 5 | RENDERED |
| GOV-01 | 5 | 10 | 5 | RENDERED |

현실 데이터로 편집 시 모든 폼의 단락·내용이 1페이지 범위 내 수용됨.  
단락 수 3~6개 — A4 1페이지 초과 가능성 없음.

### 렌더 이미지 경로

```
evidence/final-gate-007/render_realistic/REAL_{FORM}_p1.png × 14
```

**제한:** qlmanage는 첫 페이지 썸네일만 생성. `DOCX_VISUAL=GPT_PENDING` 유지.  
`POLARIS_COMPATIBILITY=UNVERIFIED` 유지.

---

## C. 회귀 및 불변성

```
pytest docs/reference-forms/scripts/test_common_engine.py -q
385 passed, 5 warnings in 19.20s   FAIL=0
```

```
output SHA (72파일) 전후 IDENTICAL
FROZEN_24 = 24/24 MATCH
ENGINE PY sha8 = be4899da MATCH
ENGINE CJS sha8 = 375250c7 MATCH
PRODUCTION_DB_WRITE = 0
```

---

## 변경 파일

| 파일 | 내용 |
|------|------|
| `scripts/qa_004.py` | Phase 2 SHA override 추가 (7줄 추가) |
| `evidence/final-gate-007/render_realistic/REAL_{FORM}_p1.png` × 14 | 현실 데이터 편집 렌더 (신규) |
| `evidence/final-gate-007/visual_supplement.json` | 표 너비·주입·단락 분석 (신규) |
| `evidence/REF01-B8-WAVE2-FINAL-GATE-007A-RESULT.md` | 본 증거 문서 (신규) |

정규 JSON 14종·PDF 14종·DOCX 14종·공통 엔진 수정 없음.

---

## 상태

```
WO                         = WO-REF01-060-B8-WAVE2-FINAL-GATE-007A
BASE_HEAD                  = 67ad5c639d8077ca00455de0e8833d172a436b2c
B8_SHA_28_28               = MATCH (Phase 2 override 반영)
SHA_TAMPER_DETECTION       = PASS (FAIL 정상 감지)
DOCX_TABLE_WIDTH           = 정상 (portrait 170mm / landscape 257mm = 전폭)
DOCX_VISUAL_REALISTIC      = 14/14 RENDERED (단락 3~6 / 1페이지 내 수용)
DOCX_VISUAL                = GPT_PENDING
POLARIS_COMPATIBILITY      = UNVERIFIED
REGRESSION                 = 385 passed FAIL=0
OUTPUT_SHA_INVARIANT       = IDENTICAL
FROZEN_24                  = 24/24 MATCH
LEGAL_REVIEW               = 14/14 PENDING
RIGHTS                     = 14/14 RIGHTS_UNVERIFIED
PUBLICATION_STATUS         = INTERNAL_POC_ONLY
B8_CLOSED_FINAL            = NO
PR_MERGE                   = BLOCKED
PRODUCTION_DEPLOY          = BLOCKED
PUBLICATION_AUTHORIZATION  = NOT_AUTHORIZED
NEXT_GATE                  = GPT_INDEPENDENT_VERIFICATION
```
