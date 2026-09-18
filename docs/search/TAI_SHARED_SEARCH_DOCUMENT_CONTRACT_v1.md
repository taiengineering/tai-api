# TAI Shared Search — Document Contract v1

**WO**: WO-TAI-SHARED-SEARCH-002
**Status**: docs-only. Zero code / DB / schema / index / deploy.
**Sibling docs**:
- `TAI_SHARED_SEARCH_CONSTITUTION_v1.md`
- `TAI_SHARED_SEARCH_RESULT_CONTRACT_v1.md`

This document freezes:

1. The semantic contract of a **SearchDocument** row (§3, §5)
2. The **Domain Identity Matrix** — what canonical identity each Domain contributes (§4)
3. The **publication eligibility** and **visibility scope** contracts (§6, §7)
4. The **context** vocabulary (§8)
5. The **reindex + tombstone** contract (§11)
6. The **conflict audit** result (§13)

Nothing in this document creates a schema. SEARCH-03 will translate
this contract into DDL.

---

## 1. Cardinality

```text
1 canonical searchable object  →  1 current SearchDocument
```

**Default:** every Domain object indexes as exactly one SearchDocument.

**Exceptions requiring a documented reason** (candidates only —
resolved during SEARCH-04 Domain-adapter WOs):

- CHEM MSDS: `kosha_msds_chemicals` (whole compound) is the natural
  Search object. The 16 `kosha_msds_sections` per chemical are NOT
  separate SearchDocuments — they augment the parent's `search_text`
  and `subjects`. Section-level retrieval, if ever needed, opens as
  a separate Owner-approved WO.
- GUIDE: 1 `kosha_guide` row = 1 SearchDocument. PDF originals are
  NOT chunked (rights + LINK_ONLY policy on `kosha_guide.original_rights_mode`).
- CSI: 1 `csi_accident_cases` row = 1 SearchDocument. Only READY
  rows are indexable.

No arbitrary chunking. If a Domain needs multi-row projections, its
SEARCH-04 adapter WO must justify it with source evidence.

## 2. Identity separation

Three IDs, none substitutable for another:

| Field | Owner | Purpose | Example |
|-------|-------|---------|---------|
| `search_document_id` | Search Projection | row identity in the Projection | opaque UUID (SEARCH-03) |
| `canonical_id` | Domain SoT | Domain object identity | `kosha_msds_chemicals.id`, `kosha_guide.id`, `risk_canonical_nodes.id`, `csi_accident_cases.id`, `industrial_accident_precedents.id`, `safe_help_content.doc_id` |
| `source_id + source_key` | Provenance | how the Domain sourced this record | `KOSHA_MSDS + <chemId>`, `KOSHA_OFFICIAL_GUIDE + <guide_id>`, etc. |

**Rules:**

- `canonical_id` MUST equal the Domain's authoritative primary key
  (or its logical stable identifier when the primary key is
  internal-only). The Domain is the sole authority.
- `search_document_id` MUST NOT be used by consumers to fetch Domain
  detail. Consumers always use `(object_type, canonical_id)`.
- `source_id + source_key` are provenance-only. They are stable
  across canonical merges (multiple sources can map to the same
  canonical object; see RISK §4.5).

## 3. SearchDocument field contract

Field-by-field semantic contract. Column types are SEARCH-03's
decision.

| Field | Req? | Meaning | Source | Normalization | Visibility | Identity role | Update trigger |
|-------|------|---------|--------|---------------|------------|---------------|----------------|
| `search_document_id` | R | Projection row id | Projection (writer-assigned) | opaque | never emitted to public consumers | Projection primary key | first-index only |
| `object_type` | R | Domain enum | Adapter (see §4) | UPPER_SNAKE_CASE from the fixed set | all consumer scopes | Domain classifier | reject on unknown |
| `canonical_id` | R | Domain canonical id | Adapter reads Domain SoT | Domain-shape (UUID / text) | all scopes | detail-resolution key | on canonical change: reject + require WO |
| `source_id` | R | provenance system id | Adapter | Domain-native (verbatim from Domain, e.g. `CSI`, `law_go_kr`, `KOSHA_MSDS`) | INTERNAL only | provenance | on canonical merge only |
| `source_key` | **O (nullable)** | provenance record key | Adapter | Domain-native shape | INTERNAL only | provenance | may be NULL when the Domain has no source-native identifier (e.g. CSI); NEVER a placeholder / synthetic value |
| `title` | R | canonical display title | Domain field | strip + trim; keep original case | scope-gated | display | on Domain title change |
| `summary` | O | preview blurb (≤ 300 chars) | Domain field or first-N of body | strip HTML | scope-gated | display | with title |
| `search_text` | R | searchable text projection | Adapter-composed | normalize_basic + compact | INTERNAL to engine only | retrieval | on title/summary/body change |
| `aliases[]` | O | approved alternate surfaces | Adapter reads Domain-approved list | shared dict normalize | INTERNAL | retrieval | Adapter re-fetches |
| `keywords[]` | O | Domain-native keywords | Adapter reads Domain metadata | strip + trim | INTERNAL | retrieval | on Domain metadata change |
| `subjects[]` | O | shared-dictionary subject axes as `(subject_type, subject_key)` pairs | Adapter maps via search-dict subjects | pair-level; shared-dict values only; sorted + deduplicated | INTERNAL | retrieval boost | when subjects join/leave. Parallel `subject_types[]` / `subject_keys[]` arrays are NOT the canonical contract; the writer emits paired tuples. Physical storage (JSONB, side-table, etc.) is F1 schema's choice. |
| `context[]` | O | typed context relations (§8) | Adapter derives from Domain + Graph read model | fixed vocabulary | scope-gated on query | filtering / boost | on Graph refresh |
| `public_url` | O | canonical Public URL if any | Domain routing | absolute URL | PUBLIC + SAAS + PAID | display | on URL contract change |
| `saas_url` | O | canonical SaaS URL if any | Domain routing | relative or absolute | SAAS + PAID | display | on URL contract change |
| `publication_status` | R | shared enum (§6) | Adapter maps from Domain state | fixed vocabulary | writer gate | index eligibility | on Domain publication change |
| `visibility_scopes[]` | R | which consumer scopes may see | Adapter (§7) | fixed vocabulary | scope enforcement | visibility | on scope policy change |
| `source_updated_at` | R | Domain-side canonical timestamp | Domain field | ISO 8601 | INTERNAL | freshness | on Domain touch |
| `content_hash` | R | deterministic retrieval-scoped hash (§5) | writer computes | sha256 hex | INTERNAL | reconciliation | on any indexed field change |
| `indexed_at` | R | when the writer produced this row | writer clock | ISO 8601 | INTERNAL | pipeline age | every reindex |

