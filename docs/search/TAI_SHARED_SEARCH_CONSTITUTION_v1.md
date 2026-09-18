# TAI Shared Search Constitution v1

**WO**: WO-TAI-SHARED-SEARCH-002 — Unified Search Contract Freeze
**Date**: 2026-09-19
**Status**: docs-only freeze. Zero code / DB / schema / index / deploy.
**Authority**: subordinate to `PLAN_safety-knowledge-hub-master_v0.1.md`
and `PLAN_safety-knowledge-object-implementation_v1.md`; carries
`docs/TAI_SHARED_SEARCH_MASTER_PLAN_v2.md` into an implementable
contract.

This document freezes the **constitutional invariants** of the TAI
Shared Search platform. Two sibling documents freeze the concrete
contracts:

- `TAI_SHARED_SEARCH_DOCUMENT_CONTRACT_v1.md` — SearchDocument fields
  + Domain Identity Matrix
- `TAI_SHARED_SEARCH_RESULT_CONTRACT_v1.md` — SearchResult fields +
  ranking / dedup / explanation

Nothing in this document opens SEARCH-03. Any DB migration, schema
create, materialized view, writer implementation, rebuild
implementation, or deployment is explicitly out of scope.

---

## Article 1 — One engine, one contract, many consumers

```text
검색엔진               = 하나
Search Projection      = 하나의 공통 contract
Domain SoT             = 각자 유지
Consumer               = 여럿  (Public / Paid / SaaS / LEG enrichment)
```

The Shared Search Engine is a **discovery layer**. Domain SoT tables
(`kosha_msds_*`, `kosha_guide`, `kosha_safety_materials`,
`csi_accident_cases`, `risk_canonical_nodes`, `safe_help_content`,
`industrial_accident_precedents`, LEG stack) remain the authoritative
stores. Each of them keeps its own identifier, publication mechanism,
and lifecycle.

## Article 2 — Boundaries (what Search is NOT)

Search is a **projection over canonical objects**. It does not
substitute for any of the following:

```text
SEARCH TERM        ≠  CANONICAL ID
SEARCH INDEX       ≠  SOURCE OF TRUTH
SEARCH RESULT      ≠  LEGAL APPLICABILITY
SEARCH RESULT      ≠  RISK CANONICAL DECISION
SEARCH RESULT      ≠  CHEM MSDS OFFICIAL PUBLICATION
SEARCH RESULT      ≠  KNOWLEDGE GRAPH CANONICAL EDGE
```

Consumers that need any of those answers MUST resolve back to the
authoritative Domain path (Legal Engine, RISK canonical review,
CHEM publish gate, Knowledge Graph read model). Search returns
`(canonical_id, object_type, match evidence)`; the consumer decides
whether to authorize applicability, publication, or activation.

## Article 3 — Detail resolution boundary

```text
Search Result
  → canonical_id + object_type
  → Domain SoT
  → detail_resolver
```

Search never dumps full Domain payloads. If a consumer needs the
full Domain object, it calls the Domain's read endpoint / read model
using the `canonical_id + object_type` pair returned by Search. This
keeps Domain-specific privacy, rights, and rate-limit contracts
local to each Domain.

## Article 4 — Publication authority

Search **never** promotes a Domain object's publication state.

- CHEM: `publish_state` transitions (`NOT_PUBLISHED` →
  `PUBLISHED_SEO_PREVIEW` → `PUBLISHED_FULL`) stay under CHEM-10 /
  cutover gates. Search adapters only READ what is already published.
- RISK: `risk_canonical_nodes.status` transitions
  (`DRAFT` → `ACTIVE`) stay under RISK-C0*. Search adapters only
  ingest ACTIVE rows.
- GUIDE / MATERIAL / CSI / KNOWLEDGE / PRECEDENT: each has its own
  publication or READY gate (see Document Contract §4). Search
  respects it, never bypasses it.
