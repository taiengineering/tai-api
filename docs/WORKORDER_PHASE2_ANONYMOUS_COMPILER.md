# 작업지시서: Phase 2 — 익명/소비자 진단 Compiler Core 연결

> Phase 1 완료: `facility_applicability_eval.py`, `compiler_core_svc.py`  
> Phase 2 목표: 익명·통합 진단이 Compiler Core temp-factory 경로 사용  
> 브랜치: `feature/connect-compiler-core-20260608` (Phase 1과 동일)  
> 원칙: 엔진 수정 금지. 연결만.

## Phase 1 산출물

- `services/facility_applicability_eval.py` — 순수 평가 로직
- `services/compiler_core_svc.py` — `fetch_compiler_candidates()`

## Phase 2 구현 (완료)

| 항목 | 파일 |
|------|------|
| 오케스트레이션 | `services/anonymous_factory_service.py` |
| 익명 API | `routers/anonymous_diagnosis.py` |
| 통합 진단 | `routers/diagnosis_integrated.py`, `services/diagnosis_integrated_svc.py` |
| [ISOLATED] | `diagnosis_runtime_step1.py`, `legal_runtime_fetch.py`, `rule_candidate_projection.py` |
| 테스트 | `tests/test_anonymous_factory_service.py` |

### anonymous_factory_service.py

- `create_temp_factory` — 소비자 입력 → `factories` INSERT (`[ANON]…`, `is_active=false`)
- `evaluate_single_factory` — `facility_applicability_eval` + `facility_applicability` INSERT
- `fetch_compiler_candidates` — `compiler_core_svc` 위임
- `_compiler_result_to_step1_format` — Compiler 출력 → step1 JSON (`rules_table`, `key_obligations`, …)
- `cleanup_temp_factory` — `facility_applicability` + `factories` DELETE
- `run_anonymous_diagnosis` — 전체 오케스트레이션 (finally cleanup)

## 흐름

```
DiagnoseStep1Body
  → create_temp_factory
  → evaluate_single_factory
  → fetch_compiler_candidates
  → _compiler_result_to_step1_format
  → cleanup_temp_factory (finally)
```

## 출력 호환

`rules_table`, `rules`, `key_obligations`, `law_badges`, `risk_level`, `summary`, `obligations`, `construction_summary`(건설)

- `engine_version`: `v3.0-compiler-core-anonymous`
- `rule_version`: `compiler_core:facility_applicability:v1`

## 검증 (수동)

- BUILDING 50명 → applicable 건수 입력 민감
- MANUFACTURING 300명 → 동일
- CONSTRUCTION 78억 → 동일
- 출력 포맷 기존 FE와 호환
- `factories` / `facility_applicability` 임시 데이터 잔류 없음 (cleanup)
