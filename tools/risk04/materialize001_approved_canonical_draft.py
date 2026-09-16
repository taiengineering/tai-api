"""Approved 1110-row DRAFT canonical materialization plan and SQL. Not ACTIVE.

This pack rebuilds the Owner-approved snapshot into a transactional INSERT plan.
Cursor does not mint canonical identity in Python. UUID is gen_random_uuid()
at production insert time. Mapping, sector, ACTIVE, and canonical_code stay closed.
"""
from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path

from tools.risk01.analyze_3way import norm_name
from tools.risk04.approve001_owner_approval_binding import (
    BINDING_PATH,
    FROZEN_FINAL_MANIFEST_SHA,
    FROZEN_HOLD_PACKAGE_SHA,
    FROZEN_OWNER_PACKAGE_SHA,
    binding_sha,
    build_binding,
)
from tools.risk04.review007_preapproval_readiness import GPT_EMPTY
from tools.risk04.review010_candidate_universe import UNIVERSE_PATH
from tools.risk04.review014_remaining_parent_label_evidence import L02_KEY
from tools.risk04.review016_preapproval_manifest_audit import graph_audit
from tools.risk04.review018_final_resolution_owner_package import (
    FINAL_MANIFEST_PATH,
    HOLD_PACKAGE_PATH,
    OWNER_PACKAGE_PATH,
    final_manifest_sha,
    hold_package_sha,
    owner_package_sha,
)
from tools.risk04.review_decisions import load_tsv, write_tsv
from tools.risk04.seed_review import universe_sha

# Explicit evidence pack. Cursor does not re-review semantics or apply migrations.
# This is an explicit evidence pack, not a classifier.
APPROVAL_ID = "RISK-04-APPROVE-001"
MATERIALIZATION_ID = "RISK-04-MATERIALIZE-001"
MATERIALIZATION_VERSION = "v1"
FROZEN_BINDING_SHA = "fc2537cb3ec72f204beda6a416f77ca7a3d1c5b55f976fe1bdfa93b6f87fcfa0"
L02_CHILD_KEY = "246dba3003df34544b7b59939c89a1aae459a17b0d356ce70df1aca64c705e94"
ORIGIN_BY_FORM = {
    "SINGLETON": "PROMOTED_FROM_SOURCE",
    "EQUIVALENCE_GROUP": "MERGED_FROM_REVIEWED_SOURCES",
}
PLAN_PATH = Path("docs/knowledge/risk/RISK04_CANONICAL_MATERIALIZATION_PLAN_v1.tsv")
SQL_PATH = Path("docs/knowledge/risk/RISK04_CANONICAL_MATERIALIZATION_v1.sql")
REPORT_PATH = Path("docs/knowledge/risk/OBJ_risk04-materialize001-approved-canonical-draft_v1.md")
PLAN_FIELDS = (
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
)


def _assert_approval_binding() -> dict:
    owner = load_tsv(OWNER_PACKAGE_PATH)
    hold = load_tsv(HOLD_PACKAGE_PATH)
    manifest = load_tsv(FINAL_MANIFEST_PATH)
    binding = load_tsv(BINDING_PATH)
    rebuilt = build_binding()
    if owner_package_sha(owner) != FROZEN_OWNER_PACKAGE_SHA:
        raise ValueError("owner package SHA drift")
    if hold_package_sha(hold) != FROZEN_HOLD_PACKAGE_SHA:
        raise ValueError("hold package SHA drift")
    if final_manifest_sha(manifest) != FROZEN_FINAL_MANIFEST_SHA:
        raise ValueError("final manifest SHA drift")
    if binding_sha(binding) != FROZEN_BINDING_SHA:
        raise ValueError("approval binding SHA drift")
    if binding_sha(rebuilt) != FROZEN_BINDING_SHA:
        raise ValueError("rebuilt approval binding SHA drift")
    if len(owner) != 1110:
        raise ValueError(f"owner package rows {len(owner)}")
    if len(hold) != 1:
        raise ValueError(f"hold package rows {len(hold)}")
    if hold[0]["review_concept_key"] != L02_KEY:
        raise ValueError("hold key drift")
    if L02_KEY in {row["review_concept_key"] for row in owner}:
        raise ValueError("L-02 leaked into approval package")
    return {"owner": owner, "hold": hold, "manifest": manifest, "binding": binding}


