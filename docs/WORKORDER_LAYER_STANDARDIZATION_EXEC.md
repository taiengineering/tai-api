# 작업지시서: 법령진단 표준화 실행 (4단계)

> 표준 정의: docs/LEGAL_DIAGNOSIS_LAYER_STANDARD.md
> 원칙: 한 레이어씩 적용 → 검증 → 다음 레이어. 한 번에 다 하지 않는다.
> 엔진(Compiler Core) 내부 수정 절대 금지.
> 브랜치: feature/layer-standardization-20260608
> PR: Draft, merge 금지.

## 절대 규칙
```
1. 엔진 내부(facility_applicability_eval 평가 로직, compare_numeric, aggregate_applicability_status)는 건드리지 않는다.
2. 한 레이어 적용 후 반드시 검증하고 보고한다.
3. 검증 통과 전에 다음 레이어로 넘어가지 않는다.
4. 13번째는 이 단계에서 엔진을 건드려서 망했다. 반복 금지.
```

## STEP 1 — Layer 1→2 (가장 안전, 먼저)
목적: 소비자 입력(building_use_code, floor_count)이 factories에 저장. P-1-01 해소.
파일: services/anonymous_factory_service.py → create_temp_factory
작업: factories INSERT에 building_use_code(←building_use_type/facility_type), floor_count, gas_capacity_m3, hazardous_material 추가. site_type 왜곡 수정(sector 코드 들어가던 것 정리).
검증: BUILDING 병원 5층 50명 → factories 저장 확인 → facility_applicability MATCH 건수 변화 → 에러 없음.
통과 후 STEP 2. **STEP 1 끝나면 멈추고 보고.**

## STEP 2 — Layer 2→3 (FIELD_MAP 확장)
목적: FIELD_MAP에 facility_type 등 추가.
파일: services/facility_applicability_eval.py → FIELD_MAP
작업: building_use_code→facility_type, ksic_code→facility_type, construction_type→facility_type, gas_capacity_m3→storage_capacity 추가. compare/status 로직 불변.
검증: facility_type 220슬롯이 MISSING_DATA→MATCH/NOT 전환되는가. 에러 없음.
통과 후 STEP 3. 멈추고 보고.

## STEP 3 — Layer 3→4 (fallback 보강)
목적: 익명 진단 fallback이 draft에서 law_name 가져옴. P-3-01 해소.
파일: services/anonymous_factory_service.py → _compiler_result_to_step1_format (또는 compiler_core_svc.py fallback)
작업: task_candidates 비었을 때 facility_applicability.draft_id로 executable_draft 조회 → law_name, obligation_type, title 채움. 엔진 평가 결과는 안 바꿈.
검증: rules_table에 law_name 채워짐(이전 빈값). rule_type, bucket 채워짐. 에러 없음.
통과 후 STEP 4. 멈추고 보고.

## STEP 4 — Layer 4→5 (obligations flat 통일)
목적: Transform이 obligations 전개. evidence 표준화.
파일: routers/diagnosis_transform.py 또는 services/diagnosis_transform.py → _extract_obligations
작업: wrapper {category,label,items:[...]}의 items[]를 순회하여 각 item 전개. evidence는 text 배열. Transform만 수정.
검증: obligations가 flat list. title/law_name/evidence 채워짐(이전 title=의무사항, evidence=[]). 에러 없음.
통과 후 STEP 5. 멈추고 보고.

## STEP 5 — Layer 5→6 (partial 함수 통합)
목적: _partial_from_full과 _build_partial 통합. 출력 일관성.
작업: _build_standard_output(full_result) 하나로 통합. 두 경로(익명/통합)가 같은 함수 호출. 출력 필드를 표준5에 맞춤.
검증: 익명/통합 출력 형태 동일. evaluated_at, rules_preview 등 일관. 프론트 기대 필드 존재. 에러 없음.
통과 후 전체 검증.

## 최종 검증
섹터별 E2E: BUILDING 병원 5층 50명 / INDUSTRIAL 제조 300명 / CONSTRUCTION 78억 120명
각 결과: rules_table에 law_name 채워짐, obligations 상세 전개, facility_type 조건 반영, 출력 일관, 에러 없음.

## 진행 방식
STEP 1 작업→검증→보고→(사용자 확인)→STEP 2→... 각 STEP 사이 멈추고 보고. 한 번에 STEP 1~5 다 하지 않는다.

## 주의
- 엔진 평가 로직 수정 금지
- 각 STEP 후 멈추고 검증 보고
- 검증 실패 시 다음 STEP 진행 금지
- Draft PR, merge 금지
- Supabase MCP 사용 가능 (project_id: vwlahtguyggrhvslabax)
