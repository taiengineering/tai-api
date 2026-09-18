---
class: records
type: report
scope: knowledge
project: chem
title: WO-CHEM-FULL-READINESS-003 receipt
version: 1
status: active
owner: taiwang
---

# WO-CHEM-FULL-READINESS-003 — Search / Terminology Acceptance QA

## Summary

Fixture-based acceptance for the full CHEM search chain:

```text
raw query
  → normalize
  → identifier detection
  → terminology expansion
  → Kiwi tokens
  → CHEM-06 scoped canonical read
```

Terminology mapping is treated as frozen. QA measured identifier /
name / terminology / Kiwi / negative matrices against a
production-shape dictionary stub and a preview-shape memory corpus,
plus scope isolation and ranking priority.

One acceptance failure was found (pagination aggregation cap in
`search_adapter.search_by_q`), and one minimal patch was applied
per WO §14. No canonical mutation, no dictionary remapping, no new
engine, no schema change.

## Anchors

```text
main at run                 = 49a9dac614ebf20be0f894fbe225bf77dfd7bf07
branch                      = work/chem-full-readiness-003-search-qa
```

## Investigation — current terminology mapping state

Source data committed at `tools/search_dict/extract/`:

```text
GROUND_TRUTH_464.tsv    subject_type counts:
  LAW_NAME     423   (statute names)
  AGENCY_NAME   26   (government agencies)
  TECH_TERM     15   (technical terms)

LAW_ALIAS_15.tsv        law short-name → canonical statute alias table.
```

Runtime projection artifact
`tools/search_dict/artifacts/TAI_SEARCH_RUNTIME_PROJECTION_v1.json`
is gitignored (built by `tools/search_dict/build_dictionary.py`).
In this repo's default state it is absent, so
`services.search_query_svc.lookup()` raises "runtime projection not
found"; CHEM-09's `_dictionary_expand()` catches this and returns
[] (fail-open).

```text
MSDS terminology subject_type =  0
MSDS mapped subjects          =  0
MSDS mapped terms             =  0
MSDS synonyms / aliases       =  0
```

MSDS-specific terminology has **not yet** been added to the shared
dictionary. All QA against MSDS synonyms in this WO uses a
SYNTHETIC stub dictionary explicitly labeled `MSDS_SYNONYM`, which
never touches the production build.

### Cross-domain risk under production deployment

When the runtime projection JSON is deployed to production, the
current adapter passes NO `subject_type` filter to
`services.search_query_svc.lookup()`. That means LAW_NAME /
AGENCY_NAME / TECH_TERM entries would be returned as candidate
expansions for chemical queries. The QA test
`test_NEG_law_and_agency_queries_do_not_leak_chemicals` proves the
current DB-side probe is the effective isolation gate: even if a
law term is returned by `lookup()`, the follow-up `read.search()`
against `chemical_name_ko` / `chemical_name_en` returns 0 rows for
that term (no chemical is named after a statute). The risk
therefore materializes only if a chemical name happens to contain
a legal term substring — currently unobserved in the 1,997-row
preview corpus.

**Recommendation (deferred to a future WO):** when MSDS-specific
terminology is added to the shared dictionary, thread a
`subject_type=<MSDS constant>` filter through the CHEM adapter's
`_dictionary_expand()`. That thin plumb is out of scope here
because no MSDS subject_type exists yet to filter against, and WO
§14 forbids new subject_type creation.

## Patch applied — minimal (WO §14)

One correctness bug found during QA and patched.