- LEG obligations: never gated by Search. Legal Engine is the sole
  authority for applicability.

## Article 5 — Query understanding remains the current stack

The existing query-understanding stack is REUSED verbatim; no new
Kiwi, no new dictionary engine, no new normalizer:

```text
T1  EXACT             tools/search_dict/search_core.py
T2  NORMALIZED_EXACT  tools/search_dict/search_core.py
T2b PUNCTUATION       tools/search_dict/search_core.py
T3  ALIAS / SYNONYM   tools/search_dict/search_core.py + seed_v2
T4  KIWI TOKEN        tools/search_dict/search_runtime_ext.py
T6  TRIGRAM           tools/search_dict/search_runtime_ext.py
```

Runtime binding is the artifact chain frozen in
`TAI_SEARCH_RUNTIME_ARTIFACT_MANIFEST_v1.md`. SEARCH-01 confirmed
production /search-dict health under `SEARCH-DICT-LEGPROD-2026-09-16`.

## Article 6 — Identifier gate

Identifier-shaped queries **must not** enter fuzzy paths:

```text
chemId | CAS | KE | EN | UN | canonical_id | law_identifier
   → T1 EXACT only
   → NO Kiwi
   → NO Trigram
   → NO alias expansion
```

The Retrieval Engine (SEARCH-05) will implement the identifier
recognizer. Consumers that already know an identifier should skip
Search entirely and call the Domain resolver directly.

## Article 7 — External discovery provider distinction

KOSHA Smart Search (via `routers/public_safety_search.py`) is a
**discovery provider**, not a Domain content source:

```text
CONTENT SOURCE         = NO
DISCOVERY PROVIDER     = YES
INDEXABLE IN tai_search_documents = NO
```

The Public consumer merges internal Shared-Search results with
external KOSHA Smart Search results at the **presentation** layer.
External results carry a distinguishing flag and never mutate
`canonical_id / object_type` semantics. See Result Contract §7.

## Article 8 — No LLM in identity, publication, canonical merge, or ranking

```text
LLM = 0
```

for:

- object identity resolution
- publication eligibility
- canonical merge / dedup
- ranking (initial score computation)

LLM-based reranking, summarization, or expansion is deliberately
deferred to a future WO after the deterministic engine ships and
its precision is measured. Master Plan v2 §14 pins this rule.

## Article 9 — Consumer scopes

```text
PUBLIC       — anonymous public discovery. Only PUBLIC-eligible objects.
SAAS         — authenticated tenant context. Company / factory /
               process / task / equipment / obligation / inspection /
               chemical context queries are permitted. Tenant secrets
               NEVER stored in the Search Document.
PAID         — paid diagnosis + report supporting context. Reads
               SAAS-visible objects; augmented with paid-only object
               types when they land.
INTERNAL     — reserved for admin / support / ops surfaces. Never
               served to unauthenticated callers.
```

The Search Document declares which scopes an object is visible to
via `visibility_scopes`; the Retrieval Engine (SEARCH-05) enforces
scope at query time.

## Article 10 — Failure philosophy (fail-closed + fail-safe)

```text
Domain adapter failure    → keep existing good projection; do NOT
                            partially replace.
FULL rebuild partial fail → do NOT promote new snapshot to current.
Unknown object_type       → reject at writer.
Missing canonical identity → reject at writer.
Publication eligibility unknown → HOLD (do not index).
External provider failure → internal Search keeps serving normally.
```

No Domain state is mutated to "help" an indexing decision. The
writer's only surface is the Shared Search Projection.

## Article 11 — Domain autonomy is preserved

Each Domain retains its own:

- source-specific query paths (e.g., CHEM identifier-exact,
  `/help/search` help-center Kiwi, `/factory-process/kcsc/search`
  operational lookup, `/ksic-engine/search` industry-code lookup,
  admin `/search` cross-search)
