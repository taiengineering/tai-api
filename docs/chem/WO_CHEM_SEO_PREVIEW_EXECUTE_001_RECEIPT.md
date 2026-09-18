# WO-CHEM-SEO-PREVIEW-EXECUTE-001 — Receipt (PHASE 1)

**Goal:** `G-mu6ntsiv-f191a0` (tai-api) — production executor + Supabase adapter + router registration.
**Branch:** `feat/chem-seo-preview-execute` (off `origin/main` `d85a4d45`).
**Turn scope:** PHASE 1 only — IMPLEMENT → TEST → COMMIT → PUSH → PR OPEN → STOP.
**PHASE 2 authorization:** After GPT final execution verify passes, PHASE 2 runs in the same session without additional intermediate approvals (merge → migration deploy → CHEM-05 plan → PATCH-A bridge → executor → env flip → deploy → API smoke → www smoke).

---

## 1. Design summary

Everything shipped in PR #391 already left the SEO_PREVIEW pipeline scaffolded. This WO adds the **only missing pieces** so PHASE 2 can execute a real production run:

- `services/kosha_msds/production_store.py` — Supabase adapters for both materializer and publish promoter. Method shapes mirror `MemoryMaterializeStore` / `MemoryPublishStore` so `materialize_writer.preflight()` and `publish.preflight_publish()` are called without any changes.
- `tools/chem_seo_preview/execute_production.py` — end-to-end orchestrator CLI. Runs frozen SHA verify → preview plan (via existing PATCH-A bridge) → live preflight → materialize → snapshot COMPLETED verify → publish preflight → PUBLISHED_SEO_PREVIEW promotion → post-write census.
- `router_registry/public.py` — one-line registration of `routers.kosha_public_msds`. Env default `KOSHA_MSDS_PUBLIC_MODE=off` keeps the router 503-dormant until PHASE 2 flips the env in prod.

**Module-level safety fences remain closed** — this WO does not touch either constant:

```python
services.kosha_msds.materialize_writer.PRODUCTION_WRITE_ALLOWED  = False
services.kosha_msds.publish.PRODUCTION_PUBLISH_ALLOWED           = False
```

The executor passes `wo_scope_allows_write=True` / `wo_scope_allows_publish=True` as **keyword-argument overrides at the two assert callsites** — and only when ALL CLI preconditions hold:

- `--scope seo_preview` (FULL is refused with a non-zero exit)
- `--owner-approved`  (unset → refused)
- `--execute`         (unset → refused)

If any precondition is missing the executor exits non-zero without touching the DB.

---

## 2. Fail-closed matrix

| Guard | Location | Trigger | Block reason |
| --- | --- | --- | --- |
| Scope must be SEO_PREVIEW | executor `_assert_preconditions` | `--scope full` | `SCOPE_NOT_SEO_PREVIEW` |
| Owner approval required | executor `_assert_preconditions` | `--owner-approved` absent | `OWNER_NOT_APPROVED` |
| Execute must be explicit | executor `_assert_preconditions` | `--execute` absent | `EXECUTE_NOT_REQUESTED` |
| Manifest SHA pin | executor `_verify_frozen_shas` | `--expected-seo-manifest-sha` mismatch | `EXPECTED_MANIFEST_SHA_MISMATCH` |
| Responses SHA pin | executor `_verify_frozen_shas` | `--expected-responses-sha` mismatch | `EXPECTED_RESPONSES_SHA_MISMATCH` |
| Census pin | executor `_verify_frozen_shas` | `--expected-chemical-count` / `--expected-section-count` mismatch | `EXPECTED_CENSUS_MISMATCH` |
| CHEM-05 plan integrity | bridge (`SHA256(plan)` vs `manifest.plan_file_sha256`) | on-disk tamper | `SOURCE_PLAN_FILE_SHA_MISMATCH` |
| CHEM-05 semantic integrity | bridge | manifest / report SHA disagree | `SOURCE_PLAN_SEMANTIC_SHA_MISMATCH` |
| Materialize preflight | writer `preflight(publication_scope=SEO_PREVIEW)` | any `block_reasons` | `MATERIALIZE_PREFLIGHT_BLOCKED` (publish path unreached) |
| Materialize write fence | writer `assert_can_execute_production_write(wo_scope_allows_write=True)` | fence still False | `MATERIALIZE_WRITE_FAILED` |
| Snapshot COMPLETED verify | executor step 5 | re-read status ≠ COMPLETED | `SNAPSHOT_NOT_COMPLETED_POST_MATERIALIZE` |
| Publish preflight | promoter `preflight_publish(scope=SEO_PREVIEW, seo_preview_expected_*, expected_materialize_binding)` | census / binding mismatch | `PUBLISH_PREFLIGHT_BLOCKED` |
| Publish fence | promoter `assert_can_execute_publish(wo_scope_allows_publish=True)` | fence still False | `PROMOTION_FAILED` |
| Target state guard | `promote_to_state` only accepts `PUBLISHED_FULL` or `PUBLISHED_SEO_PREVIEW` | anything else | `ValueError` |
| **PUBLISHED_FULL mutation** | test asserts spy on `promote_to_state` calls | never | 0 |

