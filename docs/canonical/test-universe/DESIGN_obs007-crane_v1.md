---
wo: WO-E2E-OBS007-CRANE-DESIGN-001
class: plans
type: design
scope: canonical
project: test-universe
title: Obs-007 crane object design
version: 1
status: active
owner: taiwang
---

# DESIGN — Obs-007 object crane

WO = `WO-E2E-OBS007-CRANE-DESIGN-001`

DESIGN ONLY. Implementation = PENDING. Production mutation = 0. E2E rerun = 0.

OBJECT = `crane`
CANONICAL_INPUT = `has_crane`

GPT independent legal verification is still required. This document is a design proposal grounded in AFTER evidence and existing vocabulary. It does not mutate LEG, API, UI, fixtures, or Sidecar.

## 1. Scope and locked facts

This design covers the 18 crane atoms fixed in:

```text
docs/canonical/test-universe/ANALYSIS_obs007-crane_v1.md
```

Not in this WO:

```text
elevator
welding
dust_work
boiler
pressure_vessel
demolition
ksic_major
work applicability
```

Locked analysis facts (not re-litigated):

```text
has_crane=true Profiles = 38
has_crane absent Profiles = 74
38/38 emit the same 18 atoms
mapped_field = has_crane
triggered_by = ["has_crane"]
subtype fact supplied = 0
NEGATIVE_CONTROL = PASS
GPT_VERDICT (analysis) = CHG_REQUIRED
```

Design principles applied here:

```text
Do not infer has_tower_crane from has_crane.
Do not infer mobile / jib / gantry / travelling from has_crane.
Split subtype only when the statute names an explicit target that a fact can express.
Reuse existing exact fields before inventing new ones.
Unspecified subtype is not treated as present.
generic fact → all subtype APPLICABLE is not the designed target state.
generic fact 부족 → REVIEW_REQUIRED / 미판정 is allowed.
```

`applicability=APPLICABLE` and `check_result=NOT_APPLICABLE` on all 684 rows is recorded as a deferred Observation candidate. It is not opened as a new Issue in this WO.

## 2. Vocabulary survey (before any new field)

Priority used: existing exact field → existing field combination → new explicit field.

### 2.1 Fields that exist today

| field | where observed | Official LEG AFTER request | runtime allowlist `_LEG_INPUT_FIELDS` | notes |
|---|---|---|---|---|
| `has_crane` | `DiagnoseStep1Body`; INDUSTRIAL EXISTS MVP (`크레인/호이스트 유무`); diagnosis_input_fields INDUSTRY (later PAID3 list-replaced); LEG inactive list in `STANDARD_test-universe_v1.md` snapshot | supplied true on 38/112 | YES | Current mapped_field of all 18 atoms |
| `has_tower_crane` | `SafeConstructionConsumerInput`; construction PAID contract; factories column; trigger `WORK:TOWER_CRANE` / `EQUIPMENT:TOWER_CRANE`; LEG active 24 in STANDARD snapshot; runtime comment: specific tower atoms, no alias to `has_crane` | not supplied; `contract.missing_fields` 112/112 | YES | Exact field. Must not be derived from `has_crane` |
| `crane_count` | diagnosis_input_fields INDUSTRY PAID3 (later deactivated with `has_crane`) | not in AFTER request | not in `_LEG_INPUT_FIELDS` | Count, not applicability boolean |
| `tower_crane_count` | `INPUT_CONTRACT_STANDARD.md` construction PAID | not in AFTER request | not in `_LEG_INPUT_FIELDS` | Count, not applicability boolean |

AFTER `contract.missing_fields` crane names across 112 Profiles:

```text
has_tower_crane = 112/112
has_crane = 74/74 of the has_crane-absent set
```

No other `*crane*` name appears in AFTER missing_fields.

### 2.2 Fields that do not exist as exact vocabulary

Searched in tai-api schemas, `_LEG_INPUT_FIELDS`, diagnosis_input_fields SQL, INPUT_CONTRACT_STANDARD, construction assembler, EXISTS MVP, AFTER missing_fields:

```text
has_mobile_crane
has_jib_crane
has_gantry_crane
has_travelling_crane
has_slewing_crane
has_hydraulic_crane
has_crane_without_operator_cab
crane_installation_work
crane_repair_work
crane_inspection_work
crane_dismantling_work
crane_transporting_workers
crane_erect_service_dismantle_work
```

