---
class: records
type: report
scope: knowledge
project: chem
title: OBJ-CHEM-02 catalog schema adapter contract tests
version: 1
status: active
owner: taiwang
---

# OBJ-CHEM-02 — Catalog Schema + Source Adapter + Contract Tests

```text
CHEM-02 = IN_PROGRESS (PATCH-1 on PR #344, not merged, not production-applied)
FULL PRODUCTION INGEST = BLOCKED
reason = CORPUS_ENUMERATION + PRODUCTION_QUOTA
CHEM-03 = NOT OPEN
```

## Report card

```text
branch = feat/obj-chem-02
base SHA = fe2632dd71bdcc4ec606c880df1516c8f58f3a09
PATCH-1 parent = 6956fa8241605d85c846ae540e1a37dc5c8014a9
production migration applied = NO
production chemical rows written = 0
Graph mutation = 0
Legal mutation = 0
R2 mutation = 0
live probe performed = YES
live chemId = 001008
16-section result = COMPLETE (16/16 resultCode=00)
live re-probe this PATCH = NO (local /tmp/obj-chem01 evidence reused for section 04)
```

Parent of this HEAD is CHEM-01 SHA `501a583e`. Extra commit on main (`#343`) is crane DESIGN ONLY docs.

---

## Existing `/kosha/msds` audit = FOUND

Do **not** treat this route as the catalog SoT. CHEM-02 did not modify it.

| layer | result | path |
|---|---|---|
| router | FOUND | `routers/kosha_apis.py` `APIRouter(prefix="/kosha")` |
| list | FOUND | `GET /kosha/msds` params `chem_nm`→`chemNm`, `cas_no`→`casNo` |
| detail | FOUND | `GET /kosha/msds/{kmc_no}/detail` sends `{kmcNo}` |
| sections map | FOUND | `GET /kosha/msds/sections` |
| registry | FOUND | `router_registry/external.py` → `routers.kosha_apis` |
| catalog client | NOT_FOUND (before CHEM-02) | new `services/kosha_msds/` |
| tests targeting MSDS contract | NOT_FOUND (before) | new `tests/test_kosha_msds_catalog.py` |
| frontend caller in tai-api | NOT_FOUND | no TS/JS caller |
| tai-www live UI caller | NOT_FOUND | only historical docs mention `GET /kosha/msds` |

Official contract used by the new client:

```text
searchCnd / searchWrd / pageNo / numOfRows / chemId
```

---

## Files

```text
services/kosha_msds/contract.py
services/kosha_msds/parse.py
services/kosha_msds/identity.py
services/kosha_msds/hash.py
services/kosha_msds/snapshot.py
services/kosha_msds/client.py
services/kosha_msds/__init__.py
supabase/migrations/20260914_kosha_msds_catalog.sql
tests/test_kosha_msds_catalog.py
tests/fixtures/kosha_msds/*
docs/knowledge/chem/OBJ_chem02-catalog-schema-adapter-contract_v1.md
```

Not changed: `routers/kosha_apis.py`, `services/knowledge_graph_rules.py`, factory/Legal/CSI/Graph tables.

---

## Schema (not applied)

Tables:

```text
kosha_msds_chemicals
kosha_msds_sections
kosha_msds_snapshots
kosha_msds_snapshot_items
view kosha_msds_current
```

Constraints (selected):

```text
source_id = KOSHA_MSDS
UNIQUE (source_id, source_key)     -- chemId
UNIQUE (content_id)                -- CHEM:<uuid>
chem_id NOT NULL
source_key = chem_id
cas_no NULLABLE                    -- no UNIQUE(cas_no)
section_no BETWEEN 1 AND 16
UNIQUE (chemical_id, section_no)
PUBLISHED_FULL only if FULL_OFFICIAL AND COMPLETED
enumeration_mode immutable after INSERT (BEFORE UPDATE trigger)
sections.chem_id removed; identity = chemical_id JOIN
snapshot_items.source_key removed; identity = chemical_id JOIN
```

