---
title: G1 복합 숫자·수량 필드 DB 변경안
wo: WO-DOC260-OBJ10-G1-COMPOUND-INPUT-001
status: PROPOSAL — Owner 승인 전 실행 금지
created: 2026-10-31
---

## 개요

7개 필드의 `runtime_field.input_type`을 `number`에서 `text`로 변경한다.

- `field_candidate.field_type = TEXT` 원본 확인 완료
- 현재 `input_type = number`는 오분류
- `number` 경로에서는 복합 정보(공사명+금액, 위험물 종류+수량 등)를 저장할 수 없음

## 변경 대상 (7건)

| field_key | 문서 | 의미 | 변경 전 | 변경 후 |
|-----------|------|------|--------|--------|
| `asbestos_area_quantity` | DOC-BLD-038 | 석면함유 면적 또는 수량 | `number` | `text` |
| `contract_work_name_amount` | DOC-CON-019 | 도급공사명 및 공사금액 | `number` | `text` |
| `hazardous_material_type_quantity_multiple` | DOC-FAC-009 | 위험물 종류 및 지정수량 배수 | `number` | `text` |
| `hazardous_material_type_quantity` | DOC-FAC-010 | 위험물 종류 및 수량 | `number` | `text` |
| `hazardous_material_name_max_quantity` | DOC-FAC-024 | 위험물 품명 및 최대수량 | `number` | `text` |
| `hazardous_material_quantity_multiple` | DOC-FAC-025 | 위험물 품명·수량·지정수량 배수 | `number` | `text` |
| `ppe_spec_quantity` | DOC-OSH-045 | 보호구 규격 및 수량 | `number` | `text` |

## 사전 조회 (실행 전 UUID 확인 필수)

```sql
-- 실행 전: 아래 7건이 정확히 조회되는지 확인 (count=7 가드)
SELECT id, field_key, input_type, form_schema_id
FROM runtime_field
WHERE field_key IN (
  'asbestos_area_quantity',
  'contract_work_name_amount',
  'hazardous_material_type_quantity_multiple',
  'hazardous_material_type_quantity',
  'hazardous_material_name_max_quantity',
  'hazardous_material_quantity_multiple',
  'ppe_spec_quantity'
)
ORDER BY field_key;
-- 기대: 7행. 7행 미만이면 field_key 중복/누락 — 실행 중단.
```

## 실행 SQL

```sql
-- WO-DOC260-OBJ10-G1-COMPOUND-INPUT-001 DB 변경
-- 실행 전: 반드시 Owner 최종 승인 확인
-- 실행 전: 위 사전 조회로 UUID 확인 및 count=7 검증

-- Step 1: id(UUID) 기반 UPDATE — field_key 중복 가능성 차단
UPDATE runtime_field
SET input_type = 'text'
WHERE id IN (
  -- DOC-BLD-038: asbestos_area_quantity
  '<UUID_asbestos_area_quantity>',
  -- DOC-CON-019: contract_work_name_amount
  '<UUID_contract_work_name_amount>',
  -- DOC-FAC-009: hazardous_material_type_quantity_multiple
  '<UUID_hazardous_material_type_quantity_multiple>',
  -- DOC-FAC-010: hazardous_material_type_quantity
  '<UUID_hazardous_material_type_quantity>',
  -- DOC-FAC-024: hazardous_material_name_max_quantity
  '<UUID_hazardous_material_name_max_quantity>',
  -- DOC-FAC-025: hazardous_material_quantity_multiple
  '<UUID_hazardous_material_quantity_multiple>',
  -- DOC-OSH-045: ppe_spec_quantity
  '<UUID_ppe_spec_quantity>'
);

-- Step 2: 7행 갱신 검증 (ROW COUNT가 7이어야 함)
-- psql: \echo 'Rows updated:' <위 UPDATE 결과>
-- 7 미만이면 즉시 ROLLBACK
```

**UUID 확보 절차**: 사전 조회 결과의 `id` 컬럼 값을 위 `<UUID_*>` 자리에 대입한 후 실행.

