---
wo: WO-COMPILER-CONTRACT-001
class: records
type: report
scope: canonical
project: test-universe
title: Compiler Input Contract Full Survey
version: 1
status: active
owner: taiwang
---

# REPORT — Compiler Input Contract Full Survey

> WO-COMPILER-CONTRACT-001. 조사만 수행. Compiler가 실제로 받는 입력·생성 출력을 실측 기록.
> 범위: Canonical Request → Step1 Body → Normalized Input → Factory Context → Compiler Input → Candidate Query → Compiler Output → Result Builder Input. Runtime 이후 제외.
> Evidence = Repository 코드(파일 sha·함수) / 실제 DB read-only 중 하나. 추론은 기록하지 않는다.

## 1. 단계별 조사

| Step | Component | Input | Output | Fields | Required/Optional/Default | Transform | Evidence |
|---|---|---|---|---|---|---|---|
| 1 | Canonical Request | raw dict | `CanonicalDiagnosisRequest` | origin, site_kind, scale, workers, region, sector, raw | origin=Default ANONYMOUS; 나머지 Optional(None) | 필드 복사(business logic 없음) | 코드 `services/canonical/dto.py` (sha 69cb2dd2) · `adapters.py` (sha 6712d3a0) `to_canonical` |
| 2 | Step1 Body | AnonymousDiagnosisCreate | `DiagnoseStep1Body` | 33 필드(§2 목록) | sector Required; 나머지 Optional(default None), input default {} | SECTOR_BY_KIND·SCALE_PRESETS 매핑 | 코드 `schemas/legal_engine.py` (sha 10e15c48) `class DiagnoseStep1Body` · `routers/anonymous_diagnosis.py` `_build_step1_body` |
| 3 | Normalized Input | DiagnoseStep1Body | body.input(정규화 병합) | _merge_body_input 34키 화이트리스트 | 값 None이면 미포함 | `_merge_body_input`→`normalize_input`; CONSTRUCTION 원→억 | 코드 `services/anonymous_factory_service.py` (sha b822b865) `normalize_consumer_inp` |
| 4 | Factory Context | (sector, inp) | ctx dict(28키 baseline) | sector별 분기(BUILDING/MANUFACTURING/CONSTRUCTION/SPECIAL) | 전 키 default 0/0.0/""; INDUSTRIAL→MANUFACTURING 변환 | `_input_to_facility_context` | 코드 `services/legal_context.py` (sha f6c2b556) `_input_to_facility_context` |
| 5 | Temp Factory row | ctx | factories row(id) | sector, site_type, ksic_code, building_use_code, construction_type, 수치필드 | is_active=false; 값 0/빈값이면 일부 키 미포함 | ctx→factories insert | 코드 `services/anonymous_factory_service.py` `create_temp_factory` · DB write `factories` |
| 6 | Compiler Input (Evaluation) | factories row + draft_slot | (overall_status, part_id, checks) | binding_field→factories 컬럼(FIELD_MAP 11종) | draft_value/facility_val None→MISSING_DATA | `evaluate_draft_for_facility`; compare_numeric·scope presence | 코드 `services/facility_applicability_eval.py` (sha 425be489) `FIELD_MAP`·`evaluate_draft_for_facility` |
| 7 | Candidate Query | factory_id | candidates dict | applicability/task/schedule/penalty/review/package | statuses default (MATCH_CANDIDATE, POSSIBLE_CANDIDATE); penalty_limit 50 | pre-materialized 테이블 조회 | 코드 `services/compiler_core_svc.py` (sha 1915ac8a) `fetch_compiler_candidates` |
| 8 | Compiler Output | candidates + sector_raw + facility_ctx | step1 result_data dict | rules, key_obligations, summary, risk_level, compiler_core | — | task/applicability→rule_row, bucket 분류, risk_level | 코드 `services/anonymous_factory_service.py` `_compiler_result_to_step1_format` |
| 9 | Result Builder Input | Compiler Output(full_result) | partial_result dict | rules_table, key_obligations, law_badges | preview 12·key 6·badges 18 상한 | `_build_standard_output` | 코드 `services/diagnosis_helpers.py` (sha 111d72e3) `_build_standard_output` |

