---
wo: WO-E2E-PROFILE-001
class: records
type: registry
scope: canonical
project: test-universe
title: E2E Consumer Profile Universe v1
version: 1
status: active
owner: taiwang
---

# REGISTRY — E2E Consumer Profile Universe v1

> WO-E2E-PROFILE-001. 실제 소비자가 입력하는 사업장을 재현한 대표 Profile 집합. 엔진 미실행 · 입력 데이터 구축만.
> 필드는 실측 Compiler Input Contract(DiagnoseStep1Body + _input_to_facility_context, tai-api)에 정합.
> KSIC·건설표준분류 코드값은 taeng Master(industry_master · kcsc_process_master) read-only 실측값.
> 다음 WO(E2E Runner)는 profile_universe_v1.json 을 입력으로 사용한다.

## 1. 요약

| 항목 | 값 |
|---|---|
| Total Profiles | 112 |
| 제조(MANUFACTURING) | 46 |
| 건축물(BUILDING) | 29 |
| 건설(CONSTRUCTION) | 27 |
| 특수시설(SPECIAL_FACILITY) | 10 |
| Boundary Profiles | 25 |
| 필수값 누락 | 0 |
| Profile ID 범위 | PF-0001 ~ PF-0112 |

## 2. Layer 구성 (이중 표기: 6 Layer + Compiler field_code)

| Layer | 내용 | Compiler field_code (실측 계약) |
|---|---|---|
| Company | 사업장명·산업분야·KSIC·지역·근로자수·규모 | sector · ksic_major · worker_count · region |
| Building | 건축물용도·연면적·층수 | building_use_type · total_floor_area · floor_area · floor_count |
| Process | 공정명·공정 KSIC | (facility_context 경유) |
| Facility | 설비(보일러·압력용기·크레인 등)·용량 | has_boiler · has_pressure_vessel · has_crane · boiler_capacity_kw · gas_capacity_kg 등 |
| Work | 작업(용접·고소작업·밀폐공간 등) | (has_* 매핑) |
| Construction | 건설표준분류·공종·공사금액·원/하도급 | construction_type · contract_amount_eok · direct_workers · subcon_workers |

## 3. Master 코드 출처 (taeng 실측)

| 축 | Master | 실측 코드 예시 |
|---|---|---|
| 제조 KSIC | industry_master lv2 | 10 식료품 · 20 화학 · 24 1차금속(철강) · 26 전자부품(반도체) · 29 기타기계 · 30 자동차 · 31 기타운송장비(조선) |
| 건설표준분류 | kcsc_process_master.construction_type | BUILDING(KCS 41...) · CIVIL(KCS 11...) · COMMON(KCS 10...) |
| 건물용도 | factories.building_use_code 실사용값 | 업무시설 · 공장 · 의료·복지 · 학교 · 공동주택 (용도명 문자열) |

## 4. Boundary Profiles (법령 적용 경계값)

| Profile ID | Sector | Boundary Note |
|---|---|---|
| PF-0040 | MANUFACTURING | worker_count=49 (안전관리자 선임 50명 경계) |
| PF-0041 | MANUFACTURING | worker_count=50 (안전관리자 선임 50명 경계) |
| PF-0042 | MANUFACTURING | worker_count=51 (안전관리자 선임 50명 경계) |
| PF-0043 | MANUFACTURING | worker_count=99 (100명 경계) |
| PF-0044 | MANUFACTURING | worker_count=100 (100명 경계) |
| PF-0045 | MANUFACTURING | worker_count=101 (100명 경계) |
| PF-0046 | MANUFACTURING | worker_count=299 (300명 경계) |
| PF-0047 | MANUFACTURING | worker_count=300 (300명 경계) |
| PF-0048 | MANUFACTURING | worker_count=301 (300명 경계) |
| PF-0049 | BUILDING | total_floor_area=4999.0 (연면적 5000 경계) |
| PF-0050 | BUILDING | total_floor_area=5000.0 (연면적 5000 경계) |
| PF-0051 | BUILDING | total_floor_area=5001.0 (연면적 5000 경계) |
| PF-0052 | CONSTRUCTION | contract_amount_eok=49.0 (공사금액 50억 경계) |
| PF-0053 | CONSTRUCTION | contract_amount_eok=50.0 (공사금액 50억 경계) |
| PF-0054 | CONSTRUCTION | contract_amount_eok=51.0 (공사금액 50억 경계) |
| PF-0055 | CONSTRUCTION | contract_amount_eok=119.0 (120억 경계) |
| PF-0056 | CONSTRUCTION | contract_amount_eok=120.0 (120억 경계) |
| PF-0057 | CONSTRUCTION | contract_amount_eok=121.0 (120억 경계) |
| PF-0058 | MANUFACTURING | boiler_capacity_kw=500 (보일러 용량 경계) |
| PF-0059 | MANUFACTURING | worker_count=50 (자동차 50명 경계) |
| PF-0060 | MANUFACTURING | worker_count=50 (화학 50명 경계) |
| PF-0061 | MANUFACTURING | worker_count=100 (철강 100명 경계) |
| PF-0062 | BUILDING | total_floor_area=2999.0 (연면적 3000 경계) |
| PF-0063 | BUILDING | total_floor_area=3000.0 (연면적 3000 경계) |
| PF-0064 | BUILDING | total_floor_area=3001.0 (연면적 3000 경계) |

## 5. 검증 (각 Profile)

| 검증 항목 | 결과 |
|---|---|
| KSIC 존재 (제조) | 46/46 |
| 건설표준분류 코드 존재 (건설) | 27/27 |
| 공정 존재 | 46 profiles |
| 설비 존재 | 108 profiles |
| 작업 존재 | 112 profiles |
| Construction Layer | 27 profiles |
| 필수값 누락 | 0 |

## 6. Profile 샘플 (전체는 profile_universe_v1.json)

```json
{
  "profile_id": "PF-0001",
  "sector": "MANUFACTURING",
  "boundary": false,
  "boundary_note": "",
  "layers": {
    "company": {
      "name": "[자동차]사업장001",
      "industry": "자동차",
      "ksic_major": "30",
      "ksic_name": "자동차 및 트레일러 제조업",
      "region": "서울",
      "workers": 15,
      "worker_count": 15,
      "scale": "small"
    },
    "building": {
      "building_use_type": "공장",
      "total_floor_area": 3000.0,
      "floor_area": 3000.0,
      "floor_count": 3
    },
    "process": [
      { "process_name": "프레스", "process_ksic": "30" },
      { "process_name": "용접", "process_ksic": "30" },
      { "process_name": "도장", "process_ksic": "30" }
    ],
    "facility": [
      { "code": "has_press", "value": true },
      { "code": "has_crane", "value": true },
      { "code": "has_forklift", "value": true }
    ],
    "work": [ "용접", "고소작업" ],
    "construction": null
  }
}
```

## 7. WO 종료

| 종료 조건 | 상태 |
|---|---|
| 대표 사업장 Profile 약 100개 | 완료 (112개) |
| 6 Layer 구성 | 완료 |
| KSIC·건설표준분류 포함 | 완료 (taeng 실측) |
| Boundary Profile 최소 20개 | 완료 (25개) |
| Profile ID 고정 | 완료 (PF-0001~) |
| 엔진 수정·테스트 수행 없음 | 준수 |

> 다음 WO: PROFILE_UNIVERSE_V1 → E2E Runner → Engine → Snapshot → Golden → Diff → Regression.