- specialized semantics (Legal Engine deterministic rules, CHEM
  identifier logic, RISK canonical hierarchy)
- publication cadence and gates

Migrating a **consumer** onto the Shared Search Engine does not
remove Domain logic. It replaces the consumer's own bespoke search
implementation with a shared discovery layer while the Domain's
authoritative endpoints stay intact. See Document Contract §12 for
the Duplicate Matrix classification.

## Article 12 — Reindex modes

```text
FULL REBUILD               deterministic, idempotent, countable,
                           reconcilable
OBJECT REINDEX             Domain publish/change event → single
                           object reindex
NIGHTLY RECONCILIATION     Domain SoT ↔ Search projection: count,
                           content_hash, missing, extra
```

No CDC. No streaming pipeline. SEARCH-03 will implement these three
modes over Postgres — Elasticsearch/OpenSearch is deliberately out
of scope until Postgres limits are measured (Master Plan v2 §4).

## Article 13 — Deterministic content hash

```text
content_hash(object)
  = hash( normalized canonical fields that affect retrieval )
```

`content_hash` covers ONLY the fields that materially change
retrieval or presentation of the Search Document: title, summary,
searchable text, aliases, keywords, subjects, context, publication
status. Domain-side transient metadata (write timestamps, admin
comments, internal state) is EXCLUDED. Same normalized input ⇒ same
hash — this is the invariant Nightly Reconciliation relies on.

## Article 14 — Tombstoning contract

Objects that are:

```text
unpublished | deleted | superseded | inactive
```

MUST become non-discoverable within one reindex cycle. Whether the
Search Document row is physically deleted, marked `removed`, or
excluded from the current view is a SEARCH-03 implementation choice.
The Constitution only requires:

```text
Domain SoT tombstone
  → next reindex cycle
    → Search result never surfaces the object
```

## Article 15 — Governance of contract changes

Any addition to `object_type`, `match_type`, `visibility_scopes`,
`publication_status`, or the ranking-precedence list is an
**Owner-approved contract change**, not an implementation detail.
The Consumer track and Domain-Indexer track (SEARCH-04+) MUST NOT
introduce new enum values without a follow-up WO that updates the
Contract documents in this repo and cites the Owner approval.

## Article 16 — Scope of this Constitution

This document defines what the platform **is** and **is not**. It
does not:

- name a table
- define a column type
- pick an index method (GIN / BTREE / etc.)
- pick a runtime endpoint URL
- specify a rebuild trigger mechanism

Those decisions belong to SEARCH-03 (schema) and SEARCH-05 (engine).

---

## Appendix A — Constitutional invariants (quick reference)

| # | Invariant | Enforced by |
|---|-----------|-------------|
| A1 | one engine, one Projection contract | Document Contract |
| A2 | Search ≠ SoT / applicability / activation | Boundary in Article 2 |
| A3 | canonical_id + object_type resolves to Domain SoT | Result Contract §2 |
| A4 | Search never promotes publication | Adapter contract, Document §4 |
| A5 | Query understanding reuses current stack | Runtime Manifest v1 |
| A6 | Identifier queries bypass fuzzy paths | Engine gate (SEARCH-05) |
| A7 | External provider distinct at presentation | Result Contract §7 |
| A8 | No LLM in identity / publication / ranking | Constitution Article 8 |
| A9 | Consumer scopes gate visibility | Retrieval Engine (SEARCH-05) |
| A10 | Fail-closed, fail-safe, no partial promotion | Reindex contract Document §11 |
| A11 | Domain autonomy preserved | Duplicate Matrix Document §12 |
| A12 | Three reindex modes only | Document §11 |
| A13 | content_hash is deterministic and retrieval-scoped | Document §5 |
| A14 | Tombstone within one reindex cycle | Document §11 |
| A15 | Enum expansion requires Owner-approved WO | This document Article 15 |
| A16 | SEARCH-03 boundary | This document Article 16 |