## 4. Domain Identity Matrix

Real repo evidence from `main` = `5d1fad8b`. Each row is a
SearchDocument-eligible Domain and how it maps to the contract in §3.

### 4.1 GUIDE — KOSHA safety guide catalog

```text
object_type          = GUIDE
Domain SoT           = public.kosha_guide  (id text)
Snapshot tables      = public.kosha_guide_snapshots
                       public.kosha_guide_snapshot_items
canonical_id         = kosha_guide.id
source_id            = KOSHA_OFFICIAL_GUIDE
source_key           = kosha_guide.id (text; KOSHA-issued)
publication gate     = active row present in kosha_guide + snapshot's
                       status=COMPLETED (evidence: kosha_guide_snapshots)
current read model   = latest COMPLETED snapshot join
detail resolver      = existing GUIDE read endpoint (tai-www
                       koshaGuides.js server helper)
public eligible      = YES (existing public /safety-search tab)
saas eligible        = YES (context: process / task / equipment /
                       obligation panels — SEARCH-C0*)
paid eligible        = YES (paid diagnosis related-knowledge)
publication_status   = PUBLISHED  when active + snapshot COMPLETED
                     = HOLD       otherwise
```

### 4.2 SAFETY_MATERIAL — KOSHA safety material catalog

Verified from `services/kosha_safety_material_sync.py::catalog_row_from_official`.

```text
object_type          = SAFETY_MATERIAL
Domain SoT           = public.kosha_safety_materials  (catalog)
Snapshot tables      = kosha_safety_material_snapshots
                       kosha_safety_material_snapshot_items
Details table        = kosha_safety_material_details
Assets table         = kosha_safety_material_assets
                       kosha_safety_material_asset_versions
canonical_id         = kosha_safety_materials.id
                       (computed via catalog_identity(url, title, raw);
                        stable identity of the material)
source_id            = KOSHA_OFFICIAL_MATERIAL
source_key           = kosha_safety_materials.source_med_seq
                       (KOSHA-issued media sequence, when present).
                       source_key MAY be NULL for rows whose source-
                       native identifier was not captured. `material_id`
                       is a DETAILS-side field (see _resolve_material_id
                       in the sync module) — it is NOT the catalog
                       primary key and must not be used as source_key.
publication gate     = catalog row + latest COMPLETED snapshot +
                       storage policy not in HOLD state (see
                       kosha_safety_material_storage_holds* migrations)
current read model   = latest COMPLETED snapshot with storage holds excluded
detail resolver      = MATERIAL read (tai-www server helper)
public eligible      = YES
saas eligible        = YES
paid eligible        = YES
publication_status   = PUBLISHED  when catalog row + COMPLETED snapshot
                                  membership present + no storage hold
                     = HOLD       when a storage hold exists (review /
                                  unavailable / oversize) OR no COMPLETED
                                  membership yet
                     = REMOVED    when the material is dropped from the
                                  latest COMPLETED snapshot
                       (UNAVAILABLE is NOT a shared enum value — the
                        adapter collapses it into HOLD per §6.)
```

### 4.3 CSI (ACCIDENT) — construction accident cases

Verified from `supabase/migrations/20260913_csi_accident_catalog.sql`:

```text
object_type          = CSI_ACCIDENT
Domain SoT           = public.csi_accident_cases (content_id PK, text)
Snapshot tables      = csi_accident_snapshots
                       csi_accident_snapshot_items
canonical_id         = csi_accident_cases.content_id     # 'CSI:<uuid>' text
source_id            = "CSI"                              # NOT "KOSHA_CSI"
source_key           = NULL                               # column is TEXT NULL;
                                                          # per catalog COMMENT:
                                                          # "Official source-native
                                                          #  ID. CSI file has none;
                                                          #  remains NULL."
publication gate     = latest COMPLETED snapshot +
                       snapshot_items.identity_status == READY
                       (per catalog COMMENT: identity_status on the
                        cases row is a "catalog convenience only.
                        Matching/public/Graph status truth is
                        COMPLETED snapshot_items.identity_status.")
current read model   = READY-only public read
detail resolver      = /public/accidents/csi/{uuid_part}
                       (routers/public_csi_accidents.py; uuid_part is
                        the portion of content_id after the "CSI:" prefix)
public eligible      = YES (READY only)
saas eligible        = YES
paid eligible        = YES
publication_status   = PUBLISHED  when latest COMPLETED snapshot_items row
                                  is identity_status=READY for this content_id
                     = HOLD       when identity_status=HOLD or no COMPLETED
                                  membership present
                     = REMOVED    when the case is no longer in any COMPLETED
                                  snapshot
```

### 4.4 CHEM — MSDS chemicals

