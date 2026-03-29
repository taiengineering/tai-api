# TAI Backend MEMORY — 2026-03-29

## API 버전
- **main.py**: v4.2.0
- **legal_engine.py**: v4.2.0
- **kosha_apis.py**: v1.4.0
- **Railway**: 배포 완료

---

## 오늘 완료된 작업 (2026-03-29)

### 1. 미완료 항목 전체 처리 ✅

| 항목 | 결과 |
|------|------|
| contracts 503 | ✅ 이미 200 정상 (이전 세션에서 해결됨) |
| 행안부 안전정보 URL | ✅ `1741000/FcltsSafetyInfoService2025` 확인 (data.go.kr: 15073554) |
| MSDS 파라미터명 | ✅ `materialName` → `chemNm` 수정, XML 전용 파싱 추가 |
| kosha-guide body | ✅ 원인: IP 제한으로 브라우저 직접 차단, Railway에서는 정상 |

### 2. safety_info.py v1.0.0 신규 ✅
- prefix: `/safety-info`
- End Point: `apis.data.go.kr/1741000/FcltsSafetyInfoService2025`
- `GET /safety-info/types` — 제공 시설 타입 목록 (19종)
- `GET /safety-info/{facility_type}` — 시설별 안전정보 조회
  - 공통 파라미터: fclts_cd, sido, sigungu, fclt_nm, page_no, num_of_rows
  - 지원 타입: facilities, buildings, multi-use, playground, childcare, hospital, hotel, resort, school, youth-training, amusement, performance, food, water-leisure, harbor, hazmat, traditional-market, long-term-care (18종)

### 3. kosha_apis.py v1.4.0 업데이트 ✅
- `_parse_xml_response()` 신규: XML 전용 파싱 → items 리스트 자동 변환
- MSDS 파라미터명: `materialName` → `chemNm` (실제 API 기준)
- MSDS `type=json` 파라미터 제거 (XML 전용 API)
- kosha-guide 브라우저 IP 제한 주석 추가

### 4. 법령진단 3단계 재구성 ✅ (작업지시서: TAI_Backend_작업지시서_법령진단_3단계.md)

#### DB 변경사항

**master_building_legal_rules 컬럼 추가:**
- `sector` VARCHAR(30) — BUILDING/MANUFACTURING/CONSTRUCTION/SPECIAL_FACILITY
- `diagnosis_stage` SMALLINT DEFAULT 1 — 진단 단계
- `obligation_summary` TEXT — 의무 요약
- `penalty_summary` TEXT — 과태료 요약
- `source_api` VARCHAR(100) — 법령 출처

**신규 인덱스:**
- `idx_mblr_sector` ON master_building_legal_rules(sector)
- `idx_mblr_stage` ON master_building_legal_rules(diagnosis_stage)

**신규 테이블:**
- `factory_diagnosis_results` — 진단 결과 이력
  - id, factory_id, sector, diagnosis_stage, input_data(jsonb), result_data(jsonb), rule_count, is_latest, created_by, created_at
  - 인덱스: idx_fdr_factory_id, idx_fdr_latest
- `diagnosis_rule_results` — 룰별 적용 결과
  - id, diagnosis_id, rule_code, rule_name, law_name, law_article, obligation, due_date, status, form_code, created_at
  - 인덱스: idx_drr_diagnosis_id

**기존 데이터 마이그레이션:**
- 기존 396개 룰 전체 → `sector=BUILDING`, `diagnosis_stage=1` 업데이트 완료

#### legal_engine.py v4.2.0 신규 API

| 엔드포인트 | 설명 | 비용 |
|-----------|------|------|
| `POST /legal-engine/diagnose/step1` | 기초 진단 (sector + 기초 input) | 무료 |
| `POST /legal-engine/diagnose/step2` | 공정 진단 (processes 선택) | 유료 |
| `POST /legal-engine/diagnose/step3` | 설비 진단 (설비 등록 + D-day) | 유료 |
| `GET /legal-engine/diagnose/{id}/latest` | 최신 진단 결과 조회 | - |
| `GET /legal-engine/diagnose/{id}/history` | 진단 이력 목록 | - |

**신규 헬퍼 함수:**
- `_evaluate_condition(rule, input_data)` — IN/NOT_IN/>=/<=/==/==true/==false 연산자 지원
- `_determine_risk_level(rule_count)` — LOW/MEDIUM/HIGH 판정
- `_save_diagnosis_result(...)` — factory_diagnosis_results 저장 (is_latest 자동 관리)
- `_create_report_events_from_rules(...)` — REPORT/APPOINTMENT 타입 룰 → report_events 자동 생성 (중복 방지)

