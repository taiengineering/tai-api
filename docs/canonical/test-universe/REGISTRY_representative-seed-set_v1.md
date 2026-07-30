---
wo: WO-E2E-DATASET-001
class: records
type: registry
scope: canonical
project: test-universe
title: Representative Seed Set (Contract-Signature-driven Minimum Representative Set)
version: 1
status: active
owner: taiwang
---

# REGISTRY — Representative Seed Set (Stage 1)

> WO-E2E-DATASET-001 Stage 1. **Repository = SoT(설계 자산).** DB는 Generator 생성 실행데이터(별도).
> **Seed Set** — 닫힌 목록 아님. 새 법령·설비·계약 발산점 발견 시 Representative 추가.
> 선정 기준 = **Contract Signature 차이**(업종명 아님). Expected/Golden/E2E 미포함.

## 원칙

```
1. Repository = Representative 원본 / Database = Generator 산출 실행데이터 (역할 분리)
2. 대표성 = 활성 Contract 필드 집합(Signature)의 발산점. 업종명 아님.
3. Unique 판정: 신규 후보 Signature == 기존이면 → Representative 불필요(중복).
4. Signature는 실제 계약필드(LEG 66 + Compiler 5)에만 앵커. 없는 개념은 GAP(제외, 억지매핑 금지).
5. baseline: test-universe-v1 (Universe Freeze) 위에서만 생성.
```

**Universal baseline 필드(전 Case 공통, 발산점 아님 → Signature에서 제외):**
`worker_count · ksic_major · building_use_type · total_floor_area · has_safety_manager`

## Representative 기록 템플릿 (Stage 1 동결 필드)

```
representative_id       : REP-<SECTOR>-<INDUSTRY>-NN
contract_signature[]    : 활성 계약 필드 집합 (발산점, 실제 field_code)
unique                  : YES(신규 signature) | 흡수(기존 REP-xxx와 동일)
why_representative       : 이 signature가 커버하는 발산 근거
key_equipment[] / key_process[] / key_task[]
gap[]                   : 대표하지만 계약필드 부재(향후 확장 후보)
representative_coverage : 이 대표가 대표하는 하위 조합 범위
```

## Representative Seed Set — Contract Signature

### 제조 (SEC-MFG)
```
REP-MFG-MACHINERY-01  일반기계
  signature: has_machinery, has_press, has_welding, has_crane, has_forklift, has_grinding
  unique: YES · key: 프레스·용접·연삭·크레인 · task: 운전·정비
  coverage: 범용 금속가공 제조 (프레스+용접 기본형)

REP-MFG-AUTO-01  자동차
  signature: has_machinery, has_press, has_painting, has_welding, has_conveyor, has_forklift
  unique: YES (vs 일반기계: +has_painting +has_conveyor −has_grinding)
  gap: has_industrial_robot, has_compressor (계약 부재)
  coverage: 라인 조립+도장 제조

REP-MFG-CHEM-01  화학
  signature: has_chemical, has_chemical_substance, has_hazardous_material, has_hazmat_storage,
             has_high_pressure_gas, has_gas, has_pressure_vessel, gas_capacity_kg
  unique: YES · coverage: 위험물·고압가스·반응공정 제조

REP-MFG-FOOD-01  식품
  signature: has_boiler, boiler_capacity_kw, has_cooling_tower, has_confined_space,
             has_chemical, has_conveyor, has_forklift
  unique: YES (증기+냉동+밀폐탱크 세척) · coverage: 가공식품 (위생·열/냉)

REP-MFG-STEEL-01  철강
  signature: has_casting, has_rolling, has_heat_treatment, has_crane, has_tower_crane,
             has_dust_work, has_noise_work, has_machinery
  unique: YES · coverage: 주조·압연·열처리 중공업

REP-MFG-SHIP-01  조선
  signature: has_welding, has_painting, has_crane, has_tower_crane, has_confined_space,
             has_high_place_work, has_scaffold
  unique: YES (밀폐+고소+대형양중+용접/도장) · coverage: 선박 블록 건조

REP-MFG-SEMI-01  반도체
  signature: has_chemical, has_chemical_substance, has_hazardous_material, has_high_pressure_gas,
             has_gas, has_radiation, has_central_hvac
  unique: YES (vs 화학: +has_radiation +has_central_hvac −hazmat_storage)
  gap: has_cleanroom (계약 부재) · coverage: 클린룸·특수가스·이온화 공정
```

