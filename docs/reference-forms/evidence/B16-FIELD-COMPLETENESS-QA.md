---
wo: WO-REF01-060-B16-FIELD-COMPLETENESS-001
base_wo: WO-REF01-060-B11-BULK-BUILD-001
date: 2026-10-10
status: FIELD_COMPLETENESS_CORRECTED
publication: NOT_FOR_PUBLICATION
---

# B16 필드 완전성 교정 QA 증거

WO-REF01-060-B16-FIELD-COMPLETENESS-001 교정 결과 증거 문서.
교정 대상: FIELD_COMPLETENESS_HOLD 9종. 교정 후 18 파일 재빌드.

## 1. 교정 대상 및 교정 내용 행렬

| research_id | 교정 사유 | 교정 내용 |
|-------------|----------|----------|
| CHW-03 | 보관구역·로트번호·승인란 누락 | S01 보관구역 추가, S02 로트번호+보관구역 열 추가(landscape 257mm 11col), S03 승인란(257mm) 신설 |
| EQUIP-01 | 지게차 특화 입력항목 누락 | S01 작업구역·운반물 추가(8fields), S02 labeled_grid 신설(이동 동선·충돌·통제·작업자 확인), S03 freeform 삽입 |
| EQUIP-02 | 적재물·중량·하역 방법 누락 | S01 작업시간·적재물명·적재 중량(kg) 추가(8fields), S02 labeled_grid 신설(적재·하역·안전조치·유도자) |
| EQUIP-03 | 장비 기종·이동경로·추락방지 누락 | S01 장비 기종 추가(7fields), S02 labeled_grid 신설(이동경로·바닥전도·추락방지·비상조치) |
| EQUIP-04 | 인양물·작업반경·지반 조건 누락 | S01 인양물명·인양 중량(ton) 추가(8fields), S02 labeled_grid 신설(작업반경·지반·운용신호·통제조치) |
| EQUIP-05 | 작업구역·지반 조건·접근통제 누락 | S02 labeled_grid 신설(작업구역·지반·접근통제·매설물·운행계획·유도자, 3rows) |
| P-01 | 공종·인터페이스 위험·승인란 누락 | S01 작업 예정일·총괄 책임자 추가(5fields), S02 공종+인터페이스 위험 열 추가(8col/170mm), S04 승인란 신설 |
| ENV-04 | 설비 중지시간 기재란 누락 | S02 labeled_grid 신설(중지 시작·중지 종료) |
| P-10 | 사진증거 참조란 누락 | S02 사진번호 열 추가(6col/170mm) |

## 2. SHA256 비교표 (교정 전 → 교정 후)

### JSON

| research_id | 교정 전 JSON SHA256 (64자리) | 교정 후 JSON SHA256 (64자리) |
|-------------|---------------------------|---------------------------|
| CHW-03 | (FIELD_COMPLETENESS_HOLD 이전 버전) | f210e580b8074809bc29c3c8f3aca90d439e81913d26e652235bf12d3d7296c4 |
| EQUIP-01 | (FIELD_COMPLETENESS_HOLD 이전 버전) | ab7afb9f2f6bc0a03a38a90525f5c8c9d818885b01465f49c2d7cb3c9708ec24 |
| EQUIP-02 | (FIELD_COMPLETENESS_HOLD 이전 버전) | 67c875ec71889beaea718cb6c4d003379b21ee3db6c81d39b62380d53b66a19c |
| EQUIP-03 | (FIELD_COMPLETENESS_HOLD 이전 버전) | aaedf3f0c913d702df054a60d2ffe125aa4e8f97e9f4b8a68ac402d83a42fda6 |
| EQUIP-04 | (FIELD_COMPLETENESS_HOLD 이전 버전) | f5772fccaa44cf96ac0411e4cc4af4ba3dfd173ba09df200370b786939ba65ad |
| EQUIP-05 | (FIELD_COMPLETENESS_HOLD 이전 버전) | 902cf0c49efd2ee0e98e00eb30ad4fe809b78c99a6a3c8a6aefa0532d8354a21 |
| P-01 | (FIELD_COMPLETENESS_HOLD 이전 버전) | e47c2bac02bc625d8543093366655b40e6179be1502f6c99f3429d9a38de85fc |
| ENV-04 | (FIELD_COMPLETENESS_HOLD 이전 버전) | 3fe5f8ba6c710a67668e9987f8f36e24e0940f3b2f8054247edaed3077f4eed7 |
| P-10 | (FIELD_COMPLETENESS_HOLD 이전 버전) | 6f68350d9d2ea597197886d6b04be5f534e1817eaae9b1e579e0f9cf68707e57 |

### PDF (교정 전 → 교정 후)

