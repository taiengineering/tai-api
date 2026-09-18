# TAI Shared Search — Result Contract v1

**WO**: WO-TAI-SHARED-SEARCH-002
**Status**: docs-only. Zero code / DB / schema / index / deploy.
**Sibling docs**:
- `TAI_SHARED_SEARCH_CONSTITUTION_v1.md`
- `TAI_SHARED_SEARCH_DOCUMENT_CONTRACT_v1.md`

This document freezes:

1. The **SearchResult** shape returned to consumers (§2)
2. The **ranking precedence** every consumer must expect (§3)
3. The **dedup** rule that guarantees "one canonical object → one result" (§4)
4. The **match explanation** every result must carry (§5)
5. The **external discovery provider** presentation contract (§7)
6. Three concrete **consumer request/response examples** (Public / SaaS / Paid) — §8

Nothing here defines an HTTP endpoint URL or a Python signature.
SEARCH-05 (Retrieval Engine) turns this contract into an API.

---

## 1. Scope

`SearchResult` is the shape produced by the Shared Search Engine
(SEARCH-05) when serving a query from **internal** Shared Search
Projection rows. External discovery-provider results (KOSHA Smart
Search) carry a related but distinct shape (see §7); the consumer
merges the two at the presentation layer.

Every field described here is CONSUMER-facing. Fields marked
`INTERNAL` in the Document Contract (`search_document_id`, `source_id`,
`source_key`, `search_text`, raw `aliases[]`) are NEVER emitted.

## 2. SearchResult item shape

```yaml
# One SearchResult item, per canonical object.

object_type:        <fixed enum, §Document 3+4>
canonical_id:       <Domain canonical id>

title:              <string, canonical display title>
summary:            <string ≤ 300 chars, optional>

# match evidence (required — every result must be explainable)
match_type:         <fixed enum, §5>
matched_term:       <string>
subject_type:       <search-dict subject_type, optional>
subject_key:        <search-dict subject_key, optional>

# ranking score (0..100 deterministic; SEARCH-05 fixes numbers)
score:              <number>

# additional evidence (optional — only when dedup collapsed multiple
# hits into one; see §4)
additional_matches:
  - {match_type, matched_term, subject_type, subject_key, score}

# routing
public_url:         <string, optional>
saas_url:           <string, optional>

# freshness
source_updated_at:  <ISO 8601, optional>
```

### 2.1 Field-by-field

| Field | Req | Type | Meaning |
|-------|-----|------|---------|
| `object_type` | R | enum | fixed set from Document §4 |
| `canonical_id` | R | string | Domain SoT id; consumer uses `(object_type, canonical_id)` for detail resolution |
| `title` | R | string | display title from the SearchDocument |
| `summary` | O | string | preview (may be absent for identifier-only hits) |
| `match_type` | R | enum | why this row matched — §5 |
| `matched_term` | R | string | the exact string that produced the match |
| `subject_type` | O | string | search-dict subject_type when the match went through T1..T3 |
| `subject_key` | O | string | search-dict subject_key |
| `score` | R | number | deterministic score, `0..100` (SEARCH-05 fixes) |
| `additional_matches` | O | list | non-primary hits collapsed by dedup |
| `public_url` | O | string | canonical Public URL |
| `saas_url` | O | string | canonical SaaS URL |
| `source_updated_at` | O | ISO date | Domain last-update timestamp |

Consumers may safely IGNORE unknown optional fields.

### 2.2 Envelope

The engine's response wraps `items` in the standard TAI envelope:

```yaml
status: success
data:
  query:           <string>
  normalized_query: <string>
  compact_query:    <string>
  snapshot:         <search-dict runtime snapshot id>
  active_tiers:     [<T1_EXACT, T2_..., T4_KIWI_TOKEN, T6_TRIGRAM as applicable>]
  items:            [<SearchResult items>]
  total:            <int, when the request asks for it>
  scope:            <PUBLIC | SAAS | PAID | INTERNAL>
  request_context:  <optional echoed context input>
```

The `snapshot` + `active_tiers` fields already exist in
`/search-dict/lookup` (SEARCH-01 verified). The Retrieval Engine
carries them forward at the Search-of-documents layer for the same
reason: explainability + operational drift detection.

