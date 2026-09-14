---
wo: WO-E2E-INTEGRATION-DOC-REFRESH-001
class: records
type: status
scope: canonical
project: test-universe
title: E2E Integration Current Status
version: 1
status: active
owner: taiwang
updated_at: 2026-09-15
---

# E2E Integration Current Status

> 이 문서는 E2E 통합의 **현재 상태 SoT**다. `REPORT_review-003-semantic_v1.md`의 Observation 원문은 역사기록으로 유지하고, 해결 여부·현재 object·최신 검증 기준은 이 문서에서 갱신한다.
>
> 과거 BEFORE/AFTER 차이는 자동 Regression이 아니다. 현재 판정은 Official LEG full result, explicit canonical facts, semantic evidence를 기준으로 한다.

## 1. Current anchors

```text
TAI_API_REPO_MAIN = 2855091d5edd0dbcc8e558e4cd0cbd24ef66589a
TAI_API_E2E_BEHAVIORAL_ANCHOR = 8bc144ffbad4b0ac0717a748afd2bd12a7371001
LEG_MAIN = 46a07c1ac3c1d171eaad97bfb7a3c85b7d0c41d9
```

`TAI_API_REPO_MAIN`에는 E2E 통합 이후 다른 기능 변경이 포함되어 있다. E2E semantic closeout에서 마지막으로 확정된 API behavior anchor는 `8bc144ff...`다.

## 2. Frozen / certification baseline

E2E200 B1은 frozen baseline으로 유지한다.

```text
CERT3 = E2E200_CERT3_20260913T104300_KST
MECHANICAL = 200/200 PASS
GPT_SEMANTIC = 200/200 PASS
GPT_FINAL = KEEP
MATERIAL_REGRESSION = 0
NOT_JUDGABLE = 0

B1_MANIFEST_SHA256 = 7bb235800a37456b5f51fde0c57a92a9fa7a9df288e7a5f781b194f10ad201ab
B1_CASES_SHA256 = 4125a62f008f31585aba454aace3ef854401210464760f4a413dc8d5743d7ba4
APPROVED_SIDECAR_SHA256 = 301d62a012151f9a6e60d1eec6313374c8b502a307b541e1f89fe61fbc29e824
```

B1/Approved Sidecar/Runner는 silent modify 금지.

## 3. Observation lifecycle

| Observation | Current status | Current meaning |
|---|---|---|
| Obs007 | CLOSED | generic capability가 subtype/detail 의무를 자동 발동하던 계열 수정 완료 |
| Obs008 | CLOSED | 철거 generic 입력이 타 대상 철거 의무를 발동하던 문제 수정 완료 |
| Obs009 | OPEN | SaaS 작업 사실의 canonical applicability 표현/coverage 보완 진행 중 |
| Obs010 | CLOSED | `ksic_major` transport surplus 해소; KSIC/산업명칭은 LEG applicability에서 사용하지 않음 |
| Obs002 | NOT STARTED in current sequence | Obs009 종료 후 진행 |
| Obs005/006 | NOT STARTED in current sequence | Obs002 이후 |
| Obs001~006 historical revalidation | PENDING | 후속 sequence에서 재검증 |

Current sequence:

```text
Obs007 CLOSED
Obs008 CLOSED
Obs010 CLOSED
Obs009 OPEN
  current object = OBS009-A-CONFINED-SPACE
  current stage  = GPT_OBS009A_CONFINED_SPACE_DESIGN_VERIFY

NEXT AFTER OBS009 = OBS002_DUPLICATES
START = NO
```

## 4. Obs007 — CLOSED

Obs007은 하나의 `has_*` generic fact가 세부 설비형식·작업조건까지 자동으로 true 취급되는 문제였다.

최종 원칙:

```text
generic existence/capability != every subtype/detail true
missing != false
specific duty requires exact specific fact
```

### 4.1 Crane

- generic 4개 의무만 `has_crane` 유지.
- mobile/jib/gantry/hydraulic/crane-operation detail은 exact field로 분리.
- `has_crane=true`만으로 subtype/operation 의무 자동 발동 금지.

Final Live112:

```text
has_crane true = 38
CRANE_ROWS = 152 = 38 x 4
FORBIDDEN_SPECIFIC = 0
NO_CRANE_ROWS = 0
```

### 4.2 Elevator

