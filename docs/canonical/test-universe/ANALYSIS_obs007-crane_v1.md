---
wo: WO-E2E-OBS007-CRANE-ANALYSIS-001
class: records
type: analysis
scope: canonical
project: test-universe
title: Obs-007 crane object analysis
version: 1
status: active
owner: taiwang
---

# ANALYSIS — Obs-007 object crane

WO = `WO-E2E-OBS007-CRANE-ANALYSIS-001`

ANALYSIS ONLY. Production mutation = 0. E2E rerun = 0. CHG = none. Legal verdict = not in this document.

OBJECT = `crane`
CANONICAL_INPUT = `has_crane`

## 1. Scope

This document investigates only:

```text
has_crane
crane
```

Not in this WO:

```text
has_elevator
has_welding
has_dust_work
has_boiler
has_pressure_vessel
Obs-008
Obs-009
Obs-010
```

Canonical Observation text in `REPORT_review-003-semantic_v1.md` Obs-007 is not rewritten here.

Question answered: what input was present, what was transported, under what recorded condition identifiers, and which crane obligations appeared in Official LEG AFTER `obligations_raw`.

## 2. Source anchors

Canonical Observation:

```text
docs/canonical/test-universe/REPORT_review-003-semantic_v1.md
Obs-007
```

Official LEG AFTER freeze used by that Observation (not later CORE22 revalidation bundles):

```text
local: /Users/taiwangsim/45cm-test/GPT_SEMANTIC_REVIEW_BUNDLE_112/
AFTER = AFTER_OFFICIAL_LEG_V1
AFTER checksum = 2ebfe2e907e2639485acea31484987a04894b1e00c5c86d7bcb8f73d9141b1e4
Frozen = Frozen/profile_universe_v1.json
UNIVERSE_SHA256 = 4818a63ab261c5a36c1432647b6b17e7636641071801d36fd1b85d1361af751b
request files = AFTER_OFFICIAL_LEG_V1/request/PF-*.json (112)
full_result files = AFTER_OFFICIAL_LEG_V1/full_result/PF-*.json (112)
```

BEFORE snapshots exist (`BEFORE_BASELINE_V1/snapshots`, e.g. PF-0001 = `SNAP-0001-001.json`) and are not the Official LEG AFTER request. They are not used as Runtime input for this lineage.

Engine identifiers observed on all 38 `has_crane=true` AFTER results:

```text
engine_family = LEG
engine_version = leg-runtime-v3
rule_source = leg-prod
fallback_used = False
provenance.freeze_signature = 15cd17e871b6885d34214c84a58adf47
provenance.repository_version = SEMREPO-CAL022-2026.07.20
provenance.release_version = SEMREPO-RC1-2026.07.20
```

IDs that do **not** appear on these crane `obligations_raw` rows (not invented):

```text
rule_id
requirement_id
condition_desc
predicate
crane_type
has_tower_crane (as supplied fact)
has_mobile_crane
has_jib_crane
has_gantry_crane
equipment_type
```

## 3. has_crane Profile inventory

### Q1 result

Official LEG request files with `form_data.has_crane=true`: **38**.

`has_crane=false`: **0**.

`has_crane` absent from `form_data`: **74**.

Total Official LEG request files scanned: **112**.

The 38 Profile IDs:

```text
PF-0001 PF-0002 PF-0003 PF-0004 PF-0005
PF-0012 PF-0013
PF-0028 PF-0030 PF-0031 PF-0032 PF-0034 PF-0036
PF-0040 PF-0041 PF-0042 PF-0043 PF-0044 PF-0045 PF-0046 PF-0047 PF-0048
PF-0059 PF-0060 PF-0061
PF-0066 PF-0067
PF-0071
PF-0078 PF-0079
PF-0094 PF-0096 PF-0097 PF-0099
PF-0101 PF-0103 PF-0104 PF-0108
```

Official request `sector` on these 38: MANUFACTURING 24, CONSTRUCTION 13, BUILDING 1 (PF-0108).

Frozen `layers.facility` on the same 38: `{"code":"has_crane","value":true}` present on 38/38. Frozen `has_crane=false`: 0.

Frozen facility codes containing `crane` other than `has_crane`: **0**.

Request `form_data` keys containing `crane` other than `has_crane`: **0** (38/38 and 74/74).