## 3. Ranking precedence

The engine ranks hits by the following precedence. When two hits
would tie by rule, the higher-precedence rule wins. Concrete score
numbers are SEARCH-05's decision — this contract fixes ONLY the
precedence order and its rationale.

```text
1.  IDENTIFIER EXACT          (identifier gate, Constitution §6)
2.  CANONICAL EXACT           (query == canonical_id / canonical_code)
3.  SUBJECT EXACT             (T1 EXACT + subject match, from search-dict)
4.  TITLE EXACT               (query == title)
5.  ALIAS / SYNONYM           (T3 EXPANSION via search-dict)
6.  CONTEXT MATCH             (query resolves to a context tuple that
                                the document carries in §Document 8)
7.  FULL-TEXT SEARCH          (Postgres FTS over search_text)
8.  KIWI TOKEN MATCH          (T4 tokenization → subject overlap)
9.  TRIGRAM FALLBACK          (T6, only when TAI_SEARCH_SCRATCH_DSN set)
```

### 3.1 Why this order

- **Identifier / canonical exact must win** — Constitution §6.
  Domain-issued identifiers are the highest-precision signal
  available, and fuzzy paths must not compete with them.
- **Subject exact > title exact** — subjects come from the curated
  `search-dict` snapshot (471 subjects / 491 indexed terms today).
  A subject-key match implies vocabulary approval, which is
  stronger than a title substring collision.
- **Alias / synonym > context match** — approved expansions are
  vocabulary-controlled; context signals are query-time inferences.
- **FTS > Kiwi > Trigram** — degrades from precise to fuzzy. Kiwi
  and Trigram are optional tiers (SEARCH-01 §Manifest); their
  results MUST carry `match_type=TOKEN` or `match_type=TRIGRAM` so
  consumers can filter or de-rank if desired.

### 3.2 Precedence tie-break

When two hits share the same tier, tie-break in order:

1. Higher `subject_type` priority (LEGAL > CHEM_TERM > EQUIPMENT_TERM > ...
   — final priority list frozen in SEARCH-05)
2. Higher `object_type` priority per consumer scope (SEARCH-05 fixes)
3. More recent `source_updated_at`
4. Lexicographic `canonical_id` (deterministic tiebreaker of last resort)

### 3.3 Rerank policy

**No LLM reranking in the initial retrieval path** (Constitution §8).
Deterministic scores only. A future reranker WO may layer on top
after precision is measured against the frozen precedence.

## 4. Dedup contract

```text
1 canonical object (object_type, canonical_id)
  → 1 SearchResult item
  → at most 1 primary match (highest-precedence tier that hit)
  → optional additional_matches[] for the non-primary evidence
```

### 4.1 Dedup rule

For each `(object_type, canonical_id)` pair:

1. Compute the set of hits from all active tiers.
2. Keep the highest-precedence hit as the **primary**:
   `match_type`, `matched_term`, `subject_type`, `subject_key`,
   `score` are set from this hit.
3. Preserve the remaining hits as `additional_matches[]`. Consumers
   who want the "why" of a duplicate can inspect this list.
4. Sort the flattened result set by primary `score` DESC, then by
   the tiebreak chain in §3.2.

### 4.2 Cross-object collisions are NOT dedup

Two distinct canonical objects may match the same query; they stay
as two separate SearchResult items. Dedup is per canonical object,
never across.

## 5. Match explanation contract

Every SearchResult item carries a **black-box-free** explanation.

### 5.1 `match_type` vocabulary

The Retrieval Engine reuses `tools/search_dict/search_core.py::MATCH_SCORE`
values **verbatim** (no simplification, no aliasing) and adds five
engine-level tiers on top. Simplifying `ABBREVIATION_OF` to
`ABBREVIATION` (or `SYNONYM_OF` to `SYNONYM`) is FORBIDDEN — the
existing runtime keys already carry directionality that consumers
depend on.

Search-dict runtime values (verbatim from `MATCH_SCORE`):

```text
EXACT
NORMALIZED_EXACT
PUNCTUATION
ABBREVIATION_OF
SPACING_VARIANT_OF
PUNCTUATION_VARIANT_OF
SPELLING_VARIANT_OF
ENGLISH_OF
EXACT_ALIAS
SYNONYM_OF
TOKEN
TRIGRAM
```