## 기존 저장 데이터 영향

- 현재 `input_type=number`로 저장된 값이 있으면 DB에 `numeric` 타입으로 저장돼 있음
- `input_type`만 변경하면 기존 `numeric` 값은 그대로 유지됨
- 렌더러가 `text` 경로로 읽을 경우 숫자를 문자열로 표시 (예: `50` → `"50"`) — 정보 손실 없음
- 7개 문서 모두 현재 `G1_DB_UPDATE_REQUIRED` 또는 `OWNER_REVIEW_BLOCKED`로 고객이 값을 저장한 사례가 없어 기존 데이터 위험 낮음

## 롤백

```sql
-- 롤백 시 실행 (사전 조회에서 확보한 UUID 사용)
UPDATE runtime_field
SET input_type = 'number'
WHERE id IN (
  '<UUID_asbestos_area_quantity>',
  '<UUID_contract_work_name_amount>',
  '<UUID_hazardous_material_type_quantity_multiple>',
  '<UUID_hazardous_material_type_quantity>',
  '<UUID_hazardous_material_name_max_quantity>',
  '<UUID_hazardous_material_quantity_multiple>',
  '<UUID_ppe_spec_quantity>'
);
```

## 연계 영향

| 구성요소 | 영향 |
|---------|------|
| BE `_validate_runtime_keys` | 없음 — `text` 타입에 대한 별도 값 검증 없음 |
| FE `collectRuntimeData` | `text` 경로 → string으로 저장. `Number()` 변환 없음 |
| FE `validateNumberInputs` | `input_type=text` 필드는 검증 대상 제외 → 안전 |
| FE `G1_COMPOUND_FIELD_KEYS` Gate 1 | `input_type=text` 확인 후 해제 → Gate 2로 진입 |
| FE `G1_APPROVED_FIELD_IDS` Gate 2 | DB 변경 후에도 Owner가 각 field UUID를 승인해야 편집 가능 |
| 렌더러 / PDF 출력 | `text` 값을 그대로 출력 — 복합 정보 손실 없음 |
| 기존 증적 차단 (CANDIDATE evidence) | 별도 승인 조건 — 이 DB 변경의 영향 범위 밖 |

## 배포 순서

1. DB 사전 조회 실행 → UUID 7건 확보 + count=7 검증
2. Owner 최종 승인 획득
3. DB UPDATE 실행 (UUID 기반) → Row count=7 검증 → 이상 시 즉시 ROLLBACK
4. FE 코드 PR 병합 (`G1_COMPOUND_FIELD_KEYS` + `G1_APPROVED_FIELD_IDS`)
5. Owner가 승인할 field_id를 `G1_APPROVED_FIELD_IDS`에 추가 후 재배포
6. 검증: 승인된 문서 편집기 진입 확인 → `G1_DB_UPDATE_REQUIRED` / `G1_OWNER_APPROVAL_REQUIRED` 없음
7. 고객 사용 가능 집계는 각 문서의 증적 차단 해제 Gate와 별도로 판단

## 고객 사용 가능 문서 예상 증가

입력 타입 보정 + Owner 승인 후 남은 차단 조건:

| 문서 | G1 해제 후 잔여 차단 |
|------|---------------------|
| DOC-BLD-038 | 없음 (증적 연결 미확인) — 잠재적 개방 가능 |
| DOC-CON-019 | REPORT_NUMBER 증적 CANDIDATE |
| DOC-FAC-009 | DATE 증적 CANDIDATE |
| DOC-FAC-010 | DATE 증적 CANDIDATE |
| DOC-FAC-024 | REPORT_NUMBER 증적 CANDIDATE |
| DOC-FAC-025 | 없음 (증적 연결 미확인) — 잠재적 개방 가능 |
| DOC-OSH-045 | DATE + SIGNATURE 증적 CANDIDATE |

CANDIDATE 증적 해제는 별도 Gate (이 WO 범위 밖).
