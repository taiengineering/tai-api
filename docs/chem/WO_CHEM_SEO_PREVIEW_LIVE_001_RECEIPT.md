# WO-CHEM-SEO-PREVIEW-LIVE-001 — Receipt

**Goal:** `G-mu6k1c3v-f191a0` (tai-api) — 1,997 complete MSDS temporary SEO preview.
**Branch:** `feat/chem-seo-preview-live-001` (off `origin/main` `7bd7aaf4`).
**Turn scope:** IMPLEMENT → TEST → COMMIT → PUSH → PR OPEN. **No production DB write, no publish, no router activation** (WO §23).
**Verdict target:** READY FOR GPT DELTA VERIFY.

---

## 1. Design summary

Additive, dual-view model. `kosha_msds_current` (PUBLISHED_FULL only) is untouched. A new sibling view `kosha_msds_seo_preview_current` filters on `publish_state = 'PUBLISHED_SEO_PREVIEW'`. The read service, search adapter, and dormant public router all thread a keyword-only `scope` (or env-driven `mode`) parameter through — defaults preserve existing FULL-only behavior. CHEM-08 materializer and CHEM-10 publish promoter gain a `publication_scope` parameter; both `PRODUCTION_WRITE_ALLOWED` and `PRODUCTION_PUBLISH_ALLOWED` fences remain `False` this turn.

```
Publication flow (future execution WO — NOT this turn):
                             ┌─ FULL scope ─→ PUBLISHED_FULL ──→ kosha_msds_current
CHEM-08 materialize (plan) ──┤
                             └─ SEO_PREVIEW ──→ PUBLISHED_SEO_PREVIEW ──→ kosha_msds_seo_preview_current
                                    (bound by docs/chem/seo-preview-manifest.json SHA256)

Public router at request time (this turn — code is ready, dormant by default):
  env KOSHA_MSDS_PUBLIC_MODE = off   → 503 MSDS_PUBLIC_DORMANT
                              = seo_preview → serves kosha_msds_seo_preview_current
                              = full        → serves kosha_msds_current
```

---

## 2. Census (WO §22)

Verified against `/Users/taiwangsim/Desktop/tai-api-obj-chem/artifacts/chem04/official_v12/responses.jsonl`:

| Metric                       | Expected  | Measured  |
| ---------------------------- | --------- | --------- |
| source responses             | 31,961    | **31,961** |
| unique chemicals             | 1,998     | **1,998** |
| complete chemicals (16/16)   | 1,997     | **1,997** |
| preview sections (1997×16)   | 31,952    | **31,952** |
| excluded chemicals           | 1         | **1** |
| excluded chem_ids            | ["432377"]| **["432377"]** |
| authoritative_verified_bad   | 0         | **0** |
| result_code non-success      | 0         | **0** |

Manifest binding:
- `manifest_sha256 = 58b52db4bb1d620162a2e498268defecdc3e50b95cd638cade7d64297bb92154`
- `responses_sha256 = 49994a2a8d44b5c2acfae60283d5f2f76fd65e0af5842a10db43383e26b643dd`
- Manifest deterministic — `--check` reproduces the same SHA256 from the same artifact bytes.

---

## 3. Canonical / full contract invariants (WO §2)

- `kosha_msds_current` view: **unchanged bytes** — same JOIN, same WHERE predicate (`publish_state = 'PUBLISHED_FULL'`). Grep verifies.
- `PUBLISH_PUBLISHED_FULL` constant: **unchanged value** — still `"PUBLISHED_FULL"`.
- `FULL_OFFICIAL_CHEMICAL_COUNT = 20568` / `FULL_OFFICIAL_SECTION_COUNT = 329088`: unchanged.
- Full-mode expected counts in `preflight_publish`: unchanged (via `_resolve_expected_counts(FULL, ...)` returns the original constants).
- CHEM-10 `assert_can_execute_publish` three gates: unchanged behavior in FULL mode.
- `enumeration_mode` trigger: unchanged. Preview snapshots still declare `FULL_OFFICIAL` (the source hydration is FULL_OFFICIAL; only the *publication* is preview).
- New canonical table: **0**.
- New search engine / Kiwi / terminology dictionary: **0**.

---

## 4. Changed files

