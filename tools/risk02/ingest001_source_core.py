"""WO-RISK-02-INGEST-001 source snapshot/node/record ingest. Mapping write = 0."""
from __future__ import annotations

import json
from pathlib import Path

from tools.risk01.analyze_3way import sha256_file
from tools.risk02.contract import (
    A_NODES,
    A_SHA256,
    B_ROWS,
    B_SHA256,
    C_CURRENT_PROSE,
    C_DUPLICATE_EXTRAS,
    C_DUPLICATE_GROUPS,
    C_LEGACY_PROSE_COUNT,
    C_PORTAL_ROW_FIELD,
    C_RAW_ROWS,
    C_SHA256,
    C_UNIQUE_CONTENT,
    SOURCE_CIC_W,
    SOURCE_KALIS,
    SOURCE_KOSHA,
)
from tools.risk02.plan_source_core import DEFAULT_ROOT, build_plan
from tools.risk04.review_decisions import load_tsv, write_tsv
from tools.risk04.seed_review import universe_sha

INGEST_ID = "RISK-02-INGEST-001"
FROZEN_DETERMINISM_SHA = "886d45cdaaf9478d066f22e2bfca3ee35128d5bfbda2eddfff664f87ffa7bbfa"
CANONICAL_MATERIALIZATION_RECEIPT_SHA = (
    "c8c4232bf924b52636c9dc33fb1891473d548e09ed15de35f33764fe18603f3c"
)
A_FILE = Path("artifacts/risk01/source_a/cic_annex_works.txt")
B_FILE = Path("artifacts/risk01/source_b/kosha_construction_process.csv")
C_FILE = Path("artifacts/risk01/source_c/kalis_risk_profile.csv")
MANIFEST_PATH = Path("docs/knowledge/risk/RISK02_SOURCE_INGEST_MANIFEST_v1.tsv")
RECEIPT_PATH = Path("docs/knowledge/risk/RISK02_SOURCE_INGEST_RECEIPT_v1.tsv")
REPORT_PATH = Path("docs/knowledge/risk/OBJ_risk02-ingest001-production-source-core_v1.md")
CANONICAL_RECEIPT_PATH = Path("docs/knowledge/risk/RISK04_CANONICAL_MATERIALIZATION_RECEIPT_v1.tsv")

# Frozen after this WO's full planner reverify. Not a new identity algorithm.
B_NODES = 787
C_NODES = 816
C_TASK_NODES = 761
PLANNED_MEMBERSHIPS = 34021

MANIFEST_FIELDS = (
    "source_id",
    "source_sha256",
    "raw_row_count",
    "unique_record_count",
    "planned_node_count",
    "planned_record_count",
    "planned_membership_count",
    "identity_status",
    "occurrence_sum",
)
RECEIPT_FIELDS = (
    "source_id",
    "snapshot_id",
    "snapshot_status",
    "source_sha256",
    "node_count",
    "record_count",
    "membership_count",
    "occurrence_sum",
    "validation_status",
)

SNAPSHOT_SPECS = (
    {
        "source_id": SOURCE_CIC_W,
        "source_version": "2015-850",
        "source_filename": "cic_annex_works.txt",
        "source_url": "https://www.calspia.go.kr/portal/intro/introStandard04.do",
        "source_sha256": A_SHA256,
        "raw_row_count": A_NODES,
        "unique_record_count": A_NODES,
        "published_or_modified_date": "2025-07-01",
        "identity_status": "PASS",
        "metadata": {
            "ingest_id": INGEST_ID,
            "identity_status": "PASS",
            "canonical_materialization_receipt_sha": CANONICAL_MATERIALIZATION_RECEIPT_SHA,
        },
    },
    {
        "source_id": SOURCE_KOSHA,
        "source_version": "20210910",
        "source_filename": "kosha_construction_process.csv",
        "source_url": "https://www.data.go.kr/data/15087828/fileData.do",
        "source_sha256": B_SHA256,
        "raw_row_count": B_ROWS,
        "unique_record_count": 620,
        "published_or_modified_date": "2021-09-10",
        "identity_status": "HOLD",
        "metadata": {
            "ingest_id": INGEST_ID,
            "identity_status": "HOLD",
            "duplicate_path_groups": 3,
            "rows_in_duplicate_paths": 9,
            "canonical_materialization_receipt_sha": CANONICAL_MATERIALIZATION_RECEIPT_SHA,
        },
    },
    {
        "source_id": SOURCE_KALIS,
        "source_version": "20260814",
        "source_filename": "kalis_risk_profile.csv",
        "source_url": "https://www.data.go.kr/data/15090644/fileData.do",
        "source_sha256": C_SHA256,
        "raw_row_count": C_RAW_ROWS,
        "unique_record_count": C_UNIQUE_CONTENT,
        "published_or_modified_date": "2026-08-19",
        "identity_status": "PASS",
        "metadata": {
            "ingest_id": INGEST_ID,
            "identity_status": "PASS",
            "portal_row_field": C_PORTAL_ROW_FIELD,
            "legacy_prose_count": C_LEGACY_PROSE_COUNT,
            "current_prose": C_CURRENT_PROSE,
            "physical_rows": C_RAW_ROWS,
            "unique_content": C_UNIQUE_CONTENT,
            "canonical_materialization_receipt_sha": CANONICAL_MATERIALIZATION_RECEIPT_SHA,
        },
    },
)