Engine-level values (added by SEARCH-05, layered above the runtime):

```text
IDENTIFIER_EXACT    identifier gate (Constitution §6)
CANONICAL_EXACT     query == canonical_id / canonical_code
TITLE_EXACT         query == SearchDocument.title
CONTEXT             context-tuple hit against SearchDocument.context
FTS                 Postgres FTS over SearchDocument.search_text
```

`SOURCE_SEARCH` is the fixed value emitted by the external KOSHA
Smart Search provider (§7); it is NOT part of the internal engine's
`match_type` set.

### 5.2 `matched_term`

The exact string that fired the match. For CHEM identifier hits it
is the identifier (`CAS: 71-43-2`). For a Kiwi noun-decomposition
match it is the tokenized surface returned by the T4 tier (already
demonstrated in production — SEARCH-01 SMOKE-05 example:
`매치 = 건축법을 → subject_key=건축법 / match_type=TOKEN /
matched_term=건축법`).

### 5.3 `subject_type` + `subject_key`

Populated whenever the query resolved to a search-dictionary
subject, including subject-augmented T4/T6 hits. Production
evidence: `건축법을 → TOKEN / subject_type=LEGAL_TERM /
subject_key=건축법` (SEARCH-01 SMOKE-05). Absent for
identifier-exact, canonical-exact, title-exact, FTS, and pure
Kiwi/Trigram matches whose token did NOT collapse to a
subject-approved surface.

### 5.4 Consumer-visible score

`score` is a number in `[0, 100]`. Consumers do not need to
understand the scoring function — they only need to know that
higher = better and the ordering is stable across queries with the
same runtime snapshot. SEARCH-05 pins the exact function.

## 6. Result set semantics

### 6.1 Ordering

Items are returned in strict ranking order (§3). Consumers that
paginate MUST accept the engine's stable ordering — no re-sort by
`source_updated_at` etc. on the client. Stable-ordering guarantees
pagination correctness under identical `snapshot`.

### 6.2 Pagination

Stable, deterministic ordering under a fixed `snapshot` is
REQUIRED. The concrete pagination mechanism (cursor vs
offset+limit, cursor encoding, `next_cursor` shape, `total`
availability) is **DEFERRED_TO_F3** — SEARCH-05 picks it against
the retrieval-engine's actual query plan.

Present-state note (not the contract):

- `/search-dict/lookup` today uses `limit` only (no cursor)
- CHEM search adapter today uses `limit + offset`

Neither is elevated to a shared contract here.

### 6.3 Limits

- default page size = 20 items
- max page size = 100 items
- max scan depth per tier = SEARCH-05 pins
- consumer-declared `limit` is honored up to max
- consumer-declared `subject_type` filter is honored strictly
- consumer-declared `object_type` filter is honored strictly

## 7. External discovery provider contract

KOSHA Smart Search (`routers/public_safety_search.py`) is an
external discovery provider (Constitution §7). Its results:

- MUST NOT enter the shared `tai_search_documents` projection
- MUST carry a `provider` field distinguishing them from internal
  Search results
- MUST NOT masquerade as a canonical object

### 7.1 External result shape

```yaml
provider:           KOSHA_SMART_SEARCH
external_id:        <KOSHA-issued id>
title:              <string>
summary:            <string, optional>
external_url:       <string>
match_type:         SOURCE_SEARCH
matched_term:       <string>
score:              <number, external provider's own score, treated
                     as INFORMATIONAL>
```

`canonical_id` and `object_type` are **absent** — an external
provider result is not a canonical Domain object of TAI.

### 7.2 Presentation-layer merge

The Public consumer (SEARCH-06) may present:

```yaml
data:
  internal_items: [<SearchResult items>]
  external_items: [<external provider items>]
```

or interleave them in a single list under an explicit
`items[i].provider` flag. Either is acceptable as long as external
results are visually and structurally distinguishable and never
mutate `canonical_id / object_type` state.

### 7.3 External provider failure isolation

The Retrieval Engine MUST return internal results when the external
provider is unreachable, timed out, or errored:

```text
external_items = []
warnings = [ {provider: KOSHA_SMART_SEARCH, code: TIMEOUT} ]
```

