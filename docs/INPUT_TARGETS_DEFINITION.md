# 법령진단 입력 대상 정의 (확정, 2026-06-09)

> 목적: 진단/SaaS 두 진입점에서 다루는 입력 대상을 확정하고,
>       각 대상의 섹터별 소스·저장·엔진연결 상태를 한 문서로 통합.
> 근거: INPUT_TARGETS_SURVEY.md, WORK_AXIS_SECTOR_SURVEY.md(v2),
>       E2E_KSIC_TEST_20260609.md
> 성격: 조사 단계 최종 산출물 (표준 정의 전 기준 문서)

## 입력 대상 6종 (확정)

```
1. 시설 (facility/factory)
2. 공정 — 제조 (KSIC 기반)
3. 공정 — 건설 (KCSC 기반)
4. 설비 (equipment)
5. 작업 (work) — 제조/건설 모두 존재 (표현 방식 다름)
6. 위험물 (hazard/chemical)
```

## 대상별 소스 · 저장 · 엔진연결

### 1. 시설
```
진단 입력: site_kind + scale + workers (preset)
SaaS 등록: /factories
저장: factories (익명=temp / SaaS=영구)
엔진 연결: DIRECT 필드만 (employee_count, building_area, 전력)
단절: API→Body 필드 유실, SaaS factory_id 미재사용
```

### 2. 공정 — 제조 (KSIC)
```
소스: ksic_process_map (6,957건)
  계층: lv1(공정大) > lv2(공정단계) > lv3(세부공정) > lv4(작업행위)
SaaS 등록: /factory-process → factory_process
엔진 연결: ksic_code 존재만 (scope value=null, C26=C20)
단절: ksic_process_map 미조인, 진단이 factory_process 미사용
```

### 3. 공정 — 건설 (KCSC)
```
소스: kcsc_process_master
SaaS 등록: construction_site_processes
엔진 연결: 건설 진단 경로 (별도)
```

### 4. 설비 (equipment)
```
소스: equipment_model_master, process_equipment_map
  제조: process_equipment_map (공정 lv4 → 설비, equipment_role)
  건설: kcsc_work_master.equipment_type_codes
SaaS 등록: /equipment-assets → equipment_assets (41컬럼)
엔진 연결: 없음 (EQUIPMENT_JOIN 미구현)
단절: 진단이 equipment_assets 미사용
```

### 5. 작업 (work) — 제조/건설 모두 존재
```
제조: ksic_process_map.process_lv4 (작업 행위)
  예: "증착 및 코팅", "노광 및 식각", "공정 세정"
  → 설비 연결 있음 (process_equipment_map)
  → 위험/안전기준 연결 없음

건설: kcsc_work_master (243건, 독립 테이블)
  process_id → 작업(title) → is_hazardous/hazard_type
  → equipment_type_codes → safety_standard
  → 위험+설비+안전기준 모두 연결

운영 작업배정 (입력 아님): work_assignments (1,549건)
  → 점검 배정/실행 레코드
엔진 연결: draft_slot process_type value=null (존재검사만)
```

### 6. 위험물 (hazard/chemical)
```
소스: runtime_facility_hazard, kosha_safety_materials
  건설 작업 내장: kcsc_work_master.is_hazardous
진단 입력: Body 플래그 (is_hazardous_material), API 노출 없음
SaaS 등록: factories 플래그 + 용량(gas_capacity)
엔진 연결: gas AMBIGUOUS만, concentration FIELD_MAP 없음
단절: is_hazardous_material FIELD_MAP 없음
```

## 공통 구조 원인 (반복 확인)

```
1. Compiler 진단은 항상 temp factory 1행만 읽음
   → SaaS 등록 데이터(factory_process/equipment_assets) 미사용

2. 엔진 scope 조건 value=null (존재검사만)
   → process_type/equipment_type/facility_type 값 비교 불가
```

## 표준화 분류

### 입력 표준화 (엔진 안 건드림)
```
1. Anonymous API에 Body 필드 노출 (ksic, 위험물, 면적 등)
2. factory_id로 SaaS 시설 row 재사용 ★ 핵심
   → 등록된 공정/설비/위험물이 자동으로 평가 대상에 포함
3. input_data에 실입력 기록
```

### 엔진 v2 (scope value 정규화 필요, 누적)
```
1. 단위 정합 (monetary/voltage/storage)
2. facility_type 정밀 매칭
3. process_type(KSIC) 정밀 매칭 + ksic_process_map 조인
4. equipment_type 매칭 + EQUIPMENT_JOIN
5. 위험물 concentration FIELD_MAP
6. 작업(work) applicability 축
   - 제조 작업→위험 데이터 구축 (건설은 있음)
```

## 섹터별 입력 대상 매트릭스

```
              제조(KSIC)        건설(KCSC)
  ──────────────────────────────────────────
  시설         factories         factories
  공정         ksic_process_map  kcsc_process_master
  작업         process_lv4       kcsc_work_master
  설비         process_equip_map equipment_type_codes
  위험물       runtime_hazard    kcsc_work.is_hazardous
  작업→위험    없음              있음
  안전기준     없음              있음
```

## 다음 단계: 입력 대상 통합 표준 정의

```
정의할 것:
  - 6개 대상 각각의 표준 입력 형태
  - 섹터별 소스 매핑 규칙
  - 익명(temp factory) vs SaaS(factory_id 재사용) 분기
  - 입력 표준화 범위 vs 엔진 v2 범위 경계

원칙:
  - 엔진 평가 로직 미변경
  - 부분 수정 금지 (6대상 전체를 한 표준으로)
  - factory_id 재사용이 SaaS 측 핵심 열쇠
```
