---
wo: WO-REF01-060-B18-DISTINCT-FORM-BUILD-001
date: 2026-10-11
status: GATE_A_E_PASS_B18
publication: NOT_FOR_PUBLICATION
---

# B18 차별 서식 2종 제작 QA 증거

WO-REF01-060-B18-DISTINCT-FORM-BUILD-001 결과 증거 문서.
대상: PRA-22-04, REF-C025 (SHARED_TEMPLATE_DISTINCT).
신규 JSON 2 / PDF 2 / DOCX 2. 기존 서식 수정 없음.

---

## 1. B17 참조 관계

| 신규 서식 | B17 판정 | 참조 기존 서식 | 차이점 |
|---------|---------|--------------|--------|
| PRA-22-04 | SHARED_TEMPLATE_DISTINCT | CHW-04 | CHW-04에 approval 없음. 재고조정 승인 구조 독립 구현. |
| REF-C025 | SHARED_TEMPLATE_DISTINCT | REF-C012 | 사전위험확인·격리방호·종료확인 독립 구현. |

---

## 2. 필드별 출처

### PRA-22-04 필드 출처

| 섹션 | 입력항목 | 출처 |
|------|---------|------|
| S01 basic_info | 사업장명, 신청일, 신청자 | TAI_PRACTICAL_PROPOSAL |
| S01 basic_info | 참조 격리기록번호(CHW-04) | TAI_PRACTICAL_PROPOSAL — 수기 참조 필드 |
| S01 basic_info | 재고조정 대상 물질명, 용기·로트 식별 | TAI_PRACTICAL_PROPOSAL |
| S02 labeled_grid | 발생일시, 파손·누출 내용, 격리장소, 임시 위험통제 조치 | TAI_PRACTICAL_PROPOSAL |
| S03 labeled_grid | 재고조정 사유, 수량 단위, 조정 전·후·대상 수량, 조정 요청 내용 | TAI_PRACTICAL_PROPOSAL |
| S04 freeform | 재고조정 검토 의견 | TAI_PRACTICAL_PROPOSAL |
| S05 labeled_grid | 승인 여부, 승인 일시 | TAI_PRACTICAL_PROPOSAL |
| S06 approval | 신청자, 검토자, 승인자 | TAI_PRACTICAL_PROPOSAL |

DB proposed_fields = [] (빈 배열). 모든 항목 TAI 독자 설계.

### REF-C025 필드 출처

| 섹션 | 입력항목 | 출처 |
|------|---------|------|
| S01 basic_info | 사업장명, 작업번호, 작업명, 신청부서·업체 | REF-C012 구조 참조 + TAI_PRACTICAL_PROPOSAL |
| S01 basic_info | 작업장소, 작업 예정일시, 허가 요청기간, 신청자 | REF-C012 구조 참조 + TAI_PRACTICAL_PROPOSAL |
| S02 labeled_grid | 위험작업 유형, 작업 책임자, 작업 내용, 작업 참여 인원 | TAI_PRACTICAL_PROPOSAL |
| S03 freeform | 사전 위험확인 결과·주요 위험요인·추가 조치 | TAI_PRACTICAL_PROPOSAL (B17 MISSING 항목 구현) |
| S04 freeform | 격리·방호 실시 내역·미완료 조치 | TAI_PRACTICAL_PROPOSAL (B17 MISSING 항목 구현) |
| S05 approval | 신청자, 검토자, 허가자 | REF-C012 신청/허가 구조 참조 + TAI_PRACTICAL_PROPOSAL |
| S06 labeled_grid | 실제 작업 종료일시, 종료 확인자, 종료 시 조치·현장 상태, 종료 확인 서명 | TAI_PRACTICAL_PROPOSAL (B17 MISSING 항목 구현) |

---

## 3. 공통 엔진 사용 증거

두 서식 모두 기존 batch_build.py 등록 방식으로 common_v1_engine 직접 사용.

```
batch_build.py:
  REGISTRY["pra-22-04"] = _reg("pra-22-04")  ← common_v1_engine 호출
  REGISTRY["c025"]      = _reg("c025")        ← common_v1_engine 호출
  BUILD_APPROVED_IDS에 "pra-22-04", "c025" 추가

신규 전용 엔진 생성: 없음
gen_c012_pdf.py 수정: 없음
common_v1_engine.py 수정: 없음
```

---

## 4. 신규 파일 SHA256

