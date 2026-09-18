"""OBJ-CHEM-FULL-READINESS-005 — FULL acceptance harness tools.

- check.py: read-only harness CLI. Composes existing collectors
  (ops.collect_hydration_status / ops.collect_dictionary_runtime /
  ops.collect_public_runtime) with cutover.is_full_ready and
  materialize_writer classifiers via
  services.kosha_msds.full_acceptance.evaluate_full_acceptance.
  Emits a single verdict + per-stage evidence dict. No production
  mutation, no publish, no env change, no KOSHA API call, no deploy.
"""
