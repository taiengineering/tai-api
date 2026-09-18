"""OBJ-CHEM-FULL-READINESS-004 — MSDS ops observability tools.

- status.py: read-only operator status CLI. Reads existing CHEM-04
  artifacts + production DB (via the publish/materialize store
  interface) + live /search-dict/* endpoints. Never mutates.
"""
