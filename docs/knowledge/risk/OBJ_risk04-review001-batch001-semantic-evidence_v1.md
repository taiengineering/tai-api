---
class: records
type: report
scope: knowledge
project: risk
title: OBJ-RISK-04 REVIEW-001 Batch 001 semantic evidence pack
version: 1
status: active
owner: taiwang
---

# OBJ-RISK-04-REVIEW-001 — Batch 001 Semantic Review Evidence Pack

This WO adds source context for GPT/Owner semantic review of frozen Batch 001. Cursor does not fill `KEEP_AS_DISTINCT` / `MERGE_CANDIDATE` / `HOLD` / `REJECT`. Those values remain `PENDING`.

```text
WO-RISK-04                 = REVIEW_READY / TECHNICAL PASS
RISK-04                    = IN REVIEW
PR                         = #366
previous HEAD              = 78a4140ae92b7ba8e2041f05f499da9028601bb0
MERGE                      = NOT AUTHORIZED
RISK-04-APPROVE-001        = NOT OPENED
WO-RISK-04-REVIEW-001      = EVIDENCE_READY
SEMANTIC DECISIONS         = 0 / 100
OWNER REVIEW               = PENDING
SYSTEMIC_KIND_RULE_ISSUE   = PENDING GPT
```

---

## Review target

```text
path     = docs/knowledge/risk/RISK04_BATCH001.tsv
count    = 100
PROCESS  = 50
TASK     = 50
HOLD     = 50
REVIEW_READY = 50
CIC_W    = 50
KALIS    = 50
KOSHA    = 0
```

KOSHA 0 is the frozen Batch 001 composition. This WO does not add KOSHA rows.

---

## Frozen batch SHA

```text
Batch SHA = 955b3c11f092b657b54d3d94f639270f767da4156c6a3710663deeeabbb4c4b8
FROZEN BATCH = PASS
proposal keys missing = 0
proposal keys extra   = 0
proposal keys duplicate = 0
order unchanged
file content unchanged
```

---

## Worksheet SHA

```text
REVIEW INPUT = docs/knowledge/risk/RISK04_BATCH001_REVIEW_INPUT.tsv
REVIEW INPUT SHA =
c28fa67368ff3af3d05f7b771cebca455c6cf5cd94884bbff44dd1bd5087df1b
RUN1 SHA =
c28fa67368ff3af3d05f7b771cebca455c6cf5cd94884bbff44dd1bd5087df1b
RUN2 SHA =
c28fa67368ff3af3d05f7b771cebca455c6cf5cd94884bbff44dd1bd5087df1b
DETERMINISM = PASS
```

Owner columns on every row:

```text
owner_decision        = PENDING
merge_candidate_keys  = EMPTY
owner_reason          = EMPTY
KEEP_AS_DISTINCT      = 0
MERGE_CANDIDATE       = 0
HOLD                  = 0
REJECT                = 0
```

`KEEP_AS_DISTINCT ≠ APPROVED canonical`. Cursor did not write those decisions.

---

## PROCESS / TASK / source counts

```text
PROCESS = 50
TASK    = 50
CIC_W   = 50
KALIS   = 50
KOSHA   = 0
```

Batch numbers 1–100 follow the frozen TSV order (TASK rows 1–50, PROCESS rows 51–100).

---

## Same-name groups

Inside Batch 001, 9 normalized names appear more than once. All are KALIS TASK:

```text
설치작업           = 13
이동               = 6
굴착작업           = 5
타설작업           = 5
양중작업           = 4
조립작업           = 3
해체작업           = 3
부설 및 다짐작업   = 2
마감작업           = 2
```

```text
same-name groups (batch)                 = 9
same-name multi-parent rows (batch)      = 50
TASK same-name multi-parent              = 50
compatible-kind same-name groups (batch) = 9
incompatible-kind same-name groups (batch) = 0
```

Every KALIS row in Batch 001 has mechanical flag `SAME_NAME_MULTI_PARENT`. Example: `설치작업` appears under `토목 > 가설공사`, `건축 > 가설공사`, `건축 > 철근콘크리트공사`, and other parents. Paths are listed on the worksheet (max 10).

Full 3103-universe name facts (not batch decisions):

```text
universe incompatible-kind same-name groups     = 6
universe compatible-kind multi-name groups      = 207
universe compatible-kind multi-parent groups    = 205
```

The six incompatible-kind names are PROCESS vs TASK across sources (`타워크레인`, `리프트`, `윈치`, `발파`, `콘크리트타설`, `콘크리트양생`). None of those six names is in Batch 001. Flag `INCOMPATIBLE_KIND` is 0 in this worksheet.

---

## CIC_W leaf / non-leaf

Among the 50 CIC_W PROCESS rows:

```text
PROCESS leaf     = 42
PROCESS non-leaf = 8
CIC_W W_ROOT     = 1
CIC_W W_MID      = 12
CIC_W W_LEAF     = 37
```

Depth:

```text
depth 1 = 1
depth 2 = 12
depth 3 = 37
```

The eight non-leaf rows and child samples (max 5, `source_key` ASC):

