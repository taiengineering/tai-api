---
wo: CHEM-WO-DATA-KECO-002
status: READY_FOR_LIVE_GATE
date: 2026-10-04
---

# KECO_002_REFERENCE_FOUNDATION_EVIDENCE

tai-api base SHA = 8b4858019018f9b6abd80b5ca25fc5a60f8eb781
branch = feat/keco-reference-foundation
HEAD SHA = 2b89bef4380fa9c25dfea37c0a2d49b90616ec71

## new files

- services/keco_chemical/__init__.py
- services/keco_chemical/contract.py
- services/keco_chemical/client.py
- services/keco_chemical/parse.py
- services/keco_chemical/hash.py
- services/keco_chemical/models.py
- services/keco_chemical/store.py
- services/keco_chemical/probe.py
- tests/test_keco_chemical.py
- tests/fixtures/keco/normal_response.json
- tests/fixtures/keco/empty_response.json
- tests/fixtures/keco/null_items_response.json
- tests/fixtures/keco/absent_items_response.json
- tests/fixtures/keco/multi_typelist_response.json
- docs/sql/20261004_keco_reference_foundation.sql

## modified files

NONE

## migration

migration = docs/sql/20261004_keco_reference_foundation.sql
migration applied = YES
migration target = leg-prod (wrfcedzgdrfupenzqhur)
migration method = mcp__claude_ai_guri__apply_migration
migration result = success:true
tables created = msds_ref.keco_ingestion_runs, msds_ref.keco_raw_records, msds_ref.keco_chemicals, msds_ref.keco_regulatory_facts

## tests

tests = 38/38 PASS
skip = 0
test cmd = pytest tests/test_keco_chemical.py -v

## secrets

KECO_API_SERVICE_KEY = NOT_SET
LIVE API CALLS = 0
SECRET EXPOSURE = 0

## data

KECO RAW ROWS = 0
KECO CHEMICAL ROWS = 0
KECO FACT ROWS = 0

IDEMPOTENCY = N/A (no live data)
BULK COLLECTION = 0
KOSHA MUTATION = 0
PRODUCT DB WRITE = 0

## exit

EXIT = READY_FOR_LIVE_GATE
NEXT = KECO_API_SERVICE_KEY 발급 후 live probe WO 별도 진행
