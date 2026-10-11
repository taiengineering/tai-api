---
wo: WO-REF01-060-B8-11FORM-LEGAL-RIGHTS-EVIDENCE-010
doc_type: AUTHORING_PROVENANCE
date: 2026-10-10
base_head: f32702d2950935c5312bbbd593acc69b327c0f05
---

# B8 11종 — 작성 이력 증거

조사 대상: C026, C027, C028, C037, GOV-01, C039, C040, C041, C042, C043, C044

---

## 1. 공통 이력 요약

| 서식 | 최초 커밋 | 최초 WO | 최종 수정 커밋 | 최종 WO | authoring_class | source_evidence |
|------|---------|--------|------------|--------|---------------|----------------|
| C026 | 3c8f9bf6 | WO-REF01-060-B8-WAVE2-BATCH-001 | 9259e0b8 | WO-REF01-060-B8-WAVE2-BUILD-003 | TAI_ORIGINAL_DRAFT | TAI_PROPOSED |
| C027 | 3c8f9bf6 | WO-REF01-060-B8-WAVE2-BATCH-001 | 9259e0b8 | WO-REF01-060-B8-WAVE2-BUILD-003 | TAI_ORIGINAL_DRAFT | TAI_PROPOSED |
| C028 | 3c8f9bf6 | WO-REF01-060-B8-WAVE2-BATCH-001 | 9259e0b8 | WO-REF01-060-B8-WAVE2-BUILD-003 | TAI_ORIGINAL_DRAFT | TAI_PROPOSED |
| C037 | 3c8f9bf6 | WO-REF01-060-B8-WAVE2-BATCH-001 | 9259e0b8 | WO-REF01-060-B8-WAVE2-BUILD-003 | TAI_ORIGINAL_DRAFT | TAI_PROPOSED |
| GOV-01 | 3c8f9bf6 | WO-REF01-060-B8-WAVE2-BATCH-001 | 9259e0b8 | WO-REF01-060-B8-WAVE2-BUILD-003 | TAI_ORIGINAL_DRAFT | OFFICIAL_PROCESS_AND_TAI_HYPOTHESIS |
| C039 | 3c8f9bf6 | WO-REF01-060-B8-WAVE2-BATCH-001 | 9259e0b8 | WO-REF01-060-B8-WAVE2-BUILD-003 | TAI_ORIGINAL_DRAFT | MIXED |
| C040 | 3c8f9bf6 | WO-REF01-060-B8-WAVE2-BATCH-001 | 9259e0b8 | WO-REF01-060-B8-WAVE2-BUILD-003 | TAI_ORIGINAL_DRAFT | MIXED |
| C041 | 3c8f9bf6 | WO-REF01-060-B8-WAVE2-BATCH-001 | 9259e0b8 | WO-REF01-060-B8-WAVE2-BUILD-003 | TAI_ORIGINAL_DRAFT | MIXED |
| C042 | 3c8f9bf6 | WO-REF01-060-B8-WAVE2-BATCH-001 | 9259e0b8 | WO-REF01-060-B8-WAVE2-BUILD-003 | TAI_ORIGINAL_DRAFT | MIXED |
| C043 | 3c8f9bf6 | WO-REF01-060-B8-WAVE2-BATCH-001 | e85c4187 | WO-REF01-060-B8-WAVE2-VISUAL-REPAIR-005-PHASE2-CANONICAL-006 | TAI_ORIGINAL_DRAFT | MIXED |
| C044 | 3c8f9bf6 | WO-REF01-060-B8-WAVE2-BATCH-001 | e85c4187 | WO-REF01-060-B8-WAVE2-VISUAL-REPAIR-005-PHASE2-CANONICAL-006 | TAI_ORIGINAL_DRAFT | MIXED |

최초 커밋 공통 사항:
- 커밋: `3c8f9bf68880e742506bd452722edd59db89399e`
- 일시: 2026-10-10 04:22:43 +0900
- 메시지: `feat(ref): WO-REF01-060-B8-WAVE2-BATCH-001 — B8 Wave2 14건 스펙 등록`
- 내용: 14종 JSON 명세 일괄 신규 생성. `TAI_ORIGINAL_DRAFT / GPT_REVIEW_REQUIRED` 표시.

---

## 2. 서식별 설계 근거

### C026 — 위험성평가 기록표(3단계 판단법)