```text
ALC공사              child_count=2  ALC블록 | ALC판넬
LNG및원유저장공사    child_count=1  LNG및원유저장설비공사
PC부속공사           child_count=2  PC부속재설치공사 | PC조인트그라우팅
PC부재생산           child_count=8  sample 5 children
가공석재조적         child_count=6  sample 5 children
가구및집기           child_count=4  일반가구 | 시설별특수가구 | 집기및비품 | 시설별특수집기및비품
가구식구조목공사     child_count=7  sample 5 children
가물막이             child_count=5  나무널말뚝가물막이 | SheetPile가물막이 | ...
```

`가구및집기` is the only Batch 001 `W_ROOT`. Five `W_MID` rows have `child_count = 0` (`PC부재운반`, `PC연속벽흙막이`, `PC형틀및생산시설`, `SheetPile`, `가공목재조립식구조목공사`).

Batch 001 PROCESS names include `ALC블록`, `FCM공법`, `GIS공사`, `FRP판넬`, `NATM` is not in this 50 because of name sort. These are source nodes currently proposed as PROCESS because RISK-04 maps every CIC_W node to PROCESS. That mapping is a fact for GPT Q5; this pack does not decide validity.

---

## KALIS task risk-support distribution

All 50 TASK rows are KALIS. `risk_content_support`:

```text
min    = 115
median = 201
max    = 2438
```

Each TASK row has parent = 공종 중분류 path, grandparent = 공종 대분류, and three deterministic risk samples (occurrence DESC, `content_key` ASC). Sample fields only: 위험객체, 위험위치, 사고원인, 인적피해, 물적피해, 사고가능성, 사고심각성. No 19-field dump.

Row 1 example: `토목 > 토공사 > 굴착작업`, risk-content 2438, same-name count 31, sample 1 `객체=건설기계/굴착기; 위치=인접주변/굴착기/바닥; ...`.

---

## Mechanical flags

Flags are evidence, not decisions:

```text
HAS_CHILDREN
IS_LEAF
SAME_NAME_MULTI_PARENT
CROSS_SOURCE_SAME_NAME
INCOMPATIBLE_KIND
HIGH_RISK_SUPPORT   (risk_content_support > 0)
B_IDENTITY_HOLD
```

No regex heuristic wrote `KEEP` / `REJECT` from name suffixes.

---

## Semantic risk findings (facts only)

```text
42 PROCESS proposals in Batch 001 have child_count = 0
8 PROCESS proposals in Batch 001 have children
1 PROCESS proposal is a CIC_W W_ROOT (가구및집기)
37 PROCESS proposals are CIC_W W_LEAF
50 TASK proposals share a normalized name across multiple parent paths
9 distinct TASK names account for all Batch 001 duplicates
0 Batch 001 rows have CROSS_SOURCE_SAME_NAME
0 Batch 001 rows have INCOMPATIBLE_KIND
SEED UNIVERSE remains 3103
```

OWNER REVIEW REQUIRED.

```text
SYSTEMIC_KIND_RULE_ISSUE = PENDING GPT
```

Candidate names, paths, and node types (`W_ROOT` / `W_MID` / `W_LEAF` all proposed as PROCESS) are in the worksheet for Q5. Final `YES` / `CHG_REQUIRED` is not set here.

---

## Guards preserved

```text
SEED UNIVERSE              = 3103
PENDING MAPPING CANDIDATES = 3103
APPROVED DB MAPPINGS       = 0
CANONICAL UUID CREATED     = 0
ACTIVE CANONICALS          = 0
OWNER APPROVED SEEDS       = 0
NEW MIGRATION              = 0
A nodes                    = 1722
B raw                      = 626
B path                     = 620
B identity                 = HOLD
B occurrence               = 626
C tasks                    = 761
C unique content           = 30696
C occurrence               = 47559
production DB write        = 0
Graph / Legal / CHEM       = 0
LLM / embedding / fuzzy    = 0
customer data              = 0
```

Existing `docs/knowledge/risk/RISK04_BATCH001.tsv` was not modified. Generator modules `seed_review.py`, `review_batch.py`, `ingest_readiness.py`, `identity.py` were not modified.

---

## Next

GPT/Owner reads `RISK04_BATCH001_REVIEW_INPUT.tsv` and fills `owner_decision` / `merge_candidate_keys` / `owner_reason` for all 100 rows, plus:

```text
CIC_W → PROCESS rule valid?     YES / CHG_REQUIRED
KALIS task context model valid? YES / CHG_REQUIRED
```

RISK-04-APPROVE-001 stays closed until those semantic decisions are confirmed.

```text
NEXT = GPT SEMANTIC REVIEW
MERGE = NOT AUTHORIZED
```

---

## GPT semantic review result (append; original facts above are unchanged)

```text
WO-RISK-04-REVIEW-001 = SEMANTIC REVIEW COMPLETE
KEEP_AS_DISTINCT      = 49
MERGE_CANDIDATE       = 22
HOLD                  = 17
REJECT                = 12
SYSTEMIC_KIND_RULE_ISSUE = YES
CIC_W → PROCESS ALL   = REJECTED
KALIS MULTI-PARENT ALL HOLD = REJECTED
approval_state        = NOT_APPROVED
```

Manifest recorded in CHG1: `docs/knowledge/risk/RISK04_BATCH001_GPT_REVIEW_v1.tsv`. Original `RISK04_BATCH001_REVIEW_INPUT.tsv` owner columns remain `PENDING` as the evidence snapshot.

```text
NEXT = WO-RISK-04-CHG1
```