An external failure is never a 5xx to the consumer.

## 8. Consumer request/response examples

These are **contract examples**, not endpoint definitions. SEARCH-05
picks the URL, method, and parameter names.

### 8.1 PUBLIC — explicit knowledge search

Consumer intent: user typed "MSDS" in the public safety-search bar.

```yaml
# request
q:              "MSDS"
scope:          PUBLIC
limit:          20
```

```yaml
# response (abbreviated)
status: success
data:
  query: MSDS
  normalized_query: MSDS
  snapshot: SEARCH-DICT-LEGPROD-2026-09-16
  active_tiers: [T1_EXACT, T2_NORMALIZED_EXACT, T2b_PUNCTUATION,
                 T3_EXPANSION, T4_KIWI_TOKEN]
  scope: PUBLIC
  internal_items:
    - object_type: CHEM
      canonical_id: <kosha_msds_chemicals.id>
      title: 물질안전보건자료
      match_type: EXACT
      matched_term: MSDS
      subject_type: CHEM_TERM
      subject_key: 물질안전보건자료
      score: 100
      public_url: /public/kosha/msds/<canonical_id>
    - object_type: GUIDE
      canonical_id: <some_kosha_guide.id>
      title: 화학물질 취급 시 안전보건 지침
      match_type: TOKEN
      matched_term: 화학물질 안전
      subject_type: CHEM_TERM
      subject_key: 물질안전보건자료
      score: 55
      public_url: https://kosha.or.kr/...
  external_items:
    - provider: KOSHA_SMART_SEARCH
      external_id: kosha-smart-...
      title: ...
      external_url: https://kosha.or.kr/smart-search/...
      match_type: SOURCE_SEARCH
      matched_term: MSDS
      score: 40
```

### 8.2 SAAS — context search on a Process page (no user query)

Consumer intent: user opened the SaaS "process detail" page for a
"welding" process. Consumer sends the process context; expects
related knowledge without the user typing anything.

```yaml
# request
context:
  - {context_type: task, context_key: welding}
  - {context_type: sector, context_key: construction}
scope: SAAS
object_types: [GUIDE, CSI_ACCIDENT, LEGAL]
limit: 10
```

```yaml
# response (abbreviated)
status: success
data:
  query: null
  request_context:
    - {context_type: task, context_key: welding}
    - {context_type: sector, context_key: construction}
  snapshot: SEARCH-DICT-LEGPROD-2026-09-16
  active_tiers: []      # no keyword tiers ran; context-only retrieval
  scope: SAAS
  internal_items:
    - object_type: GUIDE
      canonical_id: <guide_id>
      title: 용접·용단 작업 안전보건 지침
      match_type: CONTEXT
      matched_term: task=welding
      subject_type: null
      subject_key: null
      score: 88
      saas_url: /saas/guide/<canonical_id>
    - object_type: CSI_ACCIDENT
      canonical_id: <csi_id>
      title: 용접 작업 중 화재 사고
      match_type: CONTEXT
      matched_term: task=welding
      subject_type: ACCIDENT_TERM
      subject_key: 화재
      score: 82
      saas_url: /saas/accident/<canonical_id>
    - object_type: LEGAL
      canonical_id: <leg_atom_id>
      title: 산업안전보건법 시행규칙 제XX조 (용접 관련)
      match_type: CONTEXT
      matched_term: task=welding
      subject_type: LEGAL_TERM
      subject_key: 산업안전보건법 시행규칙
      score: 80
      saas_url: /saas/legal/<canonical_id>
  external_items: []
```

Notes:

- No user `q` — `active_tiers` is empty because the keyword pipeline
  didn't run. The engine still emits `snapshot` for evidence.
- `LEGAL` result is **discovery only**. The SaaS consumer must still
  call the Legal Engine for applicability if it wants to display a
  compliance conclusion (Constitution §2).

### 8.3 PAID — diagnosis-adjacent related knowledge

Consumer intent: paid diagnosis result page wants "related
knowledge" for the concluded obligation set. Consumer sends
obligation atom ids as context.