def artifacts_available(root: Path = DEFAULT_ROOT) -> bool:
    return A_FILE.exists() and B_FILE.exists() and C_FILE.exists()


def verify_source_hashes() -> dict[str, str]:
    if not artifacts_available():
        raise FileNotFoundError("FROZEN_SOURCE_ARTIFACT_NOT_AVAILABLE")
    measured = {
        SOURCE_CIC_W: sha256_file(A_FILE),
        SOURCE_KOSHA: sha256_file(B_FILE),
        SOURCE_KALIS: sha256_file(C_FILE),
    }
    expected = {SOURCE_CIC_W: A_SHA256, SOURCE_KOSHA: B_SHA256, SOURCE_KALIS: C_SHA256}
    if measured != expected:
        raise ValueError(f"SOURCE_ARTIFACT_DRIFT {measured}")
    return measured


def two_run_plan(root: Path = DEFAULT_ROOT) -> dict:
    verify_source_hashes()
    first = build_plan(root)
    second = build_plan(root)
    if first["determinism_sha"] != second["determinism_sha"]:
        raise ValueError("RISK02 DETERMINISM mismatch between runs")
    if first["determinism_sha"] != FROZEN_DETERMINISM_SHA:
        raise ValueError(f"RISK02 DETERMINISM SHA drift {first['determinism_sha']}")
    _assert_census(first)
    return first


def _assert_census(plan: dict) -> None:
    if plan["A"]["nodes"] != A_NODES or plan["A"]["identity"] != "PASS":
        raise ValueError(f"A census {plan['A']}")
    if (
        plan["B"]["rows"] != B_ROWS
        or plan["B"]["path_identities"] != 620
        or plan["B"]["duplicate_path_groups"] != 3
        or plan["B"]["rows_in_duplicate_paths"] != 9
        or plan["B"]["duplicate_extras"] != 6
        or plan["B"]["leaf_occurrence_sum"] != B_ROWS
        or plan["B"]["identity"] != "HOLD"
        or plan["B"]["nodes"] != B_NODES
    ):
        raise ValueError(f"B census {plan['B']}")
    if (
        plan["C"]["raw_rows"] != C_RAW_ROWS
        or plan["C"]["unique_content"] != C_UNIQUE_CONTENT
        or plan["C"]["duplicate_groups"] != C_DUPLICATE_GROUPS
        or plan["C"]["duplicate_extras"] != C_DUPLICATE_EXTRAS
        or plan["C"]["occurrence_sum"] != C_RAW_ROWS
        or plan["C"]["nodes"] != C_NODES
    ):
        raise ValueError(f"C census {plan['C']}")
    c_task = sum(1 for n in plan["_plan"]["c_nodes"] if n["node_type"] == "TASK")
    if c_task != C_TASK_NODES:
        raise ValueError(f"C task nodes {c_task}")
    if plan["integrity"]["A_orphan_parent"] or plan["integrity"]["B_orphan_parent"]:
        raise ValueError("orphan parent")
    if plan["integrity"]["C_orphan_task_link"]:
        raise ValueError("orphan task")
    if len(plan["_plan"]["membership"]) != PLANNED_MEMBERSHIPS:
        raise ValueError(f"membership {len(plan['_plan']['membership'])}")


