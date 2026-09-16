"""Resume MATERIALIZE-001 with the approved 1-row parent overlay. Not ACTIVE.

v1 plan/SQL remain frozen blocker evidence. This pack rebuilds an effective 1110-row
DRAFT plan from the original Owner Approval plus APPROVE-002. UUID is gen_random_uuid()
at production insert time.
"""
from __future__ import annotations

from pathlib import Path

from tools.risk04.approve002_parent_amendment_binding import (
    AMENDMENT_BINDING_PATH,
    FROZEN_AMENDMENT_SHA,
    amendment_binding_sha,
    build_amendment_binding,
)
from tools.risk04.materialize001_approved_canonical_draft import (
    APPROVAL_ID,
    FROZEN_BINDING_SHA,
    FROZEN_OWNER_PACKAGE_SHA,
    L02_CHILD_KEY,
    MATERIALIZATION_ID,
    PLAN_PATH as V1_PLAN_PATH,
    SQL_PATH as V1_SQL_PATH,
    _sql_parent,
    _sql_text,
    assemble_plan,
    assert_write_ready,
    l02_parent_leak,
    plan_audit,
    plan_sha as v1_plan_sha,
    sql_sha,
)
from tools.risk04.recovery001_parent_amendment import (
    CHILD_KEY,
    NEW_PARENT_KEY,
    OLD_PARENT_KEY,
    OLD_PARENT_SOURCE_KEY,
    SOURCE_CONTEXT_POLICY,
    amendment_sha,
    build_amendment,
)
from tools.risk04.review007_preapproval_readiness import GPT_EMPTY
from tools.risk04.review014_remaining_parent_label_evidence import L02_KEY
from tools.risk04.review_decisions import load_tsv, write_tsv
from tools.risk04.seed_review import universe_sha

# Explicit overlay freeze. Cursor does not re-review semantics.
# This is an explicit evidence pack, not a classifier.
MATERIALIZATION_VERSION = "v2"
FROZEN_V1_PLAN_SHA = "48564af3da09cb659a6296ee36a6677faa05aef3f85b7aab2f1437baecd68056"
FROZEN_V1_SQL_SHA = "f0602b25b4d72197435fec68bec20377db648fbd37a0a4e509e367432f527995"
FROZEN_AMENDMENT_BINDING_SHA = "56f674abb551e403d22ab01d9833360e62dced72b0e3210ccbce88f6b29712d9"
FROZEN_RECEIPT_SHA = "c8c4232bf924b52636c9dc33fb1891473d548e09ed15de35f33764fe18603f3c"
AMENDMENT_APPROVAL_ID = "RISK-04-APPROVE-002"
V2_PLAN_PATH = Path("docs/knowledge/risk/RISK04_CANONICAL_MATERIALIZATION_PLAN_v2.tsv")
V2_SQL_PATH = Path("docs/knowledge/risk/RISK04_CANONICAL_MATERIALIZATION_v2.sql")
RECEIPT_PATH = Path("docs/knowledge/risk/RISK04_CANONICAL_MATERIALIZATION_RECEIPT_v1.tsv")
REPORT_PATH = Path("docs/knowledge/risk/OBJ_risk04-materialize001-r1-execution_v1.md")
V2_PLAN_FIELDS = (
    "review_concept_key",
    "node_kind",
    "parent_review_concept_key",
    "name",
    "name_normalized",
    "concept_form",
    "origin_type",
    "canonical_code",
    "status",
    "source_member_count",
    "source_keys",
    "source_names",
    "source_context_policy",
    "approval_id",
    "approval_package_sha",
    "amendment_approval_id",
    "amendment_package_sha",
)
RECEIPT_FIELDS = (
    "review_concept_key",
    "canonical_id",
    "node_kind",
    "parent_review_concept_key",
    "parent_canonical_id",
    "name",
    "name_normalized",
    "origin_type",
    "status",
    "approval_id",
    "approval_package_sha",
    "amendment_approval_id",
    "amendment_package_sha",
    "materialization_id",
)


