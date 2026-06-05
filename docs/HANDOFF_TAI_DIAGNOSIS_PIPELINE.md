# TAI 운영 진단 파이프라인 현황 및 인수인계 문서

> 이 문서는 **현재 시스템이 어떻게 동작하는가**를 설명한다. 조사 로그·탐색 과정·추측은 포함하지 않는다.
> 모든 내용은 운영 저장소(`taiengineering/taieng`, `taiengineering/tai-api`)의 코드와 Supabase(`vwlahtguyggrhvslabax`) 실측으로 확인된 사실이다. 확인되지 않은 것은 **[미확인]**으로 표기한다.
> 최종 갱신: 2026-06-05.

---

## 1. 시스템 개요

TAI 운영 진단은 무료·유료 모두 **단일 SPA 페이지 + 단일 실행 엔드포인트**로 동작한다.

전체 흐름:

```
[UI] free-diagnosis.html (인라인 JS)
   │  formValues[prefix][field_code] = value
   ▼
[API] POST https://api.taieng.co.kr/diagnosis/run
   │  body = { sector, tier, auth_token, disclaimer_log_id, form_data:{...} }
   ▼
[DTO] DiagnosisRunBody  (schemas/diagnosis_integrated.py)
   │  nexas_run_body_from_request() — form_data 화이트리스트 평탄화 + 원본 보존
   ▼
[SERVICE] diagnosis_integrated_svc.run_diagnosis()
   │  inp(dict) 구성 → DiagnoseStep1Body 생성
   ▼
[표준모델] run_diagnose_step1_runtime()  (services/diagnosis_runtime_step1.py)
   │  flat_fields + inp 병합
   ▼
[facility_context] _input_to_facility_context()  (services/legal_context.py)
   │  섹터별 ctx 키 생성
   ▼
[Rule 평가] evaluate_facility_conditions_db()  (services/legal_rules.py)
   │  rule.condition_code ↔ ctx 키 비교 (_db_rule_matches_facility)
   ▼
[Result] build_step1_result_data() → rules_table
   ▼
[저장] anonymous_diagnosis_results (input_data / full_result)
   ▼
[출력] build_nexas_run_response() → 무료=인라인 + free-diagnosis-result.html / 유료=paid-diagnosis-result.html
```

핵심 사실:
- 무료·유료는 **같은 엔드포인트** `POST /diagnosis/run`을 쓰며 `tier`로만 구분된다.
- 입력 항목은 프런트 하드코딩이 아니라 **서버 동적 로드**: `GET /diagnosis/fields?sector=&tier=`.
- **Candidate(rule_candidate / rule_candidate_slot)는 사용자 입력으로 생성되지 않는다.** 이들은 법령 메타데이터(룰셋) 측 테이블이며, 사용자 입력은 `facility_context`로 들어가 룰 매칭(applicable 판정)에만 쓰인다. (5절·7절 참조)

---

## 2. 실제 운영 진입점

| 구분 | 값 |
|---|---|
| 운영 URL | `https://taieng.co.kr/free-diagnosis` |
| 유료 직입 URL | `https://taieng.co.kr/free-diagnosis?paid={CODE}&order_id={ORDER_ID}` **[미구현 — 4절 참조]** |
| 입력 HTML | `taiengineering/taieng` → `nexas/free-diagnosis.html` (인라인 `<script>`에 전 로직) |
| 무료 결과 HTML | `nexas/free-diagnosis-result.html` |
| 유료 결과 HTML | `nexas/paid-diagnosis-result.html` |
| 본인인증 HTML | `nexas/identity-verify.html` |
| JS | **별도 diagnosis.js 없음.** 모든 로직은 free-diagnosis.html 인라인 스크립트 |
| API base | `const API = 'https://api.taieng.co.kr'` |
| API 저장소 | `taiengineering/tai-api` (Railway 배포, FastAPI) |
| DB | Supabase `vwlahtguyggrhvslabax` |