**최초 설계 의도**: DB `proposed_fields` 기반. 3단계 판단법: 위험수준을 상·중·하 등으로 직접 기재하는 방식.

**필드 구성 (확인)**:
- S01: 사업장명, 부서/공정명, 평가일, 작성자 (4필드)
- S02: 작업·공정 / 위험요인 / 현재 조치사항 / 위험수준(입력) / 개선 대책 / 담당자/기한 / 개선 후 확인 결과 / 재확인일/확인자 (8열)
- S03: 위험수준 입력 안내 문구 (TAI 작성)

**설계 노트**: "위험수준 자동 판정 없음 — 사용자 직접 기재. 개선 후 재확인 필드 추가(FIX-002)."

**외부 참조 관계**: 3단계 판단법은 KOSHA FAQ에서 언급된 공지 개념. TAI가 이 방법론명 및 통용 평가 필드를 사용. 특정 외부 서식의 표현·레이아웃 직접 복제 정황 없음 (미검사 상태).

### C027 — 체크리스트형 위험성평가표

**최초 설계 의도**: DB `proposed_fields` 기반. 체크리스트 방식: 점검항목별 결과(적합/부적합) 텍스트 입력.

**필드 구성 (확인)**:
- S01: 사업장명, 작업단위/공정, 평가일, 평가자 (4필드)
- S02: 번호 / 점검항목 / 결과(입력) / 부적합 내용 / 개선 대책 / 확인일 (6열)
- S03: 결과 입력 기준 안내 (TAI 작성)

**설계 노트**: "결과란은 일반 텍스트 입력(클릭형 체크박스 미지원). 점검기준이 법정 요구사항임을 주장하지 않음."

**외부 참조 관계**: 체크리스트형 위험성평가는 공지 개념. 점검항목은 사용자 직접 작성. 특정 외부 서식 복제 정황 없음 (미검사 상태).

### C028 — 핵심요인 분석법(OPS) 위험성평가표

**최초 설계 의도**: DB `proposed_fields` 기반. "핵심요인 분석법" 명칭 사용.

**필드 구성 (확인)**:
- S01: 사업장명, 공정/작업명, 평가일, 평가자 (4필드)
- S02: 작업단위 / 사고유형 / 위험요인 / 기존 조치사항 / 추가 대책 / 책임자/기한 (6열)
- S03: OPS 평가 안내 (TAI 작성)

**설계 노트**: "핵심요인 분석법(OPS) 명칭은 TAI_PRACTICAL_PROPOSAL 수준 — 법정 평가방법 주장 금지."

**OPS 명칭 출처**: OBJ-REF-01-OFFICIAL-SOURCE-DISCOVERY-02.md S4 KOSHA FAQ 스니펫에서 "핵심요인 기법"(key-factor method)이 언급됨. "OPS" 구체 약어·방법론 소유권 확인 불가 (미검사). 특정 유료 저작물 복제 정황 없음.

### C037 — 종사자 위험개선 건의·조치대장

**최초 설계 의도**: DB `proposed_fields` 기반. 건의 접수→검토→조치→확인 흐름.

**필드 구성 (확인)**:
- S01: 사업장명, 관리 부서 (2필드)
- S02: 접수일 / 건의자 / 위험요인 / 건의 내용 / 검토 결과 / 회신 내용 / 실행 상태(입력) / 확인일 (8열, landscape)

**설계 노트**: "FIX-002: 위험요인과 건의내용 분리, 가독성 확보를 위해 landscape 적용."

**외부 참조 관계**: OBJ-REF-01-GOVERNANCE-WORKFLOW-15.md S4 KOSHA e-catalog에서 "종사자 의견 청취 및 개선 이행" 업무 언급. 특정 건의대장 양식 법정 별지 여부 미확인. 외부 표현 복제 정황 없음 (미검사).

### GOV-01 — 산업안전보건위원회 회의록

**최초 설계 의도**: `source_evidence = OFFICIAL_PROCESS_AND_TAI_HYPOTHESIS`. 법 제24조 절차 기반; 법정 별지 없음.

**필드 구성 (확인)**:
- S01: 회의 일시, 장소, 사회자, 회의록 확인자 (4필드)
- S02: 참석자 및 구성 (freeform)
- S03: 안건 및 논의·의결사항 (freeform)
- S04: 안건번호 / 의결사항 / 이행담당자 / 기한 / 이행확인일 / 서명/확인 (6열)

