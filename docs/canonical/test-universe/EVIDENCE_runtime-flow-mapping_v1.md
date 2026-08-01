---
wo: WO-WIRING-001-STEP1
class: records
type: verification
scope: canonical
project: test-universe
title: Runtime Flow Mapping (Evidence Only)
version: 1
status: active
owner: taiwang
---

# RUNTIME FLOW MAPPING — EVIDENCE ONLY (WO-WIRING-001 STEP 1)

> pattern_dictionary·role_mapping이 현재 엔진 런타임에서 어디에 연결돼야 하는지 확인하기 위한 **호출 경로 복원만.** Injection Point·Wiring Plan·추론·제안·코드 수정 **없음.** 현재 엔진이 실제로 무엇을 읽는지 증거로 확정.
> 엔진 코드 taiengineering/tai-api.

## STEP 1-A — law_sector_mapping 실행 코드 사용 위치
```text
파일 : services/anonymous_factory_service.py
함수 : _load_sector_allowed_draft_ids(supabase, sector_value)
동작 : supabase.table("law_sector_mapping").select("law_id, sectors").in_("law_id", chunk)  [SELECT/READ]
용도 : 입구 sector 필터 (executable_draft→law_article→law_master←law_sector_mapping 연결)
       해당 sector가 sectors[]에 포함된 draft만 통과. 미매핑은 통과(누락방지), 타 sector 전용은 제외.
       매핑 없거나 실패 시 None → 필터 미적용(전체평가) 폴백.
구분 : 실행 코드 (주석 아님)
```
전수 28건 중 코드 8 / docs 20. 코드 파일: anonymous_factory_service·legal_engine_policy·section_sieve_service·semantic_diagnosis_service·constants/sectors·domain_filter_api·diagnosis_factory_test·schemas(reverse_check/section_candidate). **이 진단 경로의 실사용은 anonymous_factory_service의 SELECT.**

## STEP 1-B — Runtime Call Trace (생략 없이)
```text
create_anonymous_diagnosis [routers/anonymous_diagnosis.py, POST ""]
 → _create_anonymous_diagnosis_impl
   → _build_step1_body               # sector = SECTOR_BY_KIND[site_kind]
   → _run_step1_via_service
     → prepare_step1_body_for_compiler          [anonymous_factory_service]
     → run_anonymous_diagnosis                  [anonymous_factory_service]
       → create_temp_factory                    # factories.insert (sector_db=normalize_sector_db)
       → evaluate_single_factory
           → factories.select(id)
           → _load_sector_allowed_draft_ids
               → compiler_gw.fetch_executable_draft_articles  # executable_draft
               → law_article.select("id, law_id")             # law_article [READ]
               → law_sector_mapping.select("law_id, sectors") # law_sector_mapping [READ] ★
           → _load_draft_slot_groups                          # draft_slot
           → evaluate_draft_for_facility (per draft)          [facility_applicability_eval]
           → compiler_gw.insert_facility_applicability        # facility_applicability [WRITE]
       → fetch_compiler_candidates                            [compiler_core_svc]
       → _compiler_result_to_step1_format
           → _load_draft_fallback_context: law_article[READ], law_master[READ]
           → _merge_presentation_duplicates                   # Obs-002 표시 병합
       → cleanup_temp_factory
   → _partial_from_full → _build_standard_output              [diagnosis_helpers]
   → anonymous_diagnosis_results.insert
 → 응답
```

## STEP 1-C — Sector Decision 위치 (코드만, 판단 없음)
```text
사업장 sector 결정:
  파일 : routers/anonymous_diagnosis.py
  함수 : _build_step1_body
  방식 : SECTOR_BY_KIND[site_kind]  (construction/manufacturing/building/other → 입력 직접 결정)
  law_sector_mapping 사용 : NO

법령 sector 필터:
  파일 : services/anonymous_factory_service.py
  함수 : _load_sector_allowed_draft_ids
  방식 : law_sector_mapping.sectors에 해당 sector 포함 여부로 draft 통과/제외
  law_sector_mapping 사용 : YES (SELECT)
  환원 : to_mapping_sector (constants.sectors)

관측: sieve_clause(legal_engine_policy, clause_sector 거름망)는 이 진단 경로
     호출 체인에 미등장. (앞 세션의 "sieve_clause가 실질 sector 결정" 추정을 코드가 정정)
```

## STEP 1-D — pattern_dictionary 전수 검색
```text
전수 3건: docs 3 · archive 0 · runtime 0 · migration 0 · sql 0
  docs/canonical/test-universe/DEPLOY_chg009-db-sql-prep_v1.md
  docs/canonical/test-universe/DEPLOY_chg009-post-apply-validation_v1.md
  docs/canonical/test-universe/VERIFY_pattern-dictionary_v1.md
★ Runtime 사용 건수: 0
```

## STEP 1-E — role_mapping 전수 검색
```text
docs 제외 2건:
  watch_engine/identity/__init__.py  → identity_role_mapping 테이블(users.role_code 권한매핑).
                                        우리 role_mapping(규율대상/시설) 아님. 변수 _role_mapping_cache도 권한매핑 캐시.
  _archive/routers_20260608/...       → archive(비활성)
★ Runtime 사용 건수: 0 (우리 role_mapping 테이블 기준)
```

## STEP 1-F — Runtime Read Matrix
```text
Asset               Runtime Read  Evidence(함수)
law_master          YES           anonymous_factory_service._load_draft_fallback_context (law_master.select)
law_article         YES           anonymous_factory_service._load_sector_allowed_draft_ids · _load_draft_fallback_context (law_article.select)
law_sector_mapping  YES           anonymous_factory_service._load_sector_allowed_draft_ids (law_sector_mapping.select)
pattern_dictionary  NO            참조 0 (3건 전부 docs)
role_mapping        NO            참조 0 (identity_role_mapping은 별개 권한테이블; _archive 비활성)
```
(YES는 실행 코드 SELECT 근거가 있을 때만 표기.)

## Exit Criteria 점검
```text
[v] law_sector_mapping Runtime 사용 위치 확보 (_load_sector_allowed_draft_ids, SELECT)
[v] anonymous_diagnosis 호출 경로 확보 (생략 없이)
[v] Sector 결정 위치 확보 (입력 SECTOR_BY_KIND + 법령필터 law_sector_mapping)
[v] pattern_dictionary Runtime 사용 여부 확인 (NO)
[v] role_mapping Runtime 사용 여부 확인 (NO)
[v] Runtime Read Matrix 작성
```

## 산출물
```text
runtime_call_trace.md · runtime_read_matrix.csv · runtime_search_inventory.csv
```

## 규율 준수
- Injection Point 미작성 · Wiring Plan 미작성 · 연결 위치 추론 없음 · 코드 수정 0.
- 다음(별도): STEP 2 Injection Point Discovery는 이 Evidence 확정 후 진행.
```
```