| File | Change |
|------|--------|
| `services/kosha_msds/contract.py` | +publish_state `PUBLISHED_SEO_PREVIEW`, +scope constants, +public-mode constants, +`SEO_PREVIEW_MANIFEST_PATH` |
| `services/kosha_msds/read.py` | +`PREVIEW_VIEW`, +`_view_for_scope`, +`scope` kw on Memory + Supabase store methods, +`scope` param on `get_by_chem_id / get_section / list_current / search` (default FULL) |
| `services/kosha_msds/search_adapter.py` | +`scope` kw on `search_by_q`, pass-through to `read.search` and `read.list_current` |
| `services/kosha_msds/materialize_writer.py` | +`publication_scope` kw on `preflight` (default FULL). Additive validation; existing behavior preserved |
| `services/kosha_msds/publish.py` | +`target_publish_state()`, +`_resolve_expected_counts()`, +`publication_scope` + `seo_preview_expected_*` kwargs on `preflight_publish`, +scope-aware `latest_published_snapshot`, +`promote_to_state` |
| `routers/kosha_public_msds.py` | +env `KOSHA_MSDS_PUBLIC_MODE`, +`_read_mode / _mode_to_scope / _require_active_mode`, threads scope into read/search |
| `supabase/migrations/20260918_kosha_msds_seo_preview.sql` | **new** — extend publish_state CHECK, add pair-check, create `kosha_msds_seo_preview_current` view + grants |
| `tools/chem_seo_preview/__init__.py` | **new** — package marker |
| `tools/chem_seo_preview/build_manifest.py` | **new** — deterministic manifest builder + `--check` verify |
| `docs/chem/seo-preview-manifest.json` | **new** — 1,997-chemical manifest (262 KB, self-SHA256 signed) |
| `tests/test_chem_seo_preview.py` | **new** — P1–P12 + regression guards + manifest census assertions (19 tests) |
| `tests/test_chem07_public_router.py` | fixture: `KOSHA_MSDS_PUBLIC_MODE=full` (existing tests target FULL; minimum churn to keep them green after the mode gate was added) |
| `tests/test_chem09_search_adapter.py` | same fixture adjustment |
| `.github/workflows/ci.yml` | +one CI step for `test_chem_seo_preview.py` |
| `docs/chem/WO_CHEM_SEO_PREVIEW_LIVE_001_RECEIPT.md` | **new** — this file |

Not touched (per WO §20 forbidden list):
- No new canonical table / writer / read service / search engine
- No `kosha_safety_materials` coupling
- No hydration checkpoint / artifact mutation
- No CHEM-05~10 rewrite (only additive kwargs)
- No quota probe
- No unrelated refactor
- No tai-www change (frontend already shipped in the prior WO)

---

## 5. Read layer semantics (WO §9)

Single code path, two views, no duplication:

- `get_by_chem_id(chem_id, *, store, include_sections=True, scope=None)` — defaults to FULL; SEO_PREVIEW hits the preview view.
- `get_section(chem_id, section_no, *, store, scope=None)` — same. Membership is enforced via the scoped view lookup *before* section reads, so a partial section row cannot leak (WO §5 "부분 section 노출 금지").
- `list_current(*, store, limit, offset, scope=None)` — sorted by `chem_id ASC` in both scopes.
- `search(*, store, ..., scope=None)` — filter search is scoped.

Store implementations:

- `MemoryMsdsReadStore(preview_rows=..., current_rows=..., sections=...)` — sections are shared across scopes; membership picks the correct view.
- `SupabaseMsdsReadStore` — every read chooses the view via `_view_for_scope(scope)` (`kosha_msds_current` or `kosha_msds_seo_preview_current`).

---

## 6. Search semantics (WO §10)

CHEM-09 `search_by_q` is the ONE search entry point (no per-scope duplication):

1. Identifier detection first (chem_id / cas_no / ke_no / en_no / un_no). If matched → exact filter via scoped read.
2. Normalized-query exact (Korean-normalized full string).
3. Terminology-dictionary expansion (shared `services.search_query_svc.lookup`, best-effort).
4. Kiwi morphology tokens (shared `services.safe_help_kiwi.tokens`, graceful fallback).

Every candidate is dispatched through `read.search(scope=…)` so results are always constrained to the scoped membership. Preview mode CANNOT leak a full-only chemical even if a Kiwi token would otherwise match.

Match-type tags unchanged: `IDENTIFIER_EXACT`, `NORMALIZED_EXACT`, `DICTIONARY_EXPANSION`, `KIWI_TOKEN`.

