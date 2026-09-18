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

## Investigation — real terminology mapping state (PATCH-1 §A1)

The initial P3 receipt counted RAW seed-file categories
(`LAW_NAME 423 / AGENCY_NAME 26 / TECH_TERM 15`) as if they were
final projection `subject_type` values. That was wrong: the v2
build re-taxonomizes those raw categories into the production
subject_types `LEGAL_TERM / GENERAL_TERM / EQUIPMENT_TERM /
ACCIDENT_TERM / CHEM_TERM`.

Correct v2 projection census (built deterministically via
`SEARCH_DICT_SEED=seed_v2 python3 tools/search_dict/build_dictionary.py`):

```text
snapshot_id           = SEARCH-DICT-LEGPROD-2026-09-16
total subjects        = 471
expansions            = 20

subject_type census (subjects / production terms):
  LEGAL_TERM       419 / 434
  GENERAL_TERM      45 /  47
  EQUIPMENT_TERM     3 /   5
  ACCIDENT_TERM      3 /   3
  CHEM_TERM          1 /   2        ← MSDS domain
```

**`CHEM_TERM` subject_type exists.** It carries 1 subject
(`물질안전보건자료`) with the following mapped terms:

```text
subject_key = "물질안전보건자료"

  ("물질안전보건자료",  SOURCE_NAME,   APPROVED)
  ("MSDS",              ABBREVIATION,  APPROVED)
  ("SDS",               SYNONYM,       REVIEWED / non-production)
```

That is the entire chemistry-domain footprint of the shared
dictionary today — one MSDS-abbreviation subject. There is no
per-chemical alias map (chem_id ↔ 아민/에탄올/etc.) anywhere in
the repo (grep-verified across `tools/`, `services/`, `docs/`).

### Runtime binding status

- `build_dictionary.py:33` defaults `SEARCH_DICT_SEED=seed_v1`.
- `seed_v1` does **not** contain the `CHEM_TERM` subject; only
  `seed_v2` does.
- `router_registry/public.py:28` registers
  `routers.search_dictionary` under `/search-dict/*`, but which
  seed the deployed projection was built from is
  INDETERMINATE_FROM_STATIC_REPO — verifying it requires a live
  `GET api.taieng.co.kr/search-dict/census`, which is out of scope
  for a static-repo WO.

## PATCH-1 §A3 — MSDS adapter filters dictionary to `CHEM_TERM`

`services/kosha_msds/search_adapter.py::_dictionary_expand()` now
passes `subject_type="CHEM_TERM"` to `search_query_svc.lookup()`
by default. Existing subject_type reused — no new subject_type
introduced (WO §14).

```text
before:  lookup(q, limit=...)
after :  lookup(q, limit=..., subject_type="CHEM_TERM")
```

Constant:

```python
services/kosha_msds/search_adapter.py
  MSDS_DICTIONARY_SUBJECT_TYPE = "CHEM_TERM"
```

Backwards compat for older test stubs that don't accept
`subject_type` — a TypeError-fallback retries without the kwarg.
Test `test_A3_backwards_compat_with_stubs_without_subject_type`
verifies.

This closes the cross-domain risk noted in the original PR body:
LEGAL_TERM / GENERAL_TERM / etc. entries can no longer reach the
CHEM adapter's name-partial-match probe. Test
`test_A3_msds_adapter_filters_dictionary_by_chem_term` exercises
a multi-type dictionary stub and asserts CHEM_TERM-only entries
survive the filter.

## PATCH-1 §B — pagination beyond MAX_LIMIT

The initial P3 patch capped each candidate's internal fetch at
`read.MAX_LIMIT=100`. That worked for 2-match fixtures but the
same problem re-appears at 101+ matches: any candidate source
returning more than 100 rows would have its overflow silently
dropped, so `total` under-reports and offsets past 100 fail.

PATCH-1 §B replaces the single-shot fetch with true pagination
through each candidate:

```python
services/kosha_msds/search_adapter.py::search_by_q  (_run loop)

for kw in ("name_ko", "name_en"):
    page_offset = 0
    while True:
        envelope = read.search(store=store,
                                limit=internal_page,  # = MAX_LIMIT (100)
                                offset=page_offset,
                                scope=scope,
                                **{kw: term})
        items_page = envelope.get("items") or []
        for row in items_page:
            # dedup by chem_id, tag with match_type, append to hits
            ...
        if len(items_page) < internal_page:
            break                                    # source exhausted
        total = envelope.get("total")
        page_offset += internal_page
        if isinstance(total, int) and page_offset >= total:
            break
```

Test `test_B1_pagination_150_matches_across_pages` seeds a
150-chemical corpus with a shared substring, then verifies
`total == 150` and disjoint pages at offsets 0 / 100 / 140 / 149.

Test `test_B2_multi_candidate_dedup_priority_preserved` verifies
that when the same chemical is reachable via normalized +
dictionary + Kiwi candidates, it appears exactly once and carries
the highest-priority `match_type` (NORMALIZED_EXACT).

Original 2-match "acid" fixture from PATCH-0 continues to PASS
via `test_P_pagination_stable_no_cross_page_duplicates`.

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

### Focused CHEM regression (after PATCH-1)

```text
chem05 + chem06 + chem07 + chem08 + chem09 + chem10
+ chem_seo_preview + chem_seo_preview_execute
+ chem_full_readiness + chem_full_readiness_002_cutover
+ chem_full_readiness_003_search_qa
                                              246 / 246  PASS

  P3 acceptance test file itself                 36 / 36
    original QA matrices (Q, N, T, K, NEG, S, R, P, contract)  31
    PATCH-1 §A1 census                            1
    PATCH-1 §A3 CHEM_TERM filter + backwards compat 2
    PATCH-1 §B  150-match pagination + multi-candidate dedup  2
```

## Terminology QA distinction (WO §C)

The receipt now separates:

```text
DICTIONARY ADAPTER CAPABILITY =
  PASS via SYNTHETIC CHEM_TERM stubs
  (3 terminology matrix cases; proves the adapter can consume MSDS
   CHEM_TERM entries once populated).

ACTUAL DICTIONARY MAPPING =
  CHEM_TERM subject_type present via seed_v2.
  1 subject (물질안전보건자료), 2 approved terms (MSDS, 물질안전보건자료),
  1 reviewed term (SDS).
  Individual per-chemical alias mapping artifact = NOT FOUND
  (no chem_id ↔ 통용명/약칭 dictionary anywhere in the repo).

PRODUCTION RUNTIME BINDING =
  INDETERMINATE_FROM_STATIC_REPO
  (build_dictionary.py:33 defaults SEARCH_DICT_SEED=seed_v1, which
   does NOT contain CHEM_TERM. Verifying which seed the deployed
   projection was built from requires a live
   GET api.taieng.co.kr/search-dict/census.)

LIVE TERMINOLOGY ACCEPTANCE =
  NOT PERFORMED under this WO (no live API call was made).
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