Result: **0 exact hits**.

### 2.3 Current alias behavior (not to be reused as design)

`services/condition_normalizer.py` EQUIPMENT_MAP currently collapses:

```text
크레인 → has_crane
천장크레인 → has_crane
타워크레인 → has_crane
이동식크레인 → has_crane
```

That is automatic subtype → generic inference. This design does **not** adopt it. Runtime wiring comments already forbid the reverse generic→specific alias for `has_tower_crane`.

### 2.4 Sector contract split (observed)

```text
INDUSTRIAL EXISTS / Official LEG manufacturing form_data: has_crane
CONSTRUCTION PAID / SAFE construction consumer: has_tower_crane (not has_crane)
AFTER freeze construction Profiles with crane: still sent form_data.has_crane=true, not has_tower_crane
```

Construction already has an explicit tower field. The AFTER freeze did not pass it.

## 3. Atom classification (18/18)

Design state is exactly one of:

```text
GENERIC_OK
SUBTYPE_REQUIRED
OPERATION_CONDITION_REQUIRED
COMPOSITE_CONDITION_REQUIRED
INSUFFICIENT_EVIDENCE
```

Decision is exactly one of:

```text
KEEP has_crane
REMAP to existing explicit fact
REMAP to new explicit fact
REQUIRE compound condition
HOLD — insufficient evidence
```

| atom_id | article | 현재 mapped_field | 법령상 대상 (evidence 원문 기준) | 필요한 explicit fact | generic has_crane만으로 충분? | 설계 상태 |
|---|---|---|---|---|---|---|
| `5aec15bb-9ba9-5d54-87db-13dcacf41cf9` | 37 | has_crane | 타워크레인의 설치ㆍ수리ㆍ점검 또는 해체 + 순간풍속 초당 10미터 초과 시 작업 중지 | existing `has_tower_crane` + operation family (설치/수리/점검/해체). Wind is duty content, not a profile fact | NO | COMPOSITE_CONDITION_REQUIRED |
| `16ce5107-52c3-5e80-80b7-8c54ca0caf94` | 86 | has_crane | 이동식 크레인을 사용하여 근로자를 운반 | new `has_mobile_crane` + new `crane_transporting_workers` | NO | COMPOSITE_CONDITION_REQUIRED |
| `c924dad5-4d8f-5f2d-b0e8-6d537f75a087` | 86 | has_crane | 크레인을 사용하여 근로자를 운반 | `has_crane` + new `crane_transporting_workers` | NO | OPERATION_CONDITION_REQUIRED |
| `84001932-7ef6-5789-885f-34913213e810` | 136 | has_crane | 유압을 동력으로 사용하는 크레인의 안전밸브. 지브 크레인은 정격하중 산정 괄호 | hydraulic-powered crane. **Not** 지브-only applicability. No existing hydraulic field | NO (hydraulic is narrower than all cranes); also NO to remap-to-jib | INSUFFICIENT_EVIDENCE |
| `63092974-a3c8-556a-b855-cbe3be96dee5` | 137 | has_crane | 그 크레인을 사용하여 짐을 운반하는 경우 | `has_crane` (generic crane-use chapter) | YES | GENERIC_OK |
| `2437c873-e072-5c12-9257-21ee2a4a5a30` | 138 | has_crane | 지브 크레인을 사용하여 작업 / 지브 경사각 | new `has_jib_crane` | NO | SUBTYPE_REQUIRED |
| `44b2d064-d1f1-52a8-9c2a-ccbcc17ac3bc` | 139 | has_crane | 갠트리 크레인 등 바닥 고정 레일 주행 크레인의 새들 안전공간 | new `has_gantry_crane` (rail-mounted gantry class) | NO | SUBTYPE_REQUIRED |
| `fe7a74bc-57a2-5b05-b489-360b08ba92b5` | 139 | has_crane | 같은 주행로에 병렬 설치된 주행 크레인의 수리ㆍ조정ㆍ점검 등 | new `has_travelling_crane` + service/runway work. Parallel-runway layout has no existing field | NO | COMPOSITE_CONDITION_REQUIRED |
| `4aa68025-0522-5207-9c57-21595543c3c9` | 141 | has_crane | 크레인의 설치ㆍ조립ㆍ수리ㆍ점검 또는 해체 작업 | `has_crane` + operation family (설치/조립/수리/점검/해체) | NO | OPERATION_CONDITION_REQUIRED |
| `440d4db1-232c-50b7-8971-6409629728e0` | 144 | has_crane | 주행 크레인 또는 선회 크레인과 건설물ㆍ설비 사이 통로 폭 | new `has_travelling_crane` OR new `has_slewing_crane` | NO | COMPOSITE_CONDITION_REQUIRED |
| `95bdc756-b7c7-5839-84a7-ee1688be09aa` | 146 | has_crane | 크레인을 사용하여 작업을 하는 경우 | `has_crane` | YES | GENERIC_OK |
| `a20d913d-52a7-5425-bb2c-8c2d91b1b5a8` | 146 | has_crane | 조종석이 설치되지 아니한 크레인 | new `has_crane_without_operator_cab` | NO | SUBTYPE_REQUIRED |
| `d788dd1e-8b22-5328-ad28-849a3b5ce3ab` | 147 | has_crane | 이동식 크레인을 사용하는 경우 / 설계기준 준수 | new `has_mobile_crane` | NO | SUBTYPE_REQUIRED |
| `1e7527a6-2e7e-5b9e-81b0-bcc4562e9644` | 148 | has_crane | 유압을 동력으로 사용하는 이동식 크레인의 안전밸브 | new `has_mobile_crane` (hydraulic residual: HOLD, not a committed new field) | NO | SUBTYPE_REQUIRED |
| `d018d484-e92a-5588-b8b2-44e6b7e70955` | 149 | has_crane | 이동식 크레인을 사용하여 하물을 운반 | new `has_mobile_crane` | NO | SUBTYPE_REQUIRED |
| `17b44c74-9e68-5b7a-9b5c-216cb3c86ed2` | 150 | has_crane | 이동식 크레인 명세서의 지브 경사각. Subject is 이동식 크레인, not 지브 크레인 | new `has_mobile_crane` only. Do **not** require `has_jib_crane` | NO | SUBTYPE_REQUIRED |
| `5b9a8f66-4e0f-58bb-acdf-23c80b3b6c63` | 168 | has_crane | 변형ㆍ균열 철구를 크레인 또는 이동식 크레인의 고리걸이용구로 사용 금지 | KEEP `has_crane`. When `has_mobile_crane` exists later, OR that fact as well | YES (crane branch of the OR) | GENERIC_OK |
| `ea92a57d-be66-5d07-bdab-eb032faac006` | 170 | has_crane | 엔드리스가 아닌 로프ㆍ체인을 크레인 또는 이동식 크레인 고리걸이용구로 사용 금지 | KEEP `has_crane`. Same later OR `has_mobile_crane` | YES (crane branch of the OR) | GENERIC_OK |