```text
object_type          = CHEM
Domain SoT           = public.kosha_msds_chemicals
Section table        = public.kosha_msds_sections     (16 per chemical)
Snapshot tables      = public.kosha_msds_snapshots
                       public.kosha_msds_snapshot_items
canonical_id         = kosha_msds_chemicals.id (uuid)
content_id           = kosha_msds_chemicals.content_id
source_id            = KOSHA_MSDS
source_key           = kosha_msds_chemicals.source_key   (== chem_id)
publication gate     = **Domain-owned**. Search NEVER invokes
                       `services/kosha_msds/cutover.is_full_ready` at
                       index time. The adapter READS one of the
                       already-published current read models below
                       and admits whatever the Domain has already
                       promoted. Search never promotes CHEM state.
Published read models = kosha_msds_seo_preview_current      (SEO preview)
                        kosha_msds_full_current             (FULL)
                       These views are the Domain's authoritative
                       "what is currently published" surface. Adapter
                       joins the parent chemical + its 16 sections
                       through these views only.
Publication scope    = SEO_PREVIEW vs FULL is a Domain-internal enum;
                       it maps to the shared `publication_status`
                       (PUBLISHED / HOLD / REMOVED) at the adapter
                       boundary and does NOT surface as a shared
                       SearchDocument field. The consumer scope
                       (PUBLIC vs SAAS vs PAID) is set by
                       `visibility_scopes[]`, which is separate from
                       Domain scope.
Public runtime gate  = KOSHA_MSDS_PUBLIC_MODE ∈ {seo_preview, full}
                       is a RUNTIME EXPOSURE POLICY, distinct from
                       publication eligibility. If public mode is
                       `off`, PUBLIC visibility MUST be withheld even
                       if the Domain has PUBLISHED_SEO_PREVIEW /
                       PUBLISHED_FULL rows. The Retrieval Engine
                       (F3 / SEARCH-05) enforces this; F1 schema
                       must be able to represent it (via a scope
                       filter overlay or an eligibility check that
                       reads the env at query time).
detail resolver      = CHEM-06 read service (`/public/kosha/msds`
                       when KOSHA_MSDS_PUBLIC_MODE is set)
public eligible      = YES only when (Domain has PUBLISHED_SEO_PREVIEW
                       or PUBLISHED_FULL) AND public runtime gate is on
saas eligible        = YES (context: chemical / process linkage)
paid eligible        = YES (paid diagnosis chemical-related section)
publication_status   = PUBLISHED  when the row is present in one of the
                                  published current read models above
                     = HOLD       when only NOT_PUBLISHED / RUNNING / FAILED
                                  snapshots reference it
                     = REMOVED    when the row drops from all published
                                  current read models
Cardinality note     = 16 sections per chemical fold into the parent
                       SearchDocument's search_text and subjects[];
                       sections are NOT separate SearchDocument rows
                       (§1 exception rationale). Whether a chemical
                       carries `CHEM_TERM / 물질안전보건자료` as one of
                       its subjects is DEFERRED_TO_F2_CHEM_ADAPTER
                       (CHEM_TERM is a query-terminology axis, not an
                       automatic per-chemical property).
Section granularity  = held for a separate future WO.
```

### 4.5 RISK — canonical risk factor / node

```text
object_type          = RISK
Domain SoT           = public.risk_canonical_nodes
Sector links         = public.risk_canonical_node_sectors
Source mappings      = public.risk_source_mappings
                       (source_id, source_key, canonical_id,
                        mapping_status)
canonical_id         = risk_canonical_nodes.id (uuid)
canonical_code       = risk_canonical_nodes.canonical_code (stable)
status               = DRAFT | ACTIVE   (currently: 1,110 DRAFT / 0 ACTIVE)
sector links         = 0 today (risk_canonical_node_sectors is empty)
publication gate     = status == ACTIVE  (required; strict)
current read model   = none yet (RISK-C04 target)
detail resolver      = to be defined by RISK-C0* WO track
public eligible      = NO   (today, no ACTIVE canonical exists)
saas eligible        = NO   (blocked on RISK-C02 ACTIVE gate)
paid eligible        = NO
publication_status   = HOLD (uniformly today; PUBLISHED once ACTIVE)
INDEXABLE?           = NO — see §7.2. Adapter MUST reject DRAFT rows.
Multi-source note    = risk_source_mappings binds multiple
                       (source_id, source_key) tuples to one
                       canonical_id. SearchDocument carries ONE
                       primary provenance pair (source_id,
                       source_key). Additional mappings do NOT
                       enter `aliases[]` — aliases is a searchable-
                       expression channel, not a provenance ledger.
                       The full provenance authority remains in
                       risk_source_mappings; consumers who need
                       the full mapping call RISK SoT directly.
```

### 4.6 LEGAL — law norms / obligations

```text
object_type          = LEGAL
Domain SoT           = LEG stack (kept out of tai-api's canonical
                       write path; consumed via legal_engine_svc)
Related tables       = law_revision_board (tai-www), LEG published
                       obligation norms, TAI legal engine
                       deterministic rules
canonical_id         = an opaque stable Domain identifier chosen by
                       the LEGAL adapter. Whether that is an
                       obligation atom id, a law article identifier,
                       or a norm-cluster id depends on which LEGAL
                       record kind is being indexed:
                       DEFERRED_TO_F2_LEGAL_ADAPTER.
source_id            = adapter selects one of {LEG_OFFICIAL,
                       LAW_REVISION_BOARD, …} per record kind
source_key           = LEG identifier / revision id when present;
                       NULL for records that lack a source-native key
publication gate     = LEG published state + APPROVED
current read model   = existing LEG read paths
detail resolver      = LEG read endpoints
public eligible      = YES (law-updates on Public / safety-search)
saas eligible        = YES (obligation-context — see SEARCH-07 gate)
paid eligible        = YES (paid diagnosis obligation summaries)
publication_status   = PUBLISHED / HOLD / REMOVED
CRITICAL             = LEGAL SearchResult **must never** be treated as
                       an applicability decision. Consumers that need
                       applicability call the Legal Engine. This is a
                       constitutional invariant, not an adapter policy.
```

### 4.7 KNOWLEDGE_CENTER — help articles

