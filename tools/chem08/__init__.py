"""OBJ-CHEM-08 production materializer tools.

- materialize_production.py: --dry-run classification/chunk-plan CLI,
  and --execute that is hard-blocked under WO-CHEM-08 (no DB connection
  is ever opened). A future execution WO must flip
  services.kosha_msds.materialize_writer.PRODUCTION_WRITE_ALLOWED
  before any real DB write is possible.
"""