---

## 3. Changed files

| File | Change |
| --- | --- |
| `services/kosha_msds/production_store.py` | **new** — `SupabaseMaterializeStore` + `SupabasePublishStore` |
| `tools/chem_seo_preview/execute_production.py` | **new** — SEO_PREVIEW end-to-end executor CLI |
| `router_registry/public.py` | +1 line `{"module": "routers.kosha_public_msds"}` |
| `tests/test_chem_seo_preview_execute.py` | **new** — 13 tests (all fail-closed guards + positive round-trip + FULL-mutation-never) |
| `tests/test_chem07_public_router.py` | flip stale WO-CHEM-07 assertion `not in` → `in` (registry now populated by this WO) |
| `tests/test_chem09_search_adapter.py` | flip stale WO-CHEM-09 assertion `not in` → `in` |
| `tests/test_chem10_publish_promoter.py` | flip stale WO-CHEM-10 assertion `not in` → `in` |
| `.github/workflows/ci.yml` | +1 CI step `test_chem_seo_preview_execute.py` |
| `docs/chem/WO_CHEM_SEO_PREVIEW_EXECUTE_001_RECEIPT.md` | **new** — this file |

Not touched:
- `tools/chem08/materialize_production.py` — unchanged (guarded fixture CLI stays as-is)
- `tools/chem10/publish_snapshot.py` — unchanged
- `services/kosha_msds/materialize_writer.py` / `publish.py` — unchanged (fences stay `False`)
- `supabase/migrations/*` — unchanged
- Any tai-www file — unchanged
- CHEM-04 hydration artifact — untouched

---

## 4. Test evidence

```
python3 -m pytest \
    tests/test_chem05_materialize.py \
    tests/test_chem06_read_service.py \
    tests/test_chem07_public_router.py \
    tests/test_chem08_materializer.py \
    tests/test_chem09_search_adapter.py \
    tests/test_chem10_publish_promoter.py \
    tests/test_chem_seo_preview.py \
    tests/test_chem_seo_preview_execute.py \
    -q --tb=line
```

Result: **171 passed** (13 new executor + 31 preview + 127 CHEM-05..10 regression).

---

## 5. PHASE 2 runbook (executes only after GPT PASS)

After GPT final execution verify, run in-session:

1. **Merge** — `gh pr merge <PR#> --squash --delete-branch`.

2. **Migration deploy** — apply `supabase/migrations/20260918_kosha_msds_seo_preview.sql` to production Supabase. Sanity-check with `SELECT constraint_name FROM information_schema.check_constraints WHERE constraint_name = 'kosha_msds_snapshots_publish_state_check';` and `SELECT viewname FROM pg_views WHERE viewname = 'kosha_msds_seo_preview_current';`.

3. **CHEM-05 plan** —
   ```
   python -m tools.chem05.build_materialize_plan \
     --responses artifacts/chem04/official_v12/responses.jsonl \
     --out-dir artifacts/chem05/
   ```

4. **PATCH-A bridge** —
   ```
   python -m tools.chem_seo_preview.build_preview_plan \
     --chem05-plan-jsonl artifacts/chem05/materialize_plan.jsonl \
     --chem05-manifest   artifacts/chem05/materialize_manifest.json \
     --chem05-report     artifacts/chem05/materialize_report.json \
     --seo-manifest      docs/chem/seo-preview-manifest.json \
     --out-dir           artifacts/chem_seo_preview/
   ```
   Expected: `execute_eligible=true`, `chemicals=1997`, `sections=31952`.