def planned_nodes(plan: dict) -> list[dict]:
    return list(plan["_plan"]["a_nodes"]) + list(plan["_plan"]["b_nodes"]) + list(plan["_plan"]["c_nodes"])


def planned_records(plan: dict) -> list[dict]:
    return list(plan["_plan"]["c_records"])


def planned_memberships(plan: dict) -> list[dict]:
    return list(plan["_plan"]["membership"])


def build_manifest(plan: dict) -> list[dict]:
    a_mem = [m for m in plan["_plan"]["membership"] if m["source_id"] == SOURCE_CIC_W]
    b_mem = [m for m in plan["_plan"]["membership"] if m["source_id"] == SOURCE_KOSHA]
    c_mem = [m for m in plan["_plan"]["membership"] if m["source_id"] == SOURCE_KALIS]
    return [
        {
            "source_id": SOURCE_CIC_W,
            "source_sha256": A_SHA256,
            "raw_row_count": str(A_NODES),
            "unique_record_count": str(A_NODES),
            "planned_node_count": str(plan["A"]["nodes"]),
            "planned_record_count": "0",
            "planned_membership_count": str(len(a_mem)),
            "identity_status": "PASS",
            "occurrence_sum": str(sum(m["occurrence_count"] for m in a_mem)),
        },
        {
            "source_id": SOURCE_KOSHA,
            "source_sha256": B_SHA256,
            "raw_row_count": str(B_ROWS),
            "unique_record_count": "620",
            "planned_node_count": str(plan["B"]["nodes"]),
            "planned_record_count": "0",
            "planned_membership_count": str(len(b_mem)),
            "identity_status": "HOLD",
            "occurrence_sum": str(plan["B"]["leaf_occurrence_sum"]),
        },
        {
            "source_id": SOURCE_KALIS,
            "source_sha256": C_SHA256,
            "raw_row_count": str(C_RAW_ROWS),
            "unique_record_count": str(C_UNIQUE_CONTENT),
            "planned_node_count": str(plan["C"]["nodes"]),
            "planned_record_count": str(C_UNIQUE_CONTENT),
            "planned_membership_count": str(len(c_mem)),
            "identity_status": "PASS",
            "occurrence_sum": str(C_RAW_ROWS),
        },
    ]


def manifest_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *MANIFEST_FIELDS)


def receipt_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *RECEIPT_FIELDS)


def _chunks(rows: list, size: int):
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def _json_literal(payload) -> str:
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))


def snapshot_insert_sql(spec: dict) -> str:
    meta = _json_literal(spec["metadata"])
    return f"""
INSERT INTO public.risk_snapshots (
  source_id, source_version, source_filename, source_url, source_sha256,
  raw_row_count, unique_record_count, published_or_modified_date, metadata, status
) VALUES (
  '{spec["source_id"]}',
  '{spec["source_version"]}',
  '{spec["source_filename"]}',
  '{spec["source_url"]}',
  '{spec["source_sha256"]}',
  {spec["raw_row_count"]},
  {spec["unique_record_count"]},
  '{spec["published_or_modified_date"]}',
  '{meta}'::jsonb,
  'STAGED'
)
ON CONFLICT (source_id, source_sha256) DO NOTHING
RETURNING id::text AS snapshot_id, source_id, status;
"""


def nodes_insert_sql(nodes: list[dict]) -> str:
    payload = [
        {
            "source_id": n["source_id"],
            "source_key": n["source_key"],
            "parent_source_key": n["parent_source_key"],
            "native_code": n["native_code"],
            "node_type": n["node_type"],
            "depth": n["depth"],
            "name_raw": n["name_raw"],
            "name_normalized": n["name_normalized"],
            "path_raw": n["path_raw"],
            "path_normalized": n["path_normalized"],
            "content_hash": n["content_hash"],
        }
        for n in nodes
    ]
    blob = _json_literal(payload)
    return f"""
INSERT INTO public.risk_source_nodes (
  source_id, source_key, parent_source_key, native_code, node_type, depth,
  name_raw, name_normalized, path_raw, path_normalized, content_hash, attrs
)
SELECT
  x->>'source_id',
  x->>'source_key',
  NULLIF(x->>'parent_source_key', ''),
  NULLIF(x->>'native_code', ''),
  x->>'node_type',
  (x->>'depth')::integer,
  x->>'name_raw',
  x->>'name_normalized',
  x->>'path_raw',
  x->>'path_normalized',
  x->>'content_hash',
  '{{}}'::jsonb
FROM jsonb_array_elements($risk02${blob}$risk02$::jsonb) AS x
ON CONFLICT (source_id, source_key) DO NOTHING;
"""