### 구버전 자산과의 관계 (조사 금지 대상)
`survey.html`, `survey_pro.html`, `tai_survey_v5.html`, `/quotes/survey`, `public_diagnosis_requests`, `quotes` 는 **운영 진단과 무관한 구버전**이다. `tai-admin` 저장소도 구버전 폼 저장소다. 운영 진단 경로와 코드·데이터 흐름이 연결되지 않는다. **신규 작업 시 조사 대상 아님.**

---

## 3. 무료진단 구조

### 입력 단계 (UI)
```
Step0 본인인증 (KG이니시스 CI, 무료 3회 제한)
Step1 섹터 선택 (BUILDING / INDUSTRY / CONSTRUCTION)
Step2 무료 입력 → 즉시 결과
Step3 무료 결과 표시
(Step4/5는 유료 — 4절)
```

### 무료 입력항목 (DB `diagnosis_input_fields`, tier='FREE', is_active=true 실측)
| sector | 필수 | 선택 |
|---|---|---|
| BUILDING | address, total_floor_area, floor_count, building_use_type, worker_count | basement_count, built_year, main_structure |
| INDUSTRIAL | address, ksic_major, worker_count | total_floor_area |
| CONSTRUCTION | project_address, project_amount, worker_count | project_duration |

> 프런트는 섹터를 `INDUSTRY`로 전송, DB 정의는 `INDUSTRIAL`. `normalize_sector_db()`가 INDUSTRY→INDUSTRIAL 변환하여 흡수(확인됨).
> **무료에는 공정·설비·위험물·화학·고압가스 입력이 없다.**

### 흐름 (도식)
```
formValues['free']  ──POST /diagnosis/run (tier=FREE)──▶ DiagnosisRunBody
   └ form_data:{address, ksic_major, worker_count, ...}
        ▼ nexas_run_body_from_request: 별칭(ksic_code→ksic_major, address→region) + form_data 원본 보존
   run_diagnosis: inp 구성 + form_data 합류 ──▶ DiagnoseStep1Body
        ▼ engine_sector = MANUFACTURING(INDUSTRIAL) / BUILDING / CONSTRUCTION
   run_diagnose_step1_runtime ──▶ _input_to_facility_context ──▶ evaluate_facility_conditions_db
        ▼
   anonymous_diagnosis_results 저장 (source_type='free_diag', 7일 만료)
   diagnosis_auth_log.free_count += 1
```

