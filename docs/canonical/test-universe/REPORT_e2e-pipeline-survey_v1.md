---
wo: WO-E2E-PIPELINE-001
class: records
type: report
scope: canonical
project: test-universe
title: Consumer Input to Result Full Pipeline Survey (E2E Baseline)
version: 1
status: active
owner: taiwang
---

# REPORT — Consumer Input → Engine → Result Full Pipeline Survey

> WO-E2E-PIPELINE-001. 조사만 수행. 소비자 입력~최종 결과 실제 파이프라인 End-to-End 실측 기록.
> 각 Step = Step · Component · Input · Output · Transform · Evidence.
> Evidence = Repository 코드(파일 sha·함수) / 실제 DB 실측 중 하나. 추론은 근거 아님.
> 근거 부족 항목은 §2 UNKNOWN 표로 분리한다.

## 1. Pipeline Steps (실측)

| Step | Component | Input | Output | Transform | Evidence |
|---|---|---|---|---|---|
| 1 | Consumer Request | `AnonymousDiagnosisCreate` (site_kind, scale, workers, region) | 검증된 pydantic 모델 | HTTP body 파싱 | 코드: `routers/anonymous_diagnosis.py` (sha b4549343) `class AnonymousDiagnosisCreate` |
| 2 | Router 진입 | Consumer Request | `_create_anonymous_diagnosis_impl` 또는 Canonical 경로 | `canonical_enabled()` 분기: OFF→_impl 직접, ON→Adapter→Service | 코드: 동 파일 `@router.post("") create_anonymous_diagnosis` |
| 3 | Adapter | raw dict(site_kind, scale, workers, region, sector) | `CanonicalDiagnosisRequest` (origin=ANONYMOUS) | 필드 복사 + Origin 세팅(business logic 없음) | 코드: `services/canonical/adapters.py` (sha 6712d3a0) `_BaseAdapter.to_canonical` |
| 4 | DTO (Canonical Request) | Adapter 출력 | `CanonicalDiagnosisRequest` (pydantic/fallback) | origin·site_kind·scale·workers·region·sector·raw 보관 | 코드: `services/canonical/dto.py` (sha 69cb2dd2) `class CanonicalDiagnosisRequest` |
| 5 | Canonical Service | dto + delegate | `await delegate()` 결과 | evaluate() = delegate 실행만(business logic 0, engine selection "Decision Pending") | 코드: `services/canonical/service.py` (sha a5c64565) `CanonicalDiagnosisService.evaluate` |
| 6 | Step1 Body 빌드 | AnonymousDiagnosisCreate | `DiagnoseStep1Body` | SECTOR_BY_KIND·SCALE_PRESETS로 sector·preset 매핑, sector별 필드 세팅 | 코드: `routers/anonymous_diagnosis.py` `_build_step1_body` |
| 7 | Input 정규화 | DiagnoseStep1Body | body.input에 정규화값 병합 | `_merge_body_input`→`normalize_input`; CONSTRUCTION 시 contract_amount 원→억 | 코드: `services/anonymous_factory_service.py` (sha b822b865) `normalize_consumer_inp` / `prepare_step1_body_for_compiler` |
| 8 | Temp Factory 생성 | DiagnoseStep1Body | factories row id (is_active=false) | `_input_to_facility_context`→factories row insert(sector·site_type·ksic_code·building_use_code·construction_type 등) | 코드: 동 파일 `create_temp_factory` · DB write `factories` insert |
| 9 | Sector 필터 | factory.sector | 허용 draft_id 집합 또는 None | executable_draft→law_article→law_sector_mapping 조회, sector별 draft 통과/제외/미매핑 통과 | 코드: 동 파일 `_load_sector_allowed_draft_ids` · DB read `executable_draft`·`law_article`·`law_sector_mapping` |
| 10 | Draft Slot 적재 | allowed_draft_ids | numeric/scope groups (draft_id별) | draft_slot IF_NUMERIC/IF_SCOPE 페이지네이션 그룹핑 | 코드: 동 파일 `_load_draft_slot_groups` · DB read `draft_slot` |
| 11 | Evaluation (순수 로직) | facility row + numeric/scope slots | (overall_status, part_id, check_results) | FIELD_MAP으로 binding_field→factories 컬럼 매핑, compare_numeric·scope presence, aggregate_applicability_status | 코드: `services/facility_applicability_eval.py` (sha 425be489) `evaluate_draft_for_facility` |
| 12 | Applicability 저장 | MATCH/POSSIBLE rows | facility_applicability insert | _PERSIST_STATUSES 필터 후 chunk insert | 코드: `services/anonymous_factory_service.py` `evaluate_single_factory` · DB write `facility_applicability` |
| 13 | Compiler Candidates fetch | factory_id | applicability/task/schedule/penalty/review/package candidates | pre-materialized runtime 테이블 조회 | 코드: `services/compiler_core_svc.py` (sha 1915ac8a) `fetch_compiler_candidates` · DB read `task_candidate`·`schedule_candidate`·`penalty_obligation_relation`·`compliance_review_queue`·`compliance_package` |
| 14 | Result Builder | compiler candidates + sector_raw + facility_ctx | step1 result_data dict | task/applicability→rule_row 변환, bucket 분류(선임/점검/조치/신고/보고), risk_level, key_obligations, summary, compiler_core 조립 | 코드: `services/anonymous_factory_service.py` `_compiler_result_to_step1_format` |
| 15 | Fallback Context (조건부) | draft_ids | law_name·law_article·description·task_type | task_candidate 없고 applicability만 있을 때 executable_draft→law_article→law_master→draft_slot 조회 | 코드: 동 파일 `_load_draft_fallback_context` · DB read `law_article`·`law_master`·`draft_slot`·`executable_draft` |
| 16 | Cleanup | factory_id | (없음) | facility_applicability 삭제 + factories 삭제 | 코드: 동 파일 `cleanup_temp_factory` · DB delete `facility_applicability`·`factories` |
| 17 | Partial 출력 | full_result | partial_result dict | rules_table/key_obligations 상한 절단(preview 12·key 6·badges 18), _PARTIAL_MESSAGE | 코드: `services/diagnosis_helpers.py` (sha 111d72e3) `_build_standard_output` |
| 18 | DB 저장 (Report 저장) | full_result + partial + token | anonymous_diagnosis_results row | public_token(uuid), input_snapshot, TTL 7일, insert | 코드: `routers/anonymous_diagnosis.py` `_create_anonymous_diagnosis_impl` · DB write `anonymous_diagnosis_results` |
| 19 | Report/Transform 반환 | anonymous_diagnosis_results row | transform 스키마 JSON | `_extract_headline/obligations/warnings/exposure/inspection_schedule/roi` 재사용 | 코드: 동 파일 `GET /{token}/transform` (import from `routers/diagnosis_transform.py`) |
| S-1 | LEG Runtime Shadow (병렬·non-blocking) | DiagnoseStep1Body | shadow record(log만) | `build_compiler_output`(_FIELD_MAP 5필드)→HTTP POST `{LEG_RUNTIME_URL}/evaluate`; 실패 시 shadow_status=SKIP | 코드: `clients/leg_runtime_client.py` (sha 30a2eee0) `run_shadow_compare` |

