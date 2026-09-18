# TAI Shared Search — Foundation v1

**WO**: WO-TAI-SHARED-SEARCH-F1 (Phase B)
**Status**: implementation-ready. Migration file present; production
apply is **explicitly deferred** to a separate Owner-approved step.
**Contract source**:
- `docs/search/TAI_SHARED_SEARCH_CONSTITUTION_v1.md`
- `docs/search/TAI_SHARED_SEARCH_DOCUMENT_CONTRACT_v1.md`
- `docs/search/TAI_SHARED_SEARCH_RESULT_CONTRACT_v1.md`

This document describes **how F1 realizes the contracts**. No new
contract is created here — every design choice cites a clause.

---

## 1. Architecture

```
   Domain SoT (kosha_guide / kosha_msds_* / csi_accident_cases / ...)
         │
         │   (F2 adapter — separate WO per domain)
         ▼
   SearchDocument (contract §3)   ── validated + normalized + hashed
         │
         │   services.shared_search.writer.Writer
         ▼
   Unified Search Projection (single logical projection)
      ├── search_documents          — current serving rows
      ├── search_rebuild_runs       — one per FULL REBUILD attempt
      └── search_rebuild_documents  — staged rows per run
         │
         │   promote_search_rebuild(run_id)     (atomic swap)
         ▼
   consumers (F3 Retrieval / F4 Public·SaaS·Paid·LEG enrichment)
```

The three tables live under `public.` in Supabase. Only the two
supporting tables (rebuild_runs, rebuild_documents) accumulate
history; `search_documents` is the always-current serving surface.

## 2. Physical schema

`supabase/migrations/20260919_shared_search_foundation.sql`.

### 2.1 `search_documents`

One row per canonical searchable object.

- PK: `id uuid`
- **Unique**: `(object_type, canonical_id)` — enforces Document
  Contract §2 identity contract at the DB layer
- **CHECK** `publication_status IN ('PUBLISHED', 'HOLD', 'REMOVED')`
  — enforces §6 shared enum
- **CHECK** `jsonb_typeof(subjects) = 'array'` — enforces §3 subjects
  shape
- **CHECK** `jsonb_typeof(context) = 'array'` — enforces §3/§8 context
  shape
- `source_key text` is **NULLABLE** — enforces §3 nullability
- `aliases`, `keywords`, `visibility_scopes` are `text[]` with
  default `'{}'`
- `subjects`, `context` are `jsonb` arrays of paired objects (§3, §8)
- `content_hash text NOT NULL` — deterministic per §5
- `indexed_at timestamptz NOT NULL DEFAULT now()`

Foundation indexes are minimal:

- `search_documents_canonical_uk (object_type, canonical_id)` — required
- `search_documents_publication_status_idx (publication_status)` — used
  by the Writer to enumerate PUBLISHED rows during rebuild validation

FTS / trigram / ranking indexes are **NOT** created by F1 — those
land alongside the retrieval engine in F3 (SEARCH-05).

### 2.2 `search_rebuild_runs`

One row per FULL REBUILD (or scoped DOMAIN rebuild) attempt.

- PK: `run_id uuid`
- **CHECK** `status IN ('RUNNING', 'VALIDATED', 'PROMOTED', 'FAILED')`
- **CHECK** `run_type IN ('FULL', 'DOMAIN')`
- Carries `expected_domains text[]`, `completed_domains text[]`,
  `candidate_count int`, `current_count_before int`, and a
  `manifest_json jsonb` for arbitrary provenance the adapter wants to
  record (adapter SHAs, source snapshot ids, etc.).
- On success `completed_at` is set to promotion time; on failure
  `error_code` + `error_message` are recorded.

Index: `(status, started_at DESC)` for the operational "latest
run per state" query.

### 2.3 `search_rebuild_documents`

Staged SearchDocuments for an in-flight rebuild.

- PK: `(run_id, object_type, canonical_id)` — prevents duplicate stage
  within one run
- FK: `run_id → search_rebuild_runs.run_id ON DELETE CASCADE`
- `document_json jsonb` = the full SearchDocument wire dict
- `content_hash text` mirrors the doc's hash for reconciliation

### 2.4 `promote_search_rebuild(uuid) RETURNS TABLE(promoted_count integer)`

Server-side atomic promotion. Behavior:

1. Locks the target run FOR UPDATE.
2. Raises `no_data_found` if the run doesn't exist.
3. Raises `invalid_parameter_value` if the run's status is not
   `VALIDATED`.
4. `DELETE FROM search_documents` + `INSERT FROM staging` in one
   transaction. Any error inside the function rolls back the whole
   swap — the current projection is either fully replaced or fully
   preserved. This is Constitution §10's "no partial promotion"
   guarantee at the SQL layer.
5. Updates the run row to `status='PROMOTED'`, `completed_at=now()`.

## 3. Python service layer

Under `services/shared_search/` — one package for the entire
Foundation. Adapters (F2) and the Retrieval Engine (F3) import from
here; no Foundation code imports from the adapter side.

