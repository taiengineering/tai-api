"""OBJ-CHEM-05 authoritative KOSHA MSDS materialize adapter tools.

- build_materialize_plan.py: reads responses.jsonl + optional census,
  writes a deterministic materialize plan and dry-run report.
- materialize_official_v12.py: --dry-run / --execute CLI. --execute is
  fail-closed until FULL_OFFICIAL corpus is complete AND owner-authorized.
  This adapter never emits PUBLISHED_FULL (that is a separate future WO).
"""