### Counts

```text
GENERIC_OK = 4
SUBTYPE_REQUIRED = 7
OPERATION_CONDITION_REQUIRED = 2
COMPOSITE_CONDITION_REQUIRED = 4
INSUFFICIENT_EVIDENCE = 1
TOTAL = 18
```

GENERIC_OK atoms: 137, 146(사용), 168, 170.

## 4. Per-atom decision (KEEP / REMAP / REQUIRE / HOLD)

### Article 37 — tower + install/repair/inspect/dismantle + wind

```text
DECISION = REQUIRE compound condition
EXISTING = has_tower_crane
NEW (last resort) = crane_erect_service_dismantle_work
NOT a profile fact = instantaneous wind speed
MINIMUM OPEN PATH = remap mapped_field to has_tower_crane;
  if operation fact absent → REVIEW_REQUIRED, not APPLICABLE
FORBIDDEN = has_crane=true → has_tower_crane=true
```

Wind is the legal trigger inside the duty once the work is in scope. It is not designed as a diagnosis input field.

### Article 86 — two atoms

```text
16ce5107 (mobile + carry workers)
  DECISION = REQUIRE compound condition
  NEW = has_mobile_crane AND crane_transporting_workers
  absent subtype/operation → REVIEW_REQUIRED

c924dad5 (generic crane + carry workers)
  DECISION = REQUIRE compound condition
  KEEP has_crane as equipment gate
  NEW = crane_transporting_workers
  has_crane alone → REVIEW_REQUIRED
```