5. **Production executor** —
   ```
   SUPABASE_URL=... SUPABASE_SERVICE_KEY=... \
   python -m tools.chem_seo_preview.execute_production \
     --scope seo_preview --owner-approved --execute \
     --seo-manifest        docs/chem/seo-preview-manifest.json \
     --chem05-plan-jsonl   artifacts/chem05/materialize_plan.jsonl \
     --chem05-manifest     artifacts/chem05/materialize_manifest.json \
     --chem05-report       artifacts/chem05/materialize_report.json \
     --snapshot-id         seo-preview-<yyyy-mm-dd> \
     --expected-seo-manifest-sha f696a212fd9fd04659b7b75accd4c13fc539a1a71a663fb2a80599b9c255638d \
     --expected-responses-sha    49994a2a8d44b5c2acfae60283d5f2f76fd65e0af5842a10db43383e26b643dd \
     --expected-chemical-count 1997 \
     --expected-section-count  31952
   ```
   Expected JSON: `snapshot_status_after_materialize = COMPLETED`, `publish_state_after_promote = PUBLISHED_SEO_PREVIEW`, `materialized_chemicals = 1997`, `materialized_sections = 31952`.

6. **Env flag flip** — set `KOSHA_MSDS_PUBLIC_MODE=seo_preview` on the tai-api runtime.

7. **API deploy** — deploy tai-api at the merged HEAD.

8. **API smoke** —
   - `GET /public/kosha/msds` → 200 with 1997 total
   - `GET /public/kosha/msds?q=메탄올` → 200
   - `GET /public/kosha/msds/{preview_chem_id}` → 200 with 16 sections
   - `GET /public/kosha/msds/{preview_chem_id}/sections/1` → 200
   - `GET /public/kosha/msds/432377` → 404 (excluded partial)

9. **Website smoke** —
   - `https://taieng.co.kr/msds` — SSR list + canonical + JSON-LD
   - `https://taieng.co.kr/msds?q=메탄올` — SSR results, `noindex,follow`
   - `https://taieng.co.kr/msds/{real_chem_id}` — SSR detail, 16 sections in initial HTML, KOSHA attribution present

**STOP conditions during PHASE 2:** SHA mismatch, census ≠ 1997/31952, DB conflict, materialize failure, publish preflight failure, PUBLISHED_FULL mutation observed, deploy failure, live API failure. Any of these → STOP + report.

---

## 6. Frozen preview evidence (unchanged from PR #391 PATCH-1)

```
SEO PREVIEW CHEMICALS = 1,997
SEO PREVIEW SECTIONS  = 31,952
EXCLUDED               = chemId 432377 (9/16 partial)
MANIFEST SHA256 =        f696a212fd9fd04659b7b75accd4c13fc539a1a71a663fb2a80599b9c255638d
RESPONSES SHA256 =       49994a2a8d44b5c2acfae60283d5f2f76fd65e0af5842a10db43383e26b643dd
```

---

## 7. WO §24 final block

```
WO-CHEM-SEO-PREVIEW-EXECUTE-001 PHASE 1

PR =                            <post-push>
HEAD =                          <post-commit>
changed files =                 9 (2 new modules, 1 new tests, 3 test flips, 1 registry, 1 CI, 1 receipt)
CI =                            <post-push>

production executor =           tools/chem_seo_preview/execute_production.py
Supabase adapter =              services/kosha_msds/production_store.py
                                  · SupabaseMaterializeStore
                                  · SupabasePublishStore
router registration =           router_registry/public.py +1 line
                                  routers.kosha_public_msds  (dormant until KOSHA_MSDS_PUBLIC_MODE set)

FULL blocked =                  --scope full → SCOPE_NOT_SEO_PREVIEW (executor refuses at CLI-parse time)
owner gate =                    --owner-approved absent → OWNER_NOT_APPROVED
preview binding =               snapshot.metrics_json { publication_scope, seo_preview_manifest_sha256,
                                                        responses_sha256, seo_preview_expected_* }
                                bound at bridge output; CHEM-10 preflight_publish verifies via
                                expected_materialize_binding.

PRODUCTION DB WRITE   = 0 (fence still False; executor passes override at callsite only)
PRODUCTION PUBLISH    = 0 (fence still False; executor passes override at callsite only)
ROUTER ACTIVATION     = 0 (registered but env default off → 503 MSDS_PUBLIC_DORMANT)
MIGRATION DEPLOY      = 0
KOSHA_MSDS_PUBLIC_MODE = unchanged (still `off` in production env)
tai-www change        = 0
CHEM-04 resume        = 0

READY FOR GPT FINAL EXECUTION VERIFY
```

STOP.

PHASE 2 does not run until GPT PASS.
