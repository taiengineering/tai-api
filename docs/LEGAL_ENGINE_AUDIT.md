# 법령엔진 전체 감사 (LEGAL_ENGINE_AUDIT)

> 레포: `taiengineering/tai-api`  
> 기준 커밋: `main` (rollback PR #104 이후)  
> 감사일: 2026-06-07  
> 원칙: **분석만. 코드/DB 수정 없음.**  
> DB 건수: Supabase `vwlahtguyggrhvslabax` MCP `execute_sql` 실측

---

## 요약

소비자 진단(`/anonymous-diagnosis`, `/diagnosis/run`)은 **환경변수와 무관하게** `runtime_metadata_resolution` → `fetch_runtime_rules_as_v1` → `evaluate_facility_conditions_db` 경로를 **직접** 탄다. 해당 카탈로그 테이블의 `condition_value`는 **3,395건 중 7건(0.2%)만 채워짐** — 조건 없는 룰은 `evaluate_facility_conditions_db`에서 **입력과 무관하게 자동 적용**된다.

반면 등록 API `/legal-engine/diagnose/step1`은 `fetch_diagnosis_rules`(ENV 분기) + `_check_rule_conditions`를 쓴다. **같은 제품의 step1이 경로마다 다른 룰 소스·다른 평가 함수를 사용**한다.

`master_building_legal_rules` 테이블은 **DB에 존재하지 않음**(`to_regclass` → `null`). 그러나 `legal_runtime.py`, `construction_svc.py`, `public_admin.py`, `engine_qa.py` 등 **다수 경로가 여전히 이 테이블을 조회**한다.

---

## 1. 데이터 소스 목록

| 테이블 | 용도 | 건수 (실측) | 진단용? | 읽는 파일 |
|--------|------|-------------|---------|-----------|
| `runtime_metadata_resolution` | 법령 카탈로그(메타데이터) | 3,395 | **소비자 step1에서 진단 소스로 사용** (주석과 모순) | `legal_runtime_fetch.py`, `diagnosis_runtime_step1.py`, `legal_engine_svc.py`(debug) |
| `master_building_legal_rules_legacy_contaminated` | v1 진단 룰 (legacy) | 2,002 (조건코드 1,806 / 조건값 1,571) | 진단용 (의도된 v1 소스) | `legal_diagnosis_rules.py:118` (`fetch_rules_v1`) |
| `master_building_legal_rules` | v1 진단 룰 (구명칭) | **테이블 없음** | DEAD | `legal_runtime.py:208,286`, `construction_svc.py:64`, `public_admin.py:167`, `engine_qa.py:231`, `contract_kmong.py:85`, `health.py:44`, `law_rule_generator.py` 등 |
| `master_rule_v2` | 차세대 룰 | **0** | DEAD (플래그 켜도 빈 결과) | `legal_diagnosis_rules.py:142` |
| `master_rule_v2_relation` | v2 관계 | (미개별 조회) | v2 부속 | `legal_diagnosis_rules.py:62` |
| `master_rule_scope` / `master_rule_scope_mapping` / `master_rule_scope_threshold` | v2 스코프 | (미개별 조회) | v2 부속 | `legal_diagnosis_rules.py:79–101` |
| `rule_article_mapping` | rule_id → 조문 본문 | 2,677 | 조문 enrichment | `legal_article_loader.py:73`, `legal_step1_builder.py` |
| `rule_candidate` | 후보 룰 | 34,456 | 카탈로그/슬롯 조인 | `legal_runtime_fetch.py:105`, `diagnosis_runtime_step1.py:242` |
| `rule_candidate_slot` | who/when/what 슬롯 | 146,595 | 카탈로그 enrichment | `diagnosis_runtime_step1.py` |
| `facility_applicability` | 공장별 적용 draft | (미개별 조회) | factory 서브셋 필터 | `legal_runtime_fetch.py:54` |
| `executable_draft` | draft → rule_candidate | 10,725 | factory 서브셋 필터 | `legal_runtime_fetch.py:81` |
| `task_candidate` | 공장 task draft | — | factory 서브셋 폴백 | `legal_runtime_fetch.py:68` |
| `law_article` | 조문 본문 | — | enrichment | `legal_article_loader.py:98`, `diagnosis_runtime_step1.py:219` |
| `law_version` | 법령 버전 | — | enrichment | `diagnosis_runtime_step1.py` |
| `kcsc_process_master` / `kcsc_work_master` | 건설 공정/작업 | — | step2/3 | `legal_engine_svc.py:66,154` |
| `factory_diagnosis_results` | 진단 결과 저장 | — | 저장 | `legal_v510_svc.py`, `legal_rules.py`, `legal_runtime.py` |
| `anonymous_diagnosis_results` | 익명/유료 진단 저장 | 6 | 저장 | `anonymous_diagnosis.py`, `diagnosis_integrated_svc.py` |
| `factories` / `quotes` | 시설/견적 | — | apply 엔진 | `legal_runtime.py`, `legal_evaluator.py` |

### A-3. 카탈로그 vs 진단

| 소스 | 코드상 라벨 | 실제 역할 |
|------|-------------|-----------|
| `runtime_metadata_resolution` | `legal_runtime_fetch.py:1-3` **CATALOG ONLY** | 소비자 진단 **실제 소스** |
| `master_building_legal_rules_legacy_contaminated` | `fetch_diagnosis_rules` 기본 경로 | v510/legacy step1 **의도 소스** (ENV 기본) |
| `master_rule_v2` | `TAI_USE_V2_ENGINE` | 미구축 (0건) |

### A-4. `legacy_contaminated` 사용

- `legal_diagnosis_rules.fetch_rules_v1` → `master_building_legal_rules_legacy_contaminated` (```118:130:services/legal_diagnosis_rules.py```)
- `diagnosis_rule_source_label()` 기본 반환값은 `master_building_legal_rules:v1` 이지만 실제 읽는 테이블은 `_legacy_contaminated` (```29:35:services/legal_diagnosis_rules.py```)

### A-5. ENV 분기 (`fetch_diagnosis_rules`만 해당)

| `TAI_USE_RUNTIME_ENGINE` | `TAI_USE_V2_ENGINE` | 읽는 테이블 |
|--------------------------|---------------------|-------------|
| `true` | (무시) | `runtime_metadata_resolution` |
| `false` | `true` | `master_rule_v2` (+ relation/scope) |
| `false` | `false` (기본) | `master_building_legal_rules_legacy_contaminated` |

**주의:** 소비자 경로(`run_diagnose_step1_runtime`)는 `fetch_diagnosis_rules`를 **호출하지 않음** → ENV **무시**.

### `runtime_metadata_resolution` 조건 필드 실측

| 지표 | 값 |
|------|-----|
| 전체 행 | 3,395 |
| `condition_value` 비어있지 않음 | **7 (0.2%)** |
| `condition_status = RESOLVED` | 2,886 |
| `condition_status = UNRESOLVED` | 441 |
| `condition_status = PARTIAL` | 68 |

`condition_status`가 RESOLVED여도 `condition_value`가 비어 있는 경우가 대다수 → **상태 필드 신뢰 불가**.

`rule_article_mapping`과 `runtime_metadata_resolution.id` 조인: **0건** (metadata UUID는 mapping `rule_id`와 불일치).

---

## 2. 진입 경로 목록

| API | Registry | 함수 체인 | 룰 소스 | ENV 분기 |
|-----|----------|-----------|---------|----------|
| `POST /anonymous-diagnosis` | `router_registry/public.py` → `anonymous_diagnosis` | `create_anonymous_diagnosis` → `_run_step1_via_service` → `run_diagnose_step1_runtime` → `fetch_runtime_rules_as_v1` → `evaluate_facility_conditions_db` | `runtime_metadata_resolution` | **없음** |
| `POST /diagnosis/run` | `router_registry/diagnosis.py` → `diagnosis_integrated` | `run_diagnosis` → `_run_step1_via_service` → (동일) | `runtime_metadata_resolution` | **없음** |
| `POST /legal-engine/diagnose/step1` | `router_registry/legal_engine.py` → `legal_engine` | `run_diagnose_step1_v510` → `fetch_diagnosis_rules` → `_evaluate_conditions`(`_check_rule_conditions`) | ENV 의존 (기본: `legacy_contaminated`) | **있음** |
| `POST /legal-engine/diagnose/step2` | `legal_engine` | `run_diagnose_step2` → `fetch_diagnosis_rules` → `_evaluate_condition` | ENV 의존 | **있음** |
| `POST /legal-engine/diagnose/step3` | `legal_engine` | `run_diagnose_step3` → `fetch_diagnosis_rules` → `_evaluate_condition` | ENV 의존 | **있음** |
| `POST /legal-engine/apply/{factory_id}` | `legal_engine` | `run_apply_engine` → `master_building_legal_rules` 직접 조회 | **존재하지 않는 테이블** | 없음 |
| `POST /legal-engine/apply-quote/{quote_id}` | `legal_engine` | `run_apply_quote` → `master_building_legal_rules` | **존재하지 않는 테이블** | 없음 |
| `POST /admin/public-diagnosis-requests/{id}/run-diagnosis` | `public_admin` | `_input_to_facility_context` → `master_building_legal_rules` → `evaluate_facility_conditions_db` | **존재하지 않는 테이블** | 없음 |
| 건설 모듈 `construction_svc.run_diagnosis` | `router_registry/construction` | `master_building_legal_rules` → `evaluate_facility_conditions_db` | **존재하지 않는 테이블** | 없음 |
| `engine_qa` 테스트 실행 | `legal_engine` | `master_building_legal_rules` → `evaluate_facility_conditions_db` | **존재하지 않는 테이블** | 없음 |

### B-5. 룰 소스 일치 여부

| 경로 그룹 | 룰 소스 | 평가 함수 |
|-----------|---------|-----------|
| 소비자 (anonymous + diagnosis/run) | `runtime_metadata_resolution` | `evaluate_facility_conditions_db` |
| v510 step1 (legal-engine) | `fetch_diagnosis_rules` (기본 legacy) | `_check_rule_conditions` |
| apply/quote/public-admin/construction/QA | `master_building_legal_rules` (없음) | `_evaluate_conditions` 또는 `evaluate_facility_conditions_db` |

**결론: 경로마다 룰 소스·평가기가 모두 다름.**

### B-6. ENV 조합 (`fetch_diagnosis_rules` 경로만)

| # | RUNTIME | V2 | 결과 |
|---|---------|-----|------|
| 1 | `false` | `false` | legacy_contaminated 2,002건, 조건값 78% |
| 2 | `true` | * | runtime 3,395건, 조건값 0.2% |
| 3 | `false` | `true` | master_rule_v2 **0건** → 빈 진단 |
| 4 | `true` | `true` | RUNTIME 우선 → runtime (V2 무시) |

소비자 경로는 항상 #2와 동일 소스이나, 평가 함수는 v510의 `_check_rule_conditions`가 아니라 `evaluate_facility_conditions_db`를 사용 → **#2와도 결과 불일치**.

### 미등록 라우터

`routers/legal_engine_v510.py` — `POST /legal-engine/diagnose/step1` **중복 정의**이나 `router_registry`에 **미등록** → 런타임 미노출.

---

## 3. 조건 평가 함수 비교

| 함수 | alias? | 스키마 | 호출자 | 결과 차이 |
|------|--------|--------|--------|-------------|
| `_db_rule_matches_facility` | **있음** (`CONDITION_CODE_TO_CONTEXT_KEY`, `legal_rules.py:18-38`) | `condition_code` + `condition_value` | `evaluate_facility_conditions_db` → 소비자 step1, contract_kmong, construction_svc, public_admin, engine_qa | 기준 |
| `_check_rule_conditions` | **없음** — `context[condition_code]` 직접 조회 (`legal_rules.py:64-100`) | `condition_code` + `condition_value` | `legal_v510_svc` step1 (`_evaluate_conditions`), step2 (`_evaluate_step2_rule`), `legal_runtime` apply | **alias 미적용** — `employee_count` 룰 + `worker_count`만 있는 context → False |
| `_evaluate_condition` | **없음** — `condition_1_field` 등 별도 필드 (`legal_rules.py:237-278`) | v1 extended 필드 | `legal_engine_svc` step2/3, `legal_runtime` process/equipment | **스키마 자체가 다름** — legacy/v2 adapted 룰과 projection 룰에서 필드 부재 시 **무조건 True** (필드 없으면 `return True`, `:239-240`) |

### C-4 / C-5. 구체적 불일치 사례

**사례 1 — alias (`employee_count` vs `worker_count`)**

- 룰: `condition_code=employee_count`, `condition_value=50`
- context: `{worker_count: 60}` (employee_count 키 없음)
- `_db_rule_matches_facility`: alias → **True**
- `_check_rule_conditions`: `context.get("employee_count")` → None → **False**

**사례 2 — 조건 없는 룰 (runtime projection)**

- `project_metadata_to_v1` 기본: `condition_code=""`, `condition_value=None` (`rule_candidate_projection.py:115-116`)
- `_apply_runtime_condition`은 DB `condition_value` 텍스트 파싱 — **7건만 해당**
- `evaluate_facility_conditions_db`: `not cc or cv is None` → **비건설 섹터는 무조건 applicable** (`legal_rules.py:174-191`)
- `_check_rule_conditions`: `not cc` → **True** (동일하게 무조건 통과)
- **입력 변경해도 applicable_count 거의 불변** (3,388+ 룰)

**사례 3 — step2/3 `_evaluate_condition`**

- projection 룰에 `condition_1_field` 없음 → `check()`가 필드 부재 시 **True** 반환
- step2/3에서 **전 룰 매칭** 가능

**사례 4 — v510 미사용 평가기**

- `legal_v510_helpers._evaluate_facility_conditions_db_v510` 정의됨 (`legal_v510_helpers.py:146-169`)
- `legal_v510_svc.run_diagnose_step1_v510`는 `_evaluate_conditions`(→ `_check_rule_conditions`) 사용 (`legal_v510_svc.py:130-132`) — **v510 전용 평가기 미사용**

**사례 5 — 건설 임계값**

- `legal_context` / `legal_rules.get_construction_summary`: `get_construction_amount_threshold` — 건축 150억, 토목 120억 (`legal_helpers.py:30-35,96-97`)
- `legal_v510_helpers._get_construction_summary`: `BUILDING`/`SPECIALTY` → 150억, 그 외 120억 하드코드 (`legal_v510_helpers.py:104-105`) — `건축`/`토목` 한글 키와 **불일치 가능**

### 입력 정규화 경로 차이 (D-2)

| 경로 | 입력 변환 |
|------|-----------|
| 소비자 | `_input_to_facility_context` only |
| v510 step1 | `_input_to_facility_context_v510` + `normalize_input` (`input_normalizer._ensure_condition_code_keys`) |

v510만 `electric_capacity` ↔ `electrical_capacity_kw` 등 **condition_code 키 보장** (`input_normalizer.py:89-111`). 소비자 경로에는 없음.

---

## 4. 발견 목록

| 번호 | 심각도 | 위치 | 설명 | 증상 |
|------|--------|------|------|------|
| F-001 | **CRITICAL** | DB `runtime_metadata_resolution`; `legal_runtime_fetch.py:48-49` | `condition_value` 3,395건 중 **7건(0.2%)**만 존재. projection 후 대부분 `condition_code=""` | 입력(면적·인원·공사금) 변경해도 applicable 룰 수 거의 동일 |
| F-002 | **CRITICAL** | `legal_runtime_fetch.py:1-3`; `diagnosis_runtime_step1.py:413-418` | **CATALOG ONLY — NOT DIAGNOSIS SOURCE** 주석(2026-05-31)과 달리 소비자 진단이 직접 사용 | 아키텍처 의도와 운영 실태 불일치; 카탈로그 품질이 곧 서비스 품질 |
| F-003 | **HIGH** | DB `master_rule_v2`; `legal_diagnosis_rules.py:142-174` | 차세대 룰 **0건**. `TAI_USE_V2_ENGINE=true` 시 빈 룰셋 | v2 플래그 활성화 시 진단 결과 0건 |
| F-004 | **CRITICAL** | `diagnosis_runtime_step1.py:413-418`; `anonymous_diagnosis.py:79-83`; `diagnosis_integrated.py:75-79` | 소비자 경로가 `fetch_diagnosis_rules`·ENV **완전 우회**, 항상 `fetch_runtime_rules_as_v1` | Railway에서 ENV 바꿔도 무료/유료 진단 결과 동일 소스 |
| F-005 | **CRITICAL** | DB `to_regclass('master_building_legal_rules')` = null; `legal_runtime.py:208,286`, `construction_svc.py:64`, `public_admin.py:167`, `engine_qa.py:231` | **삭제된 테이블**을 apply/건설/관리자/QA가 조회 | 해당 API 호출 시 빈 룰 또는 DB 오류; apply 엔진 무력화 |
| F-006 | **HIGH** | DB: RESOLVED 2,886건 vs `condition_value` 7건 | `condition_status=RESOLVED`와 실제 조건값 공백 **불일치** | 메타데이터 파이프라인 품질 지표 신뢰 불가 |
| F-007 | **HIGH** | `diagnosis_runtime_step1.py:456` vs `legal_v510_svc.py:130-132` | 소비자=`evaluate_facility_conditions_db`, v510=`_check_rule_conditions` — **등록 step1과 소비자 step1 평가기 상이** | 동일 입력·섹터라도 API별 applicable 수·목록 상이 |
| F-008 | **HIGH** | `legal_rules.py:64-100,149-164,237-278` | 3개 평가 함수 — alias·스키마·무조건통과 규칙 **전부 다름** | step1/2/3·apply·소비자 간 교차 검증 불가 |
| F-009 | **HIGH** | `rule_candidate_projection.py:94`; `legal_article_loader.py:73`; DB 조인 0건 | runtime `rule_id` = metadata UUID, `rule_article_mapping.rule_id`와 **0건 매칭** | step1 조문 본문 enrichment 실패; `article_mapping_stats` 부정확 |
| F-010 | **MEDIUM** | `legal_diagnosis_rules.py:35,118` | 라벨 `master_building_legal_rules:v1` vs 실제 `*_legacy_contaminated` | `rule_version`·감사 추적 혼란 |
| F-011 | **MEDIUM** | `routers/legal_engine_v510.py` | `/legal-engine/diagnose/step1` 중복 라우터 **미등록** | dead code; 문서/테스트와 프로덕션 경로 혼동 |
| F-012 | **MEDIUM** | `legal_v510_helpers.py:146-169` vs `legal_v510_svc.py:132` | `_evaluate_facility_conditions_db_v510` **정의만 있고 미호출** | v510 전용 건설 필터 로직 미적용 |
| F-013 | **MEDIUM** | `legal_diagnosis_rules.py:146-152`; `legal_runtime_fetch.py:117-120`; `legal_runtime.py:144,268-273` 등 | `except Exception: pass/continue` 다수 — DB·조회 실패 **삼킴** | 빈 enrichment·저장 실패가 silent; 사용자는 성공 응답 |
| F-014 | **LOW** | `legal_engine_svc.py:74,174,353,360`; `legal_runtime.py:93,128,269,273,300`; `legal_article_loader.py:80,110` 등 | 프로덕션 경로에 `print()` 디버그 잔존 | 로그 오염; 구조화 로깅 미사용 |
| F-015 | **LOW** | `services/legal_v510_svc.py.bak` | `.bak` 파일 존재 | 유지보수 혼란 |
| F-016 | **LOW** | `legal_engine_svc.py:326-334` | `run_diagnose_step1_endpoint` — **호출처 없음** | dead code |
| F-017 | **MEDIUM** | `legal_v510_helpers.py:104-105` vs `legal_helpers.py:30-35` | 건설 금액 임계값 — v510 helper 하드코드 vs `get_construction_amount_threshold` | `construction_summary.safety_manager_required` API별 상이 |
| F-018 | **MEDIUM** | `legal_runtime_fetch.py:20`; `legal_diagnosis_rules.py:22` | Railway 프로덕션 ENV 값 **미확인** (MCP/Railway 접근 불가). 코드 기본값 둘 다 `false` | 운영에서 실제 분기 상태 불명; verification 스크립트는 `TAI_USE_RUNTIME_ENGINE=false` 강제 |
| F-019 | **HIGH** | `evaluate_facility_conditions_db` `legal_rules.py:174-191` | 조건 없는 룰 = **class C auto-applicable** (비건설 전 섹터 무조건 통과) | runtime 3,395건 중 ~99.8%가 입력 무관 적용; “진단”이 “카탈로그 나열”에 가까움 |
| F-020 | **MEDIUM** | `anonymous_diagnosis.py:64-67` vs `legal_context.py:103-104` | sector 정규화: anonymous는 MANUFACTURING→INDUSTRIAL **저장 변환**, 엔진은 INDUSTRIAL→MANUFACTURING **판정 변환** | 저장 sector와 엔진 sector 이중 변환; 추적 시 혼란 |

---

## 5. 권장 수정 순서

> **수정은 본 감사 범위 외.** 의존성·리스크 기준 우선순위만 제시.

1. **F-004 + F-001 + F-002 + F-019 (소비자 경로 룰 소스)**  
   소비자 진단이 어떤 테이블을 써야 하는지 단일 결정. `legacy_contaminated`(조건 78%) vs runtime(0.2%) vs v2(0건) 중 선택 전까지 **서비스 품질 보장 불가**.

2. **F-005 (ghost table `master_building_legal_rules`)**  
   apply/건설/QA/health 전역을 `legacy_contaminated` 또는 통합 뷰로 정렬. 현재는 런타임 오류 또는 0건.

3. **F-007 + F-008 (평가기 단일화)**  
   step1 전 경로에서 하나의 평가 함수 + alias 정책 확정. `input_normalizer` 적용 범위 통일.

4. **F-003 (master_rule_v2)**  
   v2 플래그를 켜기 전 데이터 적재 또는 플래그 비활성화 문서화.

5. **F-009 (rule_id / article mapping)**  
   runtime UUID ↔ mapping 키 체계 정합. enrichment 경로 재설계.

6. **F-006 (metadata 품질)**  
   `condition_status`와 `condition_value` 정합성. RESOLVED인데 값 없는 2,886건 재처리.

7. **F-010, F-011, F-012, F-015, F-016 (정리)**  
   라벨 정정, 미등록 라우터/.bak/dead function 제거.

8. **F-013, F-014 (운영 품질)**  
   예외 삼킴 → 로깅/실패 전파; `print` → structured log.

9. **F-018 (ENV)**  
   Railway 실측 후 `TAI_USE_*` 조합 문서화 및 소비자 경로와의 관계 명시.

---

## 부록: ENV 플래그 전체

| 변수 | 읽는 위치 | 기본값 | True 시 | False 시 |
|------|-----------|--------|---------|----------|
| `TAI_USE_RUNTIME_ENGINE` | `legal_runtime_fetch.py:20`, `legal_diagnosis_rules.py:13` | `false` | `fetch_diagnosis_rules` → runtime | legacy_contaminated (V2 false일 때) |
| `TAI_USE_V2_ENGINE` | `legal_diagnosis_rules.py:22` | `false` | RUNTIME false일 때 v2 | legacy_contaminated |

**소비자 경로:** 위 플래그 **미참조**.

**Railway 실제 값:** 본 감사 시점 MCP로 **확인 불가** (코드 기본값 `false`/`false` → v510 기본은 `legacy_contaminated`).

---

## 부록: 감사 대상 파일 체크리스트

| 파일 | 감사 완료 | 비고 |
|------|-----------|------|
| `diagnosis_runtime_step1.py` | ✓ | 소비자 메인 |
| `diagnosis_integrated_svc.py` | ✓ | persist only |
| `legal_runtime_fetch.py` | ✓ | CATALOG 주석 |
| `rule_candidate_projection.py` | ✓ | 조건 projection |
| `legal_diagnosis_rules.py` | ✓ | ENV 분기 |
| `legal_rules.py` | ✓ | 3 evaluators |
| `legal_v510_svc.py` | ✓ | v510 step1/2 |
| `legal_engine_svc.py` | ✓ | step2/3, apply |
| `legal_runtime.py` | ✓ | ghost table |
| `legal_context.py` | ✓ | facility_ctx |
| `input_normalizer.py` | ✓ | v510 only |
| `legal_evaluator.py` | ✓ | 결과 조회·inspection_sets |
| `legal_v510_svc.py.bak` | ✓ | E-2 |

관련 선행 문서: `docs/PIPELINE_TRACE.md`, `docs/WORKORDER_LEGAL_ENGINE_AUDIT.md`