def _parent_key(raw: str) -> str:
    value = (raw or "").strip()
    return GPT_EMPTY if value in {"", GPT_EMPTY} else value


def assemble_plan() -> list[dict]:
    pack = _assert_approval_binding()
    universe = {row["review_concept_key"]: row for row in load_tsv(UNIVERSE_PATH)}
    rows: list[dict] = []
    for owner in pack["owner"]:
        key = owner["review_concept_key"]
        if key == L02_KEY:
            raise ValueError("L-02 leaked into materialization plan")
        concept = universe.get(key)
        if concept is None:
            raise ValueError(f"missing universe row {key}")
        form = concept["concept_form"]
        origin = ORIGIN_BY_FORM.get(form)
        if origin is None:
            raise ValueError(f"unsupported concept_form {form}")
        name = owner["canonical_label_candidate"]
        if name in {"", GPT_EMPTY}:
            raise ValueError(f"empty canonical label {key}")
        parent = _parent_key(owner["canonical_parent_candidate"])
        if parent == key:
            raise ValueError(f"self parent {key}")
        rows.append(
            {
                "review_concept_key": key,
                "node_kind": owner["semantic_kind"],
                "parent_review_concept_key": parent,
                "name": name,
                "name_normalized": norm_name(name),
                "concept_form": form,
                "origin_type": origin,
                "canonical_code": "",
                "status": "DRAFT",
                "source_member_count": owner["source_member_count"],
                "source_keys": owner["source_keys"],
                "source_names": owner["source_names"],
                "source_context_policy": owner["source_context_policy"],
                "approval_id": APPROVAL_ID,
                "approval_package_sha": FROZEN_OWNER_PACKAGE_SHA,
            }
        )
    audit = plan_audit(rows)
    if audit["l02"] or audit["self_parent"] or audit["cycle"]:
        raise ValueError(f"identity/graph failed {audit}")
    if audit["tai_native"] or audit["active"] or audit["code_assigned"]:
        raise ValueError(f"row contract failed {audit}")
    if audit["rows"] != 1110 or audit["unique_keys"] != 1110:
        raise ValueError(f"plan rows {audit}")
    return rows


def l02_parent_leak(rows: list[dict]) -> list[dict]:
    return [row for row in rows if row["parent_review_concept_key"] == L02_KEY]


def assert_write_ready(rows: list[dict]) -> None:
    audit = plan_audit(rows)
    leak = l02_parent_leak(rows)
    if audit["unknown_parent"] or leak:
        raise ValueError(
            "PARENT_POINTS_TO_HOLD_L02 "
            + ",".join(row["review_concept_key"] for row in leak)
        )
    if audit["l02"] or audit["self_parent"] or audit["cycle"]:
        raise ValueError(f"parent closure failed {audit}")


def build_plan() -> list[dict]:
    return assemble_plan()


def plan_audit(rows: list[dict]) -> dict[str, int]:
    graph_rows = [
        {
            "review_concept_key": row["review_concept_key"],
            "canonical_parent_candidate": row["parent_review_concept_key"],
        }
        for row in rows
    ]
    graph = graph_audit(graph_rows)
    kinds = Counter(row["node_kind"] for row in rows)
    origins = Counter(row["origin_type"] for row in rows)
    return {
        "rows": len(rows),
        "unique_keys": len({row["review_concept_key"] for row in rows}),
        "empty_label": sum(1 for row in rows if row["name"] in {"", GPT_EMPTY}),
        "l02": sum(1 for row in rows if row["review_concept_key"] == L02_KEY),
        "process": kinds["PROCESS"],
        "task": kinds["TASK"],
        "promoted": origins["PROMOTED_FROM_SOURCE"],
        "merged": origins["MERGED_FROM_REVIEWED_SOURCES"],
        "tai_native": origins["TAI_NATIVE"],
        "draft": sum(1 for row in rows if row["status"] == "DRAFT"),
        "active": sum(1 for row in rows if row["status"] == "ACTIVE"),
        "code_assigned": sum(1 for row in rows if row["canonical_code"]),
        "unknown_parent": graph["unknown_parent"],
        "self_parent": graph["self_parent"],
        "cycle": graph["cycle"],
        "mapping_rows": 0,
        "sector_rows": 0,
    }