### 저장 테이블
| 테이블 | 내용 |
|---|---|
| `anonymous_diagnosis_results` | input_data(sector/tier_code/floor_area/contract_amount_eok/workers + **form_data**(PR#93 후)), full_result, partial_result |
| `diagnosis_auth_log` | 본인인증 세션, free_count/free_limit |
| `diagnosis_disclaimer_log` | 면책 동의 |

---

## 4. 유료진단 구조

### 진입 방식
1. **연속 플로우**: 무료 결과(Step3) → "유료 진단 시작" → Step4(유료 입력) → 결제 → Step5(유료 결과). `loadPaidFlow()`가 렌더.
2. **결제 직입**: `?paid=&order_id=` → `handlePaidEntry()` → `GET {API}/payment/verify?order_id=` 호출.
   - **[미확인/미구현] `GET /payment/verify`(단수형) 엔드포인트는 tai-api 코드에 존재하지 않는다.** 결제 라우터는 `/payments/...`(복수형)이며 verify가 없다. 따라서 현재 `?paid=&order_id=` 직입은 작동하지 않는다.
3. 결제 자체: 프런트 모달에 "KG이니시스 연동 최종 승인 대기 중"으로, 결제 버튼이 `fix-request.html`(도입 문의)로 우회. **현재 유료 결제를 통한 실행은 막혀 있다.**

### 유료 입력항목 (DB `diagnosis_input_fields`, tier≠FREE 실측)
- **INDUSTRIAL**: PAID1(address, ksic_major, ksic_sub, worker_count, total_floor_area, has_safety_manager, electric_capacity, has_boiler, has_chemical_substance, has_hazardous_material, has_high_pressure_gas, has_hazmat_storage, has_dust_work, has_noise_work, has_confined_space, has_radiation, operation_shift) / PAID2(process_list 테이블) / PAID3(equipment_list 테이블)
- **BUILDING (PAID)**: 무료 항목 + has_safety_manager, electric_capacity, has_emergency_gen, elevator_count, escalator_count, has_sprinkler, has_fire_hydrant, has_smoke_control, has_gas, has_oil_storage, has_chemical, has_hazmat_storage, has_water_tank, has_septic_tank, has_cooling_tower, has_asbestos, is_multi_use 등 (총 36필드)
- **CONSTRUCTION (PAID)**: 무료 항목 + construction_type, process_list(필수), has_excavation, has_pile_work, has_steel_frame, has_concrete_work, has_demolition, has_tower_crane, has_scaffold, has_gondola, has_blasting, has_diving, operation_shift, subcontractor 등

### 흐름 (도식)
```
Step4 유료 입력 (formValues['paid'])
   │  산업: tier BASIC/STANDARD/PREMIUM → API tier PAID1/PAID2/PAID3
   ▼
POST /diagnosis/run (tier=PAID*, payment_ref=order_id)
   │  ※ 결제 미연동으로 현재 실호출 차단
   ▼
run_diagnosis: payment_ref 없으면 402. 있으면 무료와 동일 경로
   ▼
anonymous_diagnosis_results (source_type='paid_diag') + diagnosis_purchases
```

### 저장 테이블
| 테이블 | 내용 |
|---|---|
| `anonymous_diagnosis_results` | 무료와 동일 (source_type='paid_diag') |
| `diagnosis_purchases` | 결제 메타(tier_code, paid_amount, payment_ref, invoice_*) |

---

## 5. Sector별 표준모델

표준모델(facility_context)에서 **Rule이 실제로 읽는 키**는 `CONDITION_CODE_TO_CONTEXT_KEY`(legal_rules.py)의 값 집합으로 한정된다:
`worker_count, total_floor_area, electric_capacity, floor_count, elevator_count, boiler_capacity_kw, boiler_capacity_th, gas_capacity_kg, gas_capacity_m3, transformer_capacity_kva, annual_energy_toe, construction_amount, contractor_count, is_hazardous_material, is_multi_use, is_factory_registered`

> Rule 평가 함수 `evaluate_facility_conditions_db`에는 `has_high_pressure_gas / has_chemical_substance / has_boiler / has_sprinkler` 등 **has_* 키를 읽는 코드가 없다.** Rule이 위험물을 보는 키는 `is_hazardous_material`(bool→0/1)이다.

### BUILDING
| 입력항목(field_code) | facility_context 키 | Rule 사용 키 |
|---|---|---|
| total_floor_area | total_floor_area / building_area | O (building_area) |
| floor_count | floor_count | O |
| building_use_type | building_use_code | [미확인 — condition_code 데이터 없음] |
| worker_count | worker_count | O (employee_count→worker_count) |
| electric_capacity (PAID) | electric_capacity | O (electrical_capacity_kw) |
| elevator_count (PAID) | elevator_count | O |
| has_gas / has_chemical / has_oil_storage 등 (PAID) | ctx 생성 안 함 (키명 불일치) | ✕ |

### INDUSTRIAL (engine_sector=MANUFACTURING)
| 입력항목 | facility_context 키 | Rule 사용 키 |
|---|---|---|
| ksic_major | ksic_code | [미확인 — condition_code 데이터 없음] |
| worker_count | worker_count | O |
| electric_capacity (PAID) | electric_capacity | O |
| has_hazardous_material (PAID) | is_hazardous_material | O |
| has_high_pressure_gas / has_chemical_substance / has_boiler (PAID) | ctx 생성됨 (동일 키) | ✕ (Rule이 has_* 안 읽음) |
| process_list / equipment_list (PAID) | ctx 생성 안 함 | ✕ |
| operation_shift, has_dust/noise/confined/radiation | ctx 생성 안 함 | ✕ |

### CONSTRUCTION
| 입력항목 | facility_context 키 | Rule 사용 키 |
|---|---|---|
| project_amount | construction_amount / contract_amount | O |
| construction_type | construction_type | [미확인 — 코드 분기로 일부 사용] |
| worker_count / direct·subcon | worker_count (direct+subcon 합산) | O (50명 임계 직접 분기) |
| has_blasting | has_blasting | ✕ (ctx 생성되나 Rule 미사용) |
| process_list, has_excavation/tower_crane 등 | ctx 생성 안 함 | ✕ |

### SPECIAL (SPECIAL_FACILITY)
| 항목 | 비고 |
|---|---|
| 입력항목 | **[미확인] FREE/PAID 입력필드가 diagnosis_input_fields에 정의돼 있지 않음** |
| facility_context 키 | facility_type, total_floor_area, hospital_beds, student_count, worker_count (코드상 존재) |
| Rule 사용 키 | worker_count, total_floor_area |

---

## 6. 현재 확인된 PASS

UI → API → DTO → DB → facility_context → Rule **키 도달**까지 살아있는 항목 (PR#93 반영 가정):

| Key | 섹터 | 상태 |
|---|---|---|
| worker_count | 전 섹터 | PASS |
| total_floor_area / floor_area | 전 섹터 | PASS |
| ksic_major → ksic_code | INDUSTRIAL | PASS (ctx 도달) |
| building_use_type → building_use_code | BUILDING | PASS (ctx 도달) |
| construction_amount (project_amount) | CONSTRUCTION | PASS |
| direct_workers / subcon_workers | CONSTRUCTION | PASS |
| floor_count | BUILDING | PASS (PR#93로 하드코딩 해제) |
| electric_capacity | BUILDING/INDUSTRIAL PAID | PASS (ctx 도달) |
| elevator_count | BUILDING PAID | PASS |
| has_hazardous_material → is_hazardous_material | INDUSTRIAL PAID | PASS |

> **중대 단서:** 위 PASS는 "키가 Rule 평가에 도달 가능"이라는 의미다. 실제 매칭 발생 횟수는 7절의 condition_code 부재로 인해 사실상 0이다.

---

## 7. 현재 확인된 FAIL

| 항목 | 끊기는 지점 | 원인 | 수정 필요 |
|---|---|---|---|
| has_high_pressure_gas, has_chemical_substance, has_boiler (INDUSTRIAL) | facility_context → Rule | Rule 평가 코드가 has_* 키를 읽지 않음. is_hazardous_material만 읽음 | 엔진 매핑 결정 필요 (배선 아님) |
| has_gas, has_chemical, has_oil_storage, has_sprinkler 등 (BUILDING) | inp → facility_context | _input_to_facility_context가 BUILDING에서 이 키명을 ctx로 변환 안 함 (has_high_pressure_gas/has_hazardous_material 키명만 read) | 키 매핑 결정 필요 |
| process_list, equipment_list | inp → facility_context | ctx 생성 로직 없음 | 신규 사양 필요 |
| operation_shift, has_dust/noise/confined/radiation | inp → facility_context | ctx 생성 로직 없음 | 신규 사양 필요 |
| **전 항목 (근본 원인)** | facility_context → Rule | **운영 룰 소스 `runtime_metadata_resolution` 3,395건 중 condition_value 보유 7건, 숫자 임계값 0건 → projection 후 condition_code 생성 0건.** condition_code 없는 룰은 ctx를 비교하지 않고 섹터/법령 prefix로만 applicable 판정 | 룰 데이터에 condition_code/value 적재 필요 (Rule/Candidate 영역) |
| `GET /payment/verify` | UI 직입 | 엔드포인트 미구현 | 유료 직입 필요 시 신설 |

> **핵심:** 사용자 입력이 Rule 판정에 거의 반영되지 않는 근본 원인은 facility_context 배선이 아니라 **룰 데이터에 조건(condition_code)이 비어 있다는 것**이다. 이는 PR #90의 "READY=0건" 관찰과 일치한다.

---

## 8. 최근 수정 내역

| PR | 상태 | 변경 파일 | 이유 | 결과 |
|---|---|---|---|---|
| **#93** | **open (미머지)** | `services/diagnosis_nexas_adapter.py`, `services/diagnosis_integrated_svc.py` | 사용자 입력값(form_data)을 엔진 입력(inp)까지 배선 복구 | form_data 원본 DTO 보존 + inp 합류 + BUILDING floor_count 하드코딩(5) 해제 + input_data에 form_data 저장 + upgrade 경로 복원 |

PR #93 세부:
1. `diagnosis_nexas_adapter.py`: `nexas_run_body_from_request`가 `payload["form_data"] = form_data`로 원본 보존 (기존엔 pop 후 소실).
2. `diagnosis_integrated_svc.py`: `_merge_form_data_into_inp()` 추가 → run_diagnosis/upgrade_diagnosis에서 form_data를 inp에 합류. BUILDING `floor_count=5` → `_form_int("floor_count", 5)`. 저장 input_data에 form_data 보존.

> **[미확인] PR #93은 머지되지 않았다.** main에는 아직 반영 안 됨. 머지 시 유료진단 판정 결과가 바뀔 수 있어(설비·위험물 입력이 ctx에 도달) 실측 1건 검증 후 머지 권장.

관련 미머지 PR (맥락): #89 Obligation Quality Layer, #90 Quality Runtime(READY=0 관찰), #91 Check→Quality 검증, #92 50개 사업장 시뮬레이션. 전부 미머지.

---

## 9. 남은 작업

### 반드시 필요 (운영 영향 큼)
1. **룰 condition_code/condition_value 적재** — `runtime_metadata_resolution` 또는 projection 로직에 사용자 입력과 매칭할 조건을 채운다. 이것 없이는 어떤 입력도 Rule 판정에 실질 반영되지 않는다. (Rule/Candidate 담당)
2. **PR #93 실측 검증 후 머지 여부 결정.**

### 선택
3. `_input_to_facility_context`에 BUILDING has_gas→has_high_pressure_gas 등 키 매핑 추가 (입력 사양 결정 동반 → 법해석 검토 필요).
4. `evaluate_facility_conditions_db`에 has_* / process_list / equipment_list 조건 평가 추가.
5. `GET /payment/verify` 신설 (유료 직입 URL 필요 시).

### 향후 개선
6. SPECIAL 섹터 입력필드 정의(diagnosis_input_fields에 부재).
7. KG이니시스 결제 연동 완료 (현재 fix-request.html 우회).

---

## 10. 검증 방법 (신규 입력항목 추가 시 체크리스트)

새 입력항목이 Rule 판정까지 살아남는지 확인하는 순서. **각 단계에서 끊기면 다음으로 가지 말 것.**

```
[1] UI 입력
    └ diagnosis_input_fields에 (sector, tier, field_code) 행 존재? (is_active=true)
       SELECT * FROM diagnosis_input_fields WHERE sector=? AND tier=? AND field_code=?

[2] API Payload
    └ free-diagnosis.html에서 formValues[prefix][field_code]로 수집되어
      POST /diagnosis/run 의 form_data에 포함되는가? (동적 폼은 자동 포함)

[3] DTO 수신
    └ nexas_run_body_from_request 후 DiagnosisRunBody.form_data에 보존되는가? (PR#93 후 보존됨)
      ※ DiagnosisRunBody top-level 필드는 화이트리스트만. form_data dict는 전체 보존.

[4] DB 저장
    └ anonymous_diagnosis_results.input_data.form_data 에 기록되는가? (PR#93 후 기록)

[5] facility_context 생성
    └ services/legal_context.py _input_to_facility_context의 해당 sector 분기가
      inp.get("<field_code>")를 읽어 ctx 키를 만드는가?
      ※ 안 만들면 여기서 끊김 → ctx 생성 코드 추가 필요

[6] Rule 사용 키 확인
    └ 그 ctx 키가 legal_rules.py CONDITION_CODE_TO_CONTEXT_KEY의 값에 있는가?
      ※ 없으면 Rule이 절대 읽지 않음

[7] Rule 조건 존재 확인
    └ 그 condition_code를 가진 룰이 실제로 있는가?
      SELECT count(*) FROM runtime_metadata_resolution
        WHERE condition_value ~ '<숫자+단위>'
      ※ 현재 0건. 이 단계가 전체 병목.

[8] 결과 확인
    └ /diagnosis/run 응답 rules_table에 해당 룰이 applicable로 나오는가?
```

검증 도구:
- DB: Supabase `vwlahtguyggrhvslabax` (execute_sql)
- 코드: `taiengineering/tai-api`
- 입력폼 항목 즉시 확인(인증 불필요): `GET https://api.taieng.co.kr/diagnosis/fields?sector=INDUSTRY&tier=PAID1`
- 유료 입력폼 화면 확인(결제·인증 우회 없이, 브라우저 콘솔): free-diagnosis 접속 후 `authToken='preview'; sector='INDUSTRY'; paidTier='BASIC'; paidFee=79000; goStep(4);`

---

# 요약 (3개 섹션)

## 현재 구조
- 운영 진단은 `taieng/nexas/free-diagnosis.html`(단일 SPA) → `POST /diagnosis/run`(무료·유료 공통, tier 구분) → `DiagnosisRunBody` → `run_diagnosis` → `DiagnoseStep1Body` → `_input_to_facility_context` → `evaluate_facility_conditions_db` → `anonymous_diagnosis_results` 저장.
- 입력 항목은 `diagnosis_input_fields`(DB)가 정의하고 `GET /diagnosis/fields`로 동적 로드.
- 무료는 면적·인원·용도·KSIC 등 소수만 입력. 공정·설비·위험물·화학·고압가스는 유료 전용.
- Candidate는 사용자 입력으로 생성되지 않음(룰셋 측 데이터). 사용자 입력은 facility_context로 들어가 룰 매칭에만 사용.

## 수정 완료
- **PR #93 (open, 미머지)**: 사용자 입력 form_data를 DTO·inp·DB에 보존/합류하여 facility_context까지 도달하도록 배선 복구. BUILDING floor_count 하드코딩(5) 해제. 무료·유료·upgrade 전 경로 적용.
- 이 배선으로 worker_count, total_floor_area, ksic_major, building_use_type, floor_count, electric_capacity, elevator_count, has_hazardous_material(→is_hazardous_material) 등이 ctx까지 도달(키 도달 PASS).

## 남은 문제
- **최대 병목은 코드 배선이 아니라 룰 데이터다.** 운영 룰 `runtime_metadata_resolution` 3,395건 중 매칭 가능한 condition_code가 사실상 0건이라, ctx에 어떤 값이 도달해도 Rule 조건 비교가 일어나지 않는다(섹터/법령 prefix 기반 판정만). PR #90의 "READY=0건" 관찰과 동일 원인.
- 따라서 다음 담당자의 핵심 과제는 (1) 룰에 condition_code/condition_value 적재, (2) 필요 시 `_input_to_facility_context`·`evaluate_facility_conditions_db`에 has_*/공정/설비 조건 추가(법해석 검토 동반), (3) PR #93 실측 검증 후 머지다.
- 유료 직입 URL(`?paid=&order_id=`)은 `GET /payment/verify` 미구현으로 작동하지 않음. 결제(KG이니시스)는 연동 대기로 fix-request.html 우회 중.
