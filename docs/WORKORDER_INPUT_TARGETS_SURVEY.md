# 작업지시서: 입력 대상 5종 진입점 조사 (시설/공정/설비/작업/위험물)

> 목적: 진단 페이지와 SaaS 등록부, 두 진입점에서
>       시설/공정/설비/작업/위험물이 어떻게 입력→저장→엔진까지 가는지 조사.
> 원칙: 조사만. 수정 금지. 추측 금지. 코드/DB에서 사실만.
> 배경: KSIC 테스트에서 "입력은 되나 엔진 평가에 안 닿는" 단절 발견.
>       부분 수정 대신 입력 대상 전체를 처음부터 표준화하기 위한 조사.

## 조사 대상: 2개 진입점 × 5개 입력 대상

```
진입점:
  A. 진단 페이지 (anonymous_diagnosis / diagnosis)
  B. SaaS 등록부 (factory/site 등록, 공정/설비 등록)

입력 대상:
  1. 시설 (facility/factory)
  2. 공정 (process)
  3. 설비 (equipment)
  4. 작업 (work/task)
  5. 위험물 (hazard/chemical)
```

## 관련 테이블 (실측, 참고)

```
시설:   factories, runtime_facility_profile, facility_condition
공정:   factory_process, construction_site_processes, ksic_process_map, v_process_unified
설비:   equipment_assets, runtime_facility_equipment, process_equipment_map,
        v_equipment_unified, equipment_model_master
작업:   construction_works, work_schedules, work_assignments, task_candidate
위험물: runtime_facility_hazard, kosha_safety_materials
```

## 조사 항목 (각 입력 대상마다)

### 매트릭스: 5 대상 × (진입점/저장/엔진연결)

각 입력 대상(시설/공정/설비/작업/위험물)에 대해:

```
[진입점 A — 진단 페이지]
  - 진단 입력 스키마에 이 대상이 있는가?
    (AnonymousDiagnosisCreate / DiagnoseStep1Body 필드 확인)
  - 있으면 어떤 필드명? 없으면 "진단에서 입력 불가"

[진입점 B — SaaS 등록부]
  - SaaS에서 이 대상을 등록하는 API/라우터가 있는가?
  - 어떤 테이블에 저장되는가?
  - source 구분(MANUAL/DB/KCSC)이 있는가?

[저장]
  - 최종 저장 테이블
  - 진단 경로와 SaaS 경로가 같은 테이블을 쓰는가 다른가?

[엔진 연결]
  - 이 대상이 facility_applicability 평가에 반영되는가?
  - FIELD_MAP / draft_slot binding_field와 연결되는가?
  - 연결 안 되면 어디서 끊기는가?
    (저장 안 됨 / FIELD_MAP 없음 / draft_slot value=null / scope 존재검사만)
```

## 산출물

파일: docs/INPUT_TARGETS_SURVEY.md

```markdown
# 입력 대상 5종 진입점 조사

## 매트릭스 요약

| 대상 | 진단 입력 | SaaS 등록 | 저장 테이블 | 엔진 반영 | 단절 지점 |
|------|----------|-----------|------------|----------|----------|
| 시설 | ? | ? | ? | ? | ? |
| 공정 | ? | ? | ? | ? | ? |
| 설비 | ? | ? | ? | ? | ? |
| 작업 | ? | ? | ? | ? | ? |
| 위험물 | ? | ? | ? | ? | ? |

## 대상별 상세
### 1. 시설
  진입점 A (진단): [필드/없음]
  진입점 B (SaaS): [API/테이블]
  저장: [테이블, 진단/SaaS 동일 여부]
  엔진 연결: [반영/단절, 단절이면 지점]

### 2. 공정
  ... (KSIC 테스트 결과 반영: ksic_process_map 있으나 draft_slot value=null로 미연결)

### 3~5. 설비/작업/위험물
  ...

## 공통 패턴
  - 어느 대상이 엔진까지 닿고, 어느 대상이 끊기는가?
  - 끊김의 공통 원인 (scope value null? FIELD_MAP 없음? 저장 안 됨?)

## 표준화 분류
  - 입력 표준화로 해결 가능 (엔진 안 건드림): [목록]
  - 엔진 v2 필요 (scope value 정규화): [목록]
```

## 주의

- 수정 금지 (조사만)
- 추측 금지 — 코드(스키마, 라우터)와 DB에서 확인
- KSIC 테스트 결과(E2E_KSIC_TEST_20260609.md) 참고
- 진단 경로와 SaaS 경로를 구분해서 기록
- 엔진 평가 로직은 읽기만 (facility_applicability_eval.py)
- Supabase MCP project_id: vwlahtguyggrhvslabax
- 이 조사가 끝나면 "입력 대상 전체 표준" 설계로 넘어감 (부분 수정 금지)
