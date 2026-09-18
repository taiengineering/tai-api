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
| `source_id` | R | provenance system id | Adapter | UPPER_SNAKE_CASE | INTERNAL only | provenance | multi-source merge tracked here |
| `source_key` | R | provenance record key | Adapter | Domain-shape | INTERNAL only | provenance | may add rows, never overwrite |
| `title` | R | canonical display title | Domain field | strip + trim; keep original case | scope-gated | display | on Domain title change |
| `summary` | O | preview blurb (≤ 300 chars) | Domain field or first-N of body | strip HTML | scope-gated | display | with title |
| `search_text` | R | searchable text projection | Adapter-composed | normalize_basic + compact | INTERNAL to engine only | retrieval | on title/summary/body change |
| `aliases[]` | O | approved alternate surfaces | Adapter reads Domain-approved list | shared dict normalize | INTERNAL | retrieval | Adapter re-fetches |
| `keywords[]` | O | Domain-native keywords | Adapter reads Domain metadata | strip + trim | INTERNAL | retrieval | on Domain metadata change |
| `subject_types[]` | O | shared dictionary subject axes | Adapter maps via search-dict subjects | shared dict values only | INTERNAL | retrieval boost | when subjects join/leave |
| `subject_keys[]` | O | shared dictionary subject keys | Adapter | shared dict values only | INTERNAL | retrieval boost | with subject_types |
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

```text
object_type          = SAFETY_MATERIAL
Domain SoT           = public.kosha_safety_materials  (catalog)
Snapshot tables      = kosha_safety_material_snapshots
                       kosha_safety_material_snapshot_items
Details table        = kosha_safety_material_details
Assets table         = kosha_safety_material_assets
                       kosha_safety_material_asset_versions
canonical_id         = kosha_safety_materials.id
source_id            = KOSHA_OFFICIAL_MATERIAL
source_key           = kosha_safety_materials.material_id (KOSHA-issued)
publication gate     = catalog row present + snapshot COMPLETED +
                       asset storage policy ≠ HOLD (see
                       kosha_safety_material_storage_holds*)
current read model   = latest COMPLETED snapshot with holds excluded
detail resolver      = existing MATERIAL read (tai-www server helper)
public eligible      = YES
saas eligible        = YES
paid eligible        = YES
publication_status   = PUBLISHED / HOLD / UNAVAILABLE
                       (adapter maps kosha_safety_material_storage_holds*
                        review / unavailable / oversize to HOLD)
```

### 4.3 CSI (ACCIDENT) — construction accident cases

```text
object_type          = CSI_ACCIDENT
Domain SoT           = public.csi_accident_cases
Snapshot tables      = csi_accident_snapshots
                       csi_accident_snapshot_items
canonical_id         = csi_accident_cases.id
source_id            = KOSHA_CSI
source_key           = csi_accident_cases.case_id
publication gate     = row.status == READY  (HOLD → 404 today per
                       routers/public_csi_accidents.py)
current read model   = READY-only public read
detail resolver      = /public/accidents/*  (routers/public_csi_accidents.py)
public eligible      = YES (READY only)
saas eligible        = YES
paid eligible        = YES
publication_status   = PUBLISHED  when status=READY
                     = HOLD       when status=HOLD
                     = REMOVED    when status=REMOVED
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
source_key           = kosha_msds_chemicals.source_key  (== chem_id)
publication gate     = kosha_msds_snapshots.publish_state in
                       (PUBLISHED_SEO_PREVIEW, PUBLISHED_FULL)
                       + services/kosha_msds/cutover.is_full_ready
                       for FULL scope
publication scope    = PUBLICATION_SCOPE_SEO_PREVIEW (1,997 today)
                       PUBLICATION_SCOPE_FULL       (0 today)
publish_state enum   = NOT_PUBLISHED / PUBLISHED_SEO_PREVIEW / PUBLISHED_FULL
current read model   = kosha_msds_seo_preview_current view (SEO preview)
                       kosha_msds_full_current view (FULL)
detail resolver      = CHEM-06 read service (currently dormant public
                       via /public/kosha/msds when KOSHA_MSDS_PUBLIC_MODE set)
public eligible      = YES when KOSHA_MSDS_PUBLIC_MODE ∈ {seo_preview, full}
saas eligible        = YES (context: chemical / process linkage)
paid eligible        = YES (paid diagnosis chemical-related section)
publication_status   = PUBLISHED  when publish_state in the PUBLISHED set
                     = HOLD       otherwise
special              = 16 sections per chemical fold into the
                       parent SearchDocument's search_text +
                       subjects[]; sections are NOT separate
                       SearchDocument rows (§1 exception rationale).
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
                       canonical_id. SearchDocument carries the
                       canonical_id + the primary (source_id,
                       source_key). Additional mappings surface via
                       aliases[] only if the mapping_status is
                       APPROVED_EXACT.
```