def _assert_effective_anchors() -> None:
    if v1_plan_sha(load_tsv(V1_PLAN_PATH)) != FROZEN_V1_PLAN_SHA:
        raise ValueError("v1 plan SHA drift")
    if sql_sha(V1_SQL_PATH.read_text(encoding="utf-8")) != FROZEN_V1_SQL_SHA:
        raise ValueError("v1 SQL SHA drift")
    if amendment_sha(build_amendment()) != FROZEN_AMENDMENT_SHA:
        raise ValueError("amendment package SHA drift")
    if amendment_binding_sha(load_tsv(AMENDMENT_BINDING_PATH)) != FROZEN_AMENDMENT_BINDING_SHA:
        raise ValueError("amendment binding SHA drift")
    if amendment_binding_sha(build_amendment_binding()) != FROZEN_AMENDMENT_BINDING_SHA:
        raise ValueError("rebuilt amendment binding SHA drift")


def assemble_v2_plan() -> list[dict]:
    _assert_effective_anchors()
    rows = []
    overrides = 0
    for base in assemble_plan():
        row = dict(base)
        if row["review_concept_key"] == CHILD_KEY:
            row["parent_review_concept_key"] = NEW_PARENT_KEY
            row["source_context_policy"] = SOURCE_CONTEXT_POLICY
            row["amendment_approval_id"] = AMENDMENT_APPROVAL_ID
            row["amendment_package_sha"] = FROZEN_AMENDMENT_SHA
            overrides += 1
        else:
            row["amendment_approval_id"] = GPT_EMPTY
            row["amendment_package_sha"] = GPT_EMPTY
        rows.append(row)
    if overrides != 1:
        raise ValueError(f"override rows {overrides}")
    assert_write_ready(rows)
    audit = plan_audit(rows)
    if audit["process"] != 556 or audit["task"] != 554:
        raise ValueError(f"kind counts {audit}")
    if audit["promoted"] != 1082 or audit["merged"] != 28:
        raise ValueError(f"origin counts {audit}")
    child = next(row for row in rows if row["review_concept_key"] == CHILD_KEY)
    if child["parent_review_concept_key"] != NEW_PARENT_KEY:
        raise ValueError("child override missing")
    if any(row["parent_review_concept_key"] == L02_KEY for row in rows):
        raise ValueError("L-02 parent remaining")
    return rows


def v2_plan_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *V2_PLAN_FIELDS)


def receipt_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *RECEIPT_FIELDS)


