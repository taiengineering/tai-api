# SAFE LEG — INDUSTRIAL / CONSTRUCTION RELEASE BASELINE (2026-09-03)

> index / handoff 문서. 이 문서는 authority(SoT)가 아니다.
> CODE SoT = 각 repo current code · LEGAL SoT = leg · DB evidence = 실측 production.
> BUILDING 판정은 반드시 실제 code + DB + frontend 재실측으로 한다.

## 0. GLOBAL INVARIANTS
- LEGAL SoT = leg. prj 법령 조사 금지.
- GPT = 설계/작업지시/독립검증. Claude = 실행/조사.
- Official LEG pipeline: run_leg_diagnosis -> build_facility -> evaluate_rtm(/rtm/evaluate)
- legacy v510/compiler = 공식 SAFE LEG wiring authority 아님.
- SAFE 원칙: 보유값 재질문 금지. 미보유값만 runtime override 후보.
- None/missing != false/0/[]/OTHER. false/0 = 명시적 유효 입력.
- PAYMENT = OUT OF SCOPE.

## 1. INDUSTRIAL RELEASE BASELINE
상태: BACKEND = LIVE/CLOSED · FRONTEND = MERGED+DEPLOYED/CLOSED · CANARY = DEFERRED.
Git: tai-api #238(LEG backend+firewall) #242(factory_materials) #243(assembler COMPAT-002) · tai-admin #59(missing7 UI) #60(->industrial-leg).

canonical exact29 (MKT_IND_PAID_CONTRACT_V1):
address, ksic_major, worker_count, total_floor_area, floor_count, basement_count,
building_use_type, built_year, main_structure, has_safety_manager, electric_capacity,
has_boiler, has_chemical_substance, has_high_pressure_gas, gas_capacity_kg, elevator_count,
annual_energy_toe, work_height_m, has_truck_loading_unloading, truck_loading_height_m,
has_manual_heavy_handling, manual_handling_weight_kg, material_profile, business_activity_types,
building_qualifications, regulated_facility_types, hazardous_work_environments, process_list, equipment_list

LEG EXPECTED14: ksic_major, worker_count, total_floor_area, building_use_type, has_safety_manager,
has_boiler, has_chemical, has_high_pressure_gas, gas_capacity_kg, work_height_m,
has_truck_loading_unloading, truck_loading_height_m, has_manual_heavy_handling, manual_handling_weight_kg
alias: SAFE has_chemical_substance -> LEG has_chemical

SAFE override exact13: ksic_major, worker_count, electric_capacity, has_high_pressure_gas,
has_chemical_substance, has_boiler, building_use_type, has_safety_manager, work_height_m,
has_truck_loading_unloading, truck_loading_height_m, has_manual_heavy_handling, manual_handling_weight_kg
규칙: undefined/None = override 없음. false/0 = explicit override.

factory_materials(신규 asset, 복원 아님) V1: id, factory_id, material_name, material_category_code,
handling_mode_codes, is_active, created_at.
의미: material_category_code NULL -> unresolved 가능. handling_mode_codes NULL != []. 0 active rows -> known-none.
원칙: physical column 없음 != DB NULL. 없는 source는 UNRESOLVED(정상 NULL 위장 금지).

## 2. CONSTRUCTION RELEASE BASELINE
상태: BACKEND = LIVE/CLOSED · FRONTEND = MERGED+DEPLOYED/CLOSED.
Git: tai-api #244(construction-leg) · tai-admin #55(extraction hub) #61(LEG wiring +PATCH-1/2/3).
backend release anchor: tai-api 144fdf08d4e5fc842f69c6b7ab568eebfc1bdc18 (이후 main 전진해도 이 SHA 기록).
frontend release: tai-admin main 4243b40b24685ce7e6bd1049b18c34a9f89c6b0b ·
  CF Pages taieng-tadmin/production deployment 6801bd2d-9b15-4813-b133-4f5eb7de09ea ·
  build SUCCESS · deploy SUCCESS · safe.taieng.co.kr alias PRESENT.

