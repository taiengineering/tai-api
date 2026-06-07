# CONDITION_CODE_RAW_INVENTORY

> **성격:** RAW 인벤토리. DB fetch 결과 그대로. **유효 코드 선정·표준화·정규화·삭제·분류·판단 없음.**
> **소스 테이블:** `master_building_legal_rules_legacy_contaminated` (is_active = true)
> **조회일:** 2026-06-07
> **Supabase:** vwlahtguyggrhvslabax

## 검증값 (DB)

| 항목 | 값 |
|---|---|
| 테이블 총 row | 2,002 |
| DISTINCT condition_code | 456 (NULL 포함 1행) |
| rule_count 합 | 2,002 (누락 없음) |
| condition_value_example | 코드별 첫 row 값 1개 (raw) |

- DISTINCT(non-null) = 455, NULL = 1행 → 표 총 456행.
- condition_value_example = 각 condition_code의 id 오름차순 첫 row의 condition_value (raw, 미가공).
- 공란 = DB에서 NULL.
- 정렬: rule_count 내림차순, 동수일 때 condition_code 오름차순 (NULL 맨 위 196 다음 위치는 rule_count 순서에 따름).

## 표

| condition_code | rule_count | condition_value_example |
|---|---|---|
| is_hazardous_material | 340 | 1 |
| _(NULL)_ | 196 |  |
| building_area | 127 | 600 |
| employee_count | 119 | 1 |
| gas_capacity_kg | 112 | 0 |
| has_high_pressure_gas | 70 | 1.0 |
| contract_amount | 65 | 50000000 |
| has_chemical_substance | 64 | 1.0 |
| elevator_count | 59 | 1.0 |
| is_factory_registered | 53 | 1 |
| is_multi_use | 43 | 1.0 |
| electrical_capacity_kw | 38 | 1 |
| construction_amount | 35 | 100000000 |
| gas_capacity_m3 | 31 | 1 |
| floor_count | 27 | 7.0 |
| annual_energy_toe | 24 | 2500.0 |
| worker_count | 22 | 5 |
| building_grade | 13 | 1 |
| electric_capacity | 11 | 22.0 |
| boiler_capacity_kw | 7 | 1 |
| business_type | 7 |  |
| is_construction_site | 7 | 1 |
| business_start_date | 5 | 30 |
| equipment_type | 5 |  |
| has_boiler | 5 | 1.0 |
| hospital_beds | 5 | 1 |
| manufacturing_business | 5 | 1 |
| EQUIPMENT_TYPE | 4 |  |
| facility_type | 4 |  |
| registration_required | 4 | 1 |
| student_count | 4 | 1 |
| TUNNEL_LENGTH | 4 | 50 |
| WATER_SPRAY_SYSTEM | 4 | 1 |
| business_succession | 3 | 1 |
| contractor_count | 3 | 1 |
| gas_facility_type | 3 |  |
| has_pressure_chamber | 3 | 1.0 |
| HEIGHT_RANGE | 3 |  |
| INSTALLATION_HEIGHT | 3 | 1.5 |
| is_mechanical_inspector_business | 3 | 1 |
| LOW_WATER_LEVEL | 3 |  |
| power_plant_monitoring | 3 | 1 |
| water_capacity_m3 | 3 | 80.0 |
| ["floor_count","building_area" | 2 |  |
| accident_occurred | 2 |  |
| BACKUP_POWER_AVAILABLE | 2 |  |
| DISTANCE_REQUIREMENT | 2 | 25 |
| EMERGENCY_BROADCAST_FACILITY | 2 | 1 |
| EMERGENCY_POWER_INSTALLED | 2 |  |
| FACILITY_EXIST | 2 |  |
| FACILITY_INSTALLATION | 2 |  |
| facility_installation_date | 2 | 0 |
| FACILITY_TYPE | 2 |  |
| fire_safety_manager_appointment_required | 2 | 1 |
| flame_retardant_required | 2 |  |
| FLOOR_AREA | 2 | 3000 |
| FLOOR_COUNT | 2 | 4 |
| HAS_EMERGENCY_POWER | 2 |  |
| has_halon_extinguishing_system | 2 |  |
| has_hazmat_tank | 2 | 1 |
| has_mechanical_facility_manager | 2 | 1 |
| HAS_MIST_FIRE_SUPPRESSION_SYSTEM | 2 |  |
| has_noise_facility | 2 | 1 |
| has_wastewater_facility | 2 | 1 |
| high_voltage_mobile_wire | 2 | 1 |
| insulation_resistance | 2 | 0.1 |
| is_fire_safety_management_object | 2 | 1 |
| is_foam_system_installed | 2 |  |
| is_mobile_tank_transport | 2 | 1 |
| is_safety_health_agency_applicant | 2 | 1 |
| management_authority_separated | 2 | 1 |
| manager_appointment | 2 | 1 |
| NON_COMPLIANCE | 2 |  |
| OUTDOOR_ANTENNA_INSTALLATION | 2 |  |
| OUTDOOR_HYDRANT_INSTALLED | 2 |  |
| POWDER_EXTINGUISHING_SYSTEM | 2 |  |
| PRESSURE_RANGE | 2 |  |
| PUMP_DISCHARGE_PRESSURE | 2 | 0.2 |
| transformer_capacity_kva | 2 | 75 |
| TUNNEL_LANES | 2 |  |
| underground_depth | 2 | 4.5 |
| WATER_FLOW_DETECTION | 2 |  |
| water_flow_detector_installation | 2 | 1 |
| accessibility_facility_required | 1 | 1 |
| accident_occurrence | 1 |  |
| ACCOMMODATION_FACILITY | 1 |  |
| ALL_BUILDINGS | 1 | 1 |
| ALWAYS_APPLICABLE | 1 |  |
| AMBIENT_TEMP_BASED | 1 |  |
| AMPLIFIER_WIRELESS_REPEATER_INSTALL | 1 | 1 |
| application_received | 1 |  |
| authority_delegation | 1 | 1 |
| AUTO_FIRE_DETECTION_SYSTEM | 1 |  |
| AUTO_OPERATION | 1 |  |
| AUTOMATIC_FIRE_DETECTION_REQUIRED | 1 |  |
| backup_power_available | 1 |  |
| BACKUP_POWER_REQUIRED | 1 | 1 |
| BATTERY_POWERED | 1 |  |
| beam_spacing | 1 | 0.9 |
| boiler_capacity_th | 1 | 20 |
| building_committee_review | 1 |  |
| building_construction | 1 | 1 |
| BUILDING_FLOOR_AREA | 1 | 1 |
| BUILDING_HEIGHT | 1 | 30 |
| BUILDING_HEIGHT_ALL | 1 | 30 |
| BUILDING_HORIZONTAL_DISTANCE | 1 | 140 |
| building_type | 1 | 25 |
| business_closure | 1 | 1 |
| business_status_change | 1 | 1 |
| ceiling_slope | 1 | 0.168 |
| CHARGE_RATIO | 1 | 0.8 |
| CLOSED_SPRINKLER_HEAD | 1 |  |
| CO_ALARM_INSTALLATION | 1 | 1 |
| CO2_EXTINGUISH_SYSTEM_INSTALLED | 1 |  |
| CO2_SAFETY_DEVICE | 1 | 1 |
| CONNECTED_SPRINKLER_SYSTEM | 1 | 1 |
| CONNECTION_FIRE_PIPE_SYSTEM | 1 | 1 |
| construction_area | 1 | 600 |
| construction_completion_date | 1 | 7 |
| construction_project | 1 | 1 |
| construction_project_required | 1 | 1 |
| construction_project_scale | 1 | 1 |
| construction_site | 1 | 1 |
| construction_site_fire_safety_manager_appointed | 1 | 1 |
| construction_site_fire_safety_manager_required | 1 | 1 |
| construction_site_history_request | 1 | 1 |
| construction_type | 1 |  |
| construction_work_active | 1 | 1 |
| CONTROL_VALVE_INSTALLATION | 1 | 1 |
| corrosive_gas_environment | 1 | 1 |
| dc_return_circuit | 1 | 1 |
| definition | 1 |  |
| delegation_authority | 1 |  |
| detection_method_measurement | 1 | 1 |
| diagnosis_order_received | 1 | 1 |
| discharge_head_count | 1 | 1 |
| DISCHARGE_METHOD | 1 |  |
| disposal_event | 1 |  |
| DOOR_CLOSING_FORCE | 1 |  |
| DRIVE_UNIT_INSPECTION | 1 | 1 |
| DUAL_USE_INSTALLATION | 1 |  |
| dusty_area_electrical | 1 | 1 |
| ELECTRIC_ENGINE_PUMP | 1 |  |
| electrical_equipment_installation | 1 | 1 |
| electrical_insulation | 1 | 1 |
| ELECTRICAL_LEAK_DETECTOR_INSTALLED | 1 | 1 |
| electrical_line_safety | 1 | 1 |
| ELECTRICAL_SUPPLY_TYPE | 1 |  |
| electrical_terminology | 1 |  |
| elevator_classification | 1 | 1 |
| elevator_management | 1 | 1 |
| emergency_backup_power | 1 | 1 |
| EMERGENCY_OUTLET_FACILITY | 1 |  |
| EMERGENCY_OUTLET_FACILITY_INSTALLED | 1 |  |
| EMERGENCY_POWER_DURATION | 1 | 40 |
| EMERGENCY_POWER_FACILITY | 1 |  |
| EMERGENCY_POWER_FACILITY_EXISTS | 1 |  |
| emergency_power_installation | 1 |  |
| EMERGENCY_POWER_REQUIRED | 1 |  |
| equipment_installation | 1 |  |
| EQUIPMENT_INSTALLATION | 1 |  |
| ev_charging_capacity_kw | 1 | 1 |
| exam_fraud_detected | 1 | 1 |
| EXCELLENT_BUSINESS_DESIGNATION | 1 |  |
| EXTINGUISHER_AGENT_TYPE | 1 |  |
| facility_change_required | 1 | 1 |
| FACILITY_EXISTS | 1 |  |
| FACILITY_INSTALLED | 1 |  |
| FIRE_CORROSION_EXPLOSION_FREE | 1 |  |
| FIRE_DETECTION_REQUIRED | 1 |  |
| FIRE_DETECTOR_CIRCUIT | 1 |  |
| fire_equipment_required | 1 | 1 |
| FIRE_EXTINGUISHING_AGENT_STORAGE | 1 | 1.0 |
| fire_info_system_cooperation | 1 | 1 |
| fire_prevention_zone | 1 | 1 |
| fire_risk_assessment_required | 1 | 1.0 |
| FIRE_RISK_ASSESSMENT_SERVICE | 1 |  |
| FIRE_RISK_WORK | 1 |  |
| fire_safety_assistant_required | 1 | 1 |
| fire_safety_impact_assessment_required | 1 |  |
| fire_safety_inspection | 1 | 1 |
| fire_safety_investigation_delay_needed | 1 | 1 |
| fire_safety_management_outsourcing | 1 | 1 |
| fire_safety_management_proxy_required | 1 | 1 |
| fire_safety_management_required | 1 | 1 |
| fire_safety_management_target | 1 | 1 |
| fire_safety_manager_appointed | 1 | 1 |
| fire_safety_manager_appointment_change | 1 | 1 |
| fire_safety_manager_needed | 1 | 1 |
| fire_safety_manager_resignation_retirement | 1 | 1 |
| fire_safety_risk | 1 | 1 |
| FIRE_TRUCK_ACCESS_DISTANCE | 1 | 2 |
| FIRE_WATER_TANK | 1 |  |
| FLOOR_AREA_OVER | 1 | 150 |
| floor_height | 1 | 13.7 |
| GAS_ALARM_POWER_SUPPLY | 1 | 1 |
| GAS_BURNER_PRESENT | 1 |  |
| GAS_COMBUSTOR_EXISTS | 1 | 1 |
| GAS_DETECTION_EFFECTIVE | 1 |  |
| gas_disposal_event | 1 |  |
| gas_insulated_equipment | 1 | 1 |
| gas_storage_capacity | 1 | 100 |
| gas_supply_measurement | 1 |  |
| general_application | 1 |  |
| GRAVITY_PRESSURE_SYSTEM | 1 |  |
| ground_fault_protection | 1 | 1 |
| HALON_FIRE_SYSTEM | 1 | 1 |
| has_auto_closure_device | 1 |  |
| has_chemical_facility | 1 | 1 |
| has_co2_suppression_system | 1 |  |
| has_construction_waste | 1 | 1 |
| has_customer_service | 1 | 1 |
| has_disqualification_reason | 1 | 1 |
| has_early_response_sprinkler | 1 |  |
| has_electrical_qualification | 1 | 1.0 |
| HAS_EMERGENCY_BROADCAST | 1 |  |
| has_energy_storage | 1 | 1 |
| has_ev_charging_area | 1 |  |
| has_ev_charging_zone | 1 |  |
| has_extra_high_voltage_overhead_wire | 1 | 1 |
| has_fire_equipment | 1 | 1 |
| has_fire_pump_or_vertical_pipe | 1 |  |
| has_fire_safety_management_object | 1 | 1 |
| has_flammable_gas_work | 1 |  |
| has_forklift | 1 | 1.0 |
| HAS_GAS_BURNER | 1 | 1 |
| HAS_GAS_COMBUSTOR | 1 |  |
| has_gas_transport_registration | 1 | 1 |
| has_generator_or_fuel_cell_or_battery | 1 | 1 |
| has_halogenated_fire_suppressi | 1 |  |
| has_halogenated_fire_system | 1 |  |
| has_halon_fire_suppression_sys | 1 |  |
| has_hazmat_facility | 1 | 1 |
| has_high_work | 1 | 2.0 |
| has_maintenance_contract_termination | 1 | 1 |
| has_maintenance_manager | 1 | 1 |
| has_maintenance_manager_change | 1 | 1 |
| has_manufacturing_facility | 1 | 1 |
| has_mechanical_facility | 1 | 1 |
| has_mechanical_facility_manager_appointment | 1 | 1 |
| has_mechanical_facility_manager_change | 1 | 1 |
| has_pressure_work | 1 | 1.0 |
| has_rock_tank | 1 | 1 |
| has_safety_health_agency | 1 | 1 |
| has_safety_manager | 1 | 1 |
| has_spray_head | 1 |  |
| HAS_SPRINKLER_CONNECTION | 1 |  |
| has_sprinkler_emergency_power | 1 |  |
| has_sprinkler_system | 1 |  |
| HAS_SPRINKLER_SYSTEM | 1 |  |
| has_tank_facility | 1 | 1 |
| has_tank_inspection_facility | 1 | 1 |
| has_underground_tank | 1 | 1 |
| has_waste_treatment_staff | 1 | 1 |
| has_water_flow_detector | 1 |  |
| hazmat_accident_occurred | 1 | 1 |
| HEIGHT_LIMIT | 1 | 1.5 |
| high_frequency_equipment_interference | 1 | 1 |
| HIGH_RISE_BUILDING | 1 | 30 |
| high_voltage_overhead_line | 1 | 1 |
| HOSE_REEL_SYSTEM | 1 |  |
| HYDRANT_DISTANCE_FROM_BUILDING | 1 | 140 |
| IMPEDANCE | 1 | 50 |
| import_export_contract_date | 1 | 30 |
| INDOOR_INSTALLATION | 1 |  |
| inspection_exemption_date | 1 | 0 |
| INSPECTOR_TYPE | 1 |  |
| installation_height | 1 |  |
| INSULATION_RESISTANCE | 1 | 20 |
| intake_height | 1 |  |
| is_airborne_infection_contact | 1 | 1.0 |
| is_apartment_or_elderly_facili | 1 |  |
| is_battery_storage_facility | 1 |  |
| is_construction_business | 1 | 1 |
| is_construction_education_institute | 1 | 1 |
| is_construction_safety_edu_org | 1 | 1 |
| is_construction_site_safety_manager | 1 | 1 |
| is_construction_work | 1 | 1 |
| is_crane_maintenance_work | 1 | 1.0 |
| is_crane_operator | 1 | 1.0 |
| is_diving_work | 1 | 1.0 |
| is_evacuation_guidance_target | 1 | 1 |
| is_fire_safety_management_target | 1 | 1 |
| is_fire_safety_target | 1 | 1 |
| is_hazardous_facility | 1 | 1 |
| is_high_pressure_operator | 1 | 1.0 |
| is_high_pressure_worker | 1 | 1.0 |
| is_high_voltage_electrical_equ | 1 |  |
| is_hospital_or_clinic | 1 |  |
| is_indoor_hydrant_facility | 1 |  |
| is_infectious_disease_exposed | 1 | 1.0 |
| is_medical_facility | 1 |  |
| is_officetel_or_lodging | 1 |  |
| is_officetel_or_lodging_facili | 1 |  |
| is_outsourcing_safety_management | 1 | 1 |
| is_parking_area | 1 |  |
| is_pregnant_worker | 1 | 1.0 |
| is_pressure_work_area | 1 | 1.0 |
| is_residential_or_care_facilit | 1 |  |
| is_safety_edu_institution | 1 | 1 |
| is_safety_education_target | 1 | 1 |
| is_safety_excellent_business | 1 | 1 |
| is_safety_health_agency | 1 | 1 |
| is_safety_health_outsourcing | 1 | 1 |
| is_safety_manager_appointed | 1 | 1 |
| is_self_inspection_company | 1 | 1 |
| is_special_fire_safety_facility | 1 | 1 |
| is_sprinkler_system | 1 |  |
| is_surface_supplied_diving | 1 | 1.0 |
| is_warehouse | 1 |  |
| large_space_area | 1 | 1000 |
| LOCATION_REQUIREMENT | 1 |  |
| low_voltage_feeder_protection | 1 | 1 |
| LOW_VOLTAGE_POWER_RECEPTION | 1 |  |
| LOW_VOLTAGE_SUPPLY | 1 |  |
| lpg_business_operation | 1 | 1 |
| lpg_pipe_exposure_m | 1 | 10.0 |
| lpg_pipe_length_m | 1 | 100.0 |
| MAINTENANCE_ACCESSIBLE | 1 |  |
| maintenance_issue_found | 1 | 1 |
| major_accident_occurred | 1 |  |
| manager_required | 1 | 1 |
| market_type | 1 |  |
| MAX_DISTANCE | 1 | 140 |
| MEASURE_ORDER_VIOLATION | 1 | 1 |
| measurement_agency_analyst | 1 | 1 |
| measurement_analysis_capacity | 1 | 1 |
| measurement_result_review | 1 | 1 |
| medical_facility_change | 1 | 1 |
| MIN_BUILDING_HEIGHT | 1 | 3 |
| MIN_PRESSURE | 1 |  |
| multi_region_coverage | 1 | 1 |
| MULTI_USE_GRADE | 1 |  |
| multiple_protection_zones | 1 | 2 |
| NATURAL_DROP_PRESSURE | 1 |  |
| NATURAL_HEAD_HEIGHT | 1 |  |
| need_fire_safety_manager_cert | 1 | 1 |
| new_construction_or_expansion_or_use_change | 1 | 1 |
| occupancy_calculation | 1 | 1 |
| OPEN_HEAD_REQUIRED | 1 | 1 |
| ORDER_NONCOMPLIANCE | 1 |  |
| orifice_area_ratio | 1 | 70 |
| OUTDOOR_ANTENNA_INSTALLED | 1 | 1 |
| OUTDOOR_OPEN_TYPE | 1 |  |
| overhead_line_voltage | 1 | 22900 |
| overhead_transmission_line | 1 | 1 |
| overhead_wire_grounding | 1 | 1 |
| overhead_wire_height | 1 | 1 |
| overhead_wire_installation | 1 | 1 |
| ownership_succession_event | 1 | 1 |
| ownership_transfer_occurred | 1 | 1 |
| PARKING_GARAGE | 1 |  |
| PARKING_GARAGE_TYPE | 1 |  |
| performance_based_design_required | 1 |  |
| PIPE_CONNECTION | 1 |  |
| PIPE_DIAMETER | 1 | 75 |
| PIPE_DIAMETER_MIN | 1 | 75 |
| PIPE_FLOW_DESIGN | 1 |  |
| pipe_labeling | 1 | 1 |
| pole_climbing_prevention | 1 | 1 |
| POWDER_CONTAINER_FILL_RATIO | 1 | 0.8 |
| POWER_SUPPLY_REQUIREMENT | 1 |  |
| POWER_TYPE | 1 |  |
| pressure_calculation | 1 |  |
| PRESSURE_MAINTAIN | 1 |  |
| PRESSURIZED_STORAGE_CONTAINER | 1 |  |
| PRESSURIZED_WATER_SUPPLY_DEVICE | 1 | 1 |
| PRODUCT_STANDARD_COMPLIANCE | 1 |  |
| protection_zone | 1 | 1 |
| protection_zone_floors | 1 | 2 |
| public_access_facility | 1 | 1 |
| PUMP_ALARM_FUNCTION | 1 |  |
| PUMP_CONTROL | 1 |  |
| PUMP_CONTROL_CAPABILITY | 1 |  |
| PUMP_INDICATOR_REQUIRED | 1 |  |
| PUMP_SUCTION_PIPE_CONNECTION | 1 | 1 |
| QUAL_REQUIREMENT | 1 |  |
| qualification_exam_eligible | 1 | 1 |
| quality_control_nonconformity | 1 | 1 |
| quality_control_required | 1 | 1 |
| quality_management_failure | 1 | 1 |
| RATED_CURRENT | 1 | 60 |
| RATED_CURRENT_AMPERAGE | 1 | 60 |
| RATED_CURRENT_OUTDOOR | 1 |  |
| report_completed | 1 |  |
| requires_machinery_manager | 1 | 1 |
| requires_safety_manager | 1 | 1 |
| requires_tank_inspector | 1 | 1 |
| risk_assessment_required | 1 | 1 |
| safety_grade | 1 |  |
| safety_inspection_passed | 1 |  |
| safety_management_performance | 1 | 2 |
| safety_manager_absent | 1 | 1 |
| safety_violation_occurred | 1 | 1 |
| shipment_contract_date | 1 | 30 |
| SMOKE_CONTROL_FAN | 1 | 1 |
| smoke_control_zone_diameter | 1 | 40.0 |
| special_combustible_material | 1 | 1 |
| special_combustible_storage | 1 | 1 |
| special_fire_target | 1 | 1 |
| special_fire_target_acquisition | 1 | 1 |
| spray_head_installation | 1 |  |
| SPRAY_HEAD_QUANTITY | 1 |  |
| SPRINKLER_FLOW_DETECTOR | 1 | 1 |
| SPRINKLER_INSTALLATION | 1 |  |
| SPRINKLER_INSTALLED | 1 |  |
| SPRINKLER_PRESSURE | 1 | 0.07 |
| sprinkler_protection_area | 1 | 1 |
| SPRINKLER_SYSTEM | 1 |  |
| SPRINKLER_SYSTEM_REQUIRED | 1 |  |
| SPRINKLER_VALVE_AREA | 1 | 1 |
| SPRINKLER_VALVE_INSTALLATION | 1 |  |
| sprinkler_zone_exists | 1 |  |
| storage_capacity | 1 | 1 |
| storage_capacity_ton | 1 | 100 |
| STORAGE_CONTAINER_VOLUME | 1 | 1 |
| structural_protrusion | 1 | 102.0 |
| STRUCTURE_TYPE | 1 |  |
| succession_date | 1 | 30 |
| tank_capacity_gte_1000000L | 1 | 1000000 |
| tuberculosis_patient_contact | 1 | 1.0 |
| TUNNEL_FIRE_SAFETY | 1 |  |
| TUNNEL_LANE_COUNT | 1 | 4 |
| TUNNEL_TYPE | 1 | 2 |
| underground_cable_installation | 1 | 1 |
| valve_installation_location | 1 |  |
| VALVE_SIZE | 1 | 40 |
| VALVE_TEST_DEVICE_INSTALLATION | 1 | 1 |
| VALVE_TYPE | 1 | 1.8 |
| VERTICAL_DUCT_COUNT | 1 | 1 |
| violation_discovery | 1 |  |
| violation_occurrence | 1 | 1 |
| VISIBILITY_RANGE | 1 | 10 |
| VOLTAGE_LEVEL | 1 |  |
| WATER_DETECTOR_INSTALLATION | 1 |  |
| WATER_FLOW_DETECTOR_COUNT | 1 | 1 |
| water_flow_detector_design | 1 | 1 |
| WATER_FLOW_DETECTOR_INSTALLATION | 1 | 1 |
| water_head_height | 1 | 10 |
| WATER_INTAKE_DIAMETER | 1 | 65 |
| WATER_LEVEL | 1 |  |
| WATER_PRESSURE_FLOW_COMPLIANCE | 1 | 0.1 |
| WATER_PRESSURE_MIN | 1 | 0.35 |
| WATER_SOURCE_CAPACITY | 1 | 20 |
| water_tank_low_level | 1 | 1 |
| wire_connection_required | 1 | 1 |
| wire_contact_prevention | 1 | 1 |
| wire_crossing_prevention | 1 | 1 |
| wire_facility_approach_cross | 1 | 1 |
| wire_facility_clearance | 1 | 1 |
| wire_insulation_standard | 1 | 1 |
| wire_insulation_voltage | 1 | 1 |
| WIRELESS_COMM_FACILITY_INSTALL | 1 |  |
| wireless_interference_prevention | 1 | 1 |
| WIRING_IDENTIFICATION | 1 |  |
| work_type_welding_or_cutting | 1 |  |

## 메타

- 위 표 행 수: 456 (NULL 1 + non-null 455).
- rule_count 합: 2,002.
- 이 문서는 RAW 인벤토리이며 어떤 선정·표준화·정규화·삭제·분류·판단도 포함하지 않는다.