```text
object_type          = KNOWLEDGE
Domain SoT           = public.safe_help_content
                       (doc_id, slug, menu_group, status)
canonical_id         = safe_help_content.doc_id
source_id            = TAI_HELP_CENTER
source_key           = safe_help_content.doc_id
publication gate     = status == PUBLISHED
current read model   = /help/search + /help/doc/{slug}
                       (routers/safe_help.py, services/safe_help_svc.py)
detail resolver      = /help/doc/{slug}
public eligible      = YES (Public /safety-search 지식센터 tab today
                       routes to help center)
saas eligible        = YES
paid eligible        = YES
publication_status   = PUBLISHED / HOLD / REMOVED
                       (adapter maps safe_help_content.status)
notes                = today, /help/search runs its own Kiwi index
                       on safe_help_content. SEARCH-04 KNOWLEDGE
                       adapter is the earliest opportunity to bring
                       this content into the Shared Projection; the
                       existing /help/search endpoint stays operational.
```

### 4.8 PRECEDENT — industrial accident precedents

Verified from `scripts/collect_precedents.py` (ingest shape) and
`routers/precedent_api.py` (query surface). The newer IAP table
`industrial_accident_precedents` supersedes the legacy `posts`
view for precedents.

```text
object_type          = PRECEDENT
Domain SoT           = public.industrial_accident_precedents  (newer,
                       primary SearchDocument source)
Legacy note          = public.posts still carries pre-migration rows;
                       adapter prefers the IAP table and falls back
                       to posts only when a row is not in IAP.
canonical_id         = industrial_accident_precedents.id  (uuid)
source_id            = law_go_kr                            # ingest
                                                            # payload's
                                                            # "source" column
source_key           = industrial_accident_precedents.prec_seq
                       (law.go.kr 판례일련번호; may be NULL for
                        legacy / manual rows)
publication gate     = is_active = true
public columns       = case_number, case_name, court_name,
                       decision_date, sector, hazard_type, summary,
                       source_url
detail resolver      = DEFERRED_TO_DOMAIN_ADAPTER
                       (routers/precedent_api.py currently exposes
                        /precedents/iap/search — the IAP listing — but
                        the per-row detail resolver for new IAP rows
                        is not finalized. Do NOT reuse the legacy
                        /precedents/{id} posts resolver.)
public eligible      = YES (when is_active = true)
saas eligible        = YES
paid eligible        = YES
publication_status   = PUBLISHED  when is_active = true
                     = HOLD       when is_active = false
                     = REMOVED    when the row is deleted
```

## 5. content_hash contract

```text
content_hash(doc) = sha256(canonical_bytes(doc))

canonical_bytes = deterministic serialization of the following
fields ONLY (retrieval-scoped, per Constitution §13):

    object_type
    canonical_id
    title
    summary
    search_text
    aliases  (sorted, deduplicated)
    keywords (sorted, deduplicated)
    subjects (sorted by (subject_type, subject_key), deduplicated)
    context  (sorted by (context_type, context_key), deduplicated)
    publication_status
    visibility_scopes (sorted)
    public_url
    saas_url

Excluded (transient / provenance / pipeline metadata):
    search_document_id
    source_id, source_key
    source_updated_at
    indexed_at
```

Same normalized input ⇒ same hash. Nightly Reconciliation compares
Domain-side recomputed hash vs Projection-stored hash.

## 6. Publication eligibility contract

The shared `publication_status` enum is EXACTLY **three** values:

```text
PUBLISHED   HOLD   REMOVED
```

Domain-specific values such as `DRAFT`, `REVIEW`, `RUNNING`,
`FAILED`, `UNAVAILABLE`, `PROPOSED`, or `NOT_PUBLISHED` MUST NOT
be surfaced on the SearchDocument. The adapter is the sole boundary
that translates Domain state into one of the three shared values.

| SearchDocument state | Semantic | Result eligibility |
|---|---|---|
| `PUBLISHED` | Domain object is authoritatively published under its own gate | eligible for all `visibility_scopes` it declares |
| `HOLD` | Domain says "not yet" (draft / review / running / failed / storage hold / abnormality / any pre-publication state) | NOT indexed as PUBLISHED; if previously PUBLISHED, tombstone on next reindex |
| `REMOVED` | Domain says "no longer valid" (deleted / unpublished / superseded / dropped from the latest COMPLETED snapshot) | tombstoned; must not surface in any scope |

Domain-adapter mapping table (from §4):

| Domain | PUBLISHED | HOLD | REMOVED |
|---|---|---|---|
| GUIDE | catalog row present + latest snapshot COMPLETED | any pre-COMPLETED state | dropped from catalog |
| SAFETY_MATERIAL | catalog row + latest snapshot COMPLETED + no storage hold | any storage hold (review / unavailable / oversize) OR no COMPLETED membership | dropped from the latest COMPLETED snapshot |
| CSI_ACCIDENT | latest COMPLETED `csi_accident_snapshot_items.identity_status = READY` for this content_id | identity_status HOLD OR no COMPLETED membership | dropped from all COMPLETED snapshots |
| CHEM | present in `kosha_msds_seo_preview_current` OR `kosha_msds_full_current` | only NOT_PUBLISHED / RUNNING / FAILED snapshots reference it | dropped from all published current read models |
| RISK | `risk_canonical_nodes.status = ACTIVE` | `DRAFT` (all rows today) | future-only |
| LEGAL | LEG PUBLISHED + APPROVED | LEG DRAFT / REVIEW / any pre-publish state | LEG SUPERSEDED / removed |
| KNOWLEDGE | `safe_help_content.status = PUBLISHED` | DRAFT / REVIEW / any pre-publish | ARCHIVED / deleted |
| PRECEDENT | `industrial_accident_precedents.is_active = true` | `is_active = false` | row deleted |

## 7. Visibility scope contract

`visibility_scopes` is a set from the fixed vocabulary
`{PUBLIC, SAAS, PAID, INTERNAL}` (Constitution §9). Adapters set it
based on Domain-side eligibility:

