---
wo: WO-REF01-060-B8-WAVE2-FINAL-GATE-007B
evidence_type: FINAL_GATE_007B_EXIT_GATE
status: EVIDENCE_COMPLETE_GPT_GATE_PENDING
date: 2026-10-10
base_head: 091a0dfb81832ba4eb5d5e0fbca35bcb9e6e71a3
engine_py_sha8: be4899da
engine_cjs_sha8: 375250c7
---

# REF01-B8-WAVE2-FINAL-GATE-007B-RESULT

WO-REF01-060-B8-WAVE2-FINAL-GATE-007B 결과.  
qa_004.py 실패 게이트 수정 + 변조 감지 6개 시나리오 검증.

---

## 1. qa_004.py 실패 게이트 수정

### 변경 내용

`if __name__ == "__main__"` 블록에 실패 집계 및 `sys.exit()` 추가:

```python
qa_matrix, sha_ok, sha_fail, frozen_ok, frozen_fail, py_sha, cjs_sha = main()
failures = []
if sha_fail:          failures.append(f"B8_SHA_FAIL={len(sha_fail)}")
if frozen_fail:       failures.append(f"FROZEN_SHA_FAIL={len(frozen_fail)}") 
if py_sha  != EXPECTED_PY:  failures.append("ENGINE_PY_SHA_MISMATCH")
if cjs_sha != EXPECTED_CJS: failures.append("ENGINE_CJS_SHA_MISMATCH")
for row in qa_matrix:
    for check in ("A_PDF","B_DOCX_BLANK","C_ROUNDTRIP"):
        if row[check]["status"] == "HOLD":
            failures.append(f"{row['form']}_{check}_HOLD")
if failures:
    print(f"QA GATE FAIL: {', '.join(failures)}")
    sys.exit(1)
else:
    print("QA GATE PASS: all checks passed")
    sys.exit(0)
```

Phase 2 SHA override 유지. BUILD-003 영수증·Phase 2 매니페스트 미변경.

---

## 2. 변조 감지 테스트 결과

모든 테스트에서 정규 파일을 직접 조작하고 즉시 복원. 복원 SHA 검증 포함.

| 테스트 | 시나리오 | exit code | 판정 |
|--------|---------|-----------|------|
| T1 NORMAL | 변조 없음 | 0 | PASS |
| T2 B8_PDF | C026 PDF 1바이트 추가 | 1 | PASS |
| T3 B8_DOCX | C026 DOCX 1바이트 추가 | 1 | PASS |
| T4 FROZEN_SHA | C001 PDF 1바이트 추가 | 1 | PASS |
| T5 ENGINE_SHA | common_v1_engine.py 1줄 추가 | 1 | PASS |
| T6 QA_HOLD | A_PDF HOLD 시뮬레이션 | 1 | PASS |

**T2 로그:** `B8 OUTPUT SHA: 27/28 MATCH FAIL=1 → QA GATE FAIL: B8_SHA_FAIL=1`  
**T4 로그:** `FROZEN SHA: 23/24 MATCH FAIL=1 → QA GATE FAIL: FROZEN_SHA_FAIL=1`  
**T5 로그:** `ENGINE PY: da6fd7fe MISMATCH → QA GATE FAIL: ENGINE_PY_SHA_MISMATCH`  
**T6 로그:** `QA GATE FAIL: C026_A_PDF_HOLD`

모든 복원 SHA: C026 PDF `8bc69c3c` / C026 DOCX `6dec4de1` / C001 PDF `27002fc4` / engine.py `be4899da` — MATCH.

---

## 3. 최종 불변 검증

### qa_004.py 정상 실행

```
B8 OUTPUT SHA: 28/28 MATCH  FAIL=0
FROZEN SHA:    24/24 MATCH  FAIL=0
ENGINE PY:  be4899da  MATCH
ENGINE CJS: 375250c7  MATCH
QA GATE PASS: all checks passed
EXIT CODE: 0
```

### 회귀 테스트

```
pytest docs/reference-forms/scripts/test_common_engine.py -q
385 passed, 5 warnings in 18.05s   FAIL=0
```

### output SHA 불변

```
sha256sum output/*.pdf output/*.docx (72파일) before = after → IDENTICAL
```

---

## 4. 변경 파일

| 파일 | 내용 |
|------|------|
| `scripts/qa_004.py` | 실패 게이트 추가 (15줄) |
| `evidence/final-gate-007/tamper_test_007b.json` | T1~T6 변조 감지 결과 |
| `evidence/REF01-B8-WAVE2-FINAL-GATE-007B-RESULT.md` | 본 증거 문서 |

정규 JSON/PDF/DOCX, 공통 엔진, DB 변경 없음.

---

## 5. 상태

```
WO                         = WO-REF01-060-B8-WAVE2-FINAL-GATE-007B
BASE_HEAD                  = 091a0dfb81832ba4eb5d5e0fbca35bcb9e6e71a3
QA_EXIT_GATE               = IMPLEMENTED (sys.exit 0/1)
B8_SHA_28_28               = MATCH (exit 0)
TAMPER_DETECTION_T1_T6     = ALL PASS (T1 exit=0 / T2~T6 exit=1)
REGRESSION                 = 385 passed FAIL=0
OUTPUT_SHA_INVARIANT       = IDENTICAL (72파일)
FROZEN_24                  = 24/24 MATCH
ENGINE_SHA                 = PY be4899da / CJS 375250c7 MATCH
LEGAL_REVIEW               = 14/14 PENDING
RIGHTS                     = 14/14 RIGHTS_UNVERIFIED
PUBLICATION_STATUS         = INTERNAL_POC_ONLY
B8_CLOSED_FINAL            = NO
PR_MERGE                   = BLOCKED
PRODUCTION_DEPLOY          = BLOCKED
PUBLICATION_AUTHORIZATION  = NOT_AUTHORIZED
NEXT_GATE                  = GPT_INDEPENDENT_VERIFICATION
```