| research_id | 교정 전 PDF SHA256 | 교정 후 PDF SHA256 |
|-------------|------------------|------------------|
| CHW-03 | 885e0e7ecac55cc9ba9a672125de07d59917d7f92ab125745d1a375d2a552f3a | 2fe79aed9b4fd508828bf7c1a2e6fc633f4242b373eb03d67aba126f4b7b3552 |
| EQUIP-01 | 9900f6aa528ea9788ee321f1e7ab72d35761acc46d9bda78ec65b3731b6cd5d3 | 3263a66bde0ae0188c01ce92ed2bf0c26a997b619aeea96c23ff6e61046aaf37 |
| EQUIP-02 | 031178e02b65db1f842490cb5bc0cbe6437349a0dbb9c66072aad574d5ae220f | 0ef669b5631da5f0e2a110dd435de52790098f6cdb0aa3ceb8496e30ab5f5c50 |
| EQUIP-03 | 2cacded75d15c1141846066c7e4d3c31413e8132d0e6a1816165c85fa3433985 | 2dfbf92bdf1414e7e02edb34b926219afc254162b7b53f7ee02d9e55b3aa6877 |
| EQUIP-04 | 56fc788c319b4a2f3cd70e1d2ec650d9994ed7306a9473271ed8b28dc2b8f2bc | 954231d7442a4d5a415afc745c89ee4d93935bc3a6f839dd5897961790f76bdc |
| EQUIP-05 | 5f810e7c70c740be30c4feaac06cc87959aa260f024c8da6c218a094e2331d5e | 93936411caffea6f69220fc60d1e0115d08fc5d260980453c0c9cf77ddbc1450 |
| P-01 | 6d3bd85c525b95b3fd08d0b6aa0509c513eeeb6d685e361b9d449b1d0f9bfef1 | 6a9c78833cad69e611563f052c50ec99e4c17165daf0f48cfadd2f41e51743e8 |
| ENV-04 | 402b855e36c7e72432fbbd7989c192be08bd7042a38c5916b79996c74b313bc2 | 83b015496843864d217f4b72ddddb44742344947ce44123b69e7f30cbe741f9d |
| P-10 | 9fb3b49b483700b5fedaeac1cdb39f56a5d1fe698e6f734e23cac57fc07f690e | 3ee2e3c8d149912d97642a7525b3ce75fcd49f501881573d6595803404663409 |

### DOCX (교정 전 → 교정 후)

| research_id | 교정 전 DOCX SHA256 | 교정 후 DOCX SHA256 |
|-------------|-------------------|-------------------|
| CHW-03 | 398df4a43130f61882ef3a8da58ba60c48bba5ce1735bf1a8029a2892a165786 | a340159b732905bd67c5067b56ee61105afc743c51654f8cc1a30ad12c46daf8 |
| EQUIP-01 | 1526093bb75efb3a4771b307e919b773965e197e0dc0205367039bd9fb8aae08 | ef4283673d58558ca2ef19f38f0c534b233a106c5613a273c0a785f9ea1314dc |
| EQUIP-02 | a3ffdf4c3a080d3924b7f79fe94be289934ab760c60e47eae707323089e1db48 | f53ca3d95bd59a405f0663095cc6e9b65b1aaec570cc677ad0bbb8e31c6716c5 |
| EQUIP-03 | 50b50ae1f225f90111a16953ae21382f4d09351671ad6b4452e2055646e5db81 | 8d1cc7f4c33fb4680e1ae43cc3ba44c47d25e035004e5d57cf6d70f474b525b7 |
| EQUIP-04 | ee11bcc8816a5dc34797faf6e37ddfa4750ddb40fe42b133b8b60062fd5eec51 | c377e50a336f2ee0f83ac28452c3a88226b91c8622a7eeceedbbc10c9a40ea8c |
| EQUIP-05 | b7082f993fda33009f6b9db5d4f046bc73d5fd5874a0d212abb8e29beb488d0c | d8f72ee86c29c123ca06bf268f89c7456d8320fab015230e95496e68656ba8d7 |
| P-01 | 8b41d0be9a4cbc72ff096d4ddedbbe74f2d75274e1c8671792d5093dd35b56ff | 582df94a551682fe78adf98e8540b7e881da5a098e189652fc7b91b492e94a5b |
| ENV-04 | 90176011cd3572009d0ebc06aad373693fc29fa3331699ba31cddd7d5d0c15f0 | 837f96100ecce160693b2a409b904c83e87b2b7c94f59ba53be028de548d67b2 |
| P-10 | d29adb9514056af72addfbec57895af98a2f60b51e985ed642b72b9db843d9b3 | 3015f6d00160d985a2514727d404f91e6a002b1ddafdf82b2529b44c39d9b4cc |

## 3. 레이아웃 검증 결과

| research_id | 페이지 방향 | 너비(mm) | 열 합계(mm) | 페이지 수 | 결과 |
|-------------|-----------|---------|-----------|---------|------|
| CHW-03 | landscape | 257 | 257 (11col) | 1 | PASS |
| EQUIP-01 | portrait | 170 | 170 (4col) | 1 | PASS |
| EQUIP-02 | portrait | 170 | 170 (4col) | 1 | PASS |
| EQUIP-03 | portrait | 170 | 170 (4col) | 1 | PASS |
| EQUIP-04 | portrait | 170 | 170 (4col) | 1 | PASS |
| EQUIP-05 | portrait | 170 | 170 (4col) | 1 | PASS |
| P-01 | portrait | 170 | 170 (8col) | 1 | PASS |
| ENV-04 | portrait | 170 | 170 (5col) | 1 | PASS |
| P-10 | portrait | 170 | 170 (6col) | 1 | PASS |

## 4. 회귀 테스트 결과

| 항목 | 결과 |
|------|------|
| 총 테스트 | 385 |
| PASS | 385 |
| FAIL | 0 |
| 기타 출력 파일 변경 | UNCHANGED 274/274 |
| DB 변경 | 0 |

## 5. 격리 보관 확인

교정 전 출력물 18건(PDF 9 + DOCX 9) 격리 위치:
`docs/reference-forms/evidence/b16-field-fix-20261010/`

ARCHIVE-MANIFEST.md에 교정 전 SHA256 전체 기록.