### 7.1 Default eligibility per Domain

| Domain | Default `visibility_scopes` |
|---|---|
| GUIDE | `{PUBLIC, SAAS, PAID}` |
| SAFETY_MATERIAL | `{PUBLIC, SAAS, PAID}` when not on storage hold |
| CSI_ACCIDENT | `{PUBLIC, SAAS, PAID}` when READY |
| CHEM | `{PUBLIC, SAAS, PAID}` when KOSHA_MSDS_PUBLIC_MODE ∈ {seo_preview, full} AND CHEM publish gate PASS |
| RISK | `{}` today (0 ACTIVE); `{SAAS, PAID}` once ACTIVE + sector-linked; PUBLIC only when RISK-C05 opens it |
| LEGAL | `{PUBLIC, SAAS, PAID}` for public law texts; `{SAAS, PAID}` for internally-annotated projections |
| KNOWLEDGE | `{PUBLIC, SAAS, PAID}` when PUBLISHED |
| PRECEDENT | `{PUBLIC, SAAS, PAID}` when live |

INTERNAL is reserved for admin / ops / support surfaces and is set
by the adapter only when explicitly required. No default Domain
grants INTERNAL.

### 7.2 RISK DRAFT special case (indexable = NO)

```text
For any row where risk_canonical_nodes.status != ACTIVE:
    publication_status  = HOLD
    visibility_scopes   = {}
    → writer MUST reject (do not create a SearchDocument)
```

Current production: 1,110 DRAFT / 0 ACTIVE / 0 sector links →
**zero** RISK SearchDocuments exist. RISK-C02 opens the ACTIVE gate.

### 7.3 Tenant / secret containment

SearchDocument **must not** contain:

- tenant-specific factory names / addresses
- user PII
- runtime diagnosis answers
- API secrets or tokens

Tenant context is a QUERY-side signal (`context[]` filter injected by
the SaaS layer per authenticated tenant), NOT a stored field.

## 8. Context vocabulary

`context[]` is an array of `(context_type, context_key)` tuples.

```text
context_type ∈ {
    process, task, equipment, chemical,
    legal_obligation, risk_factor, sector
}
```

`context_key` values come from the existing controlled vocabularies:

| context_type | key source |
|---|---|
| process | `services/knowledge_graph_rules.py::PROCESS_EXCAVATION_V1` (+ future controlled rules) |
| task | `TASK_WELDING_V1` (+ future) |
| equipment | `EQUIPMENT_FORKLIFT_V1` (+ future) |
| chemical | canonical `kosha_msds_chemicals.chem_id` |
| legal_obligation | LEG obligation atom id (SEARCH-07 wiring) |
| risk_factor | `risk_canonical_nodes.canonical_code` (only when ACTIVE) |
| sector | ISO / KSIC-derived sector code (align with `risk_canonical_node_sectors.sector_code`) |

### 8.1 Context ≠ Knowledge Graph copy

The Knowledge Graph read model
(`routers/public_knowledge_graph.py`) remains the authority for
graph edges. `context[]` in the SearchDocument is a **retrieval
projection** that carries the small subset of relations needed to
filter / boost the object at query time. The writer copies the
active graph edges for the object; it does NOT duplicate the graph.

### 8.2 Optional fields deferred to adapters

- `context_source` (rule id / manual / graph inference) — DEFERRED_TO_DOMAIN_ADAPTER
- `confidence` — DEFERRED_TO_DOMAIN_ADAPTER
- `authored_by` — DEFERRED_TO_DOMAIN_ADAPTER

## 9. Illustrative shape examples

The blocks below are **ILLUSTRATIVE SHAPE EXAMPLES** — not
fixtures. Identifiers (`<kosha_guide.id>`, `<canonical_id>`, etc.)
are placeholders that the reader substitutes with real values. Real
row-level fixtures (with real content_ids / actual ingested titles)
are produced by the Domain adapters in F2, not here.

Two classifications used in this repo:

```text
REAL EVIDENCE FIXTURE       — pinned to an actual repo row, checked
                              into tests as regression evidence
                              (F2 Domain-adapter WOs produce these)
ILLUSTRATIVE SHAPE EXAMPLE  — placeholder-valued example showing the
                              contract's required shape (this section)
```

### E1 — GUIDE (illustrative)

```yaml
object_type: GUIDE
canonical_id: <kosha_guide.id>          # KOSHA-issued text
source_id: KOSHA_OFFICIAL_GUIDE
source_key: <kosha_guide.id>            # same value; kosha_guide.id is
                                         # KOSHA-issued so it acts as both
title: 산업안전보건 관리 지침 (예시)
summary: <first N chars of guide description>
search_text: <title + description + category_name>
aliases: []
keywords: [<kosha_guide.category_name>]
subjects:
  - {subject_type: LEGAL_TERM, subject_key: 산업안전보건법}   # adapter maps
context:
  - {context_type: sector, context_key: construction}
public_url: https://kosha.or.kr/...
saas_url: /saas/guide/<canonical_id>
publication_status: PUBLISHED
visibility_scopes: [PUBLIC, SAAS, PAID]
```

### E2 — CHEM (illustrative)

```yaml
object_type: CHEM
canonical_id: <kosha_msds_chemicals.id>          # uuid
source_id: KOSHA_MSDS
source_key: <kosha_msds_chemicals.source_key>    # == chem_id
title: <chemical_name_ko>
summary: <2-3 line summary sourced from published section-1 canonical text>
search_text: <chemical_name_ko + chemical_name_en + CAS/KE/EN/UN + section-1..3 canonical text>
aliases: [<chemical_name_en>, <CAS>, <KE>, <EN>, <UN>]
keywords: []
subjects: []
                # NOTE: CHEM_TERM / 물질안전보건자료 is a QUERY-side
                # terminology axis, not a per-chemical property.
                # Whether individual chemicals carry it as a subject
                # is DEFERRED_TO_F2_CHEM_ADAPTER (WO §17).
context:
  - {context_type: chemical, context_key: <chem_id>}
public_url: /public/kosha/msds/<canonical_id>   # served only when the
                                                 # public runtime gate
                                                 # KOSHA_MSDS_PUBLIC_MODE
                                                 # ∈ {seo_preview, full}
saas_url: /saas/chemical/<canonical_id>
publication_status: PUBLISHED
                # Assumes the chemical is currently in one of the
                # published current read models (SEO preview OR FULL).
                # If public runtime gate is off, PUBLIC MUST be
                # dropped from visibility_scopes at query time (F3).
visibility_scopes: [PUBLIC, SAAS, PAID]
```

