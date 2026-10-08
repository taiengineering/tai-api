# LFR-P01 SCAFFOLD C2 Projection Contract

**Date:** 2026-10-08
**Status:** FROZEN / IMPLEMENTATION COMPLETE / GPT VERIFY PENDING

---

## Source Atoms

```
5792aae3-bbc9-5448-a4d4-b509690dadf0
69b81031-8f4c-5cba-8660-7b7063e7ddf1
```

Both remain valid source atoms in LEG main.

Applicable condition:
```
AND(has_scaffold = TRUE, scaffold_height_m >= 2.0)
```

---

## Published Runtime Norm

```
0ddbaec7-2a05-5c80-98e4-439301afe77a
```

supersedes_atom_ids:
```
[5792aae3-bbc9-5448-a4d4-b509690dadf0, 69b81031-8f4c-5cba-8660-7b7063e7ddf1]
```

Production returns `0ddbaec7...` (not source atoms directly). Source atoms remain in PSR.

---

## C2 Projection Rule

### has_scaffold

`>= 1` active SCAFFOLD row → `has_scaffold = TRUE`
0 active rows → key absent (UNKNOWN, not FALSE)

### scaffold_height_m (new in C2)

Source: `factory_work_facts.attributes.height_m` where `work_type=SCAFFOLD, active=TRUE`

**Single-row rule (exactly 1 active SCAFFOLD row):**
- Read `attributes.height_m` from that row
- Valid if: `isinstance(h, (int, float)) and not isinstance(h, bool) and math.isfinite(h) and h >= 0`
- If valid → emit `scaffold_height_m = h`
- 0 is valid (0 != ABSENT)

**Multi-row rule (>= 2 active SCAFFOLD rows):**
- `has_scaffold = TRUE`
- `scaffold_height_m = ABSENT`
- No MAX / MIN / AVG / latest / first-row selection
- Even if all rows have identical heights: absent

**Invalid / missing:**
- `height_m` absent, null, bool, non-numeric, non-finite, or `< 0` → `scaffold_height_m = ABSENT`
- No fabricated 0. No fallback question.

---

## Production Census Snapshot (2026-10-08)

```
active SCAFFOLD rows    = 31
distinct factories      = 31
per-factory exactly 1   = 31
per-factory 2+          = 0

height_m present/numeric = 31/31
min = 3m, max = 20m
zero / negative / string / bool = 0

equipment_ref non-null = 0
location_ref non-null  = 0
```

Census is evidence only. Single-row path applies because `31/31 factories == 1`. Multi-row path is schema-possible and remains fail-closed.

---

## Constraints

- No direct consumer question for `scaffold_height_m` (no new consumer schema field)
- No new pipeline layer
- No production DB write
- LEG semantic: unchanged
- Consumer schemas (INDUSTRIAL / BUILDING / CONSTRUCTION): unchanged, `extra=forbid`

---

## Implementation Location

`services/work_source/projector.py` — `project_work_rows()` function
`services/work_source/merge.py` — typing update only (numeric value support)