def render_v2_sql(rows: list[dict]) -> str:
    if len(rows) != 1110:
        raise ValueError(f"sql rows {len(rows)}")
    values = []
    for row in rows:
        values.append(
            "("
            + ", ".join(
                [
                    _sql_text(row["review_concept_key"]),
                    _sql_text(row["node_kind"]),
                    _sql_parent(row["parent_review_concept_key"]),
                    _sql_text(row["name"]),
                    _sql_text(row["name_normalized"]),
                    _sql_text(row["concept_form"]),
                    _sql_text(row["origin_type"]),
                    _sql_text(row["source_member_count"]),
                    _sql_text(row["source_keys"]),
                    _sql_text(row["source_names"]),
                    _sql_text(row["source_context_policy"]),
                    _sql_parent(row["amendment_approval_id"]) if row["amendment_approval_id"] != GPT_EMPTY else "NULL",
                    _sql_parent(row["amendment_package_sha"]) if row["amendment_package_sha"] != GPT_EMPTY else "NULL",
                ]
            )
            + ")"
        )
    staged = ",\n".join(values)
    return f"""-- Generated by tools/risk04/materialize001_resume_effective_plan.py
-- RISK-04-MATERIALIZE-001-R1 effective DRAFT canonical insert. Do not hand-edit.
-- OWNER APPROVAL PACKAGE SHA = {FROZEN_OWNER_PACKAGE_SHA}
-- AMENDMENT PACKAGE SHA = {FROZEN_AMENDMENT_SHA}
-- ROWS = 1110
-- OVERRIDE = 1
-- ACTIVE = 0
-- L-02 = NOT MATERIALIZED

BEGIN;

SELECT pg_advisory_xact_lock(4041110, 2);

DO $guard$
BEGIN
  IF to_regclass('public.risk_canonical_nodes') IS NULL
     OR to_regclass('public.risk_canonical_node_sectors') IS NULL
     OR to_regclass('public.risk_source_mappings') IS NULL THEN
    RAISE EXCEPTION 'RISK03_SCHEMA_NOT_APPLIED_OR_DRIFTED';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM public.risk_canonical_nodes
    WHERE metadata->>'materialization_id' = '{MATERIALIZATION_ID}'
       OR metadata->>'approval_package_sha' = '{FROZEN_OWNER_PACKAGE_SHA}'
  ) THEN
    RAISE EXCEPTION 'DUPLICATE MATERIALIZATION GUARD TRIGGERED';
  END IF;
END
$guard$;

CREATE TEMP TABLE risk04_m001r1_stage (
  review_concept_key text PRIMARY KEY,
  node_kind text NOT NULL,
  parent_review_concept_key text,
  name text NOT NULL,
  name_normalized text NOT NULL,
  concept_form text NOT NULL,
  origin_type text NOT NULL,
  source_member_count text NOT NULL,
  source_keys text NOT NULL,
  source_names text NOT NULL,
  source_context_policy text NOT NULL,
  amendment_approval_id text,
  amendment_package_sha text,
  staged_id uuid NOT NULL DEFAULT gen_random_uuid()
) ON COMMIT DROP;

INSERT INTO risk04_m001r1_stage (
  review_concept_key,
  node_kind,
  parent_review_concept_key,
  name,
  name_normalized,
  concept_form,
  origin_type,
  source_member_count,
  source_keys,
  source_names,
  source_context_policy,
  amendment_approval_id,
  amendment_package_sha
)
VALUES
{staged};

DO $validate$
BEGIN
  IF (SELECT count(*) FROM risk04_m001r1_stage) <> 1110 THEN
    RAISE EXCEPTION 'staged row count %', (SELECT count(*) FROM risk04_m001r1_stage);
  END IF;
  IF (SELECT count(DISTINCT review_concept_key) FROM risk04_m001r1_stage) <> 1110 THEN
    RAISE EXCEPTION 'staged unique keys';
  END IF;
  IF EXISTS (
    SELECT 1 FROM risk04_m001r1_stage WHERE review_concept_key = '{L02_KEY}'
  ) THEN
    RAISE EXCEPTION 'L-02 leaked into staging';
  END IF;
  IF EXISTS (
    SELECT 1 FROM risk04_m001r1_stage WHERE parent_review_concept_key = '{L02_KEY}'
  ) THEN
    RAISE EXCEPTION 'parent pointing to HOLD L-02';
  END IF;
  IF EXISTS (
    SELECT 1 FROM risk04_m001r1_stage WHERE origin_type = 'TAI_NATIVE'
  ) THEN
    RAISE EXCEPTION 'TAI_NATIVE not allowed';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM risk04_m001r1_stage
    WHERE parent_review_concept_key = review_concept_key
  ) THEN
    RAISE EXCEPTION 'self parent';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM risk04_m001r1_stage s
    WHERE s.parent_review_concept_key IS NOT NULL
      AND NOT EXISTS (
        SELECT 1
        FROM risk04_m001r1_stage p
        WHERE p.review_concept_key = s.parent_review_concept_key
      )
  ) THEN
    RAISE EXCEPTION 'parent outside approved set';
  END IF;
  IF (
    SELECT parent_review_concept_key
    FROM risk04_m001r1_stage
    WHERE review_concept_key = '{CHILD_KEY}'
  ) IS DISTINCT FROM '{NEW_PARENT_KEY}' THEN
    RAISE EXCEPTION 'child override missing';
  END IF;
END
$validate$;

INSERT INTO public.risk_canonical_nodes (
  id,
  canonical_code,
  node_kind,
  parent_id,
  name,
  name_normalized,
  description,
  status,
  origin_type,
  metadata
)
SELECT
  s.staged_id,
  NULL,
  s.node_kind,
  p.staged_id,
  s.name,
  s.name_normalized,
  NULL,
  'DRAFT',
  s.origin_type,
  jsonb_strip_nulls(
    jsonb_build_object(
      'materialization_id', '{MATERIALIZATION_ID}',
      'materialization_version', '{MATERIALIZATION_VERSION}',
      'approval_id', '{APPROVAL_ID}',
      'approval_package_sha', '{FROZEN_OWNER_PACKAGE_SHA}',
      'review_concept_key', s.review_concept_key,
      'parent_review_concept_key', COALESCE(s.parent_review_concept_key, '{GPT_EMPTY}'),
      'source_context_policy', s.source_context_policy,
      'source_keys', s.source_keys,
      'source_names', s.source_names,
      'concept_form', s.concept_form,
      'amendment_approval_id', s.amendment_approval_id,
      'amendment_package_sha', s.amendment_package_sha,
      'original_source_parent_review_concept_key',
        CASE
          WHEN s.review_concept_key = '{CHILD_KEY}' THEN '{OLD_PARENT_KEY}'
          ELSE NULL
        END,
      'original_source_parent_source_key',
        CASE
          WHEN s.review_concept_key = '{CHILD_KEY}' THEN '{OLD_PARENT_SOURCE_KEY}'
          ELSE NULL
        END,
      'original_source_parent_status',
        CASE
          WHEN s.review_concept_key = '{CHILD_KEY}' THEN 'HOLD_LABEL_CONFIRMED'
          ELSE NULL
        END
    )
  )
FROM risk04_m001r1_stage s
LEFT JOIN risk04_m001r1_stage p
  ON p.review_concept_key = s.parent_review_concept_key;

DO $post$
DECLARE
  inserted integer;
  draft_n integer;
  active_n integer;
  code_n integer;
  process_n integer;
  task_n integer;
  unique_ids integer;
  unique_keys integer;
BEGIN
  SELECT count(*) INTO inserted
  FROM public.risk_canonical_nodes
  WHERE metadata->>'materialization_id' = '{MATERIALIZATION_ID}';
  SELECT count(*) INTO draft_n
  FROM public.risk_canonical_nodes
  WHERE metadata->>'materialization_id' = '{MATERIALIZATION_ID}'
    AND status = 'DRAFT';
  SELECT count(*) INTO active_n
  FROM public.risk_canonical_nodes
  WHERE metadata->>'materialization_id' = '{MATERIALIZATION_ID}'
    AND status = 'ACTIVE';
  SELECT count(*) INTO code_n
  FROM public.risk_canonical_nodes
  WHERE metadata->>'materialization_id' = '{MATERIALIZATION_ID}'
    AND canonical_code IS NOT NULL;
  SELECT count(*) FILTER (WHERE node_kind = 'PROCESS'),
         count(*) FILTER (WHERE node_kind = 'TASK')
    INTO process_n, task_n
  FROM public.risk_canonical_nodes
  WHERE metadata->>'materialization_id' = '{MATERIALIZATION_ID}';
  SELECT count(DISTINCT id), count(DISTINCT metadata->>'review_concept_key')
    INTO unique_ids, unique_keys
  FROM public.risk_canonical_nodes
  WHERE metadata->>'materialization_id' = '{MATERIALIZATION_ID}';
  IF inserted <> 1110 OR draft_n <> 1110 OR active_n <> 0 OR code_n <> 0 THEN
    RAISE EXCEPTION 'post-insert contract inserted=% draft=% active=% code=%',
      inserted, draft_n, active_n, code_n;
  END IF;
  IF process_n <> 556 OR task_n <> 554 THEN
    RAISE EXCEPTION 'post-insert kinds process=% task=%', process_n, task_n;
  END IF;
  IF unique_ids <> 1110 OR unique_keys <> 1110 THEN
    RAISE EXCEPTION 'post-insert uniqueness ids=% keys=%', unique_ids, unique_keys;
  END IF;
  IF EXISTS (
    SELECT 1
    FROM public.risk_canonical_nodes
    WHERE metadata->>'review_concept_key' = '{L02_KEY}'
  ) THEN
    RAISE EXCEPTION 'L-02 materialized';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM public.risk_canonical_nodes n
    WHERE n.metadata->>'materialization_id' = '{MATERIALIZATION_ID}'
      AND n.parent_id IS NOT NULL
      AND (
        n.parent_id = n.id
        OR NOT EXISTS (
          SELECT 1
          FROM public.risk_canonical_nodes p
          WHERE p.id = n.parent_id
            AND p.metadata->>'materialization_id' = '{MATERIALIZATION_ID}'
        )
      )
  ) THEN
    RAISE EXCEPTION 'parent UUID resolution mismatch';
  END IF;
  IF (
    SELECT c.parent_id
    FROM public.risk_canonical_nodes c
    WHERE c.metadata->>'review_concept_key' = '{CHILD_KEY}'
  ) IS DISTINCT FROM (
    SELECT p.id
    FROM public.risk_canonical_nodes p
    WHERE p.metadata->>'review_concept_key' = '{NEW_PARENT_KEY}'
  ) THEN
    RAISE EXCEPTION 'child override parent UUID mismatch';
  END IF;
END
$post$;

COMMIT;
"""


