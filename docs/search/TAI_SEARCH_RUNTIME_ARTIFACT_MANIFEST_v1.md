# TAI Search Runtime Artifact Manifest v1

**WO**: WO-TAI-SHARED-SEARCH-001
**Root cause**: RC-A — runtime projection artifact was not generated
or packaged. Production `TAI_SEARCH_PROJECTION` env is UNSET; the
service falls back to `<repo>/tools/search_dict/artifacts/TAI_SEARCH_RUNTIME_PROJECTION_v1.json`
but the file is not tracked in git and no build/deploy step produces
it. `services.search_query_svc._get_projection()` raises
`SearchDictError` → `routers.search_dictionary` returns HTTP 503.
**Remediation**: Case B — attach the deterministic build to the
image-build pipeline. Zero DB / schema / env changes.

## Source inputs (git-tracked, immutable)

| Path | SHA256 (server-parity `\n`-joined, no trailing newline) |
|------|----------------------------------------------------------|
| `tools/search_dict/extract/GROUND_TRUTH_464.tsv` | `9cf9d73cb35a8884164dd999ff8aa10b59e0098c96e3a940205f801825fea178` |
| `tools/search_dict/extract/LAW_ALIAS_15.tsv` | `e3006ed67d4b93f435419ce47288aced44bcb3bdb97e97e3308bc31780cbabbe` |

File-level SHA256 (byte-for-byte, for `sha256sum -c`):

| Path | SHA256 |
|------|--------|
| `tools/search_dict/extract/GROUND_TRUTH_464.tsv` | `d70e26b9de9f928c5cda175d02d0393680c68efc7b3d327951e26f54622a195c` |
| `tools/search_dict/extract/LAW_ALIAS_15.tsv` | `e40ead56af3c7b93a845ec534cd6c511cadae07b84e6caa18ce3b116f9a3a2ab` |

## Compiler (git-tracked, stdlib-only)

- `tools/search_dict/build_dictionary.py` — deterministic compiler
- `tools/search_dict/seed_v2.py` — canonical production seed module
- `tools/search_dict/normalize.py` — shared build+runtime normalization
- `SEARCH_DICT_SEED` env var must equal `seed_v2` for the production build

## Build outputs (regenerated at image build time)

| File | Purpose | Runtime dep? | Expected SHA256 |
|------|---------|--------------|-----------------|
| `TAI_SEARCH_RUNTIME_PROJECTION_v1.json` | Deterministic tiers (T1-T3) projection | **Required** (else /search-dict = 503) | `4c1c7bb9bceafd8ccd700b2c130060d32776dbec1f7523f8ece0aeaf9f6677e1` |
| `TAI_KIWI_USER_DICTIONARY_v1.txt` | Kiwi T4 user dictionary | Optional (T4 = graceful degradation if missing) | `780213e9eaf5fe3f5741aae01b06a3609fcd693632ded26753e1b4715bb4c469` |
| `TAI_KIWI_TERMS_v1.tsv` | Kiwi terms table (T4 evidence) | Optional (build-time artifact) | `20e48580904e769a1d1473673459de39c2cd6e4a91979534cea17df6101a07e6` |
| `TAI_TERM_MASTER_v1.tsv` | Term master (offline verification) | Not runtime | `a906b95aa66a014601978ade18a1f1ef541c0cb96727070cfec1b6c66082d422` |
| `TAI_TERM_RELATIONS_v1.tsv` | Term relations table (offline verification) | Not runtime | `2395054b487303ac455f66fc6f753fdf93e97b442463a61dc490558a4349b444` |

Only the first two files are copied into the runtime tree.
BUILD_SHA256SUMS.txt on disk is preserved (it carries commentary +
extract-input SHAs that the raw build does not emit).

## Runtime identity (baked into the projection)

- `snapshot_id`   = `SEARCH-DICT-LEGPROD-2026-09-16`
- `snapshot_date` = `2026-09-16`
- `subjects`      = `471`
- `expansions`    = `20`
- `indexed_terms` = `491` (reported via `/search-dict/health`)

## Runtime bindings

