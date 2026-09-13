---
wo: WO-E2E-OBS007-CRANE-DESIGN-PATCH2
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

WO = `WO-E2E-OBS007-CRANE-DESIGN-PATCH2`

PR = `#343`
PATCH of `WO-E2E-OBS007-CRANE-DESIGN-PATCH1` (GPT re-verify PASS)
CURRENT_HEAD_BEFORE = `41b3bdb1c5abdc05ad6bc60733a2fa521a0d7453`

DESIGN FINAL PENDING GPT. Implementation = BLOCKED. Production mutation = 0. E2E rerun = 0.

OBJECT = `crane`
CANONICAL_INPUT = `has_crane`

```text
CHG_REQUIRED = 유지
DESIGN_VERDICT = PATCH2_COMPLETE_PENDING_GPT
IMPLEMENTATION = BLOCKED
STATUS = DESIGN_FINAL_PENDING_GPT
DESIGN_FROZEN = NO
IMPLEMENTATION_APPROVED = NO
```

GPT independent legal verification is still required. This document does not mutate LEG, API, UI, fixtures, or Sidecar.

## 0. PATCH-1 delta (what changed vs HEAD 6065dc8b)

Kept:

```text
has_crane → subtype 자동추론 금지
has_tower_crane existing-field reuse
Article 136 HOLD
Article 150 = mobile crane, NOT jib crane
generic crane와 subtype crane 분리
```

Removed:

```text
crane_erect_service_dismantle_work
as a shared applicability boolean for articles 37 / 139 / 141
```

Patched blockers:

```text
Article 37  = atomic tower operations, no has_crane, no wind input
Article 139 travelling = broad family removed; A not confirmed; conclusion C HOLD
Article 141 = atomic verbs including assembly, excluding adjustment
Article 144 = subtype-only APPLICABLE forbidden; passageway HOLD
Article 148 = has_mobile_crane alone discarded; hydraulic aligned with 136 HOLD
```

## 0.1 PATCH-2 delta (what changed vs HEAD 41b3bdb)

PATCH-1 GPT re-verify = PASS. Remaining correction = hydraulic applicability only.

Committed:

```text
has_hydraulic_crane
의미 = 크레인이 유압을 동력으로 사용하는지 여부
NOT has_jib_crane
NOT has_mobile_crane
NOT has_crane
generic crane → hydraulic 자동추론 금지
mobile crane → hydraulic 자동추론 금지
```

Article 136:

```text
INSUFFICIENT_EVIDENCE / HOLD
→ COMPOSITE_CONDITION_REQUIRED
has_crane AND has_hydraulic_crane
지브 정격하중 괄호 = not an applicability subtype
has_jib_crane is not a trigger
```

Article 148:

```text
INSUFFICIENT_EVIDENCE / HOLD
→ COMPOSITE_CONDITION_REQUIRED
has_mobile_crane AND has_hydraulic_crane
has_mobile_crane alone → APPLICABLE forbidden
```

Unchanged HOLD:

```text
Article 139 travelling = INSUFFICIENT_EVIDENCE / HOLD
Article 144 = INSUFFICIENT_EVIDENCE / HOLD
Article 37 = has_tower_crane AND atomic tower operations
Article 150 = mobile only
```

## 1. Scope and locked analysis facts

Source analysis:

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

Locked analysis facts:

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

Design principles:

```text
Do not infer has_tower_crane from has_crane.
Do not infer mobile / jib / gantry / travelling from has_crane.
Do not bind distinct statutory verb sets into one broad operation boolean.
Canonical facts stay atomic even if a future UI uses multi_select.
Unspecified subtype is not treated as present.
generic fact → all subtype APPLICABLE is not the designed target state.
generic fact 부족 → REVIEW_REQUIRED / 미판정 is allowed.
```

`applicability=APPLICABLE` and `check_result=NOT_APPLICABLE` on all 684 rows remains a deferred Observation candidate. Not opened here.

## 2. Vocabulary survey (PATCH-1 re-scan)

Priority: existing exact field → existing field combination → new explicit field. New names below are candidates, not implemented fields.

### 2.1 Existing crane-related fields

