# TAI / EXT-071 precedent source — EXT-036 integration decision (2026-10-11 KST)

Status: GPT independent source assessment; DESIGN DECISION ONLY; no collector, API call, or production mutation authorized.

## Decision

- EXT-071 / `INDUSTRIAL_ACCIDENT_PRECEDENT` uses Ministry of Government Legislation DRF `target=prec`; classify as **EXT-036 law.go.kr substream (prec)**, not a new independent non-law P0 bootstrap.
- Keep existing `industrial_accident_precedents` 849 records and `precedent_rule_links` 2,497 links unchanged; avoid duplicate law source collection or second canonical precedent SoT.
- Defer collection until source-key overlap, role/permissions, update contract, and approved LEG-to-search read boundary are verified.
- Continue *non-law P0* with EXT-085 KOSHA SIF dataset 15161362, separately scoped; no relation to EXT-036 collection job.

## Directly verified evidence (read-only, 2026-10-11)

1. Supabase project `vwlahtguyggrhvslabax`, table `industrial_accident_precedents`: 849 active/total records, all `source=law_go_kr` and collected 2026-04-26; 849 distinct `case_number` and 849 distinct `prec_seq`, 0 blanks.
2. `precedent_rule_links`: 2,497 links, all 849 precedents linked, 448 distinct rule IDs; 2,139 `violation` and 358 `ref_article` links.
3. Source registry `services/public_data_sync/registry.py`: `INDUSTRIAL_ACCIDENT_PRECEDENT` is labelled `provider=SUPABASE_EDGE`, `adapter_key=industrial_accident_precedent`, `INCREMENTAL`, `WEEKLY`. DB `public_data_source_runtime` source is `is_enabled=false`, no recorded run; **metadata does not prove functioning consumer/collector**.
4. In `services/public_data_sync/adapters/__init__.py`, builtin adapter registration **does not register** `industrial_accident_precedent`; there is no same-name adapter file in `main` tree. The registry alone does not provide a runnable weekly pipeline.
5. The deployed Supabase Edge Function `collect-precedents` (ACTIVE v6, queried with `get_edge_function`) fetches law.go.kr `target=prec`, with eight keywords times at most two pages, 10 results per page, and **writes to `posts`** as `source=law_go_kr_prec`, not to `industrial_accident_precedents`; matching `posts` count is 3. Do not treat the Edge Function as the legacy 849-record collector. `verify_jwt=false` is set; handler conditionally checks `TAI_COLLECT_SECRET` only when configured—verify authorization before any use, without disclosing secrets.
6. `docs/precedent-collection-20260426.md` and `scripts/collect_precedents_matched.py` document the legacy Mac allowlisted-IP collection via `lawSearch.do` (`search=3`), `lawService.do`, and Railway `/precedents/save-matched`, matching to master law reference articles. Historic documentation reports Edge/Railway law.go.kr access denied due to IP restrictions; current runtime access has **not** been probed.
7. Precedent case types confirmed: civil 349, administrative 328, criminal 163, tax 9; sector labels BUILDING 770, CONSTRUCTION 64, INDUSTRIAL 11, SPECIAL_FACILITY 4. These are corpus classification tags, not proof of relevance or applicability.
8. Old 849 records all have `full_text`; `summary` nonblank 511; `violation_laws_raw` nonblank 634. Remaining relevance/publication rights need review.

## Required downstream EXT-036 steps (READ ONLY until Owner approval)

A. Compare existing `prec_seq` keys with scoped official `prec` list/detail and all approved Knowledge/Search documents, without assuming global provider count is net-new safety content.
B. Create a single source-identity crosswalk (`prec_seq` primary, `case_number` descriptive; source metadata, effective/publication date), mapping to existing 849 records and 2,497 approved rule references.
C. Decide how `EXT-036` read-only related-case adapter references existing `industrial_accident_precedents` and Shared Search canonical `SearchDocument`, avoiding duplicate `posts` ingestion and unauthorized LEG rule judgment.
D. Independently verify official API use conditions, current law.go.kr access IP/OC, detail fields, rights, required privileges. No auto publication.
E. Never run old `collect-precedents` Edge Function as a shortcut; inspect handler security first.

## Explicit exclusions

`PRODUCTION_DB_WRITE=0`, `LIVE_API_CALL=0`, `AUTO_REFRESH=OFF`, `NEW_COLLECTOR=0`, `MERGE=NOT_AUTHORIZED`, `DEPLOY=0`, `LEG_ENGINE_CHANGE=0`.

## References

- https://github.com/taiengineering/tai-api/blob/main/docs/precedent-collection-20260426.md
- https://github.com/taiengineering/tai-api/blob/main/scripts/collect_precedents_matched.py
- https://github.com/taiengineering/tai-api/blob/main/services/public_data_sync/registry.py
- https://github.com/taiengineering/tai-api/blob/main/services/public_data_sync/adapters/__init__.py
- Supabase live read-only queries of `industrial_accident_precedents`, `precedent_rule_links`, `posts`, `public_data_source_runtime`, and retrieved Edge Function `collect-precedents` source.

NEXT: EXT036_PREC_SERVICE_CONTRACT_VERIFY; non-law P0: EXT085_SIF_SOURCE_PREFLIGHT.