- 산업용 lift와 건물 승강기를 분리.
- generic 4, subtype/config 5, operation 2, building elevator composite 1 구조.
- `has_elevator=true`만으로 특정 lift 형식/설치·조립·수리·검사·해체 의무 자동 발동 금지.

Final Live112:

```text
ELEVATOR_ROWS = 92
GENERIC4 = 23/23
FORBIDDEN_SPECIFIC = 0
```

### 4.3 Welding

- `has_welding` generic 입력으로 아세틸렌/가스집합/터널/고압 등 세부조건을 자동 발동하지 않음.
- exact welding fact로 분기.

Final Live112:

```text
WELDING_ROWS = 0
```

### 4.4 Dust work

- `has_dust_work` parent와 특정 분진원·설비·터널·환기조건을 분리.
- generic 유지 대상은 제한적으로만 남김.

Final Live112:

```text
DUST_ROWS = 3
```

### 4.5 Boiler

- generic boiler duty와 환기불충분 용접/불활성가스 배관 장소 등 detail condition을 분리.

Final Live112:

```text
BOILER_ROWS = 87
```

### 4.6 Pressure vessel

- 압력용기·공기압축기·회전체 위험·고압작업실/에어록 공급 조건을 분리.
- generic `has_pressure_vessel` 단독으로 모든 세부의무 발동 금지.

Final Live112:

```text
PRESSURE_VESSEL_ROWS = 14
```

Obs007 family regression anchor:

```text
CRANE = 152
ELEVATOR = 92
WELDING = 0
DUST = 3
BOILER = 87
PRESSURE_VESSEL = 14
```

## 5. Obs008 — CLOSED

철거 generic 입력이 어린이놀이시설 폐쇄·철거, 구조물 전도, 구조물 붕괴위험 같은 별도 semantic 조건을 대신하던 문제를 분리했다.

Approved exact facts:

```text
management_entity_bans_use_closes_or_demolishes_childrens_play_facility
performs_structure_toppling_work_during_demolition
has_structure_overturn_explosion_or_collapse_risk_due_to_loads_snow_wind_seismic_vibration_or_impact
```

`has_demolition`은 위 detail fact들의 alias가 아니다.

Merged anchors:

```text
LEG_PR_91_MERGE = f7632f0e8fb0b538853b7dad628098d851d325ee
API_PR_358_MERGE = da616f330166044e6f493b4833cf10662d062b5e
```

Final Live112:

```text
DEMOLITION_ROWS = 0
NON_TARGET_REGRESSION = 0
```

## 6. Obs010 — CLOSED

원 관측은 Manufacturing 46/46 Official request에 `ksic_major`가 있었고 LEG Runtime에서는 unknown field로 무시되고 있던 transport surplus였다.

Deep evidence 결과:

```text
INDUSTRY_EVIDENCE_CASE = C
industry_name in LEG input = NO
industry_name in effective vocabulary = NO
industry_name PSR rows = 0
industry_name Leaf count = 0
industry_name live trigger = 0
appendix3 derived from KSIC = NO
appendix3 derived from industry name = NO
```

최종 구조:

```text
KSIC / industry name
  -> SaaS classification / process-equipment registration
  -> NOT LEG applicability

LEGAL business classification
  -> explicit legal facts only
  -> appendix3_item_no / is_appendix3_* / is_construction / is_real_estate_management ...
```

`engine_context`에서도 `ksic_major`를 제거하고 `sector`만 유지했다.

Merged anchors:

```text
LEG_PR_93_MERGE = 46a07c1ac3c1d171eaad97bfb7a3c85b7d0c41d9
API_PR_361_MERGE = 8bc144ffbad4b0ac0717a748afd2bd12a7371001
```

Final Live112:

```text
ATTEMPTED / HTTP / HYDRATE = 112/112/112
Manufacturing context.sector = 46/46
context.ksic_major = 0/112
facility.ksic_major = 0/112
LEG unknown_fields.ksic_major = 0
industry_name LEG inflow = 0

other unknown unchanged:
  has_sprinkler = 20
  has_chemical = 4
  has_mech_parking = 4

OBLIGATION_REGRESSION = 0
CRANE = 152
ELEVATOR = 92
WELDING = 0
DUST = 3
BOILER = 87
PRESSURE_VESSEL = 14
DEMOLITION = 0
```