### E3 — LEGAL (illustrative)

```yaml
object_type: LEGAL
canonical_id: <opaque stable Domain identifier>
                # exact shape is DEFERRED_TO_F2_LEGAL_ADAPTER —
                # candidates: obligation_atom_id, article id, or
                # norm-cluster id
source_id: LEG_OFFICIAL                      # or LAW_REVISION_BOARD per record kind
source_key: <leg identifier if any; null otherwise>
title: 산업안전보건법 시행규칙 제XX조 (예시)
summary: <norm short text>
search_text: <title + norm body normalized>
aliases: []
keywords: []
subjects:
  - {subject_type: LEGAL_TERM, subject_key: 산업안전보건법 시행규칙}
context:
  - {context_type: legal_obligation, context_key: <obligation_atom_id>}
public_url: https://taieng.co.kr/legal/...
saas_url: /saas/legal/<canonical_id>
publication_status: PUBLISHED
visibility_scopes: [PUBLIC, SAAS, PAID]
```

### E4 — CSI_ACCIDENT (illustrative)

```yaml
object_type: CSI_ACCIDENT
canonical_id: CSI:<uuid>                  # csi_accident_cases.content_id
source_id: CSI                            # verbatim; not "KOSHA_CSI"
source_key: null                          # CSI file has no source-native id
title: <case_title>
summary: <accident summary>
search_text: <title + summary + accident_type + work_type>
aliases: []
keywords: [<accident_type>]
subjects:
  - {subject_type: ACCIDENT_TERM, subject_key: 추락}    # example, adapter maps
context:
  - {context_type: task, context_key: welding}          # if applicable
  - {context_type: sector, context_key: construction}
public_url: /public/accidents/csi/<uuid_part>
saas_url: /saas/accident/<uuid_part>
publication_status: PUBLISHED
visibility_scopes: [PUBLIC, SAAS, PAID]
```

### E5 — KNOWLEDGE_CENTER / help (illustrative)

```yaml
object_type: KNOWLEDGE
canonical_id: <safe_help_content.doc_id>
source_id: TAI_HELP_CENTER
source_key: <doc_id>                # same value; help center is
                                     # self-issued so canonical == source_key
title: <help article title>
summary: <first paragraph, stripped>
search_text: <title + body stripped>
aliases: []
keywords: [<menu_group>]
subjects: []
context: []
public_url: /help/<slug>
saas_url: /saas/help/<slug>
publication_status: PUBLISHED
visibility_scopes: [PUBLIC, SAAS, PAID]
```

### E6 — PRECEDENT (illustrative)

```yaml
object_type: PRECEDENT
canonical_id: <industrial_accident_precedents.id>  # uuid
source_id: law_go_kr                                # ingest "source" value
source_key: <prec_seq>                              # 판례일련번호; MAY be null
                                                     # for legacy/manual rows
title: <precedent title>
summary: <holding excerpt>
search_text: <title + holding + reasoning>
aliases: []
keywords: []
subjects:
  - {subject_type: LEGAL_TERM, subject_key: 산업안전보건법}  # example
context: []
public_url: null                                    # detail resolver
                                                     # DEFERRED_TO_DOMAIN_ADAPTER
saas_url: null
publication_status: PUBLISHED
visibility_scopes: [PUBLIC, SAAS, PAID]
```

### E7 — RISK NOT_INDEXABLE (illustrative negative)

```yaml
object_type: RISK
canonical_id: <risk_canonical_nodes.id>
source_id: <primary risk_source_mappings.source_id>
source_key: <primary risk_source_mappings.source_key>
                # additional (source_id, source_key) pairs stay in
                # risk_source_mappings — they are NOT copied into
                # aliases[] (§4.5).
title: <canonical_code display>
publication_status: HOLD
visibility_scopes: []
INDEXABLE: NO   # writer MUST reject (status=DRAFT, 0 sector links)
```

This example exists as **negative evidence**: the writer must
reject it. RISK-C02 opens the ACTIVE gate; only then does E7 flip
to an E1/E5-shaped PUBLISHED shape.

## 10. Domain adapter contract (input/output only)

SEARCH-04 will implement one adapter per Domain. This document
freezes the shape they must satisfy — no implementation.

```text
domain_adapter.read(cursor)          → iterable of Domain rows
domain_adapter.normalize(row)        → SearchDocument-shaped dict per §3
domain_adapter.validate(doc)         → raises on unknown object_type,
                                        missing canonical_id,
                                        publication_status not in
                                        {PUBLISHED, HOLD, REMOVED}
```

Writer contract (single implementation across Domains):

```text
writer.upsert(doc)         # doc validated + content_hash recomputed
writer.tombstone(canonical_id, object_type)
writer.reconcile(object_type) → {count, missing, extra, stale_by_hash}
```

Neither the adapter nor the writer mutates Domain SoT.

## 11. Reindex + tombstone contract

Three reindex modes (Constitution §12). Semantic behavior only —
SEARCH-03 chooses the physical mechanism.

### 11.1 FULL REBUILD

- runs per Domain (adapter-scoped) or globally
- writes to a candidate projection surface
- promotion to "current" only when the run:
  - reports non-zero output for every Domain that had non-zero
    output in the previous current
  - passes `content_hash` self-check
