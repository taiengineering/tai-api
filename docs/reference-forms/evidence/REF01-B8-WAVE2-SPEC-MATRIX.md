---
wo: WO-REF01-060-B8-WAVE2-BATCH-001
evidence_type: SPEC_MATRIX
status: GPT_REVIEW_REQUIRED
date: 2026-10-10
schema_version: common-v1
---

# REF01-B8-WAVE2-SPEC-MATRIX

WO-REF01-060-B8-WAVE2-BATCH-001 B8 Wave2 14건 서식 명세 매트릭스.

## 그룹 구성

- **그룹 A — 위험성평가 서식 (EVALUATION, 4건)**: C026 / C027 / C028 / C029
- **그룹 B — 도급·협력·화학 체크리스트 (CHECKLIST, 3건)**: C033 / C041 / C042
- **그룹 C — 대장류 (REGISTER, 3건)**: C037 / C039 / C040
- **그룹 D — 기록류 및 거버넌스 (RECORD, 4건)**: C031 / C043 / C044 / GOV-01

## 서식 명세 일람

| ID | form_type | 제목 | 방향 | 섹션 구성 | 열수 | 총폭(mm) | JSON 파일 |
|----|-----------|------|------|-----------|------|----------|-----------|
| C026 | EVALUATION | 위험성평가표 (3단계 판단법) | portrait | S01(4F)+S02(반복6열)+S03(텍스트) | 6 | 170 | c026_v1.json |
| C027 | CHECKLIST | 위험성평가 체크리스트 | portrait | S01(4F)+S02(반복6열)+S03(텍스트) | 6 | 170 | c027_v1.json |
| C028 | EVALUATION | 위험성평가표 (OPS) | portrait | S01(4F)+S02(반복6열)+S03(텍스트) | 6 | 170 | c028_v1.json |
| C029 | EVALUATION | 위험성평가표 (빈도강도법) | portrait | S01(4F)+S02(반복7열)+S03(텍스트) | 7 | 170 | c029_v1.json |
| C031 | RECORD | 안전보건교육 실시일지 | portrait | S01(5F)+S02(자유 36mm)+S03(반복5열) | 5 | 170 | c031_v1.json |
| C033 | CHECKLIST | 도급업체 안전보건 체크리스트 | portrait | S01(4F)+S02(반복6열)+S03(텍스트) | 6 | 170 | c033_v1.json |
| C037 | REGISTER | 건의·조치사항 대장 | portrait | S01(2F)+S02(반복7열) | 7 | 170 | c037_v1.json |
| C039 | REGISTER | 화학물질 취급 목록 | **landscape** | S01(3F)+S02(반복9열) | 9 | 257 | c039_v1.json |
| C040 | REGISTER | MSDS 수령·교체 이력 대장 | portrait | S01(2F)+S02(반복7열) | 7 | 170 | c040_v1.json |
| C041 | CHECKLIST | 경고표지 부착 점검 기록 | portrait | S01(4F)+S02(반복5열)+S03(텍스트) | 5 | 170 | c041_v1.json |
| C042 | CHECKLIST | 화학물질 저장구역 점검 기록 | portrait | S01(4F)+S02(반복5열)+S03(텍스트) | 5 | 170 | c042_v1.json |
| C043 | RECORD | 화학물질 누출 비상대응 훈련기록 | portrait | S01(4F)+S02(자유 32mm)+S03(자유 48mm)+S04(반복3열) | 3 | 170 | c043_v1.json |
| C044 | RECORD | MSDS 교육·주지 확인 기록 | portrait | S01(3F)+S02(자유 36mm)+S03(반복5열) | 5 | 170 | c044_v1.json |
| GOV-01 | RECORD | 산업안전보건위원회 회의록 | portrait | S01(3F)+S02(자유 24mm)+S03(자유 80mm)+S04(반복5열) | 5 | 170 | gov-01_v1.json |

## 공통 메타 속성

모든 14건 공통 적용:

```json
{
  "wo": "WO-REF01-060-B8-WAVE2-BATCH-001",
  "schema_version": "common-v1",
  "authoring_class": "TAI_ORIGINAL_DRAFT",
  "field_origin": "TAI_PRACTICAL_PROPOSAL",
  "source_match": "NOT_VERIFIED",
  "legal_review_status": "PENDING",
  "rights_status": "RIGHTS_UNVERIFIED",
  "publication_status": "INTERNAL_POC_ONLY",
  "source_document_access": "NOT_CHECKED",
  "design_gate_status": "GPT_REVIEW_REQUIRED",
  "layout_variant": "TAI_EDITABLE_VARIANT",
  "source_layout_exact": false
}
```

## source_evidence 분류

| source_evidence 값 | 해당 형식 |
|---------------------|-----------|
| TAI_PROPOSED | C026 / C027 / C028 / C029 / C033 / C037 / C039 / C040 / C041 / C042 / C031 |
| MIXED | C043 / C044 |
| OFFICIAL_PROCESS_AND_TAI_HYPOTHESIS | GOV-01 |

## BUILD 상태

BUILD_APPROVED_IDS = frozenset() — GPT 설계 검토 완료 전 빌드 차단.
REGISTRY 등록 완료, --dry-run SCHEMA_VALID 확인 완료.