def records_insert_sql(records: list[dict]) -> str:
    payload = [
        {
            "content_key": rec["content_key"],
            "task_source_key": rec["task_source_key"],
            "raw_payload": rec["raw_payload"],
        }
        for rec in records
    ]
    blob = _json_literal(payload)
    return f"""
INSERT INTO public.risk_records (
  source_id, content_key, task_source_key, raw_payload,
  facility_big, facility_mid, facility_small, work_big, work_mid, task,
  hazard_object_big, hazard_object_mid, hazard_location_big,
  hazard_location_mid_code, hazard_location_mid, hazard_location_small,
  cause, human_damage, property_damage, likelihood, severity,
  design_control, construction_control
)
SELECT
  'KALIS_RISK_PROFILE',
  x->>'content_key',
  x->>'task_source_key',
  x->'raw_payload',
  x->'raw_payload'->>'시설물분류(대)',
  x->'raw_payload'->>'시설물분류(중)',
  x->'raw_payload'->>'시설물분류(소)',
  x->'raw_payload'->>'공종분류(대)',
  x->'raw_payload'->>'공종분류(중)',
  x->'raw_payload'->>'작업프로세스명',
  x->'raw_payload'->>'위험발생객체분류(대)',
  x->'raw_payload'->>'위험발생객체분류(중)',
  x->'raw_payload'->>'위험발생위치분류(대)',
  x->'raw_payload'->>'위험발생위치코드(중)',
  x->'raw_payload'->>'위험발생위치분류(중)',
  x->'raw_payload'->>'위험발생위치분류(소)',
  x->'raw_payload'->>'사고원인',
  x->'raw_payload'->>'인적피해',
  x->'raw_payload'->>'물적피해',
  x->'raw_payload'->>'사고가능성',
  x->'raw_payload'->>'사고심각성',
  x->'raw_payload'->>'설계단계',
  x->'raw_payload'->>'시공단계'
FROM jsonb_array_elements($risk02${blob}$risk02$::jsonb) AS x
ON CONFLICT (source_id, content_key) DO NOTHING;
"""


def memberships_insert_sql(snapshot_id: str, source_id: str, rows: list[dict]) -> str:
    payload = [
        {
            "member_kind": m["member_kind"],
            "member_key": m["member_key"],
            "occurrence_count": m["occurrence_count"],
        }
        for m in rows
        if m["source_id"] == source_id
    ]
    blob = _json_literal(payload)
    return f"""
INSERT INTO public.risk_snapshot_memberships (
  snapshot_id, member_kind, source_id, member_key, occurrence_count
)
SELECT
  '{snapshot_id}'::uuid,
  x->>'member_kind',
  '{source_id}',
  x->>'member_key',
  (x->>'occurrence_count')::integer
FROM jsonb_array_elements($risk02${blob}$risk02$::jsonb) AS x
ON CONFLICT (snapshot_id, member_kind, source_id, member_key) DO NOTHING;
"""


def write_sql_batches(plan: dict, dest: Path, node_chunk: int = 80, record_chunk: int = 40) -> dict:
    dest.mkdir(parents=True, exist_ok=True)
    files = []
    idx = 0
    for chunk in _chunks(planned_nodes(plan), node_chunk):
        idx += 1
        path = dest / f"nodes_{idx:04d}.sql"
        path.write_text(nodes_insert_sql(chunk), encoding="utf-8")
        files.append(str(path))
    rec_idx = 0
    for chunk in _chunks(planned_records(plan), record_chunk):
        rec_idx += 1
        path = dest / f"records_{rec_idx:04d}.sql"
        path.write_text(records_insert_sql(chunk), encoding="utf-8")
        files.append(str(path))
    return {"files": files, "node_batches": idx, "record_batches": rec_idx}