- partial success → NO PROMOTION (Constitution §10)

### 11.2 OBJECT REINDEX

Trigger sources:

| Domain | Trigger event |
|---|---|
| GUIDE | new snapshot COMPLETED |
| SAFETY_MATERIAL | new snapshot COMPLETED / storage hold toggle |
| CSI_ACCIDENT | row status → READY / HOLD / REMOVED |
| CHEM | publish_state transition |
| RISK | status DRAFT → ACTIVE (RISK-C02) |
| LEGAL | LEG publication event |
| KNOWLEDGE | safe_help_content.status change |
| PRECEDENT | insert / update / delete |

Object reindex NEVER promotes an object to PUBLISHED; it reflects
the Domain's already-taken decision.

### 11.3 NIGHTLY RECONCILIATION

For each Domain:

```text
count(Domain SoT PUBLISHED rows)  vs  count(current Search rows)
content_hash(Domain row)          vs  content_hash(Search row)
missing = in-SoT-not-in-Search
extra   = in-Search-not-in-SoT
stale   = hash mismatch
```

Threshold-based alerting is a SEARCH-05 operational concern.

### 11.4 Tombstone semantics

```text
Domain row moves to HOLD or REMOVED
  → next OBJECT REINDEX (or Nightly)
    → Search row's publication_status = HOLD | REMOVED
    → visibility_scopes = {}
    → Search retrieval MUST NOT return the object in any consumer scope
```

## 12. Duplicate Matrix classification (from SEARCH-00, contract-side)

Constitution §11 preserves Domain autonomy. This document declares
which existing surfaces convert to Shared Search **consumers** in
future WOs vs. which stay orthogonal.

### 12.1 Shared Search consumer candidates

| Existing surface | Consumer track WO | Migration meaning |
|---|---|---|
| `/public/safety-search` (tai-www federated 6 adapters + KOSHA provider) | SEARCH-06 | 6 internal adapters replaced by one Shared Search call; KOSHA stays external |
| `services/kosha_msds/search_adapter.py` (CHEM) | SEARCH-04 CHEM indexer | CHEM identifier-exact logic stays; discovery layer moves to Shared Search |
| Future RISK read model | SEARCH-04 RISK indexer (post RISK-C02) | Shared Search hosts only ACTIVE rows |
| SaaS context panels on process / task / equipment / obligation / inspection / chemical pages | Consumer rollout track | Context-driven queries against Shared Search |
| Paid Diagnosis related-knowledge panels | Consumer rollout track | Paid queries against Shared Search |

### 12.2 KEEP SEPARATE (must not migrate under SEARCH-*)

| Surface | Reason |
|---|---|
| Admin `/search` (company / user / factory / payment cross-search) | Operational entity search, not knowledge discovery |
| `/factory-process/search`, `/factory-process/kcsc/search` | Operational lookup / KCSC master ILIKE |
| `/engine-equipment/models` | Engine master catalog |
| `/equipment-assets/model/search` | SaaS equipment-model lookup (raw fetch from `MyEqAddModal.js`) |
| `/ksic-engine/search` | Industry code lookup |
| KOSHA Smart Search (external) | Discovery provider, not a Domain content source |
| `/help/search` (help-center Kiwi) | Domain-specific help surface; may become a KNOWLEDGE Shared-Search consumer later, but the operational endpoint stays |

### 12.3 Domain-specific logic that must be retained

- CHEM identifier-exact (`chemId / CAS / KE / EN / UN`) resolvers
- Legal Engine deterministic applicability rules
- RISK canonical hierarchy + sector logic
- Search Dictionary curation (seed_v2 build)

Migrating a consumer onto the Shared Search Engine never removes
these.

## 13. Conflict audit (§47)

Names checked against the current tree (`main` = `5d1fad8b`):

| Name | Existing collision | Resolution |
|------|--------------------|------------|
| `object_type` | `services/support_routing_svc.py` uses `object_type` for support-intent axis (values include `"diagnosis"`); `services/support_classifier_svc.py` similarly | **Namespace at the boundary**: Support layer keeps its `object_type` for intent classification. The Shared Search field is the same name but scoped to Search context (payload of `search_documents` and `SearchResult`). Consumers that talk to both must not conflate. |
| `canonical_id` | `risk_canonical_mapping.sql` uses `canonical_id` as FK to `risk_canonical_nodes(id)` | **Reuse verbatim.** Search's `canonical_id` for RISK IS the same value. For other domains, `canonical_id` is the Domain's primary stable id. |
| `source_id` | CHEM `materialize_writer`, `production_store`, `document_schema_renderer`, `kosha_guide_sync`, `knowledge_graph_svc` all use `source_id` | **Reuse verbatim.** Search's `source_id` values must be drawn from the same set (`KOSHA_MSDS`, `KOSHA_OFFICIAL_GUIDE`, etc.). Adapter picks the canonical value. |
| `source_key` | Same call sites as `source_id` | **Reuse verbatim.** |
| `publication_status` | `services/kosha_msds/ops.py` uses `publication_status` in status reports; CHEM code uses `publish_state` for the actual enum column | **Adopt.** Shared enum `PUBLISHED / HOLD / REMOVED` is new but the name aligns with existing usage. CHEM adapter maps `publish_state` → `publication_status`. |
| `publication_scope` | CHEM-only enum (`FULL / SEO_PREVIEW`) in `services/kosha_msds/contract.py`, `cutover.py`, `production_store.py` | **Keep Domain-scoped.** `publication_scope` stays a CHEM-specific column in Domain tables. The SearchDocument does NOT carry `publication_scope`; the CHEM adapter reads it internally to decide whether the row is PUBLISHED in the shared sense. |
| `match_type` | `tools/search_dict/search_core.py::MATCH_SCORE` = `{EXACT, NORMALIZED_EXACT, PUNCTUATION, ABBREVIATION_OF, SPACING_VARIANT_OF, PUNCTUATION_VARIANT_OF, SPELLING_VARIANT_OF, ENGLISH_OF, EXACT_ALIAS, SYNONYM_OF, TOKEN, TRIGRAM}`; `services/legal_engine_policy.py` uses `match_type` for its own rule dispatch | **Reuse verbatim.** SearchResult's `match_type` uses the search-dict vocabulary exactly (no simplification of `ABBREVIATION_OF` → `ABBREVIATION`, etc.). Engine-level tiers (`IDENTIFIER_EXACT`, `CANONICAL_EXACT`, `TITLE_EXACT`, `CONTEXT`, `FTS`) are additive. Legal Engine's `match_type` is a private engine concern and must not be conflated in consumer code. |
| `context` | Too generic; overloaded in multiple services | **Namespace to a typed tuple**: `context` in the SearchDocument is an array of `(context_type, context_key)` from the fixed vocabulary in §8. Callers that pass a generic "context" bag must map it into these tuples. |
| `scope` | Also generic; used ephemerally | **Namespace to `visibility_scopes`** in the SearchDocument. Do not use the bare word `scope`. |