---

## 7. Public router / mode flag (WO §11–§12)

- Prefix unchanged: `/public/kosha/msds`
- Not registered in `router_registry/public.py` (this turn does not activate).
- Env var `KOSHA_MSDS_PUBLIC_MODE` (documented in `contract.PUBLIC_MODE_ENV_VAR`):
  - `off` (default) — every endpoint responds 503 with `MSDS_PUBLIC_DORMANT`
  - `seo_preview` — serves the 1,997-chemical preview slice
  - `full` — serves the PUBLISHED_FULL catalog
- Unknown / misspelled value falls back to `off` (fail-safe).
- Membership enforcement: a chem_id outside the active mode's view returns 404 (WO §11 "preview membership 밖의 chem_id는 customer-facing으로 노출하지 않는다").

---

## 8. SEO contract (WO §14, §15)

Frontend (tai-www PR #124, merged) already serves:

- `/msds` list/search SSR with meta + JSON-LD
- `/msds/{chem_id}` detail SSR with H1 + identifiers + 16 sections + JSON-LD in initial HTML (JS-off)
- `/msds?q=...` `robots=noindex,follow`, canonical `/msds`
- `/msds/{chem_id}` `robots=index,follow`, canonical `/msds/{chem_id}`

This WO opens the enumeration source that the SEO stream needs:

```
MSDS_DETAIL_URL_CONTRACT      = /msds/{chem_id}
SEO_GENERATOR_INPUT_SOURCE    = docs/chem/seo-preview-manifest.json → 1,997 chem_ids
```

The SEO stream owns sitemap generation (WO §15) and can pick up the manifest without further backend work.

---

## 9. Rollback semantics (WO §17, §18)

- Preview publication is **additive** to `kosha_msds_snapshots.publish_state` (new value only).
- `kosha_msds_current` view is untouched → FULL rollout later supersedes preview URLs automatically because both views expose the same `/msds/{chem_id}` canonical.
- URL contract stable: `/msds/{chem_id}` unchanged before and after FULL. SEO equity accrued during preview survives full rollout.
- Rollback path: `KOSHA_MSDS_PUBLIC_MODE=off` collapses the router to 503 without any code change.
- No `PUBLISHED_FULL` state is ever set by this WO's code paths.

---

## 10. Load-bearing safety fences (this turn)

| Fence | Location | State |
| --- | --- | --- |
| `PRODUCTION_WRITE_ALLOWED` | `services/kosha_msds/materialize_writer.py:61` | **False** (unchanged) |
| `PRODUCTION_PUBLISH_ALLOWED` | `services/kosha_msds/publish.py:35` | **False** (unchanged) |
| Public router registration in `router_registry/public.py` | (absent) | **not registered** (unchanged) |
| Default `KOSHA_MSDS_PUBLIC_MODE` | env unset | **off → 503** |
| Detail-status trigger `enumeration_mode` immutability | migration line 103 | **unchanged** |

A future WO must (in order):
1. Deploy the migration `20260918_kosha_msds_seo_preview.sql` to production.
2. Flip `PRODUCTION_WRITE_ALLOWED = True` in a scope-limited PR and run CHEM-08 with `publication_scope=SEO_PREVIEW`, feeding the plan from the manifest above.
3. Flip `PRODUCTION_PUBLISH_ALLOWED = True` and run CHEM-10 with `publication_scope=SEO_PREVIEW`, `seo_preview_expected_chemical_count=1997`, `seo_preview_expected_section_count=31952`, `expected_materialize_binding={"seo_preview_manifest_sha256": "58b52db4bb1d620162a2e498268defecdc3e50b95cd638cade7d64297bb92154"}`.
4. Set `KOSHA_MSDS_PUBLIC_MODE=seo_preview` in the API deployment env.
5. Register `routers/kosha_public_msds.router` in `router_registry/public.py`.

This turn provides ALL scaffolding for steps 2–5 without executing any of them.

---

## 11. Tests

Local run (`python3 -m pytest tests/test_chem06_read_service.py tests/test_chem07_public_router.py tests/test_chem08_materializer.py tests/test_chem09_search_adapter.py tests/test_chem10_publish_promoter.py tests/test_chem_seo_preview.py -q --tb=short`):

```
129 passed in 8.70s
```

- CHEM-06 read service: 27/27 (unchanged behavior)
- CHEM-07 public router: 20/20 (with fixture `KOSHA_MSDS_PUBLIC_MODE=full`)
- CHEM-08 materializer: 23/23 (additive kwarg backward-compatible)
- CHEM-09 search adapter: 25/25 (with fixture `KOSHA_MSDS_PUBLIC_MODE=full`)
- CHEM-10 publish promoter: 25/25 (additive kwargs backward-compatible)
- SEO preview (this WO): 19/19 covering P1–P12 + regression guards

---

## 12. WO §24 final report

```
WO-CHEM-SEO-PREVIEW-LIVE-001

BASE
API MAIN =                   7bd7aaf4
WWW MAIN =                   73344248 (unchanged — tai-www PR #124 already merged)

PREVIEW DESIGN
membership implementation =  view (kosha_msds_seo_preview_current, sibling of kosha_msds_current)
publication semantic =       publish_state = 'PUBLISHED_SEO_PREVIEW' (additive enum)
feature flag / mode =        env KOSHA_MSDS_PUBLIC_MODE ∈ {off, seo_preview, full}

CENSUS
source responses =           31,961
complete chemicals =         1,997
preview chemicals =          1,997
preview sections =           31,952
excluded chemicals =         1
excluded chem_ids =          ["432377"]
manifest sha256 =            58b52db4bb1d620162a2e498268defecdc3e50b95cd638cade7d64297bb92154
responses sha256 =           49994a2a8d44b5c2acfae60283d5f2f76fd65e0af5842a10db43383e26b643dd

CANONICAL
new canonical table =        0
canonical identity changed = 0
existing writer reused =     yes (materialize_writer.preflight; +publication_scope kw only)
existing read service reused = yes (get_by_chem_id / get_section / list_current / search; +scope kw)
existing search reused =     yes (search_by_q; +scope kw)

FULL CONTRACT
PUBLISHED_FULL changed =     0
full eligibility weakened =  0
CHEM-10 full path changed =  additive only (publication_scope=FULL default preserves existing 20,568/329,088 gates)

ROUTER
existing router reused =     yes (routers/kosha_public_msds.py; no new router)
activation behavior =        dormant (not in router_registry; env flag default off; 503 MSDS_PUBLIC_DORMANT)

SEO
detail indexable =           yes (frontend contract in tai-www #124: index,follow + canonical + JSON-LD)
query noindex =              yes (frontend contract: /msds?q=… → noindex,follow, canonical /msds)
canonical stable =           /msds/{chem_id} unchanged across preview and future FULL rollouts
enumeration available =      docs/chem/seo-preview-manifest.json (1,997 chem_ids, deterministic SHA256)

TEST
test command =               pytest tests/test_chem_seo_preview.py -q --tb=short
result =                     19/19 PASS  (+110/110 regression across CHEM-06..10)

CHANGED FILES =
  services/kosha_msds/contract.py
  services/kosha_msds/read.py
  services/kosha_msds/search_adapter.py
  services/kosha_msds/materialize_writer.py
  services/kosha_msds/publish.py
  routers/kosha_public_msds.py
  supabase/migrations/20260918_kosha_msds_seo_preview.sql          (new)
  tools/chem_seo_preview/__init__.py                                (new)
  tools/chem_seo_preview/build_manifest.py                          (new)
  docs/chem/seo-preview-manifest.json                               (new, 262 KB)
  tests/test_chem_seo_preview.py                                    (new, 19 tests)
  tests/test_chem07_public_router.py                                (fixture: set KOSHA_MSDS_PUBLIC_MODE=full)
  tests/test_chem09_search_adapter.py                               (fixture: set KOSHA_MSDS_PUBLIC_MODE=full)
  .github/workflows/ci.yml                                          (+1 step for test_chem_seo_preview.py)
  docs/chem/WO_CHEM_SEO_PREVIEW_LIVE_001_RECEIPT.md                 (new — this file)

COMMIT =                     <post-commit SHA>
PR =                         <post-push PR #>
HEAD =                       feat/chem-seo-preview-live-001
CI =                         pending (queued on push)

PRODUCTION DB WRITE =        0
PRODUCTION PUBLISH =         0
LIVE ROUTER ACTIVATION =     0

FINAL STATUS =               READY FOR GPT DELTA VERIFY
```

STOP.

GPT 검증 전 merge 하지 않는다.