| field | where observed | AFTER request | `_LEG_INPUT_FIELDS` | reuse for this design |
|---|---|---|---|---|
| `has_crane` | `DiagnoseStep1Body`; INDUSTRIAL EXISTS MVP; diagnosis_input_fields INDUSTRY | supplied true on 38/112 | YES | generic crane equipment gate only |
| `has_tower_crane` | `SafeConstructionConsumerInput`; construction PAID; factories column; runtime specific axis | not supplied; missing_fields 112/112 | YES | Article 37 equipment gate. No alias from `has_crane` |
| `crane_count` | diagnosis_input_fields INDUSTRY PAID3 (later deactivated) | no | no | not an applicability boolean |
| `tower_crane_count` | INPUT_CONTRACT_STANDARD construction PAID | no | no | not an applicability boolean |
| `has_demolition` | construction consumer / Official LEG | some Profiles | YES | **not** crane dismantling. Do not reuse |

AFTER `contract.missing_fields` crane names: `has_tower_crane` 112/112, `has_crane` 74/74 of the absent set. No other `*crane*` name.

### 2.2 Exact fields searched and not found

Repo schemas, `_LEG_INPUT_FIELDS`, diagnosis_input_fields SQL, INPUT_CONTRACT_STANDARD, construction assembler, EXISTS MVP, AFTER missing_fields, UI/consumer contracts:

```text
has_mobile_crane
has_jib_crane
has_gantry_crane
has_travelling_crane
has_slewing_crane
has_hydraulic_crane
has_crane_without_operator_cab
crane_installation_work
crane_assembly_work
crane_repair_work
crane_adjustment_work
crane_inspection_work
crane_dismantling_work
crane_transporting_workers
crane_erect_service_dismantle_work
crane_passageway_installation
passageway
주행로
병렬
유압
```

Exact hits: **0**.

`condition_normalizer.py` still collapses `타워크레인` / `이동식크레인` / `천장크레인` → `has_crane`. That alias is not adopted.

### 2.3 UI vs canonical (not implemented)

A future UI may ask one multi_select such as:

```text
크레인 작업 종류 = 설치 / 조립 / 수리 / 조정 / 점검 / 해체 / 근로자 운반
```

Backend may map those choices deterministically to atomic canonical facts. This DESIGN does not implement UI. Canonical facts remain separate.

## 3. Atom classification (18/18 after PATCH-2)