**Bug**: `services/kosha_msds/search_adapter.py::search_by_q()`
passed `limit=lim` (the caller's requested page size) to each
internal `read.search()` candidate query. For a caller who asks
for `limit=1` on a query that matches multiple chemicals via
`name_en` substring (e.g., "acid" → both "Sulfuric acid" and
"Nitric acid"), the aggregator would see only 1 candidate per
source, so `total` was under-reported and `offset=1` returned
empty even though a second match existed.

**Patch**: use `MAX_LIMIT` (100, from `services.kosha_msds.read`)
as the internal per-candidate fetch, and apply the caller's
`limit / offset` at aggregation time. This is a 4-line change; no
new dependency, no new type, no new module.

```text
services/kosha_msds/search_adapter.py
  before:  envelope = read.search(store=store, limit=lim, offset=0, scope=scope, **{kw: term})
  after :  internal_limit = read.MAX_LIMIT   # bounded, already the CHEM-06 clamp
           envelope = read.search(store=store, limit=internal_limit,
                                   offset=0, scope=scope, **{kw: term})
```

`test_P_pagination_stable_no_cross_page_duplicates` PASS with
`limit=1` on "acid" — page 0 and page 1 are disjoint and total is
2. Existing CHEM-09 tests (25) still all PASS.

## Acceptance matrix — results

```text
tests/test_chem_full_readiness_003_search_qa.py    31 / 31  PASS  (1.5s)

  Q  Identifier matrix (4 cases + 1 EN-pattern miss)
     chem_id 001008         → IDENTIFIER_EXACT / no Kiwi / no expansion
     CAS 71-43-2            → IDENTIFIER_EXACT
     KE-01008               → IDENTIFIER_EXACT
     UN-1203                → IDENTIFIER_EXACT
     EN-98765               → IDENTIFIER_EN detected, 0 hits, no Kiwi

  N  Name matrix (7 cases)
     "벤젠" / "Benzene" / "BENZENE" / "benzene" / "  벤젠  "
       → NORMALIZED_EXACT hit
     "메탄" / "Meth"        → substring partial hit

  T  Terminology matrix — SYNTHETIC MSDS dict (3 cases)
     "메틸알코올" → 메탄올      via DICTIONARY_EXPANSION
     "가성소다"   → 수산화나트륨
     "황산나트륨" → 황산

  K  Kiwi matrix (3 cases)
     natural-language phrase generates Kiwi tokens
     NORMALIZED_EXACT wins over KIWI_TOKEN when both apply
     KIWI_TOKEN fires for "질산 처리" (no exact/dict match)

  NEG  Cross-domain isolation (6 cases)
     "산안법" / "고압가스법" / "고용부" / "GHS"  → 0 chemicals
     "존재하지않는화학물질명"                    → 0 chemicals
     "휘"                                        → only 휘발유 (1 hit)

  S  Scope isolation (1 case; test skipped when `scope` param
     is not yet threaded through `search_by_q`)

  R  Ranking priority (2 cases)
     normalized-exact beats dictionary and Kiwi
     same chemical from multiple candidates ≡ single response entry

  P  Pagination (1 case)
     limit=1, offset=0 → chem 055555 (Sulfuric acid)
     limit=1, offset=1 → chem 099999 (Nitric acid)
     total=2 across both pages; disjoint chem_id sets

  Contract safety
     acceptance_summary_snapshot: prints WO §13 metrics
     no_canonical_mutation_after_search: byte-identical corpus
                                          after all queries
     no_new_search_engine_or_llm_dependency_in_adapter
```

### Acceptance metrics (WO §13)

```text
total_test_queries                = 20    (positive + negative)
  identifier_queries              = 4     (Q1..Q4)
  name_queries                    = 6     (N1..N6)
  terminology_queries             = 3     (T1..T3, synthetic MSDS dict)
  kiwi_queries                    = 2     (K1..K2)
  negative_queries                = 5     (NEG: 산안법 / 고압가스법 /
                                            고용부 / GHS / 존재하지않는화학물질명)

correct target hit                = 15 / 15  positive
wrong target                      = 0
no_hit                            = 0
cross_domain_false_positive       = 0

identifier_accuracy               = 4 / 4      = 100.0%
terminology_hit_rate              = 3 / 3      = 100.0%   (synthetic MSDS dict)
negative_precision                = 5 / 5      = 100.0%   (0 leakage)
```

Note the terminology hit rate is measured against a synthetic MSDS
dictionary stub — it demonstrates the adapter's CAPABILITY to
handle MSDS terms once they're added, not that any exist today.

### Focused CHEM regression

```text
chem05 + chem06 + chem07 + chem08 + chem09 + chem10
+ chem_seo_preview + chem_seo_preview_execute
+ chem_full_readiness + chem_full_readiness_002_cutover
+ chem_full_readiness_003_search_qa
                                              241 / 241  PASS
```

## Governance

```text
PRODUCTION DB WRITE               = 0
PRODUCTION PUBLISH                = 0
PUBLISHED_SEO_PREVIEW mutation    = 0
PUBLISHED_FULL mutation           = 0
RAILWAY ENV CHANGE                = 0
DEPLOY                            = 0
KOSHA API CALL                    = 0
CHEM-04 hydration                 = 0

SCHEMA CHANGE                     = 0
NEW MIGRATION                     = 0
NEW ENGINE                        = 0
NEW ROUTER                        = 0
NEW SEARCH IMPLEMENTATION         = 0
NEW LLM DEPENDENCY                = 0

DICTIONARY REMAPPING              = 0
NEW SUBJECT_TYPE                  = 0
KIWI CHANGE                       = 0
CANONICAL IDENTITY MUTATION       = 0
```

## Verdict

```text
WO-CHEM-FULL-READINESS-003 = PASS / READY FOR GPT DELTA VERIFY

Cross-domain isolation holds at the current corpus size (0 false
positives across 5 negative queries).
Identifier / name / terminology / Kiwi matrices all correct.
Pagination bug caught during QA and patched minimally (per WO §14).
Terminology dictionary is unchanged; no new subject_type; no MSDS
mapping introduced.

NEXT  =  GPT delta-only verify
         → P4 ops observability (next)
         → P5 full acceptance harness
         → CHEM-04 hydration continues in Track H (unblocking nothing here)
STOP
```