**설계 노트**: "FIX-002: 회의록 확인자·서명확인란 추가. 전자서명이나 법정 의결 적법성을 보장하지 않음."

**외부 참조 관계**: 법 제24조 절차를 기반으로 TAI가 독자 열 구조 설계. 법 제24조는 특정 양식을 지정하지 않음. OBJ-15 S1에서 회의록 작성·보존 의무 언급. WO-008B 분류: ACTIVITY_DUTY_CONFIRMED_CONDITIONAL (2차 증거, 조건부). 외부 회의록 양식 직접 복제 정황 없음 (미검사).

### C039 — 사업장 화학물질 취급목록 관리대장

**최초 설계 의도**: `source_evidence = MIXED`. OBJ-REF-01-CHEM-FIRE-OFFICIAL-EVIDENCE-10.md CHEM-01로 연구 제안.

**필드 구성 (확인)**:
- S01: 사업장명, 작성일, 작성자 (3필드)
- S02: 물질명 / 제품명 / 공급자 / CAS번호(확인 시) / 취급 공정 / 사용량 / 보관 장소 / MSDS 연결(입력) / 검토일 (9열, landscape)

**OBJ-10 CHEM-01 대응**: OBJ-10에서 제안한 CHEM-01 필드와 C039 실제 JSON 필드가 일치. TAI 연구 설계 문서에서 직접 도출.

**외부 참조 관계**: 취급목록의 물질명·CAS번호 등은 사실 정보 필드. 특정 외부 서식 표현 복제 정황 없음.

### C040 — 제품별 MSDS 수령·개정 이력대장

**최초 설계 의도**: `source_evidence = MIXED`. OBJ-10 CHEM-02로 연구 제안.

**필드 구성 (확인)**:
- S01: 사업장명, 관리 부서 (2필드)
- S02: 공급사 / 제품명 / 수령일 / 개정일 / 문서 버전 / 배포 상태(입력) / 재검토 예정일 (7열)

**OBJ-10 CHEM-02 대응**: 필드 일치 확인.

**중요 구분**: 이 서식은 MSDS 수령·이력 관리 대장이며, MSDS 원본 문서 자체가 아님. KOSHA MSDS 시스템의 MSDS 콘텐츠를 복제하지 않음.

### C041 — 화학물질 경고표지 확인 점검표

**최초 설계 의도**: `source_evidence = MIXED`. OBJ-10 CHEM-03으로 연구 제안.

**필드 구성 (확인)**:
- S01: 사업장명, 점검 구역, 점검일, 점검자 (4필드)
- S02: 용기·설비/위치 / 라벨 유무(입력) / 식별성(입력) / 발견 사항 / 시정 완료일 (5열)
- S03: 입력 안내 (TAI 작성)

**OBJ-10 CHEM-03 대응**: 필드 일치 확인.

**중요 구분**: 이 서식은 경고표지의 부착 여부·식별성을 확인하는 점검표이며, GHS 경고표지 이미지·픽토그램 자체를 포함하지 않음.

### C042 — 화학물질 저장구역 점검표

**최초 설계 의도**: `source_evidence = MIXED`. OBJ-10 CHEM-04로 연구 제안.

**필드 구성 (확인)**:
- S01: 사업장명, 저장 구역, 점검일, 점검자 (4필드)
- S02: 저장구역 / 물질군 / 보관조건 확인(입력) / 혼재·누출·환기 확인(입력) / 조치 내용 (5열)
- S03: 입력 안내 (TAI 작성)

**OBJ-10 CHEM-04 대응**: 필드 일치 확인.

**외부 참조 관계**: 보관조건·혼재·환기 확인은 실무 점검 개념. 특정 외부 서식 복제 정황 없음 (미검사).

### C043 — 화학물질 누출 비상대응 훈련기록

**최초 설계 의도**: `source_evidence = MIXED`. OBJ-10 CHEM-05로 연구 제안.

**수정 이력**: BATCH-001(3c8f9bf6) → VISUAL-REPAIR-005-PHASE2-CANONICAL-006(e85c4187) 교체.