| atom_id | article | 현재 mapped_field | 법령상 대상 (AFTER evidence) | 필요한 explicit fact | generic has_crane만으로 충분? | 설계 상태 |
|---|---|---|---|---|---|---|
| `5aec15bb-9ba9-5d54-87db-13dcacf41cf9` | 37 | has_crane | 타워크레인의 설치ㆍ수리ㆍ점검 또는 해체. 순간풍속 초당 10미터 초과 시 중지 | `has_tower_crane` AND (installation OR repair OR inspection OR dismantling). Wind = duty content, not input | NO. `has_crane` forbidden | COMPOSITE_CONDITION_REQUIRED |
| `16ce5107-52c3-5e80-80b7-8c54ca0caf94` | 86 | has_crane | 이동식 크레인을 사용하여 근로자를 운반 | `has_mobile_crane` AND `crane_transporting_workers` | NO | COMPOSITE_CONDITION_REQUIRED |
| `c924dad5-4d8f-5f2d-b0e8-6d537f75a087` | 86 | has_crane | 크레인을 사용하여 근로자를 운반 | `has_crane` AND `crane_transporting_workers` | NO | OPERATION_CONDITION_REQUIRED |
| `84001932-7ef6-5789-885f-34913213e810` | 136 | has_crane | 유압을 동력으로 사용하는 크레인. 지브는 정격하중 괄호 | `has_crane` AND `has_hydraulic_crane`. Not `has_jib_crane` | NO | COMPOSITE_CONDITION_REQUIRED |
| `63092974-a3c8-556a-b855-cbe3be96dee5` | 137 | has_crane | 그 크레인을 사용하여 짐을 운반하는 경우 | `has_crane` | YES | GENERIC_OK |
| `2437c873-e072-5c12-9257-21ee2a4a5a30` | 138 | has_crane | 지브 크레인을 사용하여 작업 | `has_jib_crane` | NO | SUBTYPE_REQUIRED |
| `44b2d064-d1f1-52a8-9c2a-ccbcc17ac3bc` | 139 | has_crane | 갠트리 크레인 등 바닥 고정 레일 주행 크레인 새들 안전공간 | `has_gantry_crane` | NO | SUBTYPE_REQUIRED |
| `fe7a74bc-57a2-5b05-b489-360b08ba92b5` | 139 | has_crane | 같은 주행로에 병렬 설치된 주행 크레인의 수리ㆍ조정 및 점검 등 / 주행로상 또는 접촉 우려 장소 작업 등. evidence truncated | see §5. A not confirmed | NO | INSUFFICIENT_EVIDENCE |
| `4aa68025-0522-5207-9c57-21595543c3c9` | 141 | has_crane | 크레인의 설치ㆍ조립ㆍ수리ㆍ점검 또는 해체 작업 | `has_crane` AND (installation OR assembly OR repair OR inspection OR dismantling). No adjustment | NO | OPERATION_CONDITION_REQUIRED |
| `440d4db1-232c-50b7-8971-6409629728e0` | 144 | has_crane | 주행 또는 선회 크레인과 건설물ㆍ설비 사이에 통로를 설치하는 경우 | subtype OR is not enough; passageway context required and currently inexpressible | NO | INSUFFICIENT_EVIDENCE |
| `95bdc756-b7c7-5839-84a7-ee1688be09aa` | 146 | has_crane | 크레인을 사용하여 작업을 하는 경우 | `has_crane` | YES | GENERIC_OK |
| `a20d913d-52a7-5425-bb2c-8c2d91b1b5a8` | 146 | has_crane | 조종석이 설치되지 아니한 크레인 | `has_crane_without_operator_cab` | NO | SUBTYPE_REQUIRED |
| `d788dd1e-8b22-5328-ad28-849a3b5ce3ab` | 147 | has_crane | 이동식 크레인을 사용하는 경우 | `has_mobile_crane` | NO | SUBTYPE_REQUIRED |
| `1e7527a6-2e7e-5b9e-81b0-bcc4562e9644` | 148 | has_crane | 유압을 동력으로 사용하는 이동식 크레인 | `has_mobile_crane` AND `has_hydraulic_crane`. `has_mobile_crane` alone forbidden | NO | COMPOSITE_CONDITION_REQUIRED |
| `d018d484-e92a-5588-b8b2-44e6b7e70955` | 149 | has_crane | 이동식 크레인을 사용하여 하물을 운반 | `has_mobile_crane` | NO | SUBTYPE_REQUIRED |
| `17b44c74-9e68-5b7a-9b5c-216cb3c86ed2` | 150 | has_crane | 이동식 크레인 명세서의 지브 경사각 | `has_mobile_crane` only. Not `has_jib_crane` | NO | SUBTYPE_REQUIRED |
| `5b9a8f66-4e0f-58bb-acdf-23c80b3b6c63` | 168 | has_crane | 크레인 또는 이동식 크레인 고리걸이용구 | KEEP `has_crane`; later OR `has_mobile_crane` | YES (crane branch) | GENERIC_OK |
| `ea92a57d-be66-5d07-bdab-eb032faac006` | 170 | has_crane | 크레인 또는 이동식 크레인 고리걸이용구 | KEEP `has_crane`; later OR `has_mobile_crane` | YES (crane branch) | GENERIC_OK |

### Counts (recomputed after PATCH-2; PATCH-1 was 4/6/2/2/4)

```text
GENERIC_OK = 4
SUBTYPE_REQUIRED = 6
OPERATION_CONDITION_REQUIRED = 2
COMPOSITE_CONDITION_REQUIRED = 4
INSUFFICIENT_EVIDENCE = 2
TOTAL = 18
```

GENERIC_OK: 137, 146(사용), 168, 170.
SUBTYPE_REQUIRED: 138, 139 gantry, 146 cabless, 147, 149, 150.
OPERATION_CONDITION_REQUIRED: 86 generic, 141.
COMPOSITE_CONDITION_REQUIRED: 37, 86 mobile, 136, 148.
INSUFFICIENT_EVIDENCE: 139 travelling, 144.