| Env var | Resolved from | Value in production (post-fix) | Notes |
|---------|---------------|-------------------------------|-------|
| `TAI_SEARCH_PROJECTION` | `services/search_query_svc.py:25-32` | UNSET → default `<repo>/tools/search_dict/artifacts/TAI_SEARCH_RUNTIME_PROJECTION_v1.json` | Path resolution unchanged; the fix ensures the default path exists. |
| `TAI_SEARCH_KIWI_DICT` | `services/search_query_svc.py:33-40` | UNSET → default `<repo>/tools/search_dict/artifacts/TAI_KIWI_USER_DICTIONARY_v1.txt` | Path resolution unchanged; the fix ensures the file exists. Optional at runtime. |
| `TAI_SEARCH_SCRATCH_DSN` | `services/search_query_svc.py:41` | UNSET → T6 disabled | Optional; unchanged by this WO. |

## Build + deploy contract

The Dockerfile runs the deterministic build after `COPY . .`:

```dockerfile
RUN python3 scripts/build_search_dict_runtime.py \
        --outdir tools/search_dict/artifacts \
        --tmpdir /tmp/tai-search-dict-build \
        --seed   seed_v2
```

`scripts/build_search_dict_runtime.py`:

1. runs `tools/search_dict/build_dictionary.py build /tmp/tai-search-dict-build`,
2. compares the two runtime files' SHA256 against `BUILD_SHA256SUMS.txt`,
3. copies exactly `TAI_SEARCH_RUNTIME_PROJECTION_v1.json` +
   `TAI_KIWI_USER_DICTIONARY_v1.txt` into `tools/search_dict/artifacts/`,
4. leaves `BUILD_SHA256SUMS.txt` untouched,
5. aborts the image build (non-zero exit) if the SHA drift is detected.

Any snapshot bump requires regenerating and re-pinning this manifest.

## Verification (deterministic, hermetic)

Local:

```bash
python3 scripts/build_search_dict_runtime.py \
    --outdir /tmp/verify-outdir \
    --tmpdir /tmp/tai-search-dict-build \
    --seed   seed_v2

# quick service-level check
TAI_SEARCH_PROJECTION=/tmp/verify-outdir/TAI_SEARCH_RUNTIME_PROJECTION_v1.json \
TAI_SEARCH_KIWI_DICT=/tmp/verify-outdir/TAI_KIWI_USER_DICTIONARY_v1.txt \
python3 -c '
from services import search_query_svc
h = search_query_svc.health()
assert h["snapshot"] == "SEARCH-DICT-LEGPROD-2026-09-16"
assert h["subjects"] == 471
assert h["token_tier"] is True
r = search_query_svc.lookup("MSDS", limit=3, subject_type="CHEM_TERM")
hit = next(i for i in r["items"] if i["subject_key"] == "물질안전보건자료")
assert hit["match_type"] == "EXACT"
print("OK")
'
```

Production smoke (after deploy of Dockerfile change):

```text
GET /search-dict/health
  →  status_code == 200
  →  data.snapshot == SEARCH-DICT-LEGPROD-2026-09-16
  →  data.subjects == 471
  →  data.token_tier == true

GET /search-dict/lookup?q=MSDS&subject_type=CHEM_TERM
  →  status_code == 200
  →  items[*].subject_key contains "물질안전보건자료" with match_type=EXACT

GET /search-dict/lookup?q=산업안전보건법
  →  status_code == 200
```

## Optional tiers (unchanged)

- **T4 Kiwi**: available when `kiwipiepy` is importable (it is — pinned
  in `requirements.txt:41-42`) AND the Kiwi user dictionary exists. The
  Docker build produces both. Verified locally: `token_tier=True`.
  Failure remains graceful — `TokenTier` init wrapped in
  `try/except → False sentinel`; deterministic tiers continue serving.
- **T6 Trigram**: enabled only when `TAI_SEARCH_SCRATCH_DSN` is set.
  UNSET in production; `trigram_tier=false` and `/search-dict/health`
  still returns HTTP 200.

Neither optional tier can cause an HTTP 503.

## Stop conditions

Abort deploy / open incident if any of:

- `snapshot_id` != `SEARCH-DICT-LEGPROD-2026-09-16`
- `subjects` != 471 or `expansions` != 20
- `TAI_SEARCH_RUNTIME_PROJECTION_v1.json` SHA drifts from `4c1c7bb9…5677e1`
- `TAI_KIWI_USER_DICTIONARY_v1.txt` SHA drifts from `780213e9…b4c469`
- `/search-dict/health` returns non-200 after the fix

Any drift means either a source-input change or a compiler regression;
both are Owner-approval material and out of scope for SEARCH-01.