Indexes: chemicals chem_id / cas_no / identity_status, snapshot status. Child identity is parent `chemical_id` only.

RLS enabled, no public policies, service_role SELECT/INSERT/UPDATE, DELETE revoked. Current view SELECT-only for service_role.

`kosha_msds_current` requires `COMPLETED + FULL_OFFICIAL + PUBLISHED_FULL`. CHEM-02 cannot create that, so **global current rows = 0** after apply (when authorized).

Raw XML is not stored. `payload_json` is the lossless normalized item array. `fetched_at` is a column, excluded from `source_content_hash`.

---

## Client / completeness

`KoshaMsdsClient.search` / `get_detail_section` / `get_full_detail`

- timeout 30s (tests use 9s)
- max_attempts 3 (transport 5xx / timeout)
- serviceKey redacted in errors/URLs
- HTTP 200 insufficient; `resultCode=00` required
- unknown section rejected
- empty section with `00` = `EMPTY_BUT_VALID`
- any of 16 section failures = `INCOMPLETE`

Search returns `candidates[]`. No first-row auto identity.

---

## Live probe (001008 only)

```text
searchCnd=1 searchWrd=71-43-2 → totalCount=1 chemId=001008
getChemDetail01-16 → COMPLETE
item counts = 8,11,4,5,3,3,2,11,21,4,26,12,2,8,20,6
live hash = 1d8f28d1084aa3b74497d100e4d2476e668589ba3996d80da8a1096e83ce55c0
```

Matches CHEM-01 benzene detail row counts. No extra corpus exploration.

## PATCH-1 fixture / hash provenance

`benzene_detail_04.xml` is reconstructed from local CHEM-01 probe evidence (`getChemDetail04` / `chemId=001008`, 5 items). It is not a live re-probe. `serviceKey` is not stored.

`empty_success_section.xml` is the synthetic `resultCode=00` empty-items fixture. `EMPTY_BUT_VALID` tests use that file only.

```text
fixture-based benzene hash =
4e71b781f7966b40f1eed24ac7409ce395a9808c45491c4bee83f85a91f2d393
live handoff hash =
1d8f28d1084aa3b74497d100e4d2476e668589ba3996d80da8a1096e83ce55c0
match = NO
```

Cause: remaining `benzene_detail_01..16` fixtures are truncated contract samples, not the full live 16-section payload. After PATCH-1, section 04 matches live row count (5). Other sections still differ:

```text
fixture row counts = 3,3,3,5,0,0,0,1,0,0,0,0,0,0,2,1
live row counts    = 8,11,4,5,3,3,2,11,21,4,26,12,2,8,20,6
```

Hash is not forced to match. Replacing all 16 fixtures with live XML is out of PATCH-1 scope.

---

## Tests

```text
python3 -m pytest tests/test_kosha_msds_catalog.py
```

Cover search params/pagination/XML/totalCount/0-results/substring, identity (chemId, CAS NULL, CAS not PK, duplicate names), detail 16/16 + 15/16 + benzene section04=5 + synthetic empty-valid + resultCode + malformed XML + timeout, hash stability, PROBE cannot FULL_OFFICIAL / cannot publish current, enumeration_mode immutable SQL guard, child identity owned by parent chemical_id, schema freeze, Graph chemical DISABLED.

CI does not call live KOSHA. Fixtures have no serviceKey. Catalog tests are included in GitHub Unit Tests.

---

## Production baseline (read-only, before and after)

```text
factory_materials      = 0
master_dangerous_goods = 49
Graph active edges     = 11776
Graph evidence         = 11776
chemical Graph edges   = 0
```

---

## STOP

```text
production migration apply = NO
full/partial corpus publish = NO
public chemical API = NO
WWW chemical pages = NO
factory-material linking = NO
Graph chemical enable = NO
Legal Engine linkage = NO
OBJ-RISK = NOT STARTED
FULL INGEST = BLOCKED
```

GPT reviews this code/schema/tests before CHEM-03.
