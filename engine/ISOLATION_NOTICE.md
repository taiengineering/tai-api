# Extraction Pipeline Isolation Notice

This directory is part of the offline extraction/decomposition pipeline.

## Confirmed Execution Path

```
scripts/track_e_phase2_run.py
  -> engine/pipeline.py (TAIExtractionPipeline)
  -> engine/iterator.py (PipelineIterator, Phase22V3Iterator)
```

## Characteristics

- CLI/script activated only (argparse)
- No FastAPI route activation confirmed
- No scheduler activation confirmed
- Not part of the canonical runtime diagnosis path

## Canonical Runtime Path (separate)

```
services/legal_engine_svc.py
services/legal_runtime.py
services/diagnosis_service.py
services/runtime_evaluator_svc.py
```

## Tables Written By This Pipeline

| Table | Operation |
|-------|-----------|
| stage_1_clauses | UPDATE |
| stage_2_elements | UPDATE |
| verification_log | INSERT |
| rule_classify_subtype | UPDATE / INSERT |

## Tables NOT Written By This Pipeline

| Table |
|-------|
| master_building_legal_rules |
| facility_applicability |
| task_candidate |
| schedule_candidate |
| penalty_obligation_relation |
| compliance_review_queue |

## Why Retained

- Legal extraction assets have historical and operational value
- Stage outputs are preserved data
- Future extraction/runtime separation may formalize this boundary

## Evidence

- Engine Activation Trace (2025-05-24): 4 files import engine.pipeline
- Stage-Runtime Propagation Audit (2025-05-24): 0 direct stage-to-runtime connections