def render_r1_report(rows: list[dict], p_sha: str, s_sha: str, extra: dict | None = None) -> str:
    audit = plan_audit(rows)
    extra = extra or {}
    receipt_sha_value = extra.get("receipt_sha", "NONE")
    execution = extra.get("production_execution", "NOT_EXECUTED")
    inserted = extra.get("inserted", "0")
    return f"""---
class: records
type: report
scope: knowledge
project: risk
title: OBJ-RISK-04 MATERIALIZE-001-R1 execution
version: 1
status: active
owner: taiwang
---

# OBJ-RISK-04-MATERIALIZE-001-R1 — Effective Overlay Draft Materialization

This pack applies the Owner-approved 1-row parent overlay to the original 1110-row snapshot and materializes DRAFT canonical nodes. v1 remains frozen blocker evidence. OWNER APPROVAL ≠ ACTIVE.

```text
BASE OWNER APPROVAL = VERIFIED
APPROVED AMENDMENT = VERIFIED
EFFECTIVE APPROVED CONCEPTS = 1110
EFFECTIVE PARENT OVERRIDES = 1
CHILD = {CHILD_KEY}
OLD PARENT = {OLD_PARENT_KEY} / HOLD
NEW PARENT = {NEW_PARENT_KEY}
L-02 = HOLD / NOT MATERIALIZED
```

This is an explicit evidence pack, not a classifier.

---

## v2 Plan Census

```text
V2 PLAN ROWS = {audit["rows"]}
PROCESS = {audit["process"]}
TASK = {audit["task"]}
PROMOTED_FROM_SOURCE = {audit["promoted"]}
MERGED_FROM_REVIEWED_SOURCES = {audit["merged"]}
TAI_NATIVE = {audit["tai_native"]}
parent outside approved set = {audit["unknown_parent"]}
parent pointing to HOLD L-02 = {len(l02_parent_leak(rows))}
self parent = {audit["self_parent"]}
cycle = {audit["cycle"]}
status DRAFT = {audit["draft"]}
status ACTIVE = {audit["active"]}
canonical_code assigned = {audit["code_assigned"]}
V2 PLAN SHA = {p_sha}
V2 SQL SHA = {s_sha}
V1 PLAN SHA = {FROZEN_V1_PLAN_SHA}
V1 SQL SHA = {FROZEN_V1_SQL_SHA}
```

---

## Production

```text
production execution = {execution}
MATERIALIZED = {inserted}
DRAFT = {extra.get("draft", inserted)}
ACTIVE = {extra.get("active", "0")}
canonical_code = {extra.get("canonical_code", "0")}
mapping write = 0
sector write = 0
partial write = 0
canonical UUID = {extra.get("unique_uuid", inserted)}
MATERIALIZATION RECEIPT SHA = {receipt_sha_value}
```

---

## Verdict

```text
WO-RISK-04-MATERIALIZE-001-R1 = {extra.get("verdict", "PLAN_READY")}
MATERIALIZATION STATE = {extra.get("state", "PLAN_READY")}
MAPPING = NOT OPENED
ACTIVE TRANSITION = NOT OPENED
MERGE = NOT AUTHORIZED
NEXT = GPT INDEPENDENT VERIFY OF MATERIALIZATION RECEIPT
THEN = SOURCE MAPPING GOVERNANCE
STOP
```
"""


