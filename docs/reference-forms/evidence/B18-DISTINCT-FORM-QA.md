---
wo: WO-REF01-060-B18-DISTINCT-FORM-BUILD-001
date: 2026-10-11
status: GATE_A_E_PASS_B18
correction: WO-REF01-060-B18-REF-C025-FIELD-CORRECTION-003
correction_date: 2026-10-11
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

DB proposed_fields 7개(EXISTING_RESEARCH_PROPOSAL / FIELDS_UNVERIFIED)와 TAI 세부 설계(TAI_PRACTICAL_PROPOSAL)를 구분한다.
CORRECTION-003: 기존 "사전 위험확인" 1개 섹션을 S03/S04/S05(3개), "격리·방호" 1개 섹션을 S06/S07(2개)로 분리. 각 항목이 PDF/DOCX에 독립 label로 표시되도록 가시화. 섹션 수: 6 → 9. 섹션 ID 재번호: S05 approval→S08, S06 labeled_grid→S09.
CORRECTION-004: S04·S05·S07 출처 표기 정정. DB 직접 제안 필드(7개)와 TAI 세부화 항목을 구분.

**DB 조사 직접 제안 필드 7개 (EXISTING_RESEARCH_PROPOSAL / FIELDS_UNVERIFIED)**

| DB 조사 제안 필드 | 출처 | JSON 구현 위치 | 세부 입력항목 | 세부 출처 |
|--------------|------|-------------|------------|---------|
| 작업식별 | EXISTING_RESEARCH_PROPOSAL / FIELDS_UNVERIFIED | S01 basic_info | 작업번호, 작업명 | TAI_PRACTICAL_PROPOSAL |
| 위험작업유형 | EXISTING_RESEARCH_PROPOSAL / FIELDS_UNVERIFIED | S02 labeled_grid | 위험작업 유형 | TAI_PRACTICAL_PROPOSAL |
| 장소/시간 | EXISTING_RESEARCH_PROPOSAL / FIELDS_UNVERIFIED | S01 basic_info | 작업장소, 작업 예정일시, 허가 요청기간 | TAI_PRACTICAL_PROPOSAL |
| 사전 위험확인 | EXISTING_RESEARCH_PROPOSAL / FIELDS_UNVERIFIED | S03 freeform_area | 사전 위험확인 결과(label) | TAI_PRACTICAL_PROPOSAL |
| 격리·방호 | EXISTING_RESEARCH_PROPOSAL / FIELDS_UNVERIFIED | S06 freeform_area | 격리·방호 실시 내역(label) | TAI_PRACTICAL_PROPOSAL |
| 승인 | EXISTING_RESEARCH_PROPOSAL / FIELDS_UNVERIFIED | S08 approval | 신청자, 검토자, 허가자 | TAI_PRACTICAL_PROPOSAL |
| 종료확인 | EXISTING_RESEARCH_PROPOSAL / FIELDS_UNVERIFIED | S09 labeled_grid | 실제 작업 종료일시, 종료 확인자, 종료 시 조치·현장 상태, 종료 확인 서명 | TAI_PRACTICAL_PROPOSAL |

**TAI 세부화 항목 (TAI_PRACTICAL_PROPOSAL) — DB 제안 필드를 TAI가 세분화한 입력란**

| 섹션 | 입력항목 | 상위 DB 제안 필드 | 출처 |
|------|---------|----------------|------|
| S04 freeform_area | 주요 위험요인 | 사전 위험확인 세부화 | TAI_PRACTICAL_PROPOSAL |
| S05 freeform_area | 추가 조치 | 사전 위험확인 세부화 | TAI_PRACTICAL_PROPOSAL |
| S07 freeform_area | 미완료 조치 및 특이사항 | 격리·방호 세부화 | TAI_PRACTICAL_PROPOSAL |

**TAI 독자 추가 항목 (REF-C012 구조 참조)**

| 섹션 | 입력항목 | 출처 |
|------|---------|------|
| S01 basic_info | 사업장명, 신청부서·업체, 신청자 | TAI_PRACTICAL_PROPOSAL (REF-C012 구조 참조) |
| S02 labeled_grid | 작업 책임자, 작업 내용, 작업 참여 인원 | TAI_PRACTICAL_PROPOSAL |

조사 제안 7개는 법정 필수항목 또는 공식 서식 검증 완료를 의미하지 않는다(FIELDS_UNVERIFIED 유지).

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
| scripts/c025_v1.json | dea4c5cc5801a140a14dfbbe733deef48df5ddae8f5b020632cf064f3d08f828 (CORRECTION-003) |
| output/TAI-FORM-C025-blank.pdf | 18bbdad00658f267af15b1d9255457bfdf24d192aa1fe11bcdbf9fbdb5842846 (CORRECTION-003) |
| output/TAI-FORM-C025-blank.docx | b90dba810675555cba370ee618a18b17f2bae5febf1bfea56ce13f1d5668c1d6 (CORRECTION-003) |

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