def render_report(plan: dict, extra: dict | None = None) -> str:
    extra = extra or {}
    return f"""---
class: records
type: report
scope: knowledge
project: risk
title: OBJ-RISK-02 INGEST-001 production source core
version: 1
status: active
owner: taiwang
---

# OBJ-RISK-02-INGEST-001 — Production Source Core Ingest

This pack loads frozen A/B/C source snapshots, nodes, records, and memberships. Mapping is not opened. Canonical DRAFT rows stay unchanged. SOURCE FILE ACCEPTED ≠ IDENTITY HOLD 해제.

```text
CANONICAL MATERIALIZATION RECEIPT SHA = {CANONICAL_MATERIALIZATION_RECEIPT_SHA}
RISK02 DETERMINISM SHA = {FROZEN_DETERMINISM_SHA}
A SHA = {A_SHA256}
B SHA = {B_SHA256}
C SHA = {C_SHA256}
```

This is an explicit evidence pack, not a classifier.

---

## Planned Census

```text
A nodes = {plan["A"]["nodes"]}
A identity = {plan["A"]["identity"]}
B raw rows = {plan["B"]["rows"]}
B path identities = {plan["B"]["path_identities"]}
B nodes = {plan["B"]["nodes"]}
B duplicate path groups = {plan["B"]["duplicate_path_groups"]}
B duplicate extras = {plan["B"]["duplicate_extras"]}
B leaf occurrence sum = {plan["B"]["leaf_occurrence_sum"]}
B identity = HOLD
C raw rows = {plan["C"]["raw_rows"]}
C unique records = {plan["C"]["unique_content"]}
C nodes = {plan["C"]["nodes"]}
C task nodes = {C_TASK_NODES}
C occurrence sum = {plan["C"]["occurrence_sum"]}
planned memberships = {len(plan["_plan"]["membership"])}
```

---

## Production

```text
production execution = {extra.get("production_execution", "NOT_EXECUTED")}
ACCEPTED snapshots = {extra.get("accepted", "0")}
risk_source_nodes = {extra.get("nodes", "0")}
risk_records = {extra.get("records", "0")}
snapshot memberships = {extra.get("memberships", "0")}
canonical DRAFT = 1110
canonical ACTIVE = 0
mapping write = 0
sector write = 0
SOURCE INGEST RECEIPT SHA = {extra.get("receipt_sha", "NONE")}
```

---

## Verdict

```text
WO-RISK-02-INGEST-001 = {extra.get("verdict", "PLAN_READY")}
MAPPING = NOT OPENED
ACTIVE TRANSITION = NOT OPENED
MERGE = NOT AUTHORIZED
NEXT = GPT INDEPENDENT VERIFY
THEN = SOURCE MAPPING GOVERNANCE
STOP
```
"""


def write_plan_artifacts(extra: dict | None = None) -> dict:
    plan = two_run_plan()
    rows = build_manifest(plan)
    write_tsv(rows, MANIFEST_PATH, MANIFEST_FIELDS)
    REPORT_PATH.write_text(render_report(plan, extra), encoding="utf-8")
    return {
        "plan": plan,
        "manifest": rows,
        "manifest_sha": manifest_sha(rows),
        "audit": {
            "A_nodes": plan["A"]["nodes"],
            "B_nodes": plan["B"]["nodes"],
            "C_nodes": plan["C"]["nodes"],
            "C_task_nodes": C_TASK_NODES,
            "memberships": len(plan["_plan"]["membership"]),
        },
    }


def write_receipt(rows: list[dict], extra: dict | None = None) -> str:
    write_tsv(rows, RECEIPT_PATH, RECEIPT_FIELDS)
    sha = receipt_sha(load_tsv(RECEIPT_PATH))
    extra = dict(extra or {})
    extra["receipt_sha"] = sha
    extra.setdefault("production_execution", "EXECUTED")
    extra.setdefault("verdict", "EVIDENCE_READY")
    plan = two_run_plan()
    REPORT_PATH.write_text(render_report(plan, extra), encoding="utf-8")
    return sha


def main() -> None:
    result = write_plan_artifacts()
    print(
        json.dumps(
            {
                "WO": INGEST_ID,
                "DETERMINISM": FROZEN_DETERMINISM_SHA,
                "MANIFEST_SHA": result["manifest_sha"],
                **result["audit"],
                "db_write": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