### 건축물 (SEC-BLD)  — building_use_type 분기
```
REP-BLD-HOSPITAL-01  병원
  signature: building_use_type, has_boiler, has_emergency_gen, has_sprinkler, has_smoke_control,
             has_biological_agent, has_central_hvac, has_water_tank, is_multi_use
  unique: YES · coverage: 의료시설 (비상전원·감염·공조)

REP-BLD-SCHOOL-01  학교
  signature: building_use_type, has_boiler, has_sprinkler, has_fire_hydrant, has_elevator
  unique: YES (vs 병원: −emergency_gen −biological_agent −central_hvac) · coverage: 교육시설 기본형

REP-BLD-APT-01  공동주택
  signature: building_use_type, has_elevator, has_mech_parking, has_sprinkler, has_septic_tank,
             has_water_tank, is_complex_building
  unique: YES (기계식주차+정화조+복합) · coverage: 아파트/주상복합

REP-BLD-LOGISTICS-01  물류센터
  signature: building_use_type, has_forklift, has_conveyor, has_sprinkler, total_floor_area(대)
  unique: YES (건물맥락 forklift+conveyor 대면적) · coverage: 창고형 물류

REP-BLD-HOTEL-01  호텔
  signature: building_use_type, is_multi_use, has_boiler, has_sprinkler, has_smoke_control,
             has_emergency_broadcast, has_central_hvac, has_elevator
  unique: YES (다중이용+숙박공조) · coverage: 숙박시설
```

### 건설 (SEC-CON)  — construction_type 분기
```
REP-CON-BUILDING-01  건축
  signature: construction_type, has_scaffold, has_steel_frame, has_concrete_work,
             has_temp_electric, has_tower_crane, has_high_place_work, has_welding
  unique: YES · coverage: 건축물 신축 (골조·비계·고소)

REP-CON-CIVIL-01  토목
  signature: construction_type, has_excavation, has_pile_work, has_blasting,
             has_concrete_work, has_temp_electric, has_scaffold
  unique: YES (굴착·항타·발파) · coverage: 토목 (도로·교량·지반)

REP-CON-PLANT-01  플랜트
  signature: construction_type, has_welding, has_pressure_vessel, has_confined_space,
             has_high_place_work, has_scaffold, has_crane, has_electric_work
  unique: YES (압력용기+밀폐+배관계) · gap: has_piping · coverage: 플랜트 설치

REP-CON-RAILWAY-01  철도
  signature: construction_type, has_excavation, has_blasting, has_pile_work,
             has_electric_work, has_temp_electric
  unique: YES · gap: has_track, has_tunnel · coverage: 철도·궤도·터널
```

## Signature Uniqueness 판정 (중복 제거)

```
16 후보 → 16 신규 Signature (전부 unique). 흡수(중복) 0.
검증 규칙: REP-x.signature == REP-y.signature 이면 하나로 흡수.
  현재 최근접 쌍: MACHINERY vs AUTO (painting/conveyor/grinding로 분기) → 별개 확정.
                 CHEM vs SEMI (radiation/central_hvac로 분기) → 별개 확정.
                 HOSPITAL vs SCHOOL (emergency_gen/biological/hvac로 분기) → 별개 확정.
```

## Stage 1 완료 기준 (Signature 기준 추가)

```
Representative Coverage   PASS  (각 REP coverage 명시)
Contract Signature        PASS  (실제 field_code 앵커, GAP 분리)
Signature Coverage        PASS  (제조/건축물/건설 주요 발산점 포함)
Signature Unique          PASS  (16/16 unique, 중복 흡수 0)
GAP 기록                  PASS  (robot/compressor/cleanroom/piping/track/tunnel 명시, 억지매핑 0)
```

## GAP (대표하나 계약필드 부재 — 향후 계약 확장 후보)
```
has_industrial_robot · has_compressor · has_cleanroom · has_piping · has_track · has_tunnel
→ 발산점으로 인지하되 Signature에는 미포함(∅). 계약 확장 시 신규 Signature로 승격.
```

## 다음 (Stage 2)
```
Universe Generator: 각 REP를 seed로 Allowed Matrix 내에서 확장 → DB 적재 → E2E.
신규 Signature 발견 시에만 REP 추가(중복 없는 성장).
```