canonical exact27 (MKT_CST_PAID_CONTRACT_V1):
project_amount, worker_count, construction_type, project_address, has_subcontractor,
subcontractor_count, process_list, has_excavation, has_demolition, work_height_m,
has_truck_loading_unloading, has_tower_crane, truck_loading_height_m, has_manual_heavy_handling,
manual_handling_weight_kg, has_confined_space, has_asbestos_demo, has_blasting, has_diving,
has_asbestos, has_chemical_substance, has_gas, has_high_pressure_gas, has_water_tank,
is_energy_intensive, is_multi_use, subcontractor

DIRECT_EXACT4: worker_count<-construction_sites.total_workers · construction_type<-site_type(RAW code) ·
  project_address<-site_address · project_amount<-contract_amount(억 RAW, 단위변환 금지).

RUNTIME20 (override allowlist = request schema exact-set):
has_excavation, has_demolition, has_tower_crane, has_confined_space, has_asbestos_demo,
has_blasting, has_diving, work_height_m, has_truck_loading_unloading, truck_loading_height_m,
has_manual_heavy_handling, manual_handling_weight_kg, has_chemical_substance, has_subcontractor,
has_asbestos, has_gas, has_high_pressure_gas, has_water_tank, is_energy_intensive, is_multi_use

NON-RUNTIME UNRESOLVED3: subcontractor_count, process_list, subcontractor.
금지: subcon_workers>0 -> has_subcontractor 자동추론 금지. distinct count -> subcontractor_count 금지.

state machine: PHASE1 legacy /construction/sites/{id}/diagnose (factory bridge/session/side effects) ->
  PHASE2 /legal-engine/diagnose/construction-leg (공식 Step1). 정상: legacy success -> factory_id ->
  construction-leg -> HTTP 2xx + outer.status=success -> Step2. LEG 실패: Step2 BLOCK, retry=LEG only, legacy 재호출 0.
session integrity: PATCH-1(tristate sentinel/LEG-only retry/memory reset/factory fail-closed) ·
  PATCH-2(cross-site localStorage reset) · PATCH-3(same-site diagnosis_id stale 제거).
SPECIALTY/PLANT: RAW PASS-THROUGH/FROZEN. construction_type LEG 소비 확정 전 신규 매핑 금지.

## 3. CROSS-SECTOR FIREWALL
BUILDING N1 sector-specific exact32 는 sector=="BUILDING" 일 때만 build_facility 통과
(WO-FIX-BUILDFACILITY-SECTOR-GATE-001, test-lock PR #240). 공유축 building_use_type 은 exact32 제외(base 공용).

exact32:
floor_count, building_height_m, floor_area_sum_at_or_above_11f, performance_use_floor_area_sum,
cantilever_projection_m, column_span_m, flat_plate_column_section_ratio, occupancy_capacity,
underground_connection_entrance_distance_m, connection_open_space_floor_area_m2,
connection_open_space_open_area_ratio, stair_or_ramp_effective_width_m, building_activity_type,
building_use_category, has_performance_assembly_use, is_target_facility_in_basement,
has_gas_boiler_heating_system, has_centralized_gas_supply, is_collapse_risk_land, has_land_preparation,
has_building_construction_activity, has_wet_land, has_water_seepage_risk, has_landfill_or_similar_ground,
has_flat_plate_structure, authority_designated_special_structure, article32_3_alternative_confirmation_subject,
has_wall_between_connection_entrances, wall_between_connection_entrances_is_fire_resistant,
has_stair_or_ramp_in_open_space, is_connected_to_subway_or_underground_mall, has_hazardous_material_in_out_event

## 4. DEFERRED
INDUSTRIAL / CONSTRUCTION / BUILDING browser canary = 3섹터 통합 batch.

## 5. 3-SECTOR STATUS (2026-09-03)
- INDUSTRIAL: backend LIVE/CLOSED · frontend MERGED+DEPLOYED/CLOSED
- CONSTRUCTION: backend LIVE/CLOSED · frontend MERGED+DEPLOYED/CLOSED
- BUILDING: SAFE wiring NOT STARTED (audit: WO-BLD-SAFE-WIRING-AUDIT-001)

> index 문서. BUILDING 판정은 실제 code + DB + frontend 재실측으로 수행한다.
