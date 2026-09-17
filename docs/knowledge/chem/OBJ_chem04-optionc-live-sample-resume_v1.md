---
class: records
type: report
scope: knowledge
project: chem
title: WO-CHEM-04-OPTIONC-RESUME-001 Option-C live sample resume evidence
version: 1
status: active
owner: taiwang
---

# WO-CHEM-04-OPTIONC-RESUME-001 — PR #359 Rebase + Quota Preflight + Frozen Option-C Live Sample (Resume)

## Scope

```text
DELTA ONLY
NO PRODUCTION INGEST
NO FULL HYDRATION
NO DB WRITE
NO CANONICAL MUTATION
NO NEW SEMANTIC POLICY
MERGE = NOT AUTHORIZED
```

Existing CHEM-02/03/04 identity + PR #359 local-audit numbers reused
verbatim. See:

```text
PR #344 = CHEM-02 catalog/schema/adapter        MERGED
PR #346 = CHEM-03 enumeration/quota research    MERGED
PR #348 = CHEM-ENUM-GATE-01                     MERGED
PR #350 = CHEM-04 official current census       MERGED
PR #359 = CHEM-04 content local audit           OPEN (this WO)
```

Frozen numbers not reverified:

```text
official current chemId = 20,568
secondary identity rows = 48,963
official ∩ secondary    = 18,478
SECONDARY_COMPLETE      =  9,124
SECONDARY_PARTIAL       =  9,354
SECONDARY_MISSING       =  2,090
STRICT_API_CALLS        = 329,088
STRUCTURAL_DELTA_CALLS  =  51,940
```

## Anchors

```text
main HEAD               = 82744667ff06b6b4ce70cb5a094526b14bf8f203
PR                      = #359
branch                  = feature/chem04-content-local-audit
PR HEAD (post-rebase)   = 1ceb069f267694cdb80dbff65cad88fb8e55ea9f
```

## STEP A — Rebase result

```text
rebase                  = PASS
strategy                = origin/main precedence for unrelated;
                           preserve PR #359 CHEM-04 delta
conflict files          = .github/workflows/ci.yml (resolved: kept
                           both current-main pipeline and PR #359
                           CHEM-04 test step)
changed-file scope      = allowed only  (services/kosha_msds/,
                           tools/chem04/, tests/test_chem04_*,
                           tests/fixtures/kosha_msds/,
                           docs/knowledge/chem/, .github/workflows/ci.yml,
                           .gitignore)
mergeable               = DIRTY / CONFLICTING → MERGEABLE / UNSTABLE  (post-rebase)
```

## STEP B — Quota preflight (WO §8)

```text
target chemId           = 001008
target section          = Detail01
service key source      = env only (LIVE_SAMPLE_KEY_ENV)
HTTP status             = 200
resultCode              = 00
fetch_error             = null
official_fetch          = OK
preflight verdict       = PASS

preflight_report SHA    = e2b92dafd5fb8195200d3ff863410facb85a045ed15d518375a00da1aedf6527
```

No 429. No resultCode=22. Quota not blocked today.

## STEP C — Frozen Option-C live sample (WO §9-§11)

Deterministic frozen manifest — 16 chemIds × 16 Detail endpoints
= 256 planned calls. Hard cap = 320.

```text
sample_manifest_sha256  = b404725ade87b289e124abcca0652e91ec4bace1f5094d79f251860035af2351
MANIFEST_MATCH          = PASS

attempted_api_calls     = 256
successful_api_calls    = 256
http_requests           = 257  (256 sample + 1 preflight)
hard cap                = 320
API_ERROR               = 0
quota_stop              = false
http_429                = 0
resultCode_22           = 0
error_token_counts      = {}   (no retryable/quota tokens)
```

### Section-level census

```text
EXACT                   = 227
NORMALIZED_EQUAL        =   0
CONTENT_DIFFERENT       =  29
SECONDARY_MISSING       =   0
OFFICIAL_EMPTY          =   0
SECONDARY_EMPTY         =   0

comparable sections     = 256
section fidelity        =  88.67%   (227 / 256)
```

### Chemical-level

```text
chemical ALL_MATCH          =  3
chemical HAS_DIFFERENCE     = 13
chemical HAS_EMPTY_CONFLICT =  0
chemical UNVERIFIED         =  0
chemical all-match pct      = 18.75%
```

### CONTENT_DIFFERENT distribution

```text
by chemId (top):
  134944 = 11    001846 = 3    007764 = 3    000003 = 3
  000001,000004,000005,000010,000043,000178,001008,013842,014097 = 1 each

by section:
  section 11 (독성정보)   = 12   ← dominant
  section 16              =  4
  section 2, 15           =  2 each
  section 4-10, 13, 14    =  1 each

possible_cause          = {"UNKNOWN": 29}
difference_causes       = {"UNKNOWN": 29}
```

The tool did not auto-classify any diff cause — every
CONTENT_DIFFERENT has GPT-review-ready evidence (see the raw diff
excerpts under `artifacts/chem04/decision/comparison.jsonl` and
`artifacts/chem04/decision/live_raw/`, both gitignored).

## Sample-run notes (transparency)

A first sample run on this session resumed from a stale checkpoint
written 2026-09-14 (before commit `8a2085e1` added the
`fetch_error` field). The stale checkpoint's `done` set caused the
new run to skip every fetch and report 256 API_ERROR rows without
error tokens. Stale artifacts under `artifacts/chem04/decision/`
(gitignored) were removed and the sample was re-run cleanly. Only
the CLEAN run is authoritative and its SHAs are captured here.

## Frozen output SHAs

```text
sample_manifest SHA (canonical, WO)  = b404725ade87b289e124abcca0652e91ec4bace1f5094d79f251860035af2351
preflight report SHA                 = e2b92dafd5fb8195200d3ff863410facb85a045ed15d518375a00da1aedf6527
comparison.jsonl SHA                 = e723c8ae9350f7acb7e66465f454e8633e03c253f4537b24e82785f494aa8b7e
live_sample_report canonical SHA     = 3bc3117e6fd66e57b03433cdc6086367f8d92dc9c37dd4fd1fe4344f2a09f930
live_sample_report file SHA          = 148f5b48bf18ba45b75233c3f73c37402771ea83738511fc4874551e58e90975
```

Local artifacts remain gitignored under `artifacts/chem04/decision/`.

## Governance state

```text
TECHNICAL_OPTION_C_GATE          = PENDING_GPT  (tool-emitted)
BOOTSTRAP POLICY                 = NOT DECIDED
OPTION_B_auto_approve            = NO
production_writer                = null
live_bulk_hydration              = NO
production_ingest                = NO
sample_checkpoint_written        = true (gitignored)
```

## Verdict

```text
WO-CHEM-04-OPTIONC-RESUME-001    = PASS / GPT_POLICY_REVIEW_READY

STEP A rebase                    = PASS
STEP B quota preflight           = PASS
STEP C 256-call sample           = COMPLETE

frozen CHEM evidence reverified  = NO
identity recensus                = NO
local full audit rerun           = NO

PRODUCTION INGEST                = 0
DB WRITE                         = 0
FULL HYDRATION                   = 0
CANONICAL MUTATION               = 0
BOOTSTRAP POLICY                 = NOT DECIDED
PR #359                          = OPEN / UNMERGED / MERGEABLE

NEXT = GPT DELTA-ONLY VERIFY → GPT OPTION A/C POLICY DECISION
STOP
```