| profile_id | request sector | Frozen has_crane | request has_crane | leg_trace_id | other supplied crane facts |
|---|---|---|---|---|---|
| PF-0001 | MANUFACTURING | true | true | rtm-77d467136a20 | none supplied |
| PF-0002 | MANUFACTURING | true | true | rtm-d0592d95f9d7 | none supplied |
| PF-0003 | MANUFACTURING | true | true | rtm-8c9a5dfcdd6c | none supplied |
| PF-0004 | MANUFACTURING | true | true | rtm-a5aa3e25e2fd | none supplied |
| PF-0005 | MANUFACTURING | true | true | rtm-f9793fb141bc | none supplied |
| PF-0012 | MANUFACTURING | true | true | rtm-5d9d8b00b6e0 | none supplied |
| PF-0013 | MANUFACTURING | true | true | rtm-f8f55d342189 | none supplied |
| PF-0028 | CONSTRUCTION | true | true | rtm-f1c38d9c573d | none supplied |
| PF-0030 | CONSTRUCTION | true | true | rtm-84a718b6e36b | none supplied |
| PF-0031 | CONSTRUCTION | true | true | rtm-efd23b857670 | none supplied |
| PF-0032 | CONSTRUCTION | true | true | rtm-f7001f5a1f3d | none supplied |
| PF-0034 | CONSTRUCTION | true | true | rtm-46ac8caae125 | none supplied |
| PF-0036 | CONSTRUCTION | true | true | rtm-746a54d6af07 | none supplied |
| PF-0040 | MANUFACTURING | true | true | rtm-2c0578d8606a | none supplied |
| PF-0041 | MANUFACTURING | true | true | rtm-42bae44ae392 | none supplied |
| PF-0042 | MANUFACTURING | true | true | rtm-08c8be5d73ff | none supplied |
| PF-0043 | MANUFACTURING | true | true | rtm-55360546f432 | none supplied |
| PF-0044 | MANUFACTURING | true | true | rtm-6fb6914039eb | none supplied |
| PF-0045 | MANUFACTURING | true | true | rtm-5f6221e9c6cf | none supplied |
| PF-0046 | MANUFACTURING | true | true | rtm-046de4babf15 | none supplied |
| PF-0047 | MANUFACTURING | true | true | rtm-8dd3580af1ff | none supplied |
| PF-0048 | MANUFACTURING | true | true | rtm-14defcd1ea8d | none supplied |
| PF-0059 | MANUFACTURING | true | true | rtm-255cdae918a0 | none supplied |
| PF-0060 | MANUFACTURING | true | true | rtm-ae14305ab02b | none supplied |
| PF-0061 | MANUFACTURING | true | true | rtm-69fa00a3f511 | none supplied |
| PF-0066 | MANUFACTURING | true | true | rtm-2677f07e71ee | none supplied |
| PF-0067 | MANUFACTURING | true | true | rtm-d619470c4d35 | none supplied |
| PF-0071 | MANUFACTURING | true | true | rtm-13e78d6b2038 | none supplied |
| PF-0078 | MANUFACTURING | true | true | rtm-fdd81ec9ef0a | none supplied |
| PF-0079 | MANUFACTURING | true | true | rtm-3f9796fba36a | none supplied |
| PF-0094 | CONSTRUCTION | true | true | rtm-c78ae92d4a2b | none supplied |
| PF-0096 | CONSTRUCTION | true | true | rtm-7b97e9654d81 | none supplied |
| PF-0097 | CONSTRUCTION | true | true | rtm-0c967c3f06ba | none supplied |
| PF-0099 | CONSTRUCTION | true | true | rtm-c8a90ebc4b41 | none supplied |
| PF-0101 | CONSTRUCTION | true | true | rtm-5e42749fdadc | none supplied |
| PF-0103 | CONSTRUCTION | true | true | rtm-8a3140b89a26 | none supplied |
| PF-0104 | CONSTRUCTION | true | true | rtm-2edc857a1f73 | none supplied |
| PF-0108 | BUILDING | true | true | rtm-49cfd35ef8aa | none supplied | Frozen `sector=SPECIAL_FACILITY`; Official request `sector=BUILDING`

PF-0001 Frozen `layers.facility` original:

```text
{"code":"has_press","value":true}
{"code":"has_crane","value":true}
{"code":"has_forklift","value":true}
```

PF-0001 Official request `form_data` keys original:

```text
building_use_type, floor_count, has_crane, has_forklift, has_press, ksic_major, total_floor_area, worker_count
```

PF-0001 Official request crane path original:

```text
form_data.has_crane = True
```

## 4. subtype obligation inventory

### Classification method (keyword on AFTER evidence text)

Used only to label rows already present in `obligations_raw`. Not a legal classification.

| subtype | evidence token used |
|---|---|
| tower crane | `타워크레인` |
| mobile crane | `이동식 크레인` |
| jib crane | `지브 크레인` or `지브의` |
| gantry crane | `갠트리` |
| overhead/travelling crane | `주행 크레인` |
| generic crane | `크레인` without the subtype tokens above as exclusive primary, or remainder after subtype tokens |
| 기타 crane subtype | separate exclusive class not assigned; `선회 크레인` appears inside article 144 evidence (counted under overhead/travelling) |

Article 150 evidence contains both `이동식 크레인` and `지브의`. That atom is counted in **both** jib and mobile (non-exclusive). All other 17 atoms have exactly one subtype label.

### Unique atom set S1 (18 atoms)

All 38 `has_crane=true` Profiles emit the same 18 `atom_id` set. 38 × 18 = **684** `obligations_raw` rows.

Law name on all 18: `산업안전보건기준에 관한 규칙`.

`applicability=APPLICABLE` and `check_result=NOT_APPLICABLE` on all 684 rows (recorded as stored fields; not judged here).

`mapped_field=has_crane` and `triggered_by=["has_crane"]` on all 684 rows.