### 3.1 `contract.py`

Fixed vocabulary + typed error.

- `PUBLICATION_STATUS_{PUBLISHED,HOLD,REMOVED}` + `ALLOWED_PUBLICATION_STATUSES`
- `VISIBILITY_{PUBLIC,SAAS,PAID,INTERNAL}` + `ALLOWED_VISIBILITY_SCOPES`
- `ALLOWED_CONTEXT_TYPES = {process, task, equipment, chemical,
  legal_obligation, risk_factor, sector}` (Document Contract §8)
- `RUN_STATUS_{RUNNING,VALIDATED,PROMOTED,FAILED}` + `RUN_TYPE_{FULL,DOMAIN}`
- `FORBIDDEN_DOCUMENT_KEYS` — tenant / secret / legal-applicability /
  LLM keys. Any of these on a payload triggers `SearchContractError`.
- `SearchContractError(ValueError)` — typed error surface.

### 3.2 `document.py`

`SearchDocument` dataclass + `normalize_document(dict) -> SearchDocument`.

Normalization guarantees:

- required fields present (object_type, canonical_id, source_id,
  title, search_text, publication_status, source_updated_at)
- `source_key` is `None` OR a non-empty string (never `""`)
- `aliases[]` and `keywords[]` sorted + deduplicated
- `subjects[]` deduplicated then sorted by
  `(subject_type, subject_key)`
- `context[]` deduplicated then sorted by
  `(context_type, context_key)`, and every `context_type` must be
  in `ALLOWED_CONTEXT_TYPES`
- `visibility_scopes[]` restricted to `ALLOWED_VISIBILITY_SCOPES`
- `publication_status` restricted to `ALLOWED_PUBLICATION_STATUSES`
- `source_updated_at` parsed from ISO 8601 string or accepted as
  `datetime`
- forbidden keys (`FORBIDDEN_DOCUMENT_KEYS`) always rejected

Normalization is **idempotent** — a second pass yields the same
canonical shape. This is what makes `content_hash` deterministic.

### 3.3 `hash_utils.py`

`content_hash(SearchDocument) -> str`:

- Serializes the retrieval-scoped fields (Document Contract §5)
  with `json.dumps(..., sort_keys=True, ensure_ascii=False,
  separators=(",", ":"))`
- Excludes `source_document_id`, `source_id`, `source_key`,
  `source_updated_at`, `indexed_at` from the hash
- Returns the SHA-256 hex of the UTF-8 bytes

Also exports `_document_as_dict(doc)` — the wire shape shared by
the Writer and the rebuild staging tables. Same shape flows through
the SQL `document_json` column.

### 3.4 `writer.py`

`MemoryStore` — a Python mirror of the three SQL tables. Adapters
in F2 will pass a `SupabaseStore` with the same interface; F1 tests
use `MemoryStore`.

`Writer(store)`:

- `upsert_current(payload) → SearchDocument` — for **OBJECT REINDEX**.
  Validates + normalizes + hashes; PUBLISHED rows go into the
  current projection, HOLD / REMOVED rows physically drop from
  current (Foundation tombstone option B from Document Contract §11.4).
- `stage(run_id, payload) → SearchDocument` — for **FULL REBUILD**
  staging. Refuses if the run is not RUNNING; refuses forbidden keys
  before the store call.
- `tombstone(object_type, canonical_id) → bool` — explicit removal,
  idempotent.

`WriterRejected` inherits from `SearchContractError`.

### 3.5 `rebuild.py`

`RebuildFramework(store)` implements the four-state lifecycle:

```
begin(expected_domains, run_type='FULL')  →  status RUNNING
      ↓
stage(run, payload) × N                    (may be interleaved across domains)
      ↓
mark_domain_done(run, domain) × |expected_domains|
      ↓
validate(run)                              →  status VALIDATED
      ↓
promote(run)                               →  status PROMOTED  (atomic swap)

any error at validate/promote  →  fail(run, code, message)  →  status FAILED
                                   current projection unchanged.
```

`promote()` in `MemoryStore` mirrors the SQL function's
"replace-in-single-critical-section" behavior: it builds the new
`_current` dict, then swaps it in one assignment; if any exception
raises inside, the pre-swap current is restored and the run is
marked FAILED. The SQL side relies on transaction rollback for the
identical property.

Only PUBLISHED staged rows enter the promoted current — HOLD /
REMOVED staged rows are filtered out (they are still present in
`search_rebuild_documents` for post-run inspection, but never in
`search_documents`).

### 3.6 `reconcile.py`

`reconcile(store, object_type, expected) → ReconcileReport`:

- `expected` is an iterable of `{"canonical_id", "content_hash"}` dicts
  produced by the Domain adapter (F2)
- Compares against `store.iter_current(object_type=...)`
- Reports `match`, `missing`, `extra`, `stale_by_hash`
- `ok = True` iff all three of `missing / extra / stale_by_hash` are
  empty
- **No mutation.** The function does not touch the store.

`ReconcileReport.to_dict()` gives an operational-friendly payload.