## 2. UNKNOWN

> 근거 부족 항목. 추론하지 않고 필요한 실측을 기록한다.

| Step | UNKNOWN | 필요한 실측 |
|---|---|---|
| 2 | 라이브에서 canonical_enabled() 값(ON/OFF) | `services/canonical/flags.py` 코드 + 라이브 env 실측 |
| 5 | Canonical Service engine selection("Decision Pending")의 현재 결정 상태 | engine_interface.py 및 후속 WO 문서 실측 |
| 9~11 | law_sector_mapping·draft_slot·executable_draft 등 테이블 실제 행수·스키마 | 해당 DB(project_ref 미확정) read-only 실측 |
| 9~19 | 이 파이프라인이 조회하는 테이블의 소재 DB(project_ref) | 라이브 DB 연결(supabase_client) 설정 실측 |
| S-1 | 라이브 LEG_RUNTIME_URL 설정값(설정/미설정) | 라이브 env 실측 (미설정 시 shadow SKIP) |
| S-1 | LEG 소비자 경로(build_facility/evaluate_rtm `/rtm/evaluate`)의 호출 지점 | 이 함수들을 호출하는 라우터/서비스 실측 |
| 14 | Result Builder가 산출하는 rule_row의 실제 값 예시(라이브 데이터) | 라이브 진단 1건 실행 결과 실측 |

## 3. 관찰된 테이블 (실측된 코드가 참조)

> 파이프라인 코드가 참조·조작하는 테이블(코드 근거). 소재 DB는 §2 UNKNOWN.

| 테이블 | 접근 | 참조 코드 |
|---|---|---|
| factories | write(insert/delete) · read | create_temp_factory · evaluate_single_factory · cleanup_temp_factory |
| executable_draft | read | _load_sector_allowed_draft_ids · _load_draft_fallback_context |
| law_article | read | _load_sector_allowed_draft_ids · _load_draft_fallback_context |
| law_sector_mapping | read | _load_sector_allowed_draft_ids |
| law_master | read | _load_draft_fallback_context |
| draft_slot | read | _load_draft_slot_groups · _load_draft_fallback_context |
| facility_applicability | write(insert/delete) · read | evaluate_single_factory · fetch_compiler_candidates · cleanup |
| task_candidate | read | fetch_compiler_candidates |
| schedule_candidate | read | fetch_compiler_candidates |
| penalty_obligation_relation | read | fetch_compiler_candidates |
| compliance_review_queue | read | fetch_compiler_candidates |
| compliance_package | read | fetch_compiler_candidates |
| anonymous_diagnosis_results | write(insert/update/delete) · read | _create_anonymous_diagnosis_impl · _fetch_row · admin endpoints |

## 4. WO 종료

| 종료 조건 | 상태 |
|---|---|
| 모든 Pipeline Step 조사 완료 | 완료 (Step 1~19 + Shadow S-1) |
| 모든 Step에 Evidence 기록 | 완료 (전 Step 파일 sha·함수명·DB 접근) |
| UNKNOWN 분리 완료 | 완료 (§2, 7건) |
| 새 설계 결론 0건 | 준수 |

> 이 문서는 다음 WO의 유일 입력이다. Grounding·Master·Boundary는 이 문서에서 확인된 Evidence를 기반으로만 조사한다.