| atom_id | law_article | subtype label | evidence (original) |
|---|---|---|---|
| `5aec15bb-9ba9-5d54-87db-13dcacf41cf9` | 37 | tower crane | 사업주는 순간풍속이 초당 10미터를 초과하는 경우 타워크레인의 설치ㆍ수리ㆍ점검 또는 해체 작업을 중지하여야 하며 |
| `16ce5107-52c3-5e80-80b7-8c54ca0caf94` | 86 | mobile crane | 사업주는 이동식 크레인을 사용하여 근로자를 운반하거나 |
| `c924dad5-4d8f-5f2d-b0e8-6d537f75a087` | 86 | generic crane | 사업주는 크레인을 사용하여 근로자를 운반하거나 |
| `84001932-7ef6-5789-885f-34913213e810` | 136 | jib crane | 사업주는 유압을 동력으로 사용하는 크레인의 과도한 압력상승을 방지하기 위한 안전밸브에 대하여 정격하중(지브 크레인은 최대의 정격하중으로 한다)을 건 때의 압력 이하로 작동되도록 조정하여야 한다. |
| `63092974-a3c8-556a-b855-cbe3be96dee5` | 137 | generic crane | 그 크레인을 사용하여 짐을 운반하는 경우 |
| `2437c873-e072-5c12-9257-21ee2a4a5a30` | 138 | jib crane | 사업주는 지브 크레인을 사용하여 작업을 하는 경우에 크레인 명세서에 적혀 있는 지브의 경사각(인양하중이 3톤 미만인 지브 크레인의 경우에는 제조한 자가 지정한 지브의 경사각)의 범위에서 사용하도록 하여야 한다. |
| `44b2d064-d1f1-52a8-9c2a-ccbcc17ac3bc` | 139 | gantry crane | 사업주는 갠트리 크레인 등과 같이 작업장 바닥에 고정된 레일을 따라 주행하는 크레인의 새들(saddle) 돌출부와 주변 구조물 사이의 안전공간이 40센티미터 이상 되도록 바닥에 표시를 하는 등 안전공간을 확보하여야 한다. |
| `fe7a74bc-57a2-5b05-b489-360b08ba92b5` | 139 | overhead/travelling crane | 사업주는 같은 주행로에 병렬로 설치되어 있는 주행 크레인의 수리ㆍ조정 및 점검 등의 작업을 하는 경우, 주행로상이나 그 밖에 주행 크레인이 근로자와 접촉할 우려가 있는 장소에서 작업을 하는 경우 등에 주행 크레인끼리 충돌하거나 |
| `4aa68025-0522-5207-9c57-21595543c3c9` | 141 | generic crane | 사업주는 크레인의 설치ㆍ조립ㆍ수리ㆍ점검 또는 해체 작업을 하는 경우 다음 각 호의 조치를 하여야 한다. |
| `440d4db1-232c-50b7-8971-6409629728e0` | 144 | overhead/travelling crane | 사업주는 주행 크레인 또는 선회 크레인과 건설물 또는 설비와의 사이에 통로를 설치하는 경우 그 폭을 0.6미터 이상으로 하여야 한다. |
| `95bdc756-b7c7-5839-84a7-ee1688be09aa` | 146 | generic crane | 사업주는 크레인을 사용하여 작업을 하는 경우 다음 각 호의 조치를 준수하고 |
| `a20d913d-52a7-5425-bb2c-8c2d91b1b5a8` | 146 | generic crane | 사업주는 조종석이 설치되지 아니한 크레인에 대하여 다음 각 호의 조치를 하여야 한다. |
| `d788dd1e-8b22-5328-ad28-849a3b5ce3ab` | 147 | mobile crane | 사업주는 이동식 크레인을 사용하는 경우에 그 이동식 크레인이 넘어지거나 그 이동식 크레인의 구조 부분을 구성하는 강재 등이 변형되거나 부러지는 일 등을 방지하기 위하여 해당 이동식 크레인의 설계기준(제조자가 제공하는 사용설명서)을 준수하여야 한다. |
| `1e7527a6-2e7e-5b9e-81b0-bcc4562e9644` | 148 | mobile crane | 사업주는 유압을 동력으로 사용하는 이동식 크레인의 과도한 압력상승을 방지하기 위한 안전밸브에 대하여 최대의 정격하중을 건 때의 압력 이하로 작동되도록 조정하여야 한다. |
| `d018d484-e92a-5588-b8b2-44e6b7e70955` | 149 | mobile crane | 사업주는 이동식 크레인을 사용하여 하물을 운반하는 경우에는 해지장치를 사용하여야 한다. |
| `17b44c74-9e68-5b7a-9b5c-216cb3c86ed2` | 150 | jib crane + mobile crane | 사업주는 이동식 크레인을 사용하여 작업을 하는 경우 이동식 크레인 명세서에 적혀 있는 지브의 경사각(인양하중이 3톤 미만인 이동식 크레인의 경우에는 제조한 자가 지정한 지브의 경사각)의 범위에서 사용하도록 하여야 한다. |
| `5b9a8f66-4e0f-58bb-acdf-23c80b3b6c63` | 168 | mobile crane | 사업주는 훅ㆍ샤클ㆍ클램프 및 링 등의 철구로서 변형되어 있는 것 또는 균열이 있는 것을 크레인 또는 이동식 크레인의 고리걸이용구로 사용해서는 아니 된다. |
| `ea92a57d-be66-5d07-bdab-eb032faac006` | 170 | mobile crane | 사업주는 엔드리스(endless)가 아닌 와이어로프 또는 달기 체인에 대하여 그 양단에 훅ㆍ샤클ㆍ링 또는 고리를 구비한 것이 아니면 크레인 또는 이동식 크레인의 고리걸이용구로 사용해서는 아니 된다. |

PF-0001 tower-crane `obligation_detail` original fields:

```text
who = 사업주
what = 사업주는 순간풍속이 초당 10미터를 초과하는 경우 타워크레인의 설치ㆍ수리ㆍ점검 또는 해체 작업을 중지하여야 하며
condition = 사업주는 순간풍속이 초당 10미터를 초과하는 경우
```

`obligation_detail.condition` is Korean obligation text, not an engine predicate identifier.

## 5. input → result lineage

Observed chain for all 38 Profiles / all 684 crane rows:

```text
Frozen layers.facility {code:has_crane, value:true}
→ Official LEG request form_data.has_crane=true
→ AFTER contract.active_fields includes has_crane (38/38)
→ AFTER facility_used.has_crane=true (38/38)
→ LEG rule_source=leg-prod engine_family=LEG engine_version=leg-runtime-v3
→ obligations_raw.mapped_field=has_crane
→ obligations_raw.triggered_by=["has_crane"]
→ atom_id + law_name + law_article + evidence
→ AFTER full_result.obligations_raw
```

PF-0001 contract excerpts original:

```text
contract.active_fields includes has_crane
contract.missing_fields includes has_tower_crane
facility_used.has_crane = true
leg_trace_id = rtm-77d467136a20
```

`has_tower_crane` appears in `contract.missing_fields` for **112/112** Profiles (38 with `has_crane=true` and 74 without). It is listed as missing, not as a supplied Runtime fact.