| 파일 | SHA256 (64자리) |
|------|---------------|
| scripts/pra-22-04_v1.json | 64dbc7be6bf87a756c8a4818b004677bd4e82bb313462eae97b9dcb2802f6d30 |
| output/TAI-FORM-PRA-22-04-blank.pdf | 44f38c688b59a5ed9e23dad8382976bb51030a8b55a836a4e96e93760ed44fda |
| output/TAI-FORM-PRA-22-04-blank.docx | c2f7797962a69bb25b2742b0992cfced736dd1f76f647120dd3f70d04bda9af4 |
| scripts/c025_v1.json | 34772c200dc399304eeaf5cb33d5e7b41af55be978992607c716b0ca5bf6badf |
| output/TAI-FORM-C025-blank.pdf | c25cc1b018c46f3c111720b2d1ae586247e505ba9ba3189fe4c0b8992e0f8188 |
| output/TAI-FORM-C025-blank.docx | 99030afac58427105bebdedae92d1cdf1400648cad6b432bc14a49e21f07646c |

---

## 5. PDF 페이지 수·방향

| 서식 | 방향 | 페이지 수 |
|------|------|---------|
| PRA-22-04 | portrait (A4 세로) | 1 |
| REF-C025 | portrait (A4 세로) | 1 |

---

## 6. DOCX 구조 검증

| 항목 | PRA-22-04 | REF-C025 |
|------|-----------|----------|
| DOCX 패키지 정상 | PASS | PASS |
| 문서 구조 | PASS | PASS |
| PDF 동일 필드 구성 | PASS | PASS |
| WORD_INTERACTIVE_QA | UNVERIFIED | UNVERIFIED |

Word 실제 입력·저장·재열기 검증은 수행하지 않았음.

---

## 7. 기존 292개 출력물 불변 증거

```
git diff --name-only HEAD -- docs/reference-forms/output/ | grep -v "PRA-22-04|C025" → 0건
output/ 총계: 296 (292 + 4 신규)
```

---

## 8. CHW-04 및 REF-C012 불변 증거

| 파일 | B18 이전 SHA256 | B18 이후 SHA256 | 결과 |
|------|----------------|----------------|------|
| scripts/chw-04_v1.json | 18cbd75863e3d6b4f5c20267647126a1c4ae2090e13defe0143cf5505bdbe774 | 18cbd75863e3d6b4f5c20267647126a1c4ae2090e13defe0143cf5505bdbe774 | UNCHANGED |
| output/TAI-FORM-CHW-04-blank.pdf | d04fba09f776df0e240a35c2dada79f481394c940869f38104c5861813c6b61d | d04fba09f776df0e240a35c2dada79f481394c940869f38104c5861813c6b61d | UNCHANGED |
| output/TAI-FORM-CHW-04-blank.docx | 856ee85536e1ca1590643d3e38ff4766da55fb6214ffd6875836e2691b8e1a86 | 856ee85536e1ca1590643d3e38ff4766da55fb6214ffd6875836e2691b8e1a86 | UNCHANGED |
| scripts/c012_fields.json | 25f5514bed0d8db968fc99b43915dae93e2a0db755edcbebf4adbdececce39cd | 25f5514bed0d8db968fc99b43915dae93e2a0db755edcbebf4adbdececce39cd | UNCHANGED |
| output/TAI-FORM-C012-blank.pdf | ebb4b915708721d2f5e16993d4045cd87b0905fee38da4ad9dafe915eb8c68c3 | ebb4b915708721d2f5e16993d4045cd87b0905fee38da4ad9dafe915eb8c68c3 | UNCHANGED |
| output/TAI-FORM-C012-blank.docx | 2e6b5d9eca4d6dab51f8d50ff208972cedbe4842a68156b7548927db09970e53 | 2e6b5d9eca4d6dab51f8d50ff208972cedbe4842a68156b7548927db09970e53 | UNCHANGED |

---

## 9. 회귀 테스트 결과

```
pytest test_common_engine.py
  385 passed / 0 failed / 5 warnings
  실행 시간: 30.22s
```

---

## 10. 법률·권리·공개 HOLD 유지

| 항목 | PRA-22-04 | REF-C025 |
|------|-----------|----------|
| legal_review_status | PENDING | PENDING |
| rights_status | RIGHTS_UNVERIFIED | RIGHTS_UNVERIFIED |
| publication_status | INTERNAL_POC_ONLY | INTERNAL_POC_ONLY |
| field_required_freeze | LEGAL_REVIEW_PENDING | LEGAL_REVIEW_PENDING |
| design_gate_status | GPT_REVIEW_REQUIRED | GPT_REVIEW_REQUIRED |

법정 필수항목 적합성, 실제 허가·승인 효력, 재고 반영 기능은 이 서식에 구현되지 않았으며 주장하지 않는다.