## 4. Special articles

### 4.1 Article 37

AFTER evidence:

```text
사업주는 순간풍속이 초당 10미터를 초과하는 경우 타워크레인의 설치ㆍ수리ㆍ점검 또는 해체 작업을 중지하여야 하며
```

```text
DECISION = REQUIRE compound condition
equipment gate = has_tower_crane
operation gate =
  crane_installation_work
  OR crane_repair_work
  OR crane_inspection_work
  OR crane_dismantling_work
FORBIDDEN mapped_field = has_crane
FORBIDDEN inference = has_crane=true → has_tower_crane=true
wind = duty/runtime condition, not consumer profile input
assembly / adjustment are not in this article's verb set
```

Design state: `COMPOSITE_CONDITION_REQUIRED`.

If operation facts are absent: REVIEW_REQUIRED / 미판정, not APPLICABLE on `has_tower_crane` alone for this atom. GPT may confirm whether equipment-only is ever enough. This DESIGN does not treat equipment-only as sufficient.

### 4.2 Article 139 travelling (`fe7a74bc-57a2-5b05-b489-360b08ba92b5`)

AFTER evidence (truncated in freeze):

```text
사업주는 같은 주행로에 병렬로 설치되어 있는 주행 크레인의 수리ㆍ조정 및 점검 등의 작업을 하는 경우, 주행로상이나 그 밖에 주행 크레인이 근로자와 접촉할 우려가 있는 장소에서 작업을 하는 경우 등에 주행 크레인끼리 충돌하거나
```

`obligation_detail.condition`:

```text
사업주는 같은 주행로에 병렬로 설치되어 있는 주행 크레인의 수리ㆍ조정 및 점검 등의 작업을 하는 경우
```

Broad family `crane_erect_service_dismantle_work` is removed.

Minimum operation tokens present in the first 경우:

```text
has_travelling_crane
AND (
  crane_repair_work
  OR crane_adjustment_work
  OR crane_inspection_work
)
```

This is **not** confirmed sufficient (A forbidden without evidence).

Additional statutory tokens in the same evidence:

```text
같은 주행로
병렬로 설치
주행로상 작업
근로자와 접촉할 우려가 있는 장소
경우 등에
```

A second 경우 is work on the runway / contact-risk location. That clause is not the same as repair/adjustment/inspection. `등에` marks an open list. The evidence string is truncated.

Current input contract cannot express runway / parallel layout / contact-risk location. No existing exact field.

```text
CONCLUSION = C
HOLD — current input model cannot express runway/layout/contact context
A = not confirmed
B = not frozen (candidate layout facts exist in the statute text, but applicability vs illustration is not proven from truncated evidence)
```

Design state: `INSUFFICIENT_EVIDENCE`.

Necessary-but-not-sufficient **candidates** (not an A freeze):

```text
has_travelling_crane
crane_repair_work
crane_adjustment_work
crane_inspection_work
```

HOLD context (not named as committed fields):

```text
same-runway parallel installation
work on runway
worker-contact-risk location
```

installation / assembly / dismantling from articles 37 and 141 are **not** mixed into this atom.

### 4.3 Article 141

AFTER evidence:

```text
사업주는 크레인의 설치ㆍ조립ㆍ수리ㆍ점검 또는 해체 작업을 하는 경우 다음 각 호의 조치를 하여야 한다.
```

```text
DECISION = REQUIRE compound condition
has_crane
AND (
  crane_installation_work
  OR crane_assembly_work
  OR crane_repair_work
  OR crane_inspection_work
  OR crane_dismantling_work
)
```

`crane_adjustment_work` is not in this article. Do not mix Article 139 adjustment into Article 141. Do not mix Article 141 assembly into Article 37.

Design state: `OPERATION_CONDITION_REQUIRED`.
`has_crane` alone → REVIEW_REQUIRED.

### 4.4 Article 144

AFTER evidence and `obligation_detail.condition`:

```text
사업주는 주행 크레인 또는 선회 크레인과 건설물 또는 설비와의 사이에 통로를 설치하는 경우 그 폭을 0.6미터 이상으로 하여야 한다.
```

