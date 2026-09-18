---
class: records
type: report
scope: knowledge
project: chem
title: WO-CHEM-09-KIWI-SEARCH-INTEGRATION-001 receipt
version: 1
status: active
owner: taiwang
---

# WO-CHEM-09-KIWI-SEARCH-INTEGRATION-001 — MSDS Search Integrated with Shared Kiwi / Terminology Dictionary

## Summary

Thin CHEM search adapter that composes the repo's **existing** shared
search assets (Kiwi tokenizer + normalization + terminology dictionary)
and delegates to CHEM-06's canonical read service. No new search
engine, no new Kiwi implementation, no new dictionary, no DB mutation.
The dormant router (CHEM-07) gains a `q` query parameter but stays
unregistered.

## Anchors

```text
main at run                = b72fd8e42747e2eb90e31338e1044868040fe6e8
branch                     = feature/chem09-kiwi-search-integration
```

## Existing assets discovered (WO §3)

Discovery via `grep -rEln "kiwipiepy|kiwi|search_dict|terminology|synonym"`.
Case §4-A: **shared common search modules already exist**. No new
engine is needed; only a thin CHEM adapter.

```text
Kiwi tokenizer
  services/safe_help_kiwi.py
    tokens(text)         Kiwi-based tokenizer with kiwipiepy-optional
                          graceful fallback to regex; production
                          endpoint used by /help/*.

Shared dictionary + tiered search
  tools/search_dict/normalize.py            deterministic normalization
                                             (nfc, normalize_basic, compact,
                                              latin_lower, no_punctuation,
                                              term_id, relation_id)
  tools/search_dict/search_core.py          SearchEngine with tiers:
                                             T1 EXACT, T2 NORMALIZED_EXACT,
                                             T2b PUNCTUATION, T3 ALIAS/SYNONYM
  tools/search_dict/search_runtime_ext.py   TokenTier (T4 Kiwi) +
                                             TrigramTier (T6 pg_trgm)
  services/search_query_svc.py              orchestrator that composes
                                             T1..T4/T6 into a single
                                             lookup(q, limit, subject_type)
  services/search_dictionary_svc.py         dictionary metadata/census
  routers/search_dictionary.py              /search-dict/{lookup,health,census}
                                             (registered in router_registry)

Kiwipiepy version installed              0.23.1
```

## Reuse decision

```text
REUSED
  tools/search_dict/normalize    -> query normalization identical to
                                     the shared dictionary
  services/safe_help_kiwi        -> Kiwi tokenization (with fallback)
  services/search_query_svc      -> OPTIONAL terminology-dictionary
                                     expansion (fail-open)

NEW CODE (minimum-viable adapter)
  services/kosha_msds/search_adapter.py     ~250 lines
    build_search_plan()   normalize + identifier detection + Kiwi
                          + optional dictionary expansion
    search_by_q()         plan-based dispatch into CHEM-06 read.search
    SearchPlan            deterministic snapshot of a query's derived
                          tokens/expansions for debugging + metadata

  routers/kosha_public_msds.py
    + q query parameter that delegates to search_by_q when non-empty.
    Structured filters, list_current, get_by_chem_id, get_section
    are unchanged. Router remains dormant / unregistered.
```

## Kiwi role (WO §14)

```text
- 형태소 분석 for free-text natural-language queries
- 조사/어미 제거 via Kiwi tag whitelist (NNG NNP NNB SL SH SN NR NP VV VA XR)
- 띄어쓰기 영향 완화 (identical fallback under kiwipiepy absence)
- LLM query parsing = 0
```

Identifiers (`chem_id`, `cas_no`, `ke_no`, `en_no`, `un_no`) are
detected FIRST and bypass Kiwi entirely (§8). Test 10 verifies this.

## Dictionary role (WO §12/§13)

```text
- preferred term / synonym / alias / abbreviation / domain term
  expansion via services.search_query_svc.lookup(q, limit)
- adapter never mutates canonical DB rows
- fail-open: dictionary lookup exceptions return [] silently and the
  adapter continues with Kiwi tokens only (test 25)
```

## Search dispatch (priority)

```text
1. IDENTIFIER_EXACT     (chem_id / CAS / KE / EN / UN)
2. NORMALIZED_EXACT     (full-query name-KO or name-EN match)
3. DICTIONARY_EXPANSION (synonyms/aliases returned by search_query_svc)
4. KIWI_TOKEN           (per-token name-KO or name-EN candidates)
```