No AFTER crane obligation row contains `rule_id` or engine `condition_desc` / `predicate`.

### Comparison matrix (profile × lineage)

Identical crane obligation set S1 on every row. `other crane facts` = no supplied subtype field.

| profile_id | has_crane | other crane facts | obligation subtype | law/article | matched id | lineage status |
|---|---:|---|---|---|---|---|
| PF-0001 | true | none (request `form_data.has_crane=true` only) | tower + mobile + generic + jib + gantry + overhead/travelling (18 atoms, set S1) | 산업안전보건기준에 관한 규칙 37/86/136/137/138/139/141/144/146/147/148/149/150/168/170 | S1 (18 atom_id) | A |
| PF-0002 | true | none (request `form_data.has_crane=true` only) | tower + mobile + generic + jib + gantry + overhead/travelling (18 atoms, set S1) | 산업안전보건기준에 관한 규칙 37/86/136/137/138/139/141/144/146/147/148/149/150/168/170 | S1 (18 atom_id) | A |
| PF-0003 | true | none (request `form_data.has_crane=true` only) | tower + mobile + generic + jib + gantry + overhead/travelling (18 atoms, set S1) | 산업안전보건기준에 관한 규칙 37/86/136/137/138/139/141/144/146/147/148/149/150/168/170 | S1 (18 atom_id) | A |
| PF-0004 | true | none (request `form_data.has_crane=true` only) | tower + mobile + generic + jib + gantry + overhead/travelling (18 atoms, set S1) | 산업안전보건기준에 관한 규칙 37/86/136/137/138/139/141/144/146/147/148/149/150/168/170 | S1 (18 atom_id) | A |
| PF-0005 | true | none (request `form_data.has_crane=true` only) | tower + mobile + generic + jib + gantry + overhead/travelling (18 atoms, set S1) | 산업안전보건기준에 관한 규칙 37/86/136/137/138/139/141/144/146/147/148/149/150/168/170 | S1 (18 atom_id) | A |
| PF-0012 | true | none (request `form_data.has_crane=true` only) | tower + mobile + generic + jib + gantry + overhead/travelling (18 atoms, set S1) | 산업안전보건기준에 관한 규칙 37/86/136/137/138/139/141/144/146/147/148/149/150/168/170 | S1 (18 atom_id) | A |
| PF-0013 | true | none (request `form_data.has_crane=true` only) | tower + mobile + generic + jib + gantry + overhead/travelling (18 atoms, set S1) | 산업안전보건기준에 관한 규칙 37/86/136/137/138/139/141/144/146/147/148/149/150/168/170 | S1 (18 atom_id) | A |
| PF-0028 | true | none (request `form_data.has_crane=true` only) | tower + mobile + generic + jib + gantry + overhead/travelling (18 atoms, set S1) | 산업안전보건기준에 관한 규칙 37/86/136/137/138/139/141/144/146/147/148/149/150/168/170 | S1 (18 atom_id) | A |
| PF-0030 | true | none (request `form_data.has_crane=true` only) | tower + mobile + generic + jib + gantry + overhead/travelling (18 atoms, set S1) | 산업안전보건기준에 관한 규칙 37/86/136/137/138/139/141/144/146/147/148/149/150/168/170 | S1 (18 atom_id) | A |
| PF-0031 | true | none (request `form_data.has_crane=true` only) | tower + mobile + generic + jib + gantry + overhead/travelling (18 atoms, set S1) | 산업안전보건기준에 관한 규칙 37/86/136/137/138/139/141/144/146/147/148/149/150/168/170 | S1 (18 atom_id) | A |
| PF-0032 | true | none (request `form_data.has_crane=true` only) | tower + mobile + generic + jib + gantry + overhead/travelling (18 atoms, set S1) | 산업안전보건기준에 관한 규칙 37/86/136/137/138/139/141/144/146/147/148/149/150/168/170 | S1 (18 atom_id) | A |
| PF-0034 | true | none (request `form_data.has_crane=true` only) | tower + mobile + generic + jib + gantry + overhead/travelling (18 atoms, set S1) | 산업안전보건기준에 관한 규칙 37/86/136/137/138/139/141/144/146/147/148/149/150/168/170 | S1 (18 atom_id) | A |
| PF-0036 | true | none (request `form_data.has_crane=true` only) | tower + mobile + generic + jib + gantry + overhead/travelling (18 atoms, set S1) | 산업안전보건기준에 관한 규칙 37/86/136/137/138/139/141/144/146/147/148/149/150/168/170 | S1 (18 atom_id) | A |
| PF-0040 | true | none (request `form_data.has_crane=true` only) | tower + mobile + generic + jib + gantry + overhead/travelling (18 atoms, set S1) | 산업안전보건기준에 관한 규칙 37/86/136/137/138/139/141/144/146/147/148/149/150/168/170 | S1 (18 atom_id) | A |
| PF-0041 | true | none (request `form_data.has_crane=true` only) | tower + mobile + generic + jib + gantry + overhead/travelling (18 atoms, set S1) | 산업안전보건기준에 관한 규칙 37/86/136/137/138/139/141/144/146/147/148/149/150/168/170 | S1 (18 atom_id) | A |
| PF-0042 | true | none (request `form_data.has_crane=true` only) | tower + mobile + generic + jib + gantry + overhead/travelling (18 atoms, set S1) | 산업안전보건기준에 관한 규칙 37/86/136/137/138/139/141/144/146/147/148/149/150/168/170 | S1 (18 atom_id) | A |
| PF-0043 | true | none (request `form_data.has_crane=true` only) | tower + mobile + generic + jib + gantry + overhead/travelling (18 atoms, set S1) | 산업안전보건기준에 관한 규칙 37/86/136/137/138/139/141/144/146/147/148/149/150/168/170 | S1 (18 atom_id) | A |
| PF-0044 | true | none (request `form_data.has_crane=true` only) | tower + mobile + generic + jib + gantry + overhead/travelling (18 atoms, set S1) | 산업안전보건기준에 관한 규칙 37/86/136/137/138/139/141/144/146/147/148/149/150/168/170 | S1 (18 atom_id) | A |
| PF-0045 | true | none (request `form_data.has_crane=true` only) | tower + mobile + generic + jib + gantry + overhead/travelling (18 atoms, set S1) | 산업안전보건기준에 관한 규칙 37/86/136/137/138/139/141/144/146/147/148/149/150/168/170 | S1 (18 atom_id) | A |
| PF-0046 | true | none (request `form_data.has_crane=true` only) | tower + mobile + generic + jib + gantry + overhead/travelling (18 atoms, set S1) | 산업안전보건기준에 관한 규칙 37/86/136/137/138/139/141/144/146/147/148/149/150/168/170 | S1 (18 atom_id) | A |
| PF-0047 | true | none (request `form_data.has_crane=true` only) | tower + mobile + generic + jib + gantry + overhead/travelling (18 atoms, set S1) | 산업안전보건기준에 관한 규칙 37/86/136/137/138/139/141/144/146/147/148/149/150/168/170 | S1 (18 atom_id) | A |
| PF-0048 | true | none (request `form_data.has_crane=true` only) | tower + mobile + generic + jib + gantry + overhead/travelling (18 atoms, set S1) | 산업안전보건기준에 관한 규칙 37/86/136/137/138/139/141/144/146/147/148/149/150/168/170 | S1 (18 atom_id) | A |
| PF-0059 | true | none (request `form_data.has_crane=true` only) | tower + mobile + generic + jib + gantry + overhead/travelling (18 atoms, set S1) | 산업안전보건기준에 관한 규칙 37/86/136/137/138/139/141/144/146/147/148/149/150/168/170 | S1 (18 atom_id) | A |
| PF-0060 | true | none (request `form_data.has_crane=true` only) | tower + mobile + generic + jib + gantry + overhead/travelling (18 atoms, set S1) | 산업안전보건기준에 관한 규칙 37/86/136/137/138/139/141/144/146/147/148/149/150/168/170 | S1 (18 atom_id) | A |
| PF-0061 | true | none (request `form_data.has_crane=true` only) | tower + mobile + generic + jib + gantry + overhead/travelling (18 atoms, set S1) | 산업안전보건기준에 관한 규칙 37/86/136/137/138/139/141/144/146/147/148/149/150/168/170 | S1 (18 atom_id) | A |
| PF-0066 | true | none (request `form_data.has_crane=true` only) | tower + mobile + generic + jib + gantry + overhead/travelling (18 atoms, set S1) | 산업안전보건기준에 관한 규칙 37/86/136/137/138/139/141/144/146/147/148/149/150/168/170 | S1 (18 atom_id) | A |
| PF-0067 | true | none (request `form_data.has_crane=true` only) | tower + mobile + generic + jib + gantry + overhead/travelling (18 atoms, set S1) | 산업안전보건기준에 관한 규칙 37/86/136/137/138/139/141/144/146/147/148/149/150/168/170 | S1 (18 atom_id) | A |
| PF-0071 | true | none (request `form_data.has_crane=true` only) | tower + mobile + generic + jib + gantry + overhead/travelling (18 atoms, set S1) | 산업안전보건기준에 관한 규칙 37/86/136/137/138/139/141/144/146/147/148/149/150/168/170 | S1 (18 atom_id) | A |
| PF-0078 | true | none (request `form_data.has_crane=true` only) | tower + mobile + generic + jib + gantry + overhead/travelling (18 atoms, set S1) | 산업안전보건기준에 관한 규칙 37/86/136/137/138/139/141/144/146/147/148/149/150/168/170 | S1 (18 atom_id) | A |
| PF-0079 | true | none (request `form_data.has_crane=true` only) | tower + mobile + generic + jib + gantry + overhead/travelling (18 atoms, set S1) | 산업안전보건기준에 관한 규칙 37/86/136/137/138/139/141/144/146/147/148/149/150/168/170 | S1 (18 atom_id) | A |
| PF-0094 | true | none (request `form_data.has_crane=true` only) | tower + mobile + generic + jib + gantry + overhead/travelling (18 atoms, set S1) | 산업안전보건기준에 관한 규칙 37/86/136/137/138/139/141/144/146/147/148/149/150/168/170 | S1 (18 atom_id) | A |
| PF-0096 | true | none (request `form_data.has_crane=true` only) | tower + mobile + generic + jib + gantry + overhead/travelling (18 atoms, set S1) | 산업안전보건기준에 관한 규칙 37/86/136/137/138/139/141/144/146/147/148/149/150/168/170 | S1 (18 atom_id) | A |
| PF-0097 | true | none (request `form_data.has_crane=true` only) | tower + mobile + generic + jib + gantry + overhead/travelling (18 atoms, set S1) | 산업안전보건기준에 관한 규칙 37/86/136/137/138/139/141/144/146/147/148/149/150/168/170 | S1 (18 atom_id) | A |
| PF-0099 | true | none (request `form_data.has_crane=true` only) | tower + mobile + generic + jib + gantry + overhead/travelling (18 atoms, set S1) | 산업안전보건기준에 관한 규칙 37/86/136/137/138/139/141/144/146/147/148/149/150/168/170 | S1 (18 atom_id) | A |
| PF-0101 | true | none (request `form_data.has_crane=true` only) | tower + mobile + generic + jib + gantry + overhead/travelling (18 atoms, set S1) | 산업안전보건기준에 관한 규칙 37/86/136/137/138/139/141/144/146/147/148/149/150/168/170 | S1 (18 atom_id) | A |
| PF-0103 | true | none (request `form_data.has_crane=true` only) | tower + mobile + generic + jib + gantry + overhead/travelling (18 atoms, set S1) | 산업안전보건기준에 관한 규칙 37/86/136/137/138/139/141/144/146/147/148/149/150/168/170 | S1 (18 atom_id) | A |
| PF-0104 | true | none (request `form_data.has_crane=true` only) | tower + mobile + generic + jib + gantry + overhead/travelling (18 atoms, set S1) | 산업안전보건기준에 관한 규칙 37/86/136/137/138/139/141/144/146/147/148/149/150/168/170 | S1 (18 atom_id) | A |
| PF-0108 | true | none (request `form_data.has_crane=true` only) | tower + mobile + generic + jib + gantry + overhead/travelling (18 atoms, set S1) | 산업안전보건기준에 관한 규칙 37/86/136/137/138/139/141/144/146/147/148/149/150/168/170 | S1 (18 atom_id) | A |