def plan_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *PLAN_FIELDS)


def sql_sha(sql: str) -> str:
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def _sql_text(value: str) -> str:
    if any(ch in value for ch in ("\x00", "\n", "\r")):
        raise ValueError("illegal control character in SQL literal")
    return "'" + value.replace("'", "''") + "'"


def _sql_parent(value: str) -> str:
    if value in {"", GPT_EMPTY}:
        return "NULL"
    return _sql_text(value)


def render_sql(rows: list[dict]) -> str:
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
                ]
            )
            + ")"
        )
    staged = ",\n".join(values)
    return f"""-- Generated by tools/risk04/materialize001_approved_canonical_draft.py
-- RISK-04-MATERIALIZE-001 approved DRAFT canonical insert. Do not hand-edit.
-- OWNER APPROVAL PACKAGE SHA = {FROZEN_OWNER_PACKAGE_SHA}
-- APPROVAL ID = {APPROVAL_ID}
-- ROWS = 1110
-- ACTIVE = 0
-- mapping write = 0
-- sector write = 0
-- canonical_code = NULL
-- L-02 = NOT MATERIALIZED

BEGIN;

SELECT pg_advisory_xact_lock(4041110, 1);

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
    WHERE metadata->>'approval_id' = '{APPROVAL_ID}'
       OR metadata->>'approval_package_sha' = '{FROZEN_OWNER_PACKAGE_SHA}'
  ) THEN
    RAISE EXCEPTION 'DUPLICATE MATERIALIZATION GUARD TRIGGERED';
  END IF;
END
$guard$;

CREATE TEMP TABLE risk04_m001_stage (
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
  staged_id uuid NOT NULL DEFAULT gen_random_uuid()
) ON COMMIT DROP;

INSERT INTO risk04_m001_stage (
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
  source_context_policy
)
VALUES
{staged};

DO $validate$
BEGIN
  IF (SELECT count(*) FROM risk04_m001_stage) <> 1110 THEN
    RAISE EXCEPTION 'staged row count %', (SELECT count(*) FROM risk04_m001_stage);
  END IF;
  IF EXISTS (
    SELECT 1 FROM risk04_m001_stage WHERE review_concept_key = '{L02_KEY}'
  ) THEN
    RAISE EXCEPTION 'L-02 leaked into staging';
  END IF;
  IF EXISTS (
    SELECT 1 FROM risk04_m001_stage WHERE origin_type = 'TAI_NATIVE'
  ) THEN
    RAISE EXCEPTION 'TAI_NATIVE not allowed';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM risk04_m001_stage
    WHERE parent_review_concept_key = review_concept_key
  ) THEN
    RAISE EXCEPTION 'self parent';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM risk04_m001_stage s
    WHERE s.parent_review_concept_key IS NOT NULL
      AND NOT EXISTS (
        SELECT 1
        FROM risk04_m001_stage p
        WHERE p.review_concept_key = s.parent_review_concept_key
      )
  ) THEN
    RAISE EXCEPTION 'parent outside approved set';
  END IF;
  IF EXISTS (
    WITH RECURSIVE walk AS (
      SELECT
        s.review_concept_key AS root_key,
        s.parent_review_concept_key AS parent_key,
        1 AS depth
      FROM risk04_m001_stage s
      WHERE s.parent_review_concept_key IS NOT NULL
      UNION ALL
      SELECT
        w.root_key,
        s.parent_review_concept_key,
        w.depth + 1
      FROM walk w
      JOIN risk04_m001_stage s
        ON s.review_concept_key = w.parent_key
      WHERE w.depth < 64
        AND s.parent_review_concept_key IS NOT NULL
    )
    SELECT 1
    FROM walk
    WHERE root_key = parent_key
       OR depth >= 63
  ) THEN
    RAISE EXCEPTION 'cycle';
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
  jsonb_build_object(
    'approval_id', '{APPROVAL_ID}',
    'approval_package_sha', '{FROZEN_OWNER_PACKAGE_SHA}',
    'review_concept_key', s.review_concept_key,
    'parent_review_concept_key', COALESCE(s.parent_review_concept_key, '{GPT_EMPTY}'),
    'source_context_policy', s.source_context_policy,
    'materialization_id', '{MATERIALIZATION_ID}',
    'materialization_version', '{MATERIALIZATION_VERSION}',
    'source_keys', s.source_keys,
    'source_names', s.source_names,
    'concept_form', s.concept_form
  )
FROM risk04_m001_stage s
LEFT JOIN risk04_m001_stage p
  ON p.review_concept_key = s.parent_review_concept_key;

DO $post$
DECLARE
  inserted integer;
  draft_n integer;
  active_n integer;
  code_n integer;
  unique_ids integer;
  unique_keys integer;
BEGIN
  SELECT count(*) INTO inserted
  FROM public.risk_canonical_nodes
  WHERE metadata->>'approval_id' = '{APPROVAL_ID}';
  SELECT count(*) INTO draft_n
  FROM public.risk_canonical_nodes
  WHERE metadata->>'approval_id' = '{APPROVAL_ID}'
    AND status = 'DRAFT';
  SELECT count(*) INTO active_n
  FROM public.risk_canonical_nodes
  WHERE metadata->>'approval_id' = '{APPROVAL_ID}'
    AND status = 'ACTIVE';
  SELECT count(*) INTO code_n
  FROM public.risk_canonical_nodes
  WHERE metadata->>'approval_id' = '{APPROVAL_ID}'
    AND canonical_code IS NOT NULL;
  SELECT count(DISTINCT id), count(DISTINCT metadata->>'review_concept_key')
    INTO unique_ids, unique_keys
  FROM public.risk_canonical_nodes
  WHERE metadata->>'approval_id' = '{APPROVAL_ID}';
  IF inserted <> 1110 OR draft_n <> 1110 OR active_n <> 0 OR code_n <> 0 THEN
    RAISE EXCEPTION 'post-insert contract inserted=% draft=% active=% code=%',
      inserted, draft_n, active_n, code_n;
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
    WHERE n.metadata->>'approval_id' = '{APPROVAL_ID}'
      AND n.parent_id IS NOT NULL
      AND (
        n.parent_id = n.id
        OR NOT EXISTS (
          SELECT 1
          FROM public.risk_canonical_nodes p
          WHERE p.id = n.parent_id
            AND p.metadata->>'approval_id' = '{APPROVAL_ID}'
        )
      )
  ) THEN
    RAISE EXCEPTION 'parent UUID resolution mismatch';
  END IF;
END
$post$;

COMMIT;
"""