**필드 구성 (확인)**:
- S01: 훈련명, 훈련 일시, 장소, 담당자, 참여/명단참조 (5필드)
- S02: 훈련 시나리오 개요 (freeform)
- S03: 대응단계별 실시 내용 (freeform)
- S04: 문제점 / 개선책 / 담당자 / 재확인일 / 재확인 결과 (5열)

**OBJ-10 CHEM-05 대응**: 필드 일치 확인.

**외부 참조 관계**: 비상대응 훈련 기록 구조는 TAI 독자 설계. 특정 외부 서식 복제 정황 없음 (미검사).

### C044 — MSDS 교육·주지 확인 기록

**최초 설계 의도**: `source_evidence = MIXED`. OBJ-10 CHEM-06으로 연구 제안.

**수정 이력**: BATCH-001(3c8f9bf6) → VISUAL-REPAIR-005-PHASE2-CANONICAL-006(e85c4187) 교체.

**필드 구성 (확인)**:
- S01: 물질명/제품명, 교육·주지 일시, 교육자(담당자), 대상·적용 작업 (4필드)
- S02: 주지 핵심 위험정보 요약 (freeform)
- S03: 번호 / 성명 / 소속/부서 / 직책 / 확인(서명) (5열)
- S04: 후속조치 내용 및 확인 (freeform)

**OBJ-10 CHEM-06 대응**: 필드 일치 확인.

**중요 구분**: 이 서식은 MSDS 교육 이수 기록지이며, MSDS 원본 콘텐츠를 포함하지 않음.

---

## 3. 설계 추적 경로 요약

| 서식 | 설계 근거 문서 | 외부 원본 참조 | 복제 정황 |
|------|------------|------------|---------|
| C026 | DB proposed_fields | KOSHA FAQ (공지 개념) | 미발견 (미검사) |
| C027 | DB proposed_fields | KOSHA FAQ (공지 개념) | 미발견 (미검사) |
| C028 | DB proposed_fields | KOSHA FAQ 키워드 | 미발견 (미검사) |
| C037 | DB proposed_fields | KOSHA e-catalog 업무 흐름 | 미발견 (미검사) |
| GOV-01 | OBJ-15 OFFICIAL_PROCESS_AND_TAI_HYPOTHESIS | 산업안전보건법 제24조 절차 | 미발견 (미검사) |
| C039 | OBJ-10 CHEM-01 | MIXED (출처 미확인) | 미발견 (미검사) |
| C040 | OBJ-10 CHEM-02 | MIXED (출처 미확인) | 미발견 (미검사) |
| C041 | OBJ-10 CHEM-03 | MIXED (출처 미확인) | 미발견 (미검사) |
| C042 | OBJ-10 CHEM-04 | MIXED (출처 미확인) | 미발견 (미검사) |
| C043 | OBJ-10 CHEM-05 | MIXED (출처 미확인) | 미발견 (미검사) |
| C044 | OBJ-10 CHEM-06 | MIXED (출처 미확인) | 미발견 (미검사) |

---

## 4. 조사 한계

1. **TAI_ORIGINAL_DRAFT 자기 선언 ≠ 법적 독립 창작 증명**: Git 이력으로 최초 TAI 생성 사실 확인. 그러나 이것이 제3자 저작물 불사용을 법적으로 입증하지 않음.
2. **DB proposed_fields 원본 미조회**: 각 서식의 `proposed_fields` DB 레코드를 직접 조회하지 않음. `field_origin: TAI_PRACTICAL_PROPOSAL` 자기 기록만 확인.
3. **source_evidence = MIXED 원인 불명**: MIXED 표시의 구체적 참조 대상이 JSON에 명시되지 않음. OBJ-10 CHEM 계획서와의 대응만 확인.
4. **OPS 명칭 소유권 미확인**: "OPS" 약어의 출처·소유권 정보 없음.
5. **외부 서식 실물 비교 없음**: 유사 목적의 공공·민간 서식과 실제 필드 비교 미실시.

```
AUTHORING_HISTORY_STATUS = EVIDENCED (11/11 git 이력 확인)
FIRST_COMMIT_CONFIRMED   = 3c8f9bf6 (11/11)
EXTERNAL_COPY_FOUND      = 0 (조사 범위 내)
EXTERNAL_COPY_STATUS     = NO_THIRD_PARTY_COPY_FOUND_IN_REVIEWED_EVIDENCE (11/11)
```
