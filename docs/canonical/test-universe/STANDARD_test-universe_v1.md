---
wo: WO-TEST-UNIVERSE-001
class: normative
type: standard
scope: canonical
project: test-universe
title: TAI Safe Standard Test Universe (Industry Model + Contract Mapping)
version: 1
status: active
owner: taiwang
---

# STANDARD — TAI Safe Standard Test Universe

> WO-TEST-UNIVERSE-001. 모수(Universe)만 정의한다. **Expected/Golden/Engine검증/E2E 실행은 범위 밖.**
> 이후 WO-E2E-DATASET-001(Case 생성) → WO-E2E-001(실행) → WO-E2E-SEMANTIC-001(검토)가 이 Universe를 소비한다.

## STEP 1 — Contract Layer (실측 앵커)

### 1.1 Compiler (무료진단) — 5필드  [코드근거 services/canonical/adapters.py]
```
site_kind · scale · workers · region · sector
```

### 1.2 LEG Input Contract — 66필드 (active 24 / inactive 42)  [실측 leg-prod staging.requirement_input_contract_snapshot]
active(24): boiler_capacity_kw, building_use_type, gas_capacity_kg, has_asbestos_demo, has_blasting,
  has_boiler, has_chemical, has_chemical_substance, has_diving, has_emergency_broadcast, has_emergency_gen,
  has_fire_hydrant, has_gas, has_high_pressure_gas, has_safety_manager, has_smoke_control, has_sprinkler,
  has_tower_crane, has_water_tank, is_energy_intensive, is_multi_use, ksic_major, total_floor_area, worker_count
inactive(42): construction_type, has_asbestos, has_biological_agent, has_casting, has_central_hvac,
  has_concrete_work, has_confined_space, has_conveyor, has_cooling_tower, has_crane, has_demolition,
  has_dust_work, has_electric_work, has_elevator, has_excavation, has_forklift, has_gondola, has_grinding,
  has_hazardous_material, has_hazmat_storage, has_heat_treatment, has_high_place_work, has_high_pressure_work,
  has_injection, has_machinery, has_mech_parking, has_noise_work, has_oil_storage, has_painting, has_pile_work,
  has_plating, has_press, has_pressure_vessel, has_radiation, has_rolling, has_scaffold, has_septic_tank,
  has_steel_frame, has_subcontractor, has_temp_electric, has_welding, is_complex_building

> active=false 필드는 현재 LEG 출력을 구동하지 않으나, Universe는 전체에 매핑을 정의한다.
> 필드가 후에 활성화돼도 Case가 이미 값을 실어 나른다(재생성 불필요).

## STEP 2 — Taxonomy (고정 계층)

```
Sector      SEC   제조(SEC-MFG) · 건축물(SEC-BLD) · 건설(SEC-CON)
 Industry   IND   MFG: 자동차·조선·철강·식품·화학·반도체
                  BLD: 병원·호텔·아파트·물류센터·학교
                  CON: 토목·건축·플랜트·철도
  CompanyType CTP scale{small,medium,large} × workers 프로파일(밴드)
```

## STEP 3 — 산업 객체 (Object)

```
Facility  FAC(10) 공장·창고·옥외탱크·보일러·압력용기·크레인·승강기·변전실·소방시설·가스설비
Project   PRJ(7)  신축·증축·리모델링·철거·유지보수·배관공사·전기공사
Process   PROC(10) 용접·절단·도장·도금·열처리·프레스·사출·포장·혼합·건조
Task      TASK(9) 점검·정비·교체·운전·청소·검사·충전·운반·가동
Equipment EQP(10) 압력용기·보일러·크레인·지게차·승강기·컨베이어·집진기·변압기·수배전반·콤프레서
```

## STEP 4 — 표준 코드 (Code)

```
형식: <PREFIX>-<6digit>   (PREFIX ∈ SEC IND CTP FAC PRJ PROC TASK EQP)
예: FAC-000006(크레인) · PROC-000001(용접) · TASK-000006(검사) · EQP-000004(지게차)
Case: CASE-<6digit>
```

## STEP 5 & 6 — Leaf → Semantic → Contract (실측 field_code 앵커)

표기: `field` = 존재 매핑 · `∅semantic-only` = 계약필드 없음(risk modifier) · `GAP` = 개념 존재하나 계약필드 미존재(확장 후보)

### Facility
```
공장       → ManufacturingSite → ksic_major, building_use_type
창고       → StorageSite       → building_use_type, (has_forklift)
옥외탱크    → BulkStorage       → has_oil_storage, has_hazmat_storage, gas_capacity_kg
보일러     → HeatGeneration    → has_boiler, boiler_capacity_kw
압력용기    → PressureContainment → has_pressure_vessel
크레인     → Lifting           → has_crane, has_tower_crane
승강기     → VerticalTransport → has_elevator
변전실     → PowerDistribution → ∅ Coverage Gap  [GAP: has_substation 없음 · has_electric_work 임의연결 금지]
소방시설    → FireProtection    → has_sprinkler, has_fire_hydrant, has_smoke_control, has_emergency_broadcast, has_water_tank
가스설비    → GasSystem         → has_gas, has_high_pressure_gas, gas_capacity_kg
```