```yaml
# request
context:
  - {context_type: legal_obligation, context_key: <obligation_atom_id_1>}
  - {context_type: legal_obligation, context_key: <obligation_atom_id_2>}
  - {context_type: sector, context_key: manufacturing}
scope: PAID
object_types: [GUIDE, SAFETY_MATERIAL, CSI_ACCIDENT, CHEM]
limit: 15
```

```yaml
# response (abbreviated)
status: success
data:
  request_context:
    - {context_type: legal_obligation, context_key: <atom_id_1>}
    - {context_type: legal_obligation, context_key: <atom_id_2>}
    - {context_type: sector, context_key: manufacturing}
  snapshot: SEARCH-DICT-LEGPROD-2026-09-16
  scope: PAID
  internal_items:
    - object_type: GUIDE
      title: ...
      match_type: CONTEXT
      matched_term: legal_obligation=<atom_id_1>
      score: 85
      saas_url: /saas/guide/<canonical_id>
    - object_type: SAFETY_MATERIAL
      title: ...
      match_type: CONTEXT
      matched_term: legal_obligation=<atom_id_1>
      score: 82
      saas_url: /saas/material/<canonical_id>
    - object_type: CHEM
      title: ...
      match_type: CONTEXT
      matched_term: legal_obligation=<atom_id_2>
      score: 78
      saas_url: /saas/chemical/<canonical_id>
    - object_type: CSI_ACCIDENT
      title: ...
      match_type: CONTEXT
      matched_term: sector=manufacturing
      score: 60
      saas_url: /saas/accident/<canonical_id>
  external_items: []
```

Notes:

- Paid consumer sends obligation atom ids from its own diagnosis
  output. The engine treats them as `context_type=legal_obligation`
  tuples; it does NOT reinterpret them.
- Result set is bounded by `visibility_scopes ⊇ {PAID}` on each
  document.

## 9. Failure contract (consumer-facing)

The Retrieval Engine (SEARCH-05) surfaces failures explicitly:

| Situation | Consumer response |
|-----------|-------------------|
| runtime projection missing (RC-A from SEARCH-01) | HTTP 503; same shape as `/search-dict/health` failure |
| invalid `object_type` filter | HTTP 400 `INVALID_OBJECT_TYPE` |
| invalid `scope` filter | HTTP 400 `INVALID_SCOPE` |
| context tuple with unknown `context_type` | HTTP 400 `INVALID_CONTEXT_TYPE` |
| no items match | HTTP 200 with `items: []` (never a 4xx) |
| external provider failure | HTTP 200 with `external_items: []` + `warnings[]` |
| projection partially reindexing | HTTP 200 from current (pre-rebuild) projection; warnings SHOULD include `rebuild_in_progress` |

No consumer failure path returns Domain data. On any failure, the
consumer resolves back to its Domain-specific fallback (which may
be nothing — that is acceptable).

## 10. Explainability + evidence for governance

Every SearchResult item is fully explainable via its `match_type`,
`matched_term`, and (when applicable) `subject_type + subject_key`.
This is a governance requirement — Constitution §8 rules out
opaque scoring. If a consumer or auditor asks "why did this item
appear?", the answer is always one of:

- "identifier / canonical exact match on `<matched_term>`"
- "search-dict subject `<subject_type>/<subject_key>` matched exactly"
- "title exact hit on `<matched_term>`"
- "approved alias / synonym `<matched_term>` for subject `<subject_key>`"
- "context tuple `<context_type>=<context_key>` matched the document"
- "FTS matched `<matched_term>` inside search_text"
- "Kiwi tokenized the query into `<matched_term>` which is a
   subject-approved token"
- "Trigram similarity `<sim>` on `<matched_term>`"

There is no `match_type=UNKNOWN` and no `LLM_INFERRED`.

## 11. Exit criteria (from WO §49)

- [x] SearchResult item shape — frozen (§2)
- [x] Envelope + snapshot + active_tiers — frozen (§2.2)
- [x] Ranking precedence — frozen (§3)
- [x] Rerank policy (no LLM) — frozen (§3.3)
- [x] Dedup contract — frozen (§4)
- [x] Match explanation contract — frozen (§5)
- [x] External discovery provider distinction — frozen (§7)
- [x] Three consumer examples (Public / SaaS / Paid) — frozen (§8)
- [x] Consumer-facing failure contract — frozen (§9)
- [x] Explainability governance — frozen (§10)