def render_report(rows: list[dict], p_sha: str, s_sha: str, schema_status: str, schema_reason: str) -> str:
    audit = plan_audit(rows)
    leak = l02_parent_leak(rows)
    leak_keys = ",".join(row["review_concept_key"] for row in leak) or "NONE"
    leak_names = " | ".join(row["name"] for row in leak) or "NONE"
    write_ready = "PASS"
    try:
        assert_write_ready(rows)
    except ValueError as exc:
        write_ready = f"BLOCKED / {exc}"
    return f"""---
class: records
type: report
scope: knowledge
project: risk
title: OBJ-RISK-04 MATERIALIZE-001 approved canonical draft
version: 1
status: active
owner: taiwang
---

# OBJ-RISK-04-MATERIALIZE-001 — Approved Canonical Draft Materialization

This pack rebuilds the Owner-approved exact 1110-row snapshot as a DRAFT canonical plan. OWNER APPROVAL ≠ ACTIVE. Cursor does not assign canonical_code, write mappings, write sectors, insert L-02, or invent a parent for L-02 children.

```text
OWNER APPROVAL = VERIFIED
OWNER PACKAGE SHA = {FROZEN_OWNER_PACKAGE_SHA}
APPROVAL BINDING SHA = {FROZEN_BINDING_SHA}
APPROVED SNAPSHOT = 1110
HOLD ROWS = 1
L-02 = HOLD / NOT MATERIALIZED
WRITE READY = {write_ready}
```

This is an explicit evidence pack, not a classifier.

---

## Plan Census

```text
MATERIALIZATION PLAN ROWS = {audit["rows"]}
UNIQUE REVIEW CONCEPT KEY = {audit["unique_keys"]}
PROCESS = {audit["process"]}
TASK = {audit["task"]}
PROMOTED_FROM_SOURCE = {audit["promoted"]}
MERGED_FROM_REVIEWED_SOURCES = {audit["merged"]}
TAI_NATIVE = {audit["tai_native"]}
empty canonical labels = {audit["empty_label"]}
parent outside approved set = {audit["unknown_parent"]}
parent pointing to HOLD L-02 = {len(leak)}
L-02 child review_concept_key = {leak_keys}
L-02 child name = {leak_names}
self parent = {audit["self_parent"]}
cycle = {audit["cycle"]}
status DRAFT = {audit["draft"]}
status ACTIVE = {audit["active"]}
canonical_code assigned = {audit["code_assigned"]}
mapping rows generated = {audit["mapping_rows"]}
sector rows generated = {audit["sector_rows"]}
PLAN SHA = {p_sha}
SQL SHA = {s_sha}
```

---

## Expected Production Contract

```text
inserted risk_canonical_nodes = 0
DRAFT = 0
ACTIVE = 0
canonical_code assigned = 0
source mapping write = 0
sector write = 0
L-02 = HOLD / NOT MATERIALIZED
partial write = 0
UUID = gen_random_uuid at insert time
production SQL = GENERATED / NOT EXECUTED
```

The generated SQL keeps a parent-outside-approved-set RAISE EXCEPTION. It cannot complete while the L-02 child remains in the 1110 snapshot.

---

## Schema / Production

```text
SCHEMA PREFLIGHT = {schema_status}
schema blocker reason = {schema_reason}
production execution = NOT_EXECUTED
PRODUCTION WRITE = 0
MATERIALIZED = 0
canonical UUID = 0
MATERIALIZATION RECEIPT SHA = NONE
```

---

## Verdict

```text
WO-RISK-04-MATERIALIZE-001 = BLOCKED
REASON = PARENT_POINTS_TO_HOLD_L02
ALSO = {schema_reason}
OWNER APPROVAL = PRESERVED
OWNER PACKAGE SHA = {FROZEN_OWNER_PACKAGE_SHA}
PRODUCTION WRITE = 0
MAPPING = NOT OPENED
ACTIVE TRANSITION = NOT OPENED
MERGE = NOT AUTHORIZED
NEXT = GPT INDEPENDENT VERIFY OF L-02 PARENT LEAK
THEN = SCHEMA APPLY WO
STOP
```
"""