## 2. Compiler Input Contract — 필드 (DiagnoseStep1Body)

> Evidence: `schemas/legal_engine.py` (sha 10e15c48) `class DiagnoseStep1Body`. Required = pydantic `Field(...)`. Default = 코드 명시값.

| Field | Source | Required | Default | Evidence |
|---|---|---|---|---|
| sector | Router mapping (SECTOR_BY_KIND) | YES | 없음 (`Field(...)`) | legal_engine.py `sector: str = Field(...)` |
| factory_id | Consumer/None | NO | None | legal_engine.py `factory_id: Optional[str]` |
| input | 내부 dict | NO | {} (default_factory) | legal_engine.py `input: Optional[Dict]` |
| building_use_type | Consumer/Router preset | NO | None | legal_engine.py |
| employee_count | Consumer | NO | None | legal_engine.py |
| floor_area | Router preset(SCALE_PRESETS) | NO | None | legal_engine.py · anonymous_diagnosis.py SCALE_PRESETS |
| worker_count | Consumer(workers) | NO | None | legal_engine.py |
| total_floor_area | Router preset | NO | None | legal_engine.py |
| electric_capacity | Consumer | NO | None | legal_engine.py |
| floor_count | Router(building=5) | NO | None | legal_engine.py |
| contract_amount_eok | Router preset(construction) | NO | None (단위: 억원) | legal_engine.py Field description |
| ksic_major | Consumer(manufacturing) | NO | None ("" in _build_step1_body) | legal_engine.py |
| facility_type | Router(other=기타시설) | NO | None | legal_engine.py |
| elevator_count | Consumer | NO | None | legal_engine.py |
| gas_capacity_kg | Consumer | NO | None | legal_engine.py |
| gas_capacity_m3 | Consumer | NO | None | legal_engine.py |
| boiler_capacity_kw | Consumer | NO | None | legal_engine.py |
| annual_energy_toe | Consumer | NO | None | legal_engine.py |
| has_high_pressure_gas | Consumer | NO | None | legal_engine.py |
| has_boiler | Consumer | NO | None | legal_engine.py |
| has_hazardous_material | Consumer | NO | None | legal_engine.py |
| has_chemical_substance | Consumer | NO | None | legal_engine.py |
| construction_type | Router(construction=건축) | NO | None | legal_engine.py |
| direct_workers | Router(construction=workers) | NO | None | legal_engine.py |
| subcon_workers | Router(construction=0) | NO | None | legal_engine.py |
| electrical_capacity_kw | Consumer | NO | None | legal_engine.py |
| has_tunnel_bridge | Consumer | NO | None | legal_engine.py |
| has_blasting | Consumer | NO | None | legal_engine.py |
| has_crane | Consumer | NO | None | legal_engine.py |
| has_high_work | Consumer | NO | None | legal_engine.py |

> Anonymous Consumer 실제 입력 4필드: site_kind·scale·workers·region (`AnonymousDiagnosisCreate`, sha b4549343). region default "". 나머지 Step1 Body 필드는 Router의 SCALE_PRESETS·SECTOR_BY_KIND·sector 분기로 채워진다(anonymous_diagnosis.py `_build_step1_body`).

## 3. Candidate 조사

> Evidence: `services/compiler_core_svc.py` (sha 1915ac8a) `fetch_compiler_candidates` · `services/compiler_engine_gateway.py` (sha fbe529b3).

| Candidate | Source Table | Join Key | Evidence |
|---|---|---|---|
| applicability_candidates | facility_applicability | factory_id + applicability_status in statuses | compiler_engine_gateway `fetch_facility_applicability_by_factory` |
| task_candidates | task_candidate | factory_id | compiler_core_svc `fetch_compiler_candidates` (sb.table("task_candidate").eq factory_id) |
| schedule_candidates | schedule_candidate | factory_id | compiler_core_svc (sb.table("schedule_candidate").eq factory_id) |
| penalty_relations / penalty_candidates | penalty_obligation_relation | (limit 200, factory_id 조인 없음) | compiler_core_svc (sb.table("penalty_obligation_relation").limit 200) |
| review_queue / residuals | compliance_review_queue | factory_id | compiler_core_svc (sb.table("compliance_review_queue").eq factory_id) |
| compliance_package | compliance_package | factory_id | compiler_core_svc (sb.table("compliance_package").eq factory_id) |