### 4.6 LEGAL — law norms / obligations

```text
object_type          = LEGAL
Domain SoT           = LEG stack (kept out of tai-api's canonical
                       write path; consumed via legal_engine_svc)
Related tables       = law_revision_board (tai-www), LEG published
                       obligation norms, TAI legal engine
                       deterministic rules
canonical_id         = leg obligation_atom_id (when applicable) OR
                       law article identifier — adapter selects the
                       most stable id per record type
source_id            = LEG_OFFICIAL / LAW_REVISION_BOARD (choose per
                       record kind)
source_key           = leg identifier / revision id
publication gate     = LEG published state + APPROVED
current read model   = existing LEG read paths
detail resolver      = LEG read endpoints
public eligible      = YES (law-updates on Public / safety-search)
saas eligible        = YES (obligation-context — see SEARCH-07 gate)
paid eligible        = YES (paid diagnosis obligation summaries)
publication_status   = PUBLISHED / HOLD / REMOVED
CRITICAL            = LEGAL SearchResult **must never** be treated as
                       an applicability decision. Consumers that need
                       applicability call the Legal Engine.
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

```text
object_type          = PRECEDENT
Domain SoT           = public.industrial_accident_precedents (newer)
                       + legacy public.posts view (adapter picks
                       industrial_accident_precedents first)
canonical_id         = industrial_accident_precedents.id
source_id            = TAI_PRECEDENT_IAP  (or its legacy equivalent
                       when the row was migrated from posts)
source_key           = industrial_accident_precedents.source_id_of_precedent
                       or legacy posts.source_id (verify per row)
publication gate     = live row + not marked REMOVED
detail resolver      = /precedents/{id}  (routers/precedent_api.py)
public eligible      = YES
saas eligible        = YES
paid eligible        = YES
publication_status   = PUBLISHED / HOLD / REMOVED
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
    subject_types + subject_keys (sorted paired list)
    context  (sorted by (context_type, context_key))
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

Adapter maps Domain-specific publication state to the shared enum:

| SearchDocument state | Semantic | Result eligibility |
|---|---|---|
| `PUBLISHED` | Domain object is authoritatively published under its own gate | eligible for all `visibility_scopes` it declares |
| `HOLD` | Domain says "not yet" (draft / not ready / storage hold / abnormality flagged) | NOT indexed; if previously indexed, tombstone on next reindex |
| `REMOVED` | Domain says "no longer valid" (deleted / unpublished / superseded) | tombstoned; must not surface in any scope |

Domain-adapter mapping table (from §4):

| Domain | PUBLISHED | HOLD | REMOVED |
|---|---|---|---|
| GUIDE | catalog row + snapshot COMPLETED | otherwise | catalog delete |
| SAFETY_MATERIAL | catalog row + snapshot COMPLETED + storage_holds NOT set | any storage hold OR unavailable OR review | catalog delete |
| CSI_ACCIDENT | csi_accident_cases.status = READY | HOLD | REMOVED |
| CHEM | kosha_msds_snapshots.publish_state ∈ {PUBLISHED_SEO_PREVIEW, PUBLISHED_FULL} | NOT_PUBLISHED / RUNNING / FAILED | catalog delete |
| RISK | risk_canonical_nodes.status = ACTIVE | DRAFT (all rows today) | future-only |
| LEGAL | LEG PUBLISHED | LEG DRAFT / HOLD | LEG SUPERSEDED / REMOVED |
| KNOWLEDGE | safe_help_content.status = PUBLISHED | DRAFT / REVIEW | ARCHIVED / DELETE |
| PRECEDENT | live row | staged/review | REMOVED |

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

## 9. Fixtures (evidence-based)

Semantic fixtures using real repo objects. No test wire-up — just
frozen expected shapes so SEARCH-03 has target data.

### F1 — GUIDE

```yaml
object_type: GUIDE
canonical_id: <kosha_guide.id>          # KOSHA-issued text
source_id: KOSHA_OFFICIAL_GUIDE
source_key: <kosha_guide.id>
title: 산업안전보건 관리 지침 (예)
summary: <first N chars of guide description>
search_text: <title + description + category_name>
aliases: []
keywords: [<kosha_guide.category_name>]
subject_types: [LEGAL_TERM]              # via search-dict mapping
subject_keys: [산업안전보건법]
context:
  - {context_type: sector, context_key: construction}
public_url: https://kosha.or.kr/...
saas_url: /saas/guide/<canonical_id>
publication_status: PUBLISHED
visibility_scopes: [PUBLIC, SAAS, PAID]
```

### F2 — CHEM