### Subtype aggregate

Counts are non-exclusive (article 150 is in both jib and mobile). Profile count for each subtype = 38 because S1 is identical.

| subtype | profile count | obligation count | generic-only trigger observed |
|---|---:|---:|---|
| tower crane | 38 | 38 | YES (`triggered_by=["has_crane"]` only) |
| mobile crane | 38 | 266 | YES |
| generic crane | 38 | 190 | YES |
| jib crane | 38 | 114 | YES |
| gantry crane | 38 | 38 | YES |
| overhead/travelling crane | 38 | 76 | YES |
| 기타 crane subtype (exclusive extra class) | 0 | 0 | n/a |

Exclusive atom counts (article 150 counted once as dual, not split): tower 1, gantry 1, travelling 2, jib-only 2, mobile-only 6, generic 5, dual jib+mobile 1. Times 38 Profiles = 684 rows.

LINEAGE_CLASS on every row:

```text
A = 684 / 684
B = 0
C = 0
D = 0
```

A means: in the stored lineage, generic `has_crane` alone is the recorded trigger. This is an observation of identifiers, not a verdict that A is incorrect.

## 6. negative/control evidence

Control set = 74 Official LEG Profiles where request `form_data.has_crane` is absent (not false).

Scan of those 74 AFTER `obligations_raw` evidence strings for:

```text
타워크레인
타워 크레인
지브 크레인
갠트리
주행 크레인
이동식 크레인
```

Hits: **0** Profiles, **0** rows.

Scan of the same 74 for any evidence containing `크레인`: **0**.

NEGATIVE_CONTROL = PASS.

`has_crane` absent ↔ no observed tower/mobile/jib/gantry/travelling (or generic crane) obligation in this AFTER freeze.

This does not by itself prove a legal rule. It records correlation in this freeze only.

## 7. Q1–Q5 결과

### Q1

```text
HAS_CRANE_PROFILE_COUNT = 38
has_crane=false = 0
has_crane absent = 74
IDs = PF-0001 PF-0002 PF-0003 PF-0004 PF-0005 PF-0012 PF-0013 PF-0028 PF-0030 PF-0031 PF-0032 PF-0034 PF-0036 PF-0040 PF-0041 PF-0042 PF-0043 PF-0044 PF-0045 PF-0046 PF-0047 PF-0048 PF-0059 PF-0060 PF-0061 PF-0066 PF-0067 PF-0071 PF-0078 PF-0079 PF-0094 PF-0096 PF-0097 PF-0099 PF-0101 PF-0103 PF-0104 PF-0108
```

### Q2

```text
38/38 emit crane obligations
unique atoms = 18
obligation rows = 684
subtypes present on every has_crane=true Profile:
  generic crane
  tower crane
  mobile crane
  jib crane
  gantry crane
  overhead/travelling crane
기타 exclusive subtype rows = 0
law = 산업안전보건기준에 관한 규칙
```