```text
(has_travelling_crane OR has_slewing_crane)
alone = APPLICABLE forbidden
```

Passageway context is in the statute as `통로를 설치하는 경우`. No existing exact fact (`crane_passageway_installation` searched; 0 hits). Name is not frozen.

```text
DECISION = HOLD — current input model cannot express passageway context
```

Candidate compound if GPT later commits a context fact:

```text
(has_travelling_crane OR has_slewing_crane)
AND passageway_context
```

Until then this atom is not designed as APPLICABLE on subtype presence.

Design state: `INSUFFICIENT_EVIDENCE`.

### 4.5 Article 136 / 148 hydraulic (PATCH-2 committed)

Shared canonical fact:

```text
has_hydraulic_crane
의미 = 크레인이 유압을 동력으로 사용하는지 여부
HYDRAULIC_FACT_STATUS = COMMITTED_IN_DESIGN
NOT implemented in runtime/API/UI in this WO
FORBIDDEN inference:
  has_crane → has_hydraulic_crane
  has_mobile_crane → has_hydraulic_crane
```

Article 136 evidence:

```text
사업주는 유압을 동력으로 사용하는 크레인의 과도한 압력상승을 방지하기 위한 안전밸브에 대하여 정격하중(지브 크레인은 최대의 정격하중으로 한다)을 건 때의 압력 이하로 작동되도록 조정하여야 한다.
```

```text
DECISION = REQUIRE compound condition
has_crane
AND
has_hydraulic_crane
generic has_crane APPLICABLE = forbidden
DO NOT use has_jib_crane as trigger
지브 크레인은 최대의 정격하중 = rated-load calculation, not applicability subtype
```

Design state: `COMPOSITE_CONDITION_REQUIRED`.

Article 148 evidence:

```text
사업주는 유압을 동력으로 사용하는 이동식 크레인의 과도한 압력상승을 방지하기 위한 안전밸브에 대하여 최대의 정격하중을 건 때의 압력 이하로 작동되도록 조정하여야 한다.
```

```text
DECISION = REQUIRE compound condition
has_mobile_crane
AND
has_hydraulic_crane
has_mobile_crane alone → APPLICABLE forbidden
```

Design state: `COMPOSITE_CONDITION_REQUIRED`.

When only `has_crane` is known: Article 136 = REVIEW_REQUIRED / 미판정, not APPLICABLE.
When only `has_mobile_crane` is known: Article 148 = REVIEW_REQUIRED / 미판정, not APPLICABLE.

### 4.6 Article 150 — unchanged

```text
SUBJECT = 이동식 크레인
REQUIRED FACT = has_mobile_crane
지브의 경사각 = mobile-crane jib specification
NOT has_jib_crane
```

Design state: `SUBTYPE_REQUIRED`. Unchanged from DESIGN-001.

## 5. Explicit fact catalog (PATCH-2)

Status tags: `확정재사용` / `설계확정` / `후보` / `HOLD`. No field is implemented in runtime here.

### A. Existing reuse (`확정재사용`)

```text
has_crane
has_tower_crane
```

Not reused as crane-operation or crane-dismantle: `has_demolition`, `crane_count`, `tower_crane_count`.

### B. New equipment/subtype fact (`후보`)

| candidate | atoms | status |
|---|---|---|
| `has_mobile_crane` | 86-mobile, 147, 148 compound, 149, 150; later OR 168/170 | 후보 |
| `has_jib_crane` | 138 only | 후보 |
| `has_gantry_crane` | 139 gantry | 후보 |
| `has_travelling_crane` | 139 travelling candidate, 144 candidate | 후보 |
| `has_slewing_crane` | 144 candidate | 후보 |
| `has_crane_without_operator_cab` | 146 cabless | 후보 |

### B2. New committed applicability fact (`설계확정`)

```text
has_hydraulic_crane
HYDRAULIC_FACT_STATUS = COMMITTED_IN_DESIGN
atoms = 136, 148
136 = has_crane AND has_hydraulic_crane
148 = has_mobile_crane AND has_hydraulic_crane
not in existing runtime/API/UI vocabulary (survey 0 exact hits)
not inferred from has_crane or has_mobile_crane
```

### C. New operation/context fact

