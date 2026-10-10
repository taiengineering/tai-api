---
wo: WO-REF01-060-B8-WAVE2-PHASE2-SCOPE-REPAIR-006A
evidence_type: SCOPE_REPAIR_RESULT
status: CANDIDATE_READY_GPT_REVIEW_PENDING
date: 2026-10-10
base_head: e85c41873d6d7e995137b6b229c34bd131cfb7d2
engine_py_sha8: be4899da
engine_cjs_sha8: 375250c7
---

# REF01-B8-WAVE2-PHASE2-SCOPE-REPAIR-006A-RESULT

WO-REF01-060-B8-WAVE2-PHASE2-SCOPE-REPAIR-006A 실행 결과.  
C012 원상복구 + 회귀 테스트 부작용 차단 + 불변 검증.

## A. C012 원상복구

| 항목 | 값 |
|------|-----|
| 복원 출처 커밋 | `448c6f37a1e11504244d13446f48d450a1cc6bb1` |
| 복원 대상 파일 | `output/TAI-FORM-C012-blank.docx` |
| 기대 SHA256 | `2e6b5d9eca4d6dab51f8d50ff208972cedbe4842a68156b7548927db09970e53` |
| 실측 SHA256 | `2e6b5d9eca4d6dab51f8d50ff208972cedbe4842a68156b7548927db09970e53` |
| 결과 | MATCH |

복원 방법: `git show 448c6f37:docs/reference-forms/output/TAI-FORM-C012-blank.docx`

## B. 테스트 격리 수정

`test_C04_c012_docx_generation()` — `try/finally` 백업·복원 추가:

- 테스트 시작 전 정규 C012 DOCX를 임시 경로에 백업
- `gen_c012_docx.cjs blank` 실행 (기존 동작 유지: 생성 성공 + 파일 크기 검증)
- `finally` 블록에서 백업을 정규 경로에 무조건 복원
- `gen_c012_docx.cjs` 및 공통 엔진 수정 없음
- C0203 구조 검증 테스트: 복원된 정규 파일 대상으로 PASS 유지

## C. 불변 검증

### 테스트 전후 output SHA256

```
sha256sum output/*.pdf output/*.docx | sort > before.txt
pytest ... (385 passed)
sha256sum output/*.pdf output/*.docx | sort > after.txt
diff before.txt after.txt  →  IDENTICAL
```

→ 테스트 실행 전후 전체 정규 출력물 SHA256 완전 일치

### C031/C043/C044 Phase 2 신규 정규 파일 SHA256 유지

| 파일 | SHA256[:16] | 상태 |
|------|------------|------|
| TAI-FORM-C031-blank.pdf | `dcd52a9f204cbc06` | MATCH |
| TAI-FORM-C031-blank.docx | `bd2c2d35f7643737` | MATCH |
| TAI-FORM-C043-blank.pdf | `13334054dc1b1c9a` | MATCH |
| TAI-FORM-C043-blank.docx | `b0e9f95f3e29ec9b` | MATCH |
| TAI-FORM-C044-blank.pdf | `6b4f51a5d40da64f` | MATCH |
| TAI-FORM-C044-blank.docx | `c1e3da22c8ef6ec1` | MATCH |

### 공통 엔진

| 파일 | SHA8 | 상태 |
|------|------|------|
| common_v1_engine.py | be4899da | MATCH |
| common_v1_engine.cjs | 375250c7 | MATCH |

## 회귀 테스트

```
pytest docs/reference-forms/scripts/test_common_engine.py -q
385 passed, 5 warnings in 19.04s   FAIL=0
```

## 변경 파일 (이번 보정)

| 파일 | 변경 내용 |
|------|---------|
| `output/TAI-FORM-C012-blank.docx` | 448c6f37 상태로 복원 |
| `scripts/test_common_engine.py` | test_C04_c012_docx_generation 격리 수정 |
| `evidence/REF01-B8-WAVE2-PHASE2-SCOPE-REPAIR-006A-RESULT.md` | 본 증거 문서 (신규) |

C031/C043/C044 정규 파일, 공통 엔진, DB 변경 없음.

## 상태

```
WO                         = WO-REF01-060-B8-WAVE2-PHASE2-SCOPE-REPAIR-006A
BASE_HEAD                  = e85c41873d6d7e995137b6b229c34bd131cfb7d2
C012_RESTORED              = PASS (SHA256 MATCH)
TEST_ISOLATION             = PASS (try/finally 백업·복원)
OUTPUT_INVARIANT           = PASS (테스트 전후 IDENTICAL)
REGRESSION                 = 385 passed FAIL=0
C031_C043_C044_UNCHANGED   = PASS
COMMON_ENGINE_UNCHANGED    = PASS
PRODUCTION_DB_WRITE        = 0
PR_MERGE                   = BLOCKED
DEPLOY                     = BLOCKED
NEXT_GATE                  = GPT_INDEPENDENT_VERIFICATION
WO006_CLOSED_FINAL         = NO (GPT 재검증 전)
```