## 4. Contract 조사 (실제 사용 항목)

| Contract Item | Source | Used By | Evidence |
|---|---|---|---|
| engine_isolated 스키마 전용 클라이언트 | ClientOptions(schema=engine_isolated) | draft_slot·executable_draft·facility_applicability 접근 | compiler_engine_gateway.py `_make_engine_client` docstring "the ONLY module that touches engine_isolated schema" |
| FIELD_MAP (binding_field→factories 컬럼) | facility_applicability_eval.py | evaluate_numeric_check·evaluate_scope_check | facility_applicability_eval.py `FIELD_MAP` 11 항목 |
| applicability_status 값 | evaluate | MATCH_CANDIDATE·POSSIBLE_CANDIDATE·AMBIGUOUS·NOT_MATCHED·MISSING_DATA | facility_applicability_eval.py `aggregate_applicability_status` |
| _PERSIST_STATUSES | anonymous_factory_service.py | facility_applicability insert 필터 | anonymous_factory_service.py `_PERSIST_STATUSES = {MATCH_CANDIDATE, POSSIBLE_CANDIDATE}` |
| COMPILER_VERSION | compiler_core_svc.py | compiler_core 출력 | compiler_core_svc.py `COMPILER_VERSION = "v3.0-deterministic"` |
| COMPILER_WARNING | compiler_core_svc.py | compiler_core 출력 | compiler_core_svc.py `"All results are CANDIDATES. Not legal conclusions."` |
| draft_slot section | draft_slot | IF_NUMERIC·IF_SCOPE·THEN_ACTION | compiler_engine_gateway `fetch_draft_slots_numeric_scope`·`fetch_draft_slots_then_action` |
| law_sector_mapping.sectors | law_sector_mapping | sector 필터 (BUILDING/INDUSTRIAL/CONSTRUCTION/SPECIAL_FACILITY) | anonymous_factory_service.py `_load_sector_allowed_draft_ids` |
| to_mapping_sector | constants.sectors | sector 표준 환원 | anonymous_factory_service.py `_mapping_sector_key` |

## 5. UNKNOWN

| 항목 | UNKNOWN | 필요한 실측 |
|---|---|---|
| Candidate 소재 | task_candidate·schedule_candidate·penalty_obligation_relation·compliance_review_queue·compliance_package의 소재 스키마(engine_isolated / public / 기타) | 각 테이블 information_schema 실측(compiler_core_svc는 sb.table 기본 스키마 사용, engine_gateway는 engine_isolated) |
| Candidate 생성 주체 | task_candidate·schedule_candidate·penalty_obligation_relation 행을 생성하는 코드(현 파이프라인은 조회만) | 생성 배치/스크립트 실측 |
| penalty join | penalty_obligation_relation이 factory_id 조인 없이 limit 200 조회되는 이유 | 해당 테이블 스키마·행수 실측 |
| SUPABASE_URL/KEY 소재 | engine_isolated 클라이언트가 접속하는 project_ref | db/supabase_client.py + 라이브 env 실측 |
| Compiler Output 실제값 | rule_row·key_obligations 실제 데이터 예시 | 라이브 진단 1건 실행 결과 실측 |
| Step1 Body 4필드 외 소비자 입력 경로 | anonymous 외 경로(member/paid/api)에서 33필드 중 실제 전달 필드 | 해당 라우터 실측 |

## 6. WO 종료

| 종료 조건 | 상태 |
|---|---|
| Compiler Input 조사 완료 | 완료 (§1 Step 1~9) |
| Contract 필드 조사 완료 | 완료 (§2 필드표 29행) |
| Candidate 조사 완료 | 완료 (§3 6종) |
| UNKNOWN 분리 완료 | 완료 (§5, 6건) |
| 새 설계 결론 0건 | 준수 |

> 이 문서는 다음 WO의 유일 입력이다. Grounding·Master·Universe·Test Case는 이 문서에서 확인된 Compiler Contract Evidence만을 기반으로 조사한다.