### Project
```
신축       → NewConstruction   → construction_type
증축       → Extension         → construction_type
리모델링    → Remodeling        → construction_type
철거       → Demolition        → has_demolition, has_asbestos_demo
유지보수    → Maintenance       → ∅semantic-only
배관공사    → Piping            → ∅ Coverage Gap  [GAP: has_piping 없음 · has_welding 임의연결 금지]
전기공사    → ElectricalWork    → has_electric_work, has_temp_electric
```

### Process
```
용접  → Welding/HotWork  → has_welding
절단  → Cutting/HotWork  → GAP: has_cutting 없음 (fire work 계열)
도장  → Painting         → has_painting
도금  → Plating          → has_plating
열처리 → HeatTreatment   → has_heat_treatment
프레스 → Pressing        → has_press
사출  → Injection        → has_injection
포장  → Packaging        → ∅semantic-only
혼합  → Mixing           → has_chemical, has_chemical_substance (화학 혼합 시)
건조  → Drying           → ∅semantic-only
```

### Task (대부분 risk modifier)
```
점검·검사 → Inspection → ∅semantic-only
정비·교체 → Maintenance → ∅semantic-only
운전·가동 → Operation → ∅semantic-only
청소 → Cleaning → has_confined_space (밀폐 청소 시) / else ∅
충전 → Charging → ∅semantic-only
운반 → Transport → has_forklift (지게차 운반 시) / else ∅
```

### Equipment
```
압력용기 → has_pressure_vessel
보일러   → has_boiler, boiler_capacity_kw
크레인   → has_crane, has_tower_crane
지게차   → has_forklift
승강기   → has_elevator
컨베이어 → has_conveyor
집진기   → has_dust_work
변압기   → PowerDistribution → ∅ Coverage Gap  [GAP: has_transformer 없음]
수배전반 → PowerDistribution → ∅ Coverage Gap  [GAP: has_switchgear 없음]
콤프레서 → PressureContainment → has_pressure_vessel (근접) / has_machinery
```

### Contract Coverage Gap (요약 — 향후 계약 확장 후보, 본 WO는 정의만)
```
has_substation · has_transformer · has_switchgear · has_piping · has_cutting
→ 변전실·변압기·수배전반·배관공사·절단은 정확 매핑 부재 → 계약 ∅ 유지.
원칙: GAP을 유사·상위 필드로 임의 연결하지 않는다(예: 변전실→has_electric_work 금지). Gap 자체가 자산.
```

## STEP 7 — Allowed Matrix (Sector × Object, ○/×)

```
              공장 압력용기 크레인 프레스 사출 도금  선박도크  터널  궤도
제조/자동차     ○    ○      ○     ○    ○    △     ×      ×    ×
제조/조선       ○    ○      ○     △    ×    △     ○      ×    ×
제조/반도체     ○    ○      △     ×    ○    ○     ×      ×    ×
건축물/병원     ×    △(보일러) △   ×    ×    ×     ×      ×    ×
건설/토목       ×    △      ○(타워) ×   ×    ×     ×      ○    ×
건설/철도       ×    △      ○     ×    ×    ×     ×      ○    ○
(△=조건부, 규칙은 matrix 파일에서 객체별 확장)
```
> 규칙: Sector→Industry→허용 Facility/Process/Equipment 집합을 정의. 불일치 조합(예: 자동차공장×선박도크)은 × → Case 생성에서 제외. 30k 폭발 방지의 핵심 제약.

## STEP 8 — 표준 Case 구조 (기대값 없음)

```
CASE-000001
  taxonomy : {sector, industry, company_type}
  objects  : {facility[], project[], process[], task[], equipment[]}
  contract : {                                  ← leaf→contract 매핑 산출값
     compiler: {site_kind, scale, workers, region, sector},
     leg:      {has_*: bool, worker_count, total_floor_area, ...}
  }
  metadata : {code, matrix_ref, contract_version, universe_version, generated_by}
  # expected / golden / risk / claim = 본 WO 범위 아님 (미포함)
```

## STEP 9 — Universe 무결성 검증 규칙

```
∀ Leaf:  Semantic 존재            → PASS (전 객체 semantic 부여됨)
∀ Semantic: Contract 매핑 존재 OR ∅semantic-only 선언 OR GAP 명시 → PASS
∀ 조합:  Allowed Matrix 지배        → PASS (matrix 밖 조합 금지)
GAP 목록: 명시적 기록(날조 0)        → 5건(substation/transformer/switchgear/piping/cutting)
```

## STEP 10 — Freeze 대상

```
Freeze: Taxonomy · Object 집합 · 표준 코드 규칙 · Leaf→Semantic · Semantic→Contract(+GAP) · Allowed Matrix 규칙 · Case Schema
Version: universe-v1
Baseline anchor: Compiler 5필드 + LEG 66필드(active 24/inactive 42) @ 실측 시점
```

## 완료 기준

```
입력 계약        PASS  (Compiler 5 + LEG 66 실측)
Taxonomy         PASS
Semantic Mapping PASS  (전 객체)
Contract Mapping PASS  (매핑 + ∅ + GAP 5건 명시)
Allowed Matrix   PASS  (규칙 정의)
Case Schema      PASS  (기대값 없이)
Universe Freeze  PASS
```

## 다음 WO (Universe Freeze 이후에만)
```
WO-E2E-DATASET-001 (Case 생성) → WO-E2E-001 (실행) → WO-E2E-SEMANTIC-001 (검토)
```