def write_materialize001_artifacts(schema_status: str = "BLOCKED", schema_reason: str = "RISK03_SCHEMA_NOT_APPLIED_OR_DRIFTED") -> dict:
    rows = assemble_plan()
    sql = render_sql(rows)
    p_sha = plan_sha(rows)
    s_sha = sql_sha(sql)
    write_tsv(rows, PLAN_PATH, PLAN_FIELDS)
    SQL_PATH.write_text(sql, encoding="utf-8")
    REPORT_PATH.write_text(render_report(rows, p_sha, s_sha, schema_status, schema_reason), encoding="utf-8")
    return {
        "rows": rows,
        "sql": sql,
        "plan_sha": p_sha,
        "sql_sha": s_sha,
        "audit": plan_audit(rows),
    }


def main() -> None:
    first = write_materialize001_artifacts()
    second_rows = assemble_plan()
    second_sql = render_sql(second_rows)
    leak = l02_parent_leak(first["rows"])
    write_ready = "PASS"
    try:
        assert_write_ready(first["rows"])
    except ValueError as exc:
        write_ready = str(exc)
    print(
        __import__("json").dumps(
            {
                "WO": "WO-RISK-04-MATERIALIZE-001",
                "PLAN_RUN1": first["plan_sha"],
                "PLAN_RUN2": plan_sha(second_rows),
                "SQL_RUN1": first["sql_sha"],
                "SQL_RUN2": sql_sha(second_sql),
                "ROWS": first["audit"]["rows"],
                "PROCESS": first["audit"]["process"],
                "TASK": first["audit"]["task"],
                "PROMOTED_FROM_SOURCE": first["audit"]["promoted"],
                "MERGED_FROM_REVIEWED_SOURCES": first["audit"]["merged"],
                "TAI_NATIVE": first["audit"]["tai_native"],
                "L02_MATERIALIZED": first["audit"]["l02"],
                "PARENT_POINTS_TO_HOLD_L02": len(leak),
                "WRITE_READY": write_ready,
                "db_write": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