### Article 136 — hydraulic crane safety valve

```text
DECISION = HOLD — insufficient evidence
DO NOT REMAP to has_jib_crane
Reason = evidence subject is 유압 크레인; 지브 is a rated-load parenthesis
No existing hydraulic field. New has_hydraulic_crane is not committed.
Until GPT confirms a field, do not keep current has_crane→APPLICABLE as the designed target.
Designed open state = REVIEW_REQUIRED / 미판정 when only has_crane is known
```

### Article 137 / 146(사용)

```text
DECISION = KEEP has_crane
GENERIC_OK
These are generic crane-use duties, not subtype duties.
```

### Article 138 — 지브 크레인

```text
DECISION = REMAP to new explicit fact
NEW = has_jib_crane
EXISTING reuse = none
has_crane alone → REVIEW_REQUIRED
```

### Article 139 — gantry vs travelling

```text
44b2d064 gantry/rail saddle clearance
  DECISION = REMAP to new explicit fact
  NEW = has_gantry_crane
  Equipment layout duty: subtype presence is the applicability gate

fe7a74bc travelling crane repair on shared runway
  DECISION = REQUIRE compound condition
  NEW = has_travelling_crane + crane_erect_service_dismantle_work
  Parallel-runway layout = HOLD (no existing field; do not invent without GPT confirm)
  has_crane alone → REVIEW_REQUIRED
```

### Article 141 — generic crane erect/service/dismantle

```text
DECISION = REQUIRE compound condition
KEEP has_crane as equipment gate
NEW = crane_erect_service_dismantle_work
Separate equipment existence from those operations.
has_crane alone → REVIEW_REQUIRED
```

One new operation family is proposed instead of five separate install/repair/inspect/dismantle/assemble fields, because articles 37 and 141 already OR those operations in the statute text. GPT may split them later. No existing operation field was found.

### Article 144 — travelling or slewing + passageway

```text
DECISION = REQUIRE compound condition
NEW = has_travelling_crane OR has_slewing_crane
EXISTING reuse = none
has_crane alone → REVIEW_REQUIRED
```

`has_slewing_crane` is last-resort. It is not in current vocabulary. It is named because the statute says `주행 크레인 또는 선회 크레인`.

### Article 146 — crane without cab

```text
DECISION = REMAP to new explicit fact
NEW = has_crane_without_operator_cab
has_crane alone → REVIEW_REQUIRED
```

### Articles 147–150 — mobile crane family

```text
147, 148, 149, 150
DECISION = REMAP to new explicit fact
NEW = has_mobile_crane
150 지브의 경사각 = mobile-crane jib spec, NOT 지브 크레인 (article 138)
148 hydraulic residual = HOLD, not a second committed field
has_crane alone → REVIEW_REQUIRED
```

### Articles 168 / 170 — crane OR mobile crane fittings

```text
DECISION = KEEP has_crane
Later, when has_mobile_crane exists, LEG should also match that OR branch.
Current over-application issue is mobile-only articles, not these OR articles.
```

## 5. Explicit fact catalog (designed)

### Reuse (existing)

```text
has_crane
has_tower_crane
```

Not used as applicability triggers: `crane_count`, `tower_crane_count`.

### New (last resort, after survey)

| proposed field | why existing reuse failed | atoms |
|---|---|---|
| `has_mobile_crane` | no exact field; condition_normalizer currently aliases 이동식크레인→has_crane (rejected) | 86-mobile, 147, 148, 149, 150, later OR 168/170 |
| `has_jib_crane` | no exact field | 138 only |
| `has_gantry_crane` | no exact field | 139 gantry |
| `has_travelling_crane` | no exact field | 139 travelling, 144 |
| `has_slewing_crane` | no exact field; statute names 선회 크레인 | 144 OR |
| `has_crane_without_operator_cab` | no exact field | 146 cabless |
| `crane_erect_service_dismantle_work` | no exact operation field | 37, 141, 139 travelling |
| `crane_transporting_workers` | no exact operation field | 86 both atoms |

Not committed:

```text
has_hydraulic_crane          (article 136 HOLD)
parallel_runway_cranes       (article 139 travelling HOLD)
wind_speed_mps               (article 37 duty content, not input)
```

## 6. Change-impact matrix

No change is executed in this WO.

