# Canonical Runtime Boundary

> Date: 2025-05-24

TAI is not a deprecation target. TAI legal/document runtime is an active maintenance target.

## 1. Canonical Runtime Path

```
[HTTP Request]
  -> routers/engine_legal.py
  -> routers/compiler_core.py
  -> routers/report_forms.py
  -> services/legal_engine_svc.py        (runtime entry)
  -> services/legal_runtime.py           (runtime evaluation)
  -> services/diagnosis_service.py       (diagnosis)
  -> services/runtime_evaluator_svc.py   (runtime evaluator)
  -> services/simulation_svc.py          (simulation)
  -> services/rule_gen_svc.py            (rule generation)
  -> [Supabase runtime tables]
  -> [HTTP Response]
```

## 2. Runtime Tables

| Table | Read by | Written by |
|-------|---------|------------|
| master_building_legal_rules | services/legal_runtime.py | scripts/law_db_insert.py, scripts/law_to_rules.py |
| facility_applicability | search confirmed | scripts/run_facility_applicability.py |
| task_candidate | services/diagnosis_service.py, runtime_evaluator_svc.py | scripts/run_task_candidate.py, routers/compiler_core.py |
| schedule_candidate | search confirmed | scripts/run_schedule_candidate.py |
| penalty_obligation_relation | services/diagnosis_service.py | scripts/run_penalty_candidate.py, routers/compiler_core.py |
| compliance_review_queue | services/diagnosis_service.py | scripts/run_compliance_package.py, routers/compiler_core.py |

## 3. Extraction Pipeline (separate)

```
scripts/track_e_phase2_run.py (CLI only)
  -> engine/pipeline.py
  -> [stage_1_clauses, stage_2_elements, verification_log]
```

No API route. No scheduler. CLI-only.

## 4. Deletion Prohibition

Must not be deleted:
- services/legal_engine_svc.py, legal_runtime.py, diagnosis_service.py, runtime_evaluator_svc.py
- routers/compiler_core.py, engine_legal.py, report_forms.py
- scripts/run_task_candidate.py, run_facility_applicability.py, run_schedule_candidate.py, run_penalty_candidate.py, run_compliance_package.py, law_db_insert.py, law_to_rules.py
- db/database.py
- Supabase runtime tables (6)
- engine/ directory (retained)