## 7. Obs009 — OPEN

초기 Observation은 Frozen `layers.work` 문자열이 Official LEG canonical applicability에 직접 표현되지 않는다는 것이었다.

조사 후 의미를 확장했다.

### 7.1 Frozen work는 production authority가 아님

```text
Frozen layers.work = E2E semantic display layer
Official raw work string profile count = 0/112
production source equivalent = NO
```

하지만 이것은 NO-FIX 근거가 아니다. 법령에서 작업 사실 자체가 parent trigger인 경우가 확인되었고, SaaS/LEG canonical contract가 비어 있거나 불완전한 것이 실제 gap이다.

### 7.2 Deep evidence conclusion

우선 작업군:

```text
밀폐공간작업
전기작업
용접작업
고소작업
화학물질취급작업
지게차작업
도장작업
유지보수작업
```

Deep evidence:

```text
confined-space legal rows = 32
has_confined_space atoms = 15
has_confined_space unique leaf = 1
has_confined_space=true -> applicable 15
field absent -> applicable 0

confined-space covered parent = 6
Art620 = PARTIAL
missing atom = 12
over-applied = 6

electric legal trigger rows = 9
electric canonical parent = NOT_FOUND
```

### 7.3 Current object — OBS009-A-CONFINED-SPACE

Semantic design is not implemented yet.

Frozen design proposal:

```text
has_confined_space
= 법령상 밀폐공간 장소 존재

performs_confined_space_work
= 근로자가 실제 밀폐공간 작업 수행

place true != work true
work true != every detail true
missing != false
```

Current design counts:

```text
LOCATION_DUTY = Art622(1 article / 2 atoms)
WORK_PARENT_DUTY = 10
WORK_PARENT_EXISTING_ATOMS = 7
WORK_PARENT_MISSING_ATOMS = 3
DETAIL_FIELD_PROPOSALS = 6
EXCEPTION_FIELD_PROPOSALS = 1
```

Proposed detail facts:

```text
confined_space_has_always_on_supply_exhaust_ventilation
oxygen_deficiency_or_hazardous_gas_fall_risk
oxygen_deficiency_or_hazardous_gas_asphyxiation_fire_or_explosion_risk
confined_space_work_with_exposed_live_parts_in_manhole_or_basement
work_in_basement_or_pit_with_piping_through_confined_space
performs_confined_space_rescue_work
```

Proposed exception fact:

```text
confined_space_ventilation_impracticable_due_to_explosion_oxidation_or_work_nature
```

Source state:

```text
factories.has_confined_space = location authority candidate only
SaaS work parent source = SOURCE_GAP
SaaS detail source = SOURCE_GAP
Official Live112 facility.has_confined_space absent = 112/112
```

No implementation has started for Obs009-A.

```text
CODE_CHANGE = 0
DB_WRITE = 0
PR = NONE
DEPLOY = 0
```

Current next gate:

```text
NEXT = GPT_OBS009A_CONFINED_SPACE_DESIGN_VERIFY
```

## 8. Input constitution carried forward

E2E semantic fixes now use the following input constitution.

```text
Layer 1: existence / parent fact
Layer 2: if present, exact subtype / work / detail facts

parent true != every detail true
missing != false
no display-string inference
no broad alias from generic fact to specific fact
```

Examples:

```text
has_crane=true
!= has_mobile_crane=true
!= crane_installation_work=true

has_confined_space=true
!= performs_confined_space_work=true

performs_confined_space_work=true
!= all confined-space hazard detail=true
```

## 9. Current regression anchors

Until Obs009-A implementation is approved, existing closed-object anchors remain:

```text
CRANE = 152
ELEVATOR = 92
WELDING = 0
DUST = 3
BOILER = 87
PRESSURE_VESSEL = 14
DEMOLITION = 0

KSIC context = 0/112
KSIC facility = 0/112
KSIC unknown = 0
```

Any future Obs009 change must preserve non-target counts unless the semantic design explicitly changes the corresponding object.

## 10. Documentation rule

- Historical Observation wording stays immutable.
- Current lifecycle/status is updated in this file.
- Per-object detailed evidence may live outside the repo during investigation, but closure/merge/live result must be summarized here.
- No observation is marked CLOSED until implementation/deploy/live semantic regression gate is satisfied when code change is required.
