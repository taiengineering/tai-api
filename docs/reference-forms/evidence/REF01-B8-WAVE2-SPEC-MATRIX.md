---
wo: WO-REF01-060-B8-WAVE2-SPEC-FIX-002
evidence_type: SPEC_MATRIX
status: GPT_REVIEW_REQUIRED
date: 2026-10-10
schema_version: common-v1
---

# REF01-B8-WAVE2-SPEC-MATRIX

WO-REF01-060-B8-WAVE2-BATCH-001 + FIX-002 B8 Wave2 14건 서식 명세 매트릭스.

## 그룹 구성 (FIX-002 정정)

- **그룹 A — 위험성평가 서식 (EVALUATION, 3건)**: C026 / C028 / C029
- **그룹 B — 체크리스트 (CHECKLIST, 4건)**: C027 / C033 / C041 / C042
- **그룹 C — 대장류 (REGISTER, 3건)**: C037 / C039 / C040
- **그룹 D — 기록류 및 거버넌스 (RECORD, 4건)**: C031 / C043 / C044 / GOV-01

## 서식 명세 일람 (FIX-002 반영)

| ID | form_type | 제목 | 방향 | 섹션 구성 | 열수 | 총폭(mm) | FIX-002 | JSON 파일 |
|----|-----------|------|------|-----------|------|----------|---------|-----------|
| C026 | EVALUATION | 위험성평가 기록표(3단계 판단법) | portrait | S01(4F)+S02(반복8열)+S03(텍스트) | 8 | 170 | 재확인 2열 추가 | c026_v1.json |
| C027 | CHECKLIST | 위험성평가 체크리스트 | portrait | S01(4F)+S02(반복6열)+S03(텍스트) | 6 | 170 | — | c027_v1.json |
| C028 | EVALUATION | 위험성평가표(OPS) | portrait | S01(4F)+S02(반복6열)+S03(텍스트) | 6 | 170 | — | c028_v1.json |
| C029 | EVALUATION | 빈도·강도법 위험성평가표 | portrait | S01(4F)+S02(반복7열)+S03(텍스트) | 7 | 170 | 가능성/중대성 병기 | c029_v1.json |
| C031 | RECORD | 안전보건교육 실시일지 | portrait | S01(7F)+S02(자유 36mm)+S03(반복5열) | 5 | 170 | 교육자료·출석증빙 2F 추가 | c031_v1.json |
| C033 | CHECKLIST | 도급업체 안전보건 체크리스트 | portrait | S01(4F)+S02(반복6열)+S03(텍스트) | 6 | 170 | — | c033_v1.json |
| C037 | REGISTER | 종사자 위험개선 건의·조치대장 | **landscape** | S01(2F)+S02(반복8열) | 8 | 257 | 위험요인/건의내용 분리·landscape 전환 | c037_v1.json |
| C039 | REGISTER | 화학물질 취급 목록 | **landscape** | S01(3F)+S02(반복9열) | 9 | 257 | — | c039_v1.json |
| C040 | REGISTER | MSDS 수령·교체 이력 대장 | portrait | S01(2F)+S02(반복7열) | 7 | 170 | — | c040_v1.json |
| C041 | CHECKLIST | 경고표지 부착 점검 기록 | portrait | S01(4F)+S02(반복5열)+S03(텍스트) | 5 | 170 | — | c041_v1.json |
| C042 | CHECKLIST | 화학물질 저장구역 점검 기록 | portrait | S01(4F)+S02(반복5열)+S03(텍스트) | 5 | 170 | — | c042_v1.json |
| C043 | RECORD | 화학물질 누출 비상대응 훈련기록 | portrait | S01(5F)+S02(자유 32mm)+S03(자유 48mm)+S04(반복5열) | 5 | 170 | 참여자F+재확인 2열 추가 | c043_v1.json |
| C044 | RECORD | MSDS 교육·주지 확인 기록 | portrait | S01(4F)+S02(자유 36mm)+S03(반복5열)+S04(자유 24mm) | 5 | 170 | 작업대상F+후속조치 S04 추가 | c044_v1.json |
| GOV-01 | RECORD | 산업안전보건위원회 회의록 | portrait | S01(4F)+S02(자유 24mm)+S03(자유 80mm)+S04(반복6열) | 6 | 170 | 확인자F+서명확인열 추가 | gov-01_v1.json |

## 공통 메타 속성

모든 14건 공통 적용:

```json
{
  "schema_version": "common-v1",
  "authoring_class": "TAI_ORIGINAL_DRAFT",
  "field_origin": "TAI_PRACTICAL_PROPOSAL",
  "source_match": "NOT_VERIFIED",
  "legal_review_status": "PENDING",
  "rights_status": "RIGHTS_UNVERIFIED",
  "publication_status": "INTERNAL_POC_ONLY",
  "design_gate_status": "GPT_REVIEW_REQUIRED",
  "layout_variant": "TAI_EDITABLE_VARIANT",
  "source_layout_exact": false
}
```

## source_evidence 분류 (FIX-002 정정)

| source_evidence 값 | 해당 형식 |
|---------------------|-----------|
| TAI_PROPOSED | C026 / C027 / C028 / C029 / C031 / C033 / C037 (7건) |
| MIXED | C039 / C040 / C041 / C042 / C043 / C044 (6건) |
| OFFICIAL_PROCESS_AND_TAI_HYPOTHESIS | GOV-01 (1건) |

## 필드 커버리지 요약

| ID | 커버리지 상태 | FIX-002 여부 |
|----|-------------|-------------|
| C026 | COVERED | FIX-002 |
| C027 | COVERED | — |
| C028 | COVERED | — |
| C029 | COVERED_BY_COMBINATION | FIX-002 |
| C031 | COVERED | FIX-002 |
| C033 | COVERED | — |
| C037 | COVERED | FIX-002 |
| C039 | COVERED | — |
| C040 | COVERED | — |
| C041 | COVERED | — |
| C042 | COVERED | — |
| C043 | COVERED | FIX-002 |
| C044 | COVERED | FIX-002 |
| GOV-01 | COVERED | FIX-002 |

설명 없는 MISSING = 0

## BUILD 상태

BUILD_APPROVED_IDS = frozenset() — GPT 설계 검토 완료 전 빌드 차단.
FIX-002 후 SCHEMA PASS 14/14, 임시 렌더 28/28 확인 완료.