**step1 요청 예시:**
```json
{
  "factory_id": "uuid",
  "sector": "BUILDING",
  "input": {
    "building_use_category": "업무시설",
    "gross_floor_area": 5000,
    "above_ground_floors": 8,
    "worker_count": 50,
    "electric_capacity_kw": 200
  }
}
```

**step3 설비 D-day 응답:**
- `next_due_date` — 다음 검사 예정일
- `days_left` — 남은 일수
- `status` — NORMAL / URGENT(30일 이내) / OVERDUE(초과)

**기존 API 하위 호환 유지:**
- `POST /legal-engine/apply/{factory_id}` — 유지
- `POST /legal-engine/apply-quote/{quote_id}` — 유지
- `GET /legal-engine/result/{factory_id}` — 유지
- `GET /legal-engine/summary/{factory_id}` — 유지
- `POST /legal-engine/create-inspection-sets/{factory_id}` — 유지

### 5. main.py v4.2.0 ✅
- `safety_info_router` 추가 등록

---

## 현재 라우터 전체 목록 (main.py v4.2.0)

| 파일 | prefix | 버전 | 상태 |
|------|--------|------|------|
| auth.py | /auth | - | ✅ |
| users.py | /users | - | ✅ |
| companies.py | /companies | - | ✅ (nts-verify 추가) |
| factories.py | /factories | - | ✅ |
| system_codes.py | /system-codes | v2.0.0 | ✅ |
| legal_engine.py | /legal-engine | v4.2.0 | ✅ |
| ksic_engine.py | /ksic-engine | v3 | ✅ |
| factory_process_v3.py | /factory-process | v3 | ✅ |
| process_management.py | /process-management | v1.1 | ✅ |
| building_register.py | /building-register | v2.3.0 | ✅ |
| quotes.py | /quotes | - | ✅ |
| report_forms.py | /report-forms | v2.0.2 | ✅ |
| contracts.py | - | - | ✅ 200 정상 확인 |
| contacts.py | /contacts | - | ✅ |
| education.py | /education | - | ✅ |
| notifications.py | /notifications | - | ✅ |
| equipment_assets.py | /equipment-assets | v1.2.0 | ✅ |
| engine_equipment.py | /engine-equipment | v1.2.2 | ✅ |
| engine_model.py | /engine-model | v1.0.0 | ✅ |
| personnel.py | /personnel | v1.1.0 | ✅ |
| repair.py | /repair | v1.0.0 | ✅ |
| biz_verify.py | /biz-verify | v1.0.0 | ✅ |
| kosha_apis.py | /kosha | v1.4.0 | ✅ |
| fire_hazmat.py | /fire-hazmat | v1.0.0 | ✅ |
| safety_info.py | /safety-info | v1.0.0 | ✅ |
| posts.py | /posts | v1.0.0 | ✅ |
| schedule_engine.py | /schedule-engine | - | ✅ |
| roles.py | /roles | - | ✅ |
| teams.py | /teams | - | ✅ |
| areas.py | /areas | - | ✅ |
| buildings.py | /buildings | - | ✅ |
| inspection_sets.py | /inspection-sets | - | ✅ |
| work_schedules.py | /work-schedules | - | ✅ |
| inspection_checklist.py | /inspection | v1.1.0 | ✅ |
| admin_stats.py | /admin | v1.0.0 | ✅ |

---

## 공공 API 인증키 및 엔드포인트 정리 (전체)