## 14. Deferred (DOMAIN_ADAPTER-owned) decisions

The following are deliberately deferred to SEARCH-04 Domain-adapter
WOs. They are Domain-specific and cannot be finalized in a shared
contract without per-Domain evidence:

- `context_source` field (§8.2)
- `confidence` field (§8.2)
- Per-Domain `search_text` composition (which columns of the SoT
  contribute; how normalization interacts with domain-specific
  punctuation, e.g., dot in CAS numbers)
- Section granularity for CHEM (currently NO section-level docs)
- Chunk granularity for GUIDE PDFs (currently NO chunking; LINK_ONLY)
- LEGAL `canonical_id` shape when the record is a norm cluster vs a
  single obligation atom (adapter chooses the most stable id)

Each deferral is marked `DEFERRED_TO_DOMAIN_ADAPTER` and MUST be
resolved before its Domain's SEARCH-04 indexer ships.

## 14a. Contract consistency matrix

All three contract documents (Constitution, Document Contract,
Result Contract) MUST agree on the following axes. Any change to a
row here requires an Owner-approved WO that updates all three
documents together (Constitution Article 15).

| Axis | Constitution | Document Contract | Result Contract |
|------|--------------|-------------------|-----------------|
| Publication enum values | Article 4, Article 14 (implicit) | §6 (`PUBLISHED / HOLD / REMOVED` exactly) | §5 (results only surface PUBLISHED objects) |
| `search_document_id` vs `canonical_id` vs `(source_id, source_key)` | Article 3 | §2 (three-way separation) | §2 (only `canonical_id + object_type` emitted) |
| `source_key` nullability | — (adapter concern) | §3 (nullable, no synthetic values) | §2 (never emitted; INTERNAL) |
| Subjects representation | Article 5 (reuse existing runtime) | §3 (`subjects[]` as `(subject_type, subject_key)` pairs) | §2 (`subject_type` + `subject_key` are optional twin scalars per hit) |
| Legal applicability authority | Article 2 (Search ≠ applicability) | §4.6 CRITICAL | §5.4 explainability + §10 governance |
| RISK DRAFT exclusion | Article 4 (Search never promotes) | §7.2 (INDEXABLE=NO for DRAFT) | reflected in §6 (result set only over PUBLISHED) |
| External discovery provider distinction | Article 7 | §12.2 (KOSHA Smart Search KEEP SEPARATE) | §7 (separate shape + presentation merge + failure isolation) |
| `match_type` vocabulary | Article 5 (reuse current stack) | §13 (verbatim reuse of search-dict values) | §5.1 (verbatim runtime values + 5 engine-level tiers) |
| Pagination | — (SEARCH-03 boundary) | — (schema concern) | §6.2 (DEFERRED_TO_F3; only "stable deterministic ordering" required now) |
| LLM prohibition | Article 8 | §7.3 (no LLM output stored) | §3.3 (no LLM in ranking) + §10 (no `LLM_INFERRED` match_type) |
| CHEM publication authority | Article 4 (Search never promotes) | §4.4 (Search reads published current read models; NEVER calls `is_full_ready`) | (implicit via publication_status contract) |
| CHEM public runtime gate | Article 4 + Article 9 | §4.4 (public runtime gate distinct from publication) | §6/§8 (visibility_scopes filtered at query time; F3 concern) |
| Consumer scopes | Article 9 | §7 (`PUBLIC / SAAS / PAID / INTERNAL`) | §8 (three consumer examples one per non-INTERNAL scope) |
| Tenant secret exclusion | Article 9 (SaaS scope note) | §7.3 (must not store) | §2 (no tenant field in envelope) |
| Reindex modes | Article 12 (three modes) | §11 (FULL REBUILD / OBJECT REINDEX / NIGHTLY RECONCILIATION) | (implicit — results only over promoted current) |
| Fixture classification | — | §9 (ILLUSTRATIVE SHAPE EXAMPLE vs REAL EVIDENCE FIXTURE) | §8 (illustrative consumer examples only) |

Any inconsistency between a specific claim in one document and its
counterpart here means the specific claim is wrong. Escalate.

## 15. Exit criteria (from WO §49)

- [x] SearchDocument semantic contract — frozen (§3)
- [x] Domain identity matrix (8 domains) — frozen (§4)
- [x] Publication eligibility contract — frozen (§6)
- [x] Visibility scope contract — frozen (§7)
- [x] Context vocabulary — frozen (§8)
- [x] content_hash contract — frozen (§5)
- [x] Reindex modes contract — frozen (§11)
- [x] Tombstone contract — frozen (§11.4)
- [x] Adapter / writer contract shape — frozen (§10)
- [x] Duplicate Matrix classification — frozen (§12)
- [x] Conflict audit — resolved (§13)
- [x] SEARCH-03 boundary — held (see Constitution Article 16)

SEARCH-03 opens next.
