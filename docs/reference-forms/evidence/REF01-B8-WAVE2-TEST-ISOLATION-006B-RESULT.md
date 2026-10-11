---
wo: WO-REF01-060-B8-WAVE2-TEST-ISOLATION-006B
evidence_type: TEST_ISOLATION_RESULT
status: CANDIDATE_READY_GPT_REVIEW_PENDING
date: 2026-10-10
base_head: 2ac5428c4931b25855109a92e4c1055b787a0108
engine_py_sha8: be4899da
engine_cjs_sha8: 375250c7
---

# REF01-B8-WAVE2-TEST-ISOLATION-006B-RESULT

WO-REF01-060-B8-WAVE2-TEST-ISOLATION-006B 실행 결과.  
`test_C04_c012_docx_generation()` 완전 격리: 정규 output 경로 쓰기 제거.

## 격리 구현

`tempfile.TemporaryDirectory()` 기반 완전 격리:

```
TemporaryDirectory (자동 정리)
  scripts/
    gen_c012_docx.cjs       ← 복사
    common_v1_engine.cjs    ← 복사
    c012_fields.json        ← 복사
    node_modules            ← 원본 node_modules 심볼릭 링크 (읽기 전용)
  output/                   ← 생성된 DOCX 수신
```

- `gen_c012_docx.cjs blank`를 `cwd=scripts/`에서 실행
- `__dirname` 기준 출력 경로 = `scripts/../output/` → 임시 output/ 수신
- 정규 `output/TAI-FORM-C012-blank.docx` 미접촉
- `tempfile.mktemp()` 미사용
- `try/finally` 백업·복원 구조 제거
- 기존 OOXML 구조 검증 추가: ZIP 유효성 + `word/document.xml` 존재 확인

## 검증 결과

### 1. C012 정규 DOCX SHA256

```
기대: 2e6b5d9eca4d6dab51f8d50ff208972cedbe4842a68156b7548927db09970e53
실측: 2e6b5d9eca4d6dab51f8d50ff208972cedbe4842a68156b7548927db09970e53
결과: MATCH
```

### 2. 테스트 단독 실행

```
pytest test_common_engine.py::test_C04_c012_docx_generation -v
1 passed in 0.55s
```

### 3. 전수 회귀

```
pytest docs/reference-forms/scripts/test_common_engine.py -q
385 passed, 5 warnings in 19.26s   FAIL=0
```

### 4. 테스트 전후 output SHA256 매트릭스

```
sha256sum output/*.pdf output/*.docx | sort > before.txt
pytest ... (385 passed)
sha256sum output/*.pdf output/*.docx | sort > after.txt
diff before.txt after.txt → IDENTICAL (0 differences)
```

### 5. C031/C043/C044 정규 출력물 9개 SHA256

| 파일 | SHA256[:16] | 상태 |
|------|------------|------|
| TAI-FORM-C031-blank.pdf | `dcd52a9f204cbc06` | MATCH |
| TAI-FORM-C031-blank.docx | `bd2c2d35f7643737` | MATCH |
| TAI-FORM-C043-blank.pdf | `13334054dc1b1c9a` | MATCH |
| TAI-FORM-C043-blank.docx | `b0e9f95f3e29ec9b` | MATCH |
| TAI-FORM-C044-blank.pdf | `6b4f51a5d40da64f` | MATCH |
| TAI-FORM-C044-blank.docx | `c1e3da22c8ef6ec1` | MATCH |

(C031/C043/C044 JSON도 scripts/c0{31,43,44}_v1.json 내용 변경 없음)

### 6. 공통 엔진 SHA256

| 파일 | SHA8 | 상태 |
|------|------|------|
| common_v1_engine.py | be4899da | MATCH |
| common_v1_engine.cjs | 375250c7 | MATCH |

### 7. tempfile.mktemp() 사용 제거

`grep 'mktemp' test_common_engine.py` → 0건 (제거 완료)

## 변경 파일 (이번 WO-006B)

| 파일 | 변경 내용 |
|------|---------|
| `scripts/test_common_engine.py` | test_C04_c012_docx_generation 완전 격리 구현 |
| `evidence/REF01-B8-WAVE2-TEST-ISOLATION-006B-RESULT.md` | 본 증거 문서 (신규) |

정규 JSON/PDF/DOCX, 생성기, 공통 엔진, DB 변경 없음.

## 상태

```
WO                         = WO-REF01-060-B8-WAVE2-TEST-ISOLATION-006B
BASE_HEAD                  = 2ac5428c4931b25855109a92e4c1055b787a0108
TEST_ISOLATION             = COMPLETE (TemporaryDirectory, symlink, no canonical write)
MKTEMP_REMOVED             = TRUE
OUTPUT_INVARIANT           = PASS (테스트 전후 IDENTICAL)
C012_SHA256                = MATCH
REGRESSION                 = 385 passed FAIL=0
C031_C043_C044_UNCHANGED   = PASS
COMMON_ENGINE_UNCHANGED    = PASS
PRODUCTION_DB_WRITE        = 0
PR_MERGE                   = BLOCKED
DEPLOY                     = BLOCKED
NEXT_GATE                  = GPT_INDEPENDENT_VERIFICATION
WO006_CLOSED_FINAL         = NO (GPT 재검증 전)
```
