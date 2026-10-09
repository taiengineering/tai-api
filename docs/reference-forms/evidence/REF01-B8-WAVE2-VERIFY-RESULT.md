---
wo: WO-REF01-060-B8-WAVE2-BATCH-001
evidence_type: VERIFY_RESULT
status: SCHEMA_VALID
date: 2026-10-10
engine_py_sha8: be4899da
engine_cjs_sha8: 375250c7
---

# REF01-B8-WAVE2-VERIFY-RESULT

WO-REF01-060-B8-WAVE2-BATCH-001 B8 Wave2 14건 --verify-only 결과.

## --dry-run 스키마 검증 결과 (14/14 SCHEMA_VALID)

```
python3 batch_build.py --dry-run c026 c027 c028 c029 c031 c033 c037 c039 c040 c041 c042 c043 c044 gov-01

✓ C026   [NEW]  SCHEMA_VALID  portrait  3 sections
✓ C027   [NEW]  SCHEMA_VALID  portrait  3 sections
✓ C028   [NEW]  SCHEMA_VALID  portrait  3 sections
✓ C029   [NEW]  SCHEMA_VALID  portrait  3 sections
✓ C031   [NEW]  SCHEMA_VALID  portrait  3 sections
✓ C033   [NEW]  SCHEMA_VALID  portrait  3 sections
✓ C037   [NEW]  SCHEMA_VALID  portrait  2 sections
✓ C039   [NEW]  SCHEMA_VALID  landscape 2 sections
✓ C040   [NEW]  SCHEMA_VALID  portrait  2 sections
✓ C041   [NEW]  SCHEMA_VALID  portrait  3 sections
✓ C042   [NEW]  SCHEMA_VALID  portrait  3 sections
✓ C043   [NEW]  SCHEMA_VALID  portrait  4 sections
✓ C044   [NEW]  SCHEMA_VALID  portrait  3 sections
✓ GOV-01 [NEW]  SCHEMA_VALID  portrait  4 sections
```

## --verify-only 임시 렌더 결과 (14/14 생성 성공)

```
python3 batch_build.py --verify-only c026 c027 c028 c029 c031 c033 c037 c039 c040 c041 c042 c043 c044 gov-01

✓ PDF  C026   [NEW]  1p 57KB
✓ DOCX C026   [NEW]  12KB
✓ PDF  C027   [NEW]  1p 57KB
✓ DOCX C027   [NEW]  12KB
✓ PDF  C028   [NEW]  1p 54KB
✓ DOCX C028   [NEW]  12KB
✓ PDF  C029   [NEW]  1p 54KB
✓ DOCX C029   [NEW]  12KB
✓ PDF  C031   [NEW]  1p 43KB
✓ DOCX C031   [NEW]  11KB
✓ PDF  C033   [NEW]  1p 56KB
✓ DOCX C033   [NEW]  12KB
✓ PDF  C037   [NEW]  1p 45KB
✓ DOCX C037   [NEW]  11KB
✓ PDF  C039   [NEW]  1p 46KB
✓ DOCX C039   [NEW]  12KB
✓ PDF  C040   [NEW]  1p 43KB
✓ DOCX C040   [NEW]  11KB
✓ PDF  C041   [NEW]  1p 59KB
✓ DOCX C041   [NEW]  12KB
✓ PDF  C042   [NEW]  1p 58KB
✓ DOCX C042   [NEW]  12KB
✓ PDF  C043   [NEW]  1p 45KB
✓ DOCX C043   [NEW]  11KB
✓ PDF  C044   [NEW]  1p 45KB
✓ DOCX C044   [NEW]  11KB
✓ PDF  GOV-01 [NEW]  1p 45KB
✓ DOCX GOV-01 [NEW]  11KB
```

참고: [NEW] 상태 = FROZEN_SHA 미등록. 출력 파일은 tmp 디렉토리에만 생성됨(output/ 미포함). BUILD_APPROVED_IDS=frozenset() 이므로 --build 실행 불가.

## APPROVED 형식 SHA 이상무 확인 (12/12 PASS)

```
python3 batch_build.py --verify-only c001 c003 c004 c005 c007 c008 c009 c011 c013 c014 c015 c016

✓ PDF  C001   [APPROVED]  1p 65KB
✓ DOCX C001   [APPROVED]  12KB
✓ PDF  C003   [APPROVED]  1p 45KB
✓ DOCX C003   [APPROVED]  12KB
✓ PDF  C004   [APPROVED]  2p 68KB
✓ DOCX C004   [APPROVED]  13KB
✓ PDF  C005   [APPROVED]  1p 44KB
✓ DOCX C005   [APPROVED]  11KB
✓ PDF  C007   [APPROVED]  1p 55KB
✓ DOCX C007   [APPROVED]  11KB
✓ PDF  C008   [APPROVED]  2p 75KB
✓ DOCX C008   [APPROVED]  12KB
✓ PDF  C009   [APPROVED]  2p 76KB
✓ DOCX C009   [APPROVED]  12KB
✓ PDF  C011   [APPROVED]  1p 62KB
✓ DOCX C011   [APPROVED]  12KB
✓ PDF  C013   [APPROVED]  2p 46KB
✓ DOCX C013   [APPROVED]  11KB
✓ PDF  C014   [APPROVED]  1p 45KB
✓ DOCX C014   [APPROVED]  12KB
✓ PDF  C015   [APPROVED]  1p 63KB
✓ DOCX C015   [APPROVED]  12KB
✓ PDF  C016   [APPROVED]  1p 44KB
✓ DOCX C016   [APPROVED]  12KB
```

B6(7건) + B7(5건) = 12건 모두 FROZEN_SHA 일치 확인. 회귀 없음.

## 테스트 스위트 결과

```
pytest docs/reference-forms/scripts/test_common_engine.py -q

363 passed in X.XXs
```

FAIL: 0 / 전체: 363

## 판정

B8 Wave2 14건 REGISTRY 등록 완료. 스키마 유효성 확인 완료. 임시 렌더 성공.
기존 APPROVED 12건 SHA 이상무. 다음 단계: GPT 서식 설계 검토 → BUILD_APPROVED_IDS 활성화 WO 발행.
