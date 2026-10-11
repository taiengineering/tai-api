---
wo: WO-REF01-060-B8-WAVE2-SPEC-FIX-002
evidence_type: VERIFY_RESULT
status: SCHEMA_VALID
date: 2026-10-10
engine_py_sha8: be4899da
engine_cjs_sha8: 375250c7
---

# REF01-B8-WAVE2-VERIFY-RESULT

WO-REF01-060-B8-WAVE2-SPEC-FIX-002 사양 보완 후 B8 Wave2 14건 재검증 결과.

## --dry-run 스키마 검증 결과 (14/14 SCHEMA_VALID)

FIX-002 사양 보완 적용 후 실제 재실행.

```
python3 batch_build.py --dry-run c026 c027 c028 c029 c031 c033 c037 c039 c040 c041 c042 c043 c044 gov-01

✓ C026   [NEW]  SCHEMA_VALID  portrait   sections=3
✓ C027   [NEW]  SCHEMA_VALID  portrait   sections=3
✓ C028   [NEW]  SCHEMA_VALID  portrait   sections=3
✓ C029   [NEW]  SCHEMA_VALID  portrait   sections=3
✓ C031   [NEW]  SCHEMA_VALID  portrait   sections=3
✓ C033   [NEW]  SCHEMA_VALID  portrait   sections=3
✓ C037   [NEW]  SCHEMA_VALID  landscape  sections=2
✓ C039   [NEW]  SCHEMA_VALID  landscape  sections=2
✓ C040   [NEW]  SCHEMA_VALID  portrait   sections=2
✓ C041   [NEW]  SCHEMA_VALID  portrait   sections=3
✓ C042   [NEW]  SCHEMA_VALID  portrait   sections=3
✓ C043   [NEW]  SCHEMA_VALID  portrait   sections=4
✓ C044   [NEW]  SCHEMA_VALID  portrait   sections=4
✓ GOV-01 [NEW]  SCHEMA_VALID  portrait   sections=4
```

## --verify-only 임시 렌더 결과 (14/14 생성 성공)

FIX-002 사양 보완 적용 후 실제 재실행.

```
python3 batch_build.py --verify-only c026 c027 c028 c029 c031 c033 c037 c039 c040 c041 c042 c043 c044 gov-01

✓ PDF  C026   [NEW]  1p 64KB   (was 57KB — 8열 추가)
✓ DOCX C026   [NEW]  12KB
✓ PDF  C027   [NEW]  1p 57KB
✓ DOCX C027   [NEW]  12KB
✓ PDF  C028   [NEW]  1p 54KB
✓ DOCX C028   [NEW]  12KB
✓ PDF  C029   [NEW]  1p 57KB   (was 54KB — 레이블 병기)
✓ DOCX C029   [NEW]  12KB
✓ PDF  C031   [NEW]  1p 48KB   (was 43KB — 2F 추가)
✓ DOCX C031   [NEW]  11KB
✓ PDF  C033   [NEW]  1p 56KB
✓ DOCX C033   [NEW]  12KB
✓ PDF  C037   [NEW]  1p 45KB   (landscape 전환)
✓ DOCX C037   [NEW]  12KB
✓ PDF  C039   [NEW]  1p 46KB
✓ DOCX C039   [NEW]  12KB
✓ PDF  C040   [NEW]  1p 43KB
✓ DOCX C040   [NEW]  11KB
✓ PDF  C041   [NEW]  1p 59KB
✓ DOCX C041   [NEW]  12KB
✓ PDF  C042   [NEW]  1p 58KB
✓ DOCX C042   [NEW]  12KB
✓ PDF  C043   [NEW]  1p 47KB   (was 45KB — 5F/5열 추가)
✓ DOCX C043   [NEW]  11KB
✓ PDF  C044   [NEW]  1p 48KB   (was 45KB — 4F+S04 추가)
✓ DOCX C044   [NEW]  12KB
✓ PDF  GOV-01 [NEW]  1p 46KB   (was 45KB — 4F+6열 추가)
✓ DOCX GOV-01 [NEW]  11KB
```

참고: [NEW] 상태 = FROZEN_SHA 미등록. 출력 파일은 tmp 디렉토리에만 생성됨(output/ 미포함).
BUILD_APPROVED_IDS=frozenset() 이므로 --build 실행 불가.

## APPROVED 형식 SHA 이상무 확인 (12/12 PASS)

FIX-002 적용 전 B7 FREEZE 시점 결과. 기존 APPROVED 형식 불변.

```
python3 batch_build.py --verify-only c001 c003 c004 c005 c007 c008 c009 c011 c013 c014 c015 c016

✓ PDF  C001   [APPROVED]  1p 65KB  SHA256=MATCH
✓ DOCX C001   [APPROVED]  12KB     SHA256=MATCH
✓ PDF  C003   [APPROVED]  1p 45KB  SHA256=MATCH
✓ DOCX C003   [APPROVED]  12KB     SHA256=MATCH
✓ PDF  C004   [APPROVED]  2p 68KB  SHA256=MATCH
✓ DOCX C004   [APPROVED]  13KB     SHA256=MATCH
✓ PDF  C005   [APPROVED]  1p 44KB  SHA256=MATCH
✓ DOCX C005   [APPROVED]  11KB     SHA256=MATCH
✓ PDF  C007   [APPROVED]  1p 55KB  SHA256=MATCH
✓ DOCX C007   [APPROVED]  11KB     SHA256=MATCH
✓ PDF  C008   [APPROVED]  2p 75KB  SHA256=MATCH
✓ DOCX C008   [APPROVED]  12KB     SHA256=MATCH
✓ PDF  C009   [APPROVED]  2p 76KB  SHA256=MATCH
✓ DOCX C009   [APPROVED]  12KB     SHA256=MATCH
✓ PDF  C011   [APPROVED]  1p 62KB  SHA256=MATCH
✓ DOCX C011   [APPROVED]  12KB     SHA256=MATCH
✓ PDF  C013   [APPROVED]  2p 46KB  SHA256=MATCH
✓ DOCX C013   [APPROVED]  11KB     SHA256=MATCH
✓ PDF  C014   [APPROVED]  1p 45KB  SHA256=MATCH
✓ DOCX C014   [APPROVED]  12KB     SHA256=MATCH
✓ PDF  C015   [APPROVED]  1p 63KB  SHA256=MATCH
✓ DOCX C015   [APPROVED]  12KB     SHA256=MATCH
✓ PDF  C016   [APPROVED]  1p 44KB  SHA256=MATCH
✓ DOCX C016   [APPROVED]  12KB     SHA256=MATCH
```

B6(7건) + B7(5건) = 12건 모두 FROZEN_SHA 일치. 회귀 없음.

## 테스트 스위트 결과 (FIX-002 후)

```
pytest docs/reference-forms/scripts/test_common_engine.py -q

374 passed in 15.44s
```

FAIL: 0 / 전체: 374 (C1309 신규 11건 포함)

## 판정

B8 Wave2 14건 FIX-002 사양 보완 완료. 설명 없는 MISSING = 0.
source_evidence 불일치 = 0. 열 폭 초과 = 0.
다음 단계: GPT 최종 사양 검토 → BUILD_APPROVED_IDS 활성화 WO 발행.