## 4. State machine (rebuild)

```
                 ┌──────────────────────────┐
                 │       RUNNING            │
                 └────┬──────┬──────────────┘
                      │      │
     mark_domain_done │      │ fail(...) — adapter-level abort
     stage(...)       │      │
                      ▼      ▼
                 ┌──────────────────────────┐
                 │       VALIDATED          │────────┐
                 └────┬─────────────────────┘        │
                      │                              │
                      │ promote(...)                 │ fail(...)
                      ▼                              ▼
                 ┌──────────────────────────┐   ┌─────────────┐
                 │       PROMOTED           │   │   FAILED    │
                 └──────────────────────────┘   └─────────────┘
                       (terminal)                  (terminal)
```

`validate()` refuses to move to VALIDATED if:

- any expected Domain hasn't reported completion, OR
- zero documents were staged into the run.

`promote()` refuses if the run is not VALIDATED.

## 5. Failure model

Constitution §10 + Document Contract §11 require fail-closed +
fail-safe behavior. F1 implements this as:

| Failure | Effect |
|---|---|
| Domain adapter raises during ingest | Adapter calls `fail(run, code, msg)` → run FAILED, current unchanged |
| Writer rejects a document (invalid enum / missing field / forbidden key) | Raises `WriterRejected`; no store mutation |
| `validate()` finds incomplete domains | Raises `RebuildAborted`; run stays RUNNING (caller may retry or fail) |
| `promote()` raises mid-swap | Current projection restored to pre-swap snapshot; run marked FAILED |
| Reconcile finds drift | READ-only report; **never** repairs |

There is no automatic remediation. Repair paths are always
explicit — a subsequent `upsert_current` or a new FULL REBUILD.

## 6. Tombstoning

Foundation chooses **physical delete from `search_documents`** for
HOLD / REMOVED (Document Contract §11.4 option B). Rationale:

- retrieval contract requires "never discoverable" — the simplest way
  to guarantee that at the Foundation layer is absence from the
  current projection
- the rebuild-side history preserves what the object looked like when
  it was last published (in `search_rebuild_documents`)
- future auditability lives in the rebuild-runs table, not in a
  "soft-deleted" current row

If a later WO needs soft-delete semantics (e.g. for a "recently
removed" panel), the schema still supports it: add a
`retention_status` column and update the retrieval engine to filter.
No Foundation change required.

## 7. Production apply status

```text
Migration file       = supabase/migrations/20260919_shared_search_foundation.sql
Production apply     = NOT APPLIED
Owner-approval gate  = SEPARATE, pending Foundation delta verify
Schema drift risk    = 0 today (no existing search_documents table
                       in production; migration is additive)
```

The Foundation code path is exercised end-to-end against
`MemoryStore` in the test suite. Applying the migration to
production is a separate Owner action — the SEARCH-01 pattern
(deploy on Owner GO, then a production smoke acceptance WO)
applies.

## 8. F2 handoff — what a Domain adapter must provide

Under F2 each Domain adapter (GUIDE, SAFETY_MATERIAL, CSI_ACCIDENT,
CHEM, LEGAL, KNOWLEDGE, PRECEDENT) implements two Foundation-facing
entry points:

```python
def enumerate_published(cursor) -> Iterable[dict]: ...
def to_search_document(row) -> dict: ...
```

`enumerate_published` yields Domain rows that pass the Domain's own
publication gate (Document Contract §6). `to_search_document`
returns a dict that `normalize_document` accepts — Domain
adapters do not construct `SearchDocument` objects directly; they
prepare dicts and let the Writer validate.

RISK adapter waits until RISK-C02 opens the ACTIVE gate. Until then
`enumerate_published` yields the empty iterable — writer never sees
a RISK document. F1 tests §50 prove that even if a RISK-DRAFT
payload reaches the writer (via a bug), the current projection
stays clean.

## 9. Test surface

`tests/test_shared_search_foundation.py` — 52 tests covering:

- Identity (§44): 4 tests
- Contract validation (§45): 6 tests
- Hash determinism (§46): 5 tests
- Full rebuild (§47): 5 tests
- Object reindex (§48): 6 tests
- Reconcile (§49): 5 tests
- RISK DRAFT negative (§50): 2 tests
- Legal applicability leakage (§51): 5 parametrized tests
- Tenant secret exclusion (§52): 9 parametrized tests
- No-LLM audit (§53): 2 tests
- End-to-end integration chain (§54): 1 test

All 52 pass locally against `MemoryStore` with zero DB / zero
network / zero LLM.

## 10. Boundary — what F1 does NOT do

- No Domain adapter implementation (F2)
- No FTS / pg_trgm / ranking indexes (F3)
- No retrieval HTTP endpoint (F3)
- No consumer wiring (F4)
- No production deploy
- No RISK ACTIVE change
- No CHEM hydration / materialize / publish
- No graph apply
- No env change
- No secret storage

The tests explicitly assert most of these (forbidden-keys, no-LLM
audit) at the code layer.