Every response item carries `match_type` + `matched_term` for
explainability. The envelope also carries `match_metadata`
`{normalized_query, compact_query, identifier_kind, tokens,
expanded_terms}` for downstream UI/debug (WO §17).

## CHEM-06 read service — untouched

The adapter delegates every read to `services.kosha_msds.read.*`. It
does not shape rows, does not recompute hashes, does not join tables.
Response envelope preserves CHEM-06's identity + provenance verbatim;
new keys (`match_type`, `matched_term`, `match_metadata`) are additive.

## Router (dormant)

`routers/kosha_public_msds.py` gains a `q` query parameter under the
existing `/public/kosha/msds` endpoint. Precedence:

```text
q present            -> search_by_q  (CHEM-09 adapter -> CHEM-06 read.search)
structured filter    -> CHEM-06 read.search
neither              -> CHEM-06 read.list_current
```

`router_registry/public.py` is unchanged. Verified by test 18
(`routers.kosha_public_msds` is NOT in the registered module list).

## Governance boundaries verified

```text
NEW SEARCH ENGINE                     = 0
NEW KIWI IMPLEMENTATION               = 0
NEW TERMINOLOGY DICTIONARY            = 0
NEW MIGRATION                         = 0
NEW SEARCH INFRA (ES/OpenSearch/etc.) = 0  (test 14 grep-verifies)
LLM SEARCH                            = 0  (test 13 grep-verifies)

CANONICAL IDENTITY MUTATION           = 0
DB WRITE                              = 0
KOSHA API CALL                        = 0
HYDRATION RESUME                      = 0
HYDRATION ARTIFACT MUTATION           = 0

ROUTER REGISTRATION                   = 0  (test 18)
LIVE ROUTE                            = 0
CUSTOMER PUBLICATION                  = 0
CROSS-DOMAIN COUPLING                 = 0  (test 22 grep-verifies
                                             kosha_safety_materials
                                             is not referenced)
```

Reuse guards:

```text
test 23  tools.search_dict.normalize is imported (not re-implemented);
         no local `def normalize_basic` / `def compact` in the adapter.
test 24  services.safe_help_kiwi is imported (not re-implemented);
         no direct kiwipiepy import statements in the adapter.
```

## Tests

```text
tests/test_chem09_search_adapter.py     25 / 25  PASS  (1.34s)

  §25 items 1..18 individually covered:
    01 chem_id exact
    02 CAS exact
    03 Korean canonical exact
    04 English canonical exact
    05 Korean partial
    06 whitespace-normalized Korean
    07 Kiwi morphology query
    08 dictionary synonym query
    09 abbreviation / alias via dictionary
    10 identifier bypasses morphological tokenization
    11 canonical identity unchanged
    12 synonym expansion does not mutate DB
    13 no LLM search dependency
    14 no new search-engine dependency
    15 deterministic ordering
    16 empty query handling
    17 no-result handling
    18 dormant router remains unregistered

  Extra:
    19  router `q` param delegates to adapter
    20  `q` wins over structured filters when both present
    21  no `q` and no filters preserves CHEM-06 list_current behavior
    22  no services/kosha_safety_materials reference in adapter or router
    23  tools.search_dict.normalize is imported (not forked)
    24  services.safe_help_kiwi is imported (not forked; no direct kiwipiepy)
    25  dictionary_lookup failure is silent (fail-open)

Focused CHEM-05..09 regression          102 / 102 PASS
```

## Frontend integration (out of scope for this WO)

`tai-www` search UI is a separate future WO (CHEM-11 per revised
numbering below). This WO only completes the `tai-api` search
contract.

## Revised WO sequencing (WO §30)

```text
CHEM-09  Kiwi / terminology-dictionary search integration    (this WO)
CHEM-10  Publish promoter                                    (deferred)
CHEM-11  Frontend search integration in tai-www              (deferred)
CHEM-12  Router activation (adds routers.kosha_public_msds
         to router_registry/public.py)                       (deferred)
```

Numbering may change once CHEM-04 hydration completes and downstream
gates are exercised.

## Verdict

```text
WO-CHEM-09-KIWI-SEARCH-INTEGRATION-001 = PASS / KIWI_SEARCH_READY

Adapter is code-complete and fixture-validated. Router stays
dormant. Zero customer exposure until CHEM-12 activation.

NEXT  =  GPT delta-only verify
         -> CHEM-04 hydration remains armed / hold pending quota reset
         -> CHEM-10 publish promoter (separate future WO)
         -> CHEM-11 tai-www search integration (separate future WO)
STOP
```