def write_v2_artifacts(extra: dict | None = None) -> dict:
    rows = assemble_v2_plan()
    sql = render_v2_sql(rows)
    p_sha = v2_plan_sha(rows)
    s_sha = sql_sha(sql)
    write_tsv(rows, V2_PLAN_PATH, V2_PLAN_FIELDS)
    V2_SQL_PATH.write_text(sql, encoding="utf-8")
    REPORT_PATH.write_text(render_r1_report(rows, p_sha, s_sha, extra), encoding="utf-8")
    return {"rows": rows, "sql": sql, "plan_sha": p_sha, "sql_sha": s_sha, "audit": plan_audit(rows)}


def main() -> None:
    first = write_v2_artifacts()
    second = assemble_v2_plan()
    second_sql = render_v2_sql(second)
    print(
        __import__("json").dumps(
            {
                "WO": "WO-RISK-04-MATERIALIZE-001-R1",
                "PLAN_RUN1": first["plan_sha"],
                "PLAN_RUN2": v2_plan_sha(second),
                "SQL_RUN1": first["sql_sha"],
                "SQL_RUN2": sql_sha(second_sql),
                "ROWS": first["audit"]["rows"],
                "PROCESS": first["audit"]["process"],
                "TASK": first["audit"]["task"],
                "OVERRIDES": 1,
                "L02_PARENT": len(l02_parent_leak(first["rows"])),
                "db_write": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
