---
wo: WO-REF01-059-B7-BATCH-BUILD-005
evidence_type: OWNER_QA_RECEIPT
status: CLOSED_FINAL
date: 2026-10-10
commit: ccc7ce33
---

# REF01-B7-BATCH-CLOSE-RECEIPT

WO-REF01-059-B7-BATCH-BUILD-005 Owner QA 수령 기록.

## B7 빌드 결과 (5건 신규 출력)

| 형식 ID | 파일명 (PDF) | 파일명 (DOCX) | 페이지 | PDF KB | DOCX KB |
|---------|-------------|--------------|--------|--------|---------|
| C007 | TAI-FORM-C007-blank.pdf | TAI-FORM-C007-blank.docx | 1p | 55KB | 11KB |
| C008 | TAI-FORM-C008-blank.pdf | TAI-FORM-C008-blank.docx | 2p | 75KB | 12KB |
| C009 | TAI-FORM-C009-blank.pdf | TAI-FORM-C009-blank.docx | 2p | 76KB | 12KB |
| C011 | TAI-FORM-C011-blank.pdf | TAI-FORM-C011-blank.docx | 1p | 62KB | 12KB |
| C013 | TAI-FORM-C013-blank.pdf | TAI-FORM-C013-blank.docx | 2p | 46KB | 11KB |

## Frozen SHA256 (APPROVED_IDS 편입 기준)

```
c007_pdf:  2774fdc33f793fe25d3580ff089991f9b96ea2ae9efbb401dce31dd2281c82ad
c007_docx: 73374430fe7624b7eb97b5e6251de02367a726c755574bba315c9dd4233a2ed3
c008_pdf:  11c4cf4b7612fd9d776de10b29a744a5055a33ffe40137986267b13fa904fe72
c008_docx: ff6ac9747c6a72f6ca3943778a014953d345bcbf2018e9bcfc5225ae96992cb6
c009_pdf:  2397559dccc6677dd1bbc646707934bfb34857d8cee8bc6f47651cd371cf5c90
c009_docx: 4c4c34c56b93cfff84d25958789c3218a568284d0c47c6ec960f666eb11c0121
c011_pdf:  791bec736a92d76ef5b5565f04d0f0585158b231e2a98a7cf58718d14143ac46
c011_docx: 1ca2b8ed58ad42de2aa5ce3894e7a84fd10feb128634e779964fee38957b4d1c
c013_pdf:  58fe149a510cc942679de0cd10253767b088d1e0d6a8423c344a11d0fdac190e
c013_docx: a7435672d3cbe8e3f12273579ed41251b8d310e415159d90094e9735928bbd7b
```

## Owner --verify-only 결과 (5/5 PASS)

```
--verify-only c007 c008 c009 c011 c013

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
```

## 전체 테스트 결과 (B7 FROZEN 상태 기준)

- 총 PASS: 363/363
- FAIL: 0
- 테스트 파일: docs/reference-forms/scripts/test_common_engine.py

## B7 APPROVED_IDS 편입 확정

WO-REF01-059-B7-BATCH-BUILD-005 완료. c007/c008/c009/c011/c013 전원 APPROVED_IDS 편입.
BUILD_APPROVED_IDS = frozenset() (B8 대기 상태로 초기화).
