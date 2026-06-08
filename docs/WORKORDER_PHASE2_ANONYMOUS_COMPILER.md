# 작업지시서: Phase 2 — 익명 진단 Compiler Core 연결

> Phase 1 완료: facility_applicability_eval.py 추출, compiler_core_svc.py 공유 fetch
> Phase 2 목표: 익명 진단(factory_id=None)이 Compiler Core를 사용하도록 연결
> 브랜치: feature/connect-compiler-core-20260608 (Phase 1과 동일 브랜치)
> 원칙: 엔진 수정 금지. 연결만.

## Phase 1 산출물 (이미 있는 것)

- services/facility_applicability_eval.py → evaluate_single_factory()
- services/compiler_core_svc.py → fetch_compiler_candidates()

## Phase 2 구현

### 1. services/anonymous_factory_service.py (신규)

- create_temp_factory(supabase, sector, input_data) → factory_id
- run_anonymous_diagnosis(supabase, sector, input_data) → result_data
- cleanup_temp_factory(supabase, factory_id)
- _compiler_result_to_step1_format(compiler_result, sector) → 프론트 호환 포맷

### 2. routers/anonymous_diagnosis.py 변경

_run_step1_via_service()가 run_anonymous_diagnosis()를 호출하도록 교체.

### 3. services/diagnosis_integrated_svc.py 동일 변경

### 4. 격리

- services/diagnosis_runtime_step1.py → [ISOLATED]
- services/legal_runtime_fetch.py → [ISOLATED]
- services/rule_candidate_projection.py → [ISOLATED]

### 5. 검증

- BUILDING 50명 → ~100건 이하
- MANUFACTURING 300명 → ~100건 이하
- CONSTRUCTION 78억 → ~200건 이하
- 출력 포맷 기존과 호환
- factories 테이블 임시 데이터 잔류 없음

## 상세 내용은 로컬 WORKORDER_PHASE2_ANONYMOUS_COMPILER.md 참조