```yaml
object_type: CHEM
canonical_id: <kosha_msds_chemicals.id>   # uuid
source_id: KOSHA_MSDS
source_key: <kosha_msds_chemicals.source_key>   # == chem_id
title: <chemical_name_ko>
summary: <2-3 line MSDS summary from section 1>
search_text: <chemical_name_ko + chemical_name_en + CAS/KE/EN/UN + section-1..3 canonical text>
aliases: [<chemical_name_en>, <CAS>, <KE>, <EN>, <UN>]
keywords: []
subject_types: [CHEM_TERM]
subject_keys: [물질안전보건자료]
context:
  - {context_type: chemical, context_key: <chem_id>}
public_url: /public/kosha/msds/<canonical_id>  # only when KOSHA_MSDS_PUBLIC_MODE set
saas_url: /saas/chemical/<canonical_id>
publication_status: PUBLISHED
visibility_scopes: [PUBLIC, SAAS, PAID]
```

### F3 — LEGAL

```yaml
object_type: LEGAL
canonical_id: <leg obligation_atom_id OR article id>
source_id: LEG_OFFICIAL
source_key: <leg identifier>
title: 산업안전보건법 시행규칙 제XX조
summary: <norm short text>
search_text: <title + norm body normalized>
aliases: []
keywords: []
subject_types: [LEGAL_TERM]
subject_keys: [산업안전보건법 시행규칙]
context:
  - {context_type: legal_obligation, context_key: <obligation_atom_id>}
public_url: https://taieng.co.kr/legal/...
saas_url: /saas/legal/<canonical_id>
publication_status: PUBLISHED
visibility_scopes: [PUBLIC, SAAS, PAID]
```

### F4 — CSI_ACCIDENT

```yaml
object_type: CSI_ACCIDENT
canonical_id: <csi_accident_cases.id>
source_id: KOSHA_CSI
source_key: <csi_accident_cases.case_id>
title: <case_title>
summary: <accident summary>
search_text: <title + summary + accident_type + work_type>
aliases: []
keywords: [<accident_type>]
subject_types: [ACCIDENT_TERM]
subject_keys: [추락]  # example
context:
  - {context_type: task, context_key: welding}   # if applicable
  - {context_type: sector, context_key: construction}
public_url: /public/accidents/<canonical_id>
saas_url: /saas/accident/<canonical_id>
publication_status: PUBLISHED
visibility_scopes: [PUBLIC, SAAS, PAID]
```

### F5 — KNOWLEDGE_CENTER (help)

```yaml
object_type: KNOWLEDGE
canonical_id: <safe_help_content.doc_id>
source_id: TAI_HELP_CENTER
source_key: <doc_id>
title: <help article title>
summary: <first paragraph, stripped>
search_text: <title + body stripped>
aliases: []
keywords: [<menu_group>]
subject_types: []
subject_keys: []
context: []
public_url: /help/<slug>
saas_url: /saas/help/<slug>
publication_status: PUBLISHED
visibility_scopes: [PUBLIC, SAAS, PAID]
```

### F6 — PRECEDENT

```yaml
object_type: PRECEDENT
canonical_id: <industrial_accident_precedents.id>
source_id: TAI_PRECEDENT_IAP
source_key: <legacy source id>
title: <precedent title>
summary: <holding excerpt>
search_text: <title + holding + reasoning>
aliases: []
keywords: []
subject_types: [LEGAL_TERM]
subject_keys: [산업안전보건법]
context: []
public_url: /precedents/<canonical_id>
saas_url: /saas/precedent/<canonical_id>
publication_status: PUBLISHED
visibility_scopes: [PUBLIC, SAAS, PAID]
```

### F7 — RISK (NOT_INDEXABLE fixture)

```yaml
object_type: RISK
canonical_id: <risk_canonical_nodes.id>
canonical_code: <risk_canonical_nodes.canonical_code>
source_id: <mapping.source_id>
source_key: <mapping.source_key>
title: <canonical_code display>
publication_status: HOLD
visibility_scopes: []
INDEXABLE: NO   # adapter MUST reject (status=DRAFT, 0 sector links)
```

This fixture exists as **negative evidence**: the writer must
reject it. RISK-C02 opens the ACTIVE gate; only then does F7 become
an F5-shaped PUBLISHED fixture.

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
| `match_type` | `tools/search_dict/search_core.py::MATCH_SCORE` = `{EXACT, NORMALIZED_EXACT, PUNCTUATION, ABBREVIATION, SYNONYM, TOKEN, TRIGRAM}`; `services/legal_engine_policy.py` uses `match_type` for its own rule dispatch | **Reuse verbatim for search-dict-derived values.** SearchResult's `match_type` uses the search-dict vocabulary. Legal Engine's `match_type` is a private engine concern and must not be conflated in consumer code. |
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
