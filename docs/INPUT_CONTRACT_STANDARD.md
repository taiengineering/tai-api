# 법령엔진 입력부 표준 계약 (Input Contract Standard)

**작성일:** 2026-06-06
**기준 출처:** `diagnosis_input_fields` (is_active=true) — 엔진이 소비하는 입력 항목의 정본
**목적:** 입력 페이지(UI) 정합화의 기준. 이 목록에 **없는 입력은 불필요(제거 대상)**, **있는데 UI에 없으면 누락(추가 대상)**, **형식이 다르면 오입력(교정 대상)**.

> 경계: 입력부(엔진 판정 로직, factories/factory_process/equipment_assets 데이터 모델)는 건드리지 않는다.
> 이 문서는 "입력부 직전까지"의 UI/결제 흐름이 맞춰야 할 정답 목록이다.

---

## 1. 표준 입력 계층

```
factories (시설/사업장)  →  factory_process (공정)  →  equipment_assets (설비)
        factory_id 중심. 진단·SaaS 공용. 단일 표준.
```

- 시설 기본/세부 입력 → `factories` 컬럼
- 공정(process_list) → `factory_process`
- 설비(equipment_list) → `equipment_assets`

---

## 2. 섹터별 엔진 입력 계약 (정답 목록)

### 공통 (모든 섹터 시설 기본)
| field_code | type | 필수 | 비고 |
|---|---|---|---|
| address / project_address | text | ✔ | 주소. 건물=건물주소, 산업=사업장주소, 건설=현장주소 |
| worker_count | number | ✔ | 상시 근로자 수 (건설=동시 투입 인원) |
| total_floor_area | number | 건물✔ / 산업△ | 연면적 |

### BUILDING
**FREE:** address, total_floor_area*, floor_count*, basement_count*, building_use_type*, built_year*, main_structure*, worker_count
(*=building_register 자동채움)
**PAID 추가:** has_safety_manager / 전기(electric_capacity✔, has_emergency_gen, emergency_gen_kw) / 승강기(elevator_count, escalator_count, has_mech_parking, mech_parking_count) / 소방(has_sprinkler, has_fire_hydrant, has_smoke_control, has_emergency_broadcast) / 위험물(has_gas, has_oil_storage, has_chemical, has_hazmat_storage) / 수질환경(has_water_tank, water_tank_ton, has_septic_tank, septic_tank_ton, has_cooling_tower) / 석면(has_asbestos) / 다중이용(is_multi_use, multi_use_type) / 특수시설(has_central_hvac, is_energy_intensive, is_complex_building, underground_area)

### CONSTRUCTION
**FREE:** project_address, project_amount, worker_count, project_duration
**PAID 추가:** construction_type✔, has_subcontractor, subcontractor_count / 공정(process_list[table]✔, has_excavation, excavation_depth, has_pile_work, has_steel_frame, has_concrete_work, has_demolition, max_work_height) / 위험시설(has_tower_crane, tower_crane_count, has_scaffold, has_gondola, has_temp_electric, has_confined_space, has_asbestos_demo, has_blasting, has_diving) / operation_shift✔ / 협력업체(subcontractor[table])

### INDUSTRIAL (누적 tier)
**FREE:** address, ksic_major, worker_count, total_floor_area
**PAID1 추가:** ksic_sub, has_safety_manager, electric_capacity✔ / 위험물·작업(has_boiler, has_chemical_substance, has_hazardous_material, has_high_pressure_gas, has_hazmat_storage, has_dust_work, has_noise_work, has_confined_space, has_radiation) / operation_shift✔
**PAID2 추가:** process_list[table]✔ (→ factory_process)
**PAID3 추가:** equipment_list[table]✔ (→ equipment_assets)

---

## 3. 정합화 규칙 (입력 페이지에 적용)

1. **누락 보완** — 위 계약에 있는데 입력 페이지에 없는 field_code → 추가
2. **오입력 차단** — field_type 불일치 교정:
   - boolean/select/multi_select/table = **코드형(선택)만 허용** (진단은 자유입력 금지)
   - number = 단위 일치 (㎡, 명, kW, 원/억원 등)
   - text 허용은 주소·회사명 등 식별정보로 한정
3. **불필요 제거** — 위 계약에 없는 입력 항목 → 입력 페이지에서 제거

> SaaS 입력은 자유입력(임의) 허용 가능. 진단 입력은 위 코드형 규칙을 강제(엔진 판정 가능성 보장).

---

## 4. 적용 대상 페이지 (입력부 직전 — UI)
- tadmin: `diagnosis-input-building.html`, `diagnosis-input-construction.html`, `diagnosis-input-industry-paid1~3.html`, `diagnosis-step1~3.html`
- 각 페이지 필드 ↔ 본 계약 대조표(2단계 산출물)로 누락/오입력/불필요를 도출 후 정합화.