| fact | 현재 존재 여부 | AFTER request 전달 여부 | runtime 지원 여부 | 영향 atom 수 | UI 입력 필요 여부 |
|---|---|---|---|---:|---|
| `has_crane` | YES | YES (38/112) | YES | 4 KEEP + 2 operation gates | already present (industrial / Official LEG form_data) |
| `has_tower_crane` | YES | NO (missing 112/112) | YES | 1 (article 37) | construction PAID already; Official LEG manufacturing/building form_data did not collect it |
| `has_mobile_crane` | NO | NO | NO | 5 primary + 2 later OR | YES (new) |
| `has_jib_crane` | NO | NO | NO | 1 | YES (new) |
| `has_gantry_crane` | NO | NO | NO | 1 | YES (new) |
| `has_travelling_crane` | NO | NO | NO | 2 | YES (new) |
| `has_slewing_crane` | NO | NO | NO | 1 (OR with travelling) | YES (new) |
| `has_crane_without_operator_cab` | NO | NO | NO | 1 | YES (new) |
| `crane_erect_service_dismantle_work` | NO | NO | NO | 3 | YES (new) |
| `crane_transporting_workers` | NO | NO | NO | 2 | YES (new) |

### Minimum change path (not implemented)

```text
LEG-only
  = article 37 mapped_field remap onto existing has_tower_crane
    (runtime already accepts the field; AFTER freeze did not send it)

API contract
  = 8 new facts
  = plus Official LEG / DiagnoseStep1 exposure of has_tower_crane
    if manufacturing/building consumer must collect it explicitly

Canonical input contract
  = 8 new facts
  = construction already has has_tower_crane; do not replace it with has_crane
  = do not add has_crane → has_tower_crane inference

UI input
  = construction: tower field exists; still need mobile/jib/gantry/travelling/operation
  = manufacturing: has_crane exists; tower and other subtypes are additional questions
  = unspecified subtype → REVIEW_REQUIRED, not silent APPLICABLE

Fixture
  = test-universe Frozen facility currently stores has_crane only
  = future fixture must not auto-fill subtype facts

E2E Sidecar
  = future; not in this WO
```

Counts for stop-report (design intent, not executed deltas):

```text
LEG_ONLY_CHANGE_COUNT = 1
  (article 37 → existing has_tower_crane; still needs operation for full compound)

API_CONTRACT_CHANGE_COUNT = 8
  (new facts; has_tower_crane already on construction consumer)

CANONICAL_INPUT_CHANGE_COUNT = 8

UI_INPUT_CHANGE_COUNT = 8
  (+ manufacturing/building has_tower_crane collection gap, existing field)
```

KEEP atoms require no LEG remap of mapped_field.

## 7. Open-before-launch target state

Designed consumer behavior when only `has_crane=true` is known:

| atom group | designed result |
|---|---|
| GENERIC_OK (137, 146 use, 168, 170) | may remain APPLICABLE on `has_crane` |
| all SUBTYPE / OPERATION / COMPOSITE / HOLD atoms | not APPLICABLE; REVIEW_REQUIRED / 미판정 is allowed |
| article 37 | APPLICABLE only if `has_tower_crane` (and operation when that fact exists) |
| articles 147–150, 86-mobile | APPLICABLE only if `has_mobile_crane` (plus worker-transport where required) |
| article 138 | APPLICABLE only if `has_jib_crane` |

This is the opposite of the AFTER freeze, where `has_crane=true` made all 18 APPLICABLE.

## 8. Open questions (not CHG)

1. Article 136: confirm HOLD vs a committed `has_hydraulic_crane`. Do not treat as jib-only.
2. Article 148: whether hydraulic is a second gate on top of `has_mobile_crane`.
3. Article 139 travelling: whether parallel-runway is a required fact or stays inside the travelling+service compound.
4. Whether `crane_erect_service_dismantle_work` should be split into the five statutory verbs.
5. Whether `has_slewing_crane` is required or travelling covers the 144 OR in consumer vocabulary.
6. Construction Official LEG AFTER sent `has_crane` rather than `has_tower_crane`. Future implementation must not infer; it must collect the explicit field.
7. `applicability=APPLICABLE` vs `check_result=NOT_APPLICABLE` on 684 rows: deferred Observation candidate, not opened here.

GPT verifies the legal mapping before any implementation WO.