Operation (`후보`; no existing exact field):

| candidate | articles that name that verb |
|---|---|
| `crane_installation_work` | 37, 141 |
| `crane_assembly_work` | 141 only |
| `crane_repair_work` | 37, 139 travelling, 141 |
| `crane_adjustment_work` | 139 travelling only |
| `crane_inspection_work` | 37, 139 travelling, 141 |
| `crane_dismantling_work` | 37, 141 |
| `crane_transporting_workers` | 86 both atoms |

Context (`HOLD`; not committed):

```text
passageway context                  (144)
same-runway parallel installation   (139 travelling)
work on runway                      (139 travelling)
worker-contact-risk location        (139 travelling)
wind speed                          (37 duty content, not input)
```

Removed from catalog:

```text
crane_erect_service_dismantle_work
```

## 6. Change-impact matrix (not executed)

| fact | 현재 존재 | AFTER request | runtime | 영향 atom | UI |
|---|---|---|---|---:|---|
| `has_crane` | YES | YES 38/112 | YES | 4 GENERIC_OK + 141 + 86-generic | already |
| `has_tower_crane` | YES | NO | YES | 1 (article 37) | construction exists; Official LEG manufacturing/building did not collect |
| `has_mobile_crane` | NO | NO | NO | 5 primary + 148 compound | new if committed |
| `has_jib_crane` | NO | NO | NO | 1 | new if committed |
| `has_gantry_crane` | NO | NO | NO | 1 | new if committed |
| `has_travelling_crane` | NO | NO | NO | HOLD/candidate 2 | new if committed |
| `has_slewing_crane` | NO | NO | NO | HOLD/candidate 1 | new if committed |
| `has_crane_without_operator_cab` | NO | NO | NO | 1 | new if committed |
| `has_hydraulic_crane` | NO | NO | NO | 2 (136, 148) | new if implemented; COMMITTED_IN_DESIGN |
| atomic operation facts (7) | NO | NO | NO | 37, 86, 139 travelling, 141 | future multi_select allowed; not implemented |
| passageway / runway context | NO | NO | NO | 139 travelling, 144 | HOLD |

Minimum change path remains unimplemented:

```text
LEG-only = article 37 mapped_field → existing has_tower_crane
  (still insufficient without atomic operations)
API / Canonical / UI = all 후보 facts if GPT commits them
Fixture / Sidecar = future; must not auto-fill subtype or operations
```

KEEP GENERIC_OK atoms do not remap `mapped_field`.

## 7. Open-before-launch target when only `has_crane=true`

| atom group | designed result |
|---|---|
| GENERIC_OK (137, 146 use, 168, 170) | may remain APPLICABLE on `has_crane` |
| Article 37 | not APPLICABLE; needs `has_tower_crane` and atomic tower operations |
| Article 141 | not APPLICABLE; needs atomic 141 verbs |
| Articles 138 / 139 gantry / 146 cabless / 147 / 149 / 150 | not APPLICABLE without that subtype fact |
| Article 136 | not APPLICABLE; needs `has_crane` AND `has_hydraulic_crane` |
| Article 148 | not APPLICABLE; needs `has_mobile_crane` AND `has_hydraulic_crane` |
| 139 travelling / 144 | REVIEW_REQUIRED / 미판정 (HOLD) |
| 86 both | not APPLICABLE without transporting-workers (and mobile for the mobile atom) |

## 8. Open questions (not CHG)

1. Article 139 travelling: GPT confirm C HOLD vs a frozen B layout-fact set once full statutory text (not truncated evidence) is available.
2. Article 144: commit a passageway context fact vs keep HOLD.
3. Article 37: whether `has_tower_crane` without operations may ever be APPLICABLE, or always REVIEW_REQUIRED.
4. Whether future UI multi_select is the collection surface for the seven atomic operation facts.
5. Construction AFTER sent `has_crane` not `has_tower_crane`; do not infer.
6. `applicability=APPLICABLE` vs `check_result=NOT_APPLICABLE` on 684 rows: deferred Observation.

GPT Freeze 판정 전까지 `DESIGN_FROZEN` / `IMPLEMENTATION_APPROVED` 를 쓰지 않는다.