```
공통 인증키: da4e826323c2c9fef9f325bd4e39a3765d06ac1b582695bcbc475bc0a076255b
환경변수: BUILDING_API_KEY / NTS_API_KEY (Railway 설정 완료)

국세청 NTS: https://api.odcloud.kr/api/nts-businessman/v1
  POST /validate  — body: {businesses: [{b_no, start_dt, p_nm, ...}]}
  POST /status    — body: {b_no: ["번호"]}

KOSHA: https://apis.data.go.kr/B552468
  srch/smartSearch                          ✅ 법령 스마트검색 (returnType=json)
  disaster_api02/getdisaster_api02          ✅ 국내재해사례 (callApiId 고정)
  selectMediaList01/getselectMediaList01    ✅ 안전보건자료 링크
  constDsstr01/getconstDsstr01              ✅ 건설업 중대재해 (2017~2021)
  msdschem/getChemList                      ✅ MSDS 목록 (XML전용, 파라미터: chemNm, casNo)
  msdschem/getChemDetail01~16               ✅ MSDS 섹션별 상세
  koshaguide/getKoshaGuide                  ✅ 코샤가이드 (Railway에서만 정상)

소방청: https://apis.data.go.kr/1661000/materialInfoSvc
  getMaterialList  ✅ 위험물 목록
  getMaterialInfo  ✅ 위험물 상세

행정안전부: https://apis.data.go.kr/1741000/FcltsSafetyInfoService2025
  /getFcltsInfoSearch_4              ✅ 시설물 기본정보
  /getBuildSafetyInfoSearch_4        ✅ 건축물 안전정보
  /getMultiUseFacilitySafetyInfoSearch_4  ✅ 다중이용시설
  /getNlprkSafetyInfoSearch_4        ✅ 어린이놀이시설
  /getCrSafetyInfoSearch_4           ✅ 어린이집
  (외 13종)
```

---

## DB 변경사항 누적

### 신규 테이블 (전체)
- `posts` — 안전정보 게시판
- `factory_diagnosis_results` — 법령진단 결과 이력
- `diagnosis_rule_results` — 룰별 적용 결과

### 컬럼 추가
- `master_building_legal_rules`: sector, diagnosis_stage, obligation_summary, penalty_summary, source_api

### 데이터 마이그레이션
- `master_building_legal_rules` 396건 → sector=BUILDING, diagnosis_stage=1

### 수정된 컬럼 인식
- `form_templates.bylseq` (소문자) — 기존 코드 `bylSeq` 오류 수정

---

## 섹터별 핵심 입력 변수 (step1 input)

| sector | 입력 변수 |
|--------|----------|
| BUILDING | building_use_category, gross_floor_area, above_ground_floors, worker_count, electric_capacity_kw, has_hazardous_material, has_high_pressure_gas |
| MANUFACTURING | ksic_lv1_code, worker_count, gross_floor_area, has_hazardous_material, has_high_pressure_gas, has_chemical_substance, has_boiler, electric_capacity_kw |
| CONSTRUCTION | contract_amount, worker_count, construction_type, has_tunnel_bridge |
| SPECIAL_FACILITY | facility_type, gross_floor_area, hospital_beds, student_count, worker_count |

---

## 미완료 / PENDING

| 항목 | 내용 |
|------|------|
| MSDS 실 데이터 반환 확인 | chemNm 파라미터 수정 후 Railway에서 실제 데이터 반환 여부 미확인 |
| 진단 3단계 실제 룰 데이터 | 현재 BUILDING 396개만 stage=1. MANUFACTURING/CONSTRUCTION/SPECIAL_FACILITY 룰 데이터 추가 필요 |
| step3 cycle_years 동적 조회 | 현재 기본값 2년 하드코딩 → 추후 DB 기준으로 확장 필요 |

---

## 주요 원칙 / 트러블슈팅 기록 (누적)

- **PostgreSQL 컬럼명**: 항상 소문자 (bylseq ✓, bylSeq ✗)
- **main.py 수정**: 반드시 단독 `create_or_update_file`로 (push_files와 혼용 시 SHA 충돌)
- **FastAPI 라우팅 순서**: 정적 경로(`/msds/sections`)를 파라미터 경로(`/msds/{kmc_no}/detail`) 보다 먼저 선언
- **Railway PDF**: WeasyPrint(GTK 의존) 사용 불가 → xhtml2pdf(순수 Python) 사용
- **KOSHA API returnType**: 각 엔드포인트별 명시 필요 (기본값 없음)
- **MSDS API**: XML 전용 응답 (type/returnType 파라미터 없음), 파라미터명 `chemNm` (not materialName)
- **NTS API**: POST 방식, serviceKey는 query string, body는 JSON body로 분리
- **공공API IP 제한**: KOSHA 일부 API는 브라우저 직접 호출 불가 (IP 화이트리스트) → Railway 서버에서만 정상 작동
- **법령진단 3단계**: stage=1 룰은 condition_1_field/operator/value 기준으로 _evaluate_condition() 평가
  - 기존 엔진(/apply)의 _check_rule_conditions()와 별개 함수로 관리 (호환성 분리)
- **factory_diagnosis_results is_latest**: 새 진단 저장 시 기존 is_latest=True → False 자동 갱신