### Q3

Supplied Runtime / request / Frozen facility crane facts on the 38:

```text
has_crane=true
has_tower_crane = not supplied
has_mobile_crane = not supplied
crane_type = not present
equipment_type = not present
facility subtype field = not present
```

`has_tower_crane` exists only as `contract.missing_fields` (112/112), not as an input value.

### Q4

Lineage identifiers that exist are recorded in §5. Identifiers that do not exist were not created.

Per-Profile `leg_trace_id` values are in §3.

### Q5

```text
LINEAGE_CLASS = A
A = 684 rows / 38 Profiles / all listed subtypes
B = 0
C = 0
D = 0
```

A is recorded because `mapped_field` and `triggered_by` contain only `has_crane`. No second supplied crane fact is on the request or `facility_used`.

## 8. Evidence sufficiency

Sufficient to answer Q1–Q5 from Official LEG AFTER request + full_result + Frozen facility:

```text
profile inventory
identical 18-atom set
trigger field
negative control
```

Not present in this freeze (limits engine-internal reconstruction, does not block Q5 class A on stored identifiers):

```text
rule_id
requirement_id
engine predicate / condition_desc on these APPLICABLE crane atoms
```

## 9. Open questions

These are unanswered here. They are not CHG items.

1. Why `applicability=APPLICABLE` and `check_result=NOT_APPLICABLE` coexist on all 684 crane rows is not explained by identifiers in this freeze.
2. Engine-internal predicate text for these atoms is not in `obligations_raw`.
3. `rule_id` / `requirement_id` are absent; atom_id is the matched id that exists.
4. `has_tower_crane` is named in `missing_fields` for 112/112; this WO does not interpret that contract list as a supplied fact.
5. PF-0108 Frozen `sector=SPECIAL_FACILITY` vs Official request `sector=BUILDING` is recorded as inventory fact only; not analyzed as Obs-010.
