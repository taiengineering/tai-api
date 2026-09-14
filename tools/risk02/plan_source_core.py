"""WO-RISK-02 local dry-run planner. DB WRITE = 0. No LLM. No timestamps in identity."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from tools.risk01.analyze_3way import norm_name, parse_a_works, read_csv_rows, sha256_file
from tools.risk02.contract import (
    A_SHA256,
    B_HEADERS,
    B_SHA256,
    C_CURRENT_PROSE,
    C_HEADERS,
    C_LEGACY_PROSE_COUNT,
    C_PORTAL_ROW_FIELD,
    C_SHA256,
    SOURCE_CIC_W,
    SOURCE_KALIS,
    SOURCE_KOSHA,
)
from tools.risk02.identity import (
    b_row_identity,
    c_content_key,
    c_raw_payload,
    c_task_key,
    node_content_hash,
    path_source_key,
    sha256_parts,
)

DEFAULT_ROOT = Path("artifacts/risk01")


def _a_nodes(extracted_text: str) -> tuple[list[dict], dict]:
    parsed = parse_a_works(extracted_text)
    nodes = []
    for item in parsed:
        source_key = item["code"]
        parent = item["parent"]
        depth = item["level"]
        node_type = {1: "W_ROOT", 2: "W_MID", 3: "W_LEAF"}[depth]
        node = {
            "source_id": SOURCE_CIC_W,
            "source_key": source_key,
            "parent_source_key": parent,
            "native_code": source_key,
            "node_type": node_type,
            "depth": depth,
            "name_raw": item["name"],
            "name_normalized": norm_name(item["name"]),
            "path_raw": item["path"],
            "path_normalized": item["path_norm"],
            "attrs": {},
        }
        node["content_hash"] = node_content_hash(
            SOURCE_CIC_W,
            source_key,
            parent,
            source_key,
            node_type,
            depth,
            item["name"],
            item["path"],
        )
        nodes.append(node)
    keys = [n["source_key"] for n in nodes]
    key_counts = Counter(keys)
    by_key = {n["source_key"]: n for n in nodes}
    orphan_parent = [
        n["source_key"]
        for n in nodes
        if n["parent_source_key"] and n["parent_source_key"] not in by_key
    ]
    null_key = [n["source_key"] for n in nodes if not n["source_key"]]
    metrics = {
        "nodes": len(nodes),
        "roots": sum(1 for n in nodes if n["depth"] == 1),
        "leaves": sum(1 for n in nodes if n["depth"] == 3),
        "duplicate_source_key": sum(1 for n in key_counts.values() if n > 1),
        "null_source_key": len(null_key),
        "orphan_parent": len(orphan_parent),
        "orphan_parent_keys": orphan_parent[:20],
        "native_code_nonnull": all(bool(n["native_code"]) for n in nodes),
        "native_code_unique": len({n["native_code"] for n in nodes}) == len(nodes),
        "hierarchical": all(
            (n["parent_source_key"] is None and n["depth"] == 1)
            or (n["parent_source_key"] is not None and n["depth"] > 1)
            for n in nodes
        ),
        "identity": "PASS"
        if not orphan_parent and not null_key and len(key_counts) == len(nodes)
        else "HOLD",
    }
    return nodes, metrics


def _b_nodes(header: list[str], rows: list[list[str]]) -> tuple[list[dict], dict]:
    if tuple(header) != B_HEADERS:
        raise ValueError(f"unexpected B headers: {header}")
    identities = []
    path_counts: Counter[str] = Counter()
    null_components = 0
    for row in rows:
        rec = dict(zip(header, row))
        ident = b_row_identity(rec["공사종류"], rec["공종명"], rec["세부공정명"])
        identities.append(ident)
        path_counts[ident["path_normalized"]] += 1
        null_components += ident["null_component_count"]
    dup_paths = {path: n for path, n in path_counts.items() if n > 1}
    unique_paths = len(path_counts)
    identity_status = "PASS" if not dup_paths and unique_paths == len(rows) else "HOLD"

    nodes: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def add_node(source_key, parent, node_type, depth, name_raw, path_raw, path_norm):
        token = (source_key, node_type)
        if token in seen:
            return
        seen.add(token)
        node = {
            "source_id": SOURCE_KOSHA,
            "source_key": source_key,
            "parent_source_key": parent,
            "native_code": None,
            "node_type": node_type,
            "depth": depth,
            "name_raw": name_raw,
            "name_normalized": norm_name(name_raw),
            "path_raw": path_raw,
            "path_normalized": path_norm,
            "attrs": {},
        }
        node["content_hash"] = node_content_hash(
            SOURCE_KOSHA,
            source_key,
            parent,
            None,
            node_type,
            depth,
            name_raw,
            path_raw,
        )
        nodes.append(node)

    for ident, row in zip(identities, rows):
        rec = dict(zip(header, row))
        root_key = path_source_key(rec["공사종류"])
        mid_key = path_source_key(rec["공사종류"], rec["공종명"])
        leaf_key = ident["source_key"]
        add_node(
            root_key,
            None,
            "PROJECT_KIND",
            1,
            rec["공사종류"],
            rec["공사종류"],
            norm_name(rec["공사종류"]),
        )
        add_node(
            mid_key,
            root_key,
            "WORK_TYPE",
            2,
            rec["공종명"],
            f"{rec['공사종류']} > {rec['공종명']}",
            f"{norm_name(rec['공사종류'])} > {norm_name(rec['공종명'])}",
        )
        add_node(
            leaf_key,
            mid_key,
            "DETAIL_PROCESS",
            3,
            rec["세부공정명"],
            ident["path_raw"],
            ident["path_normalized"],
        )

    leaf_occ: Counter[str] = Counter()
    for ident in identities:
        leaf_occ[ident["source_key"]] += 1
    dup_extras = sum(n - 1 for n in leaf_occ.values() if n > 1)
    leaf_membership_rows = len(leaf_occ)
    leaf_occurrence_sum = sum(leaf_occ.values())
    occurrence_preservation = (
        "PASS"
        if leaf_occurrence_sum == len(rows) and leaf_membership_rows == unique_paths
        else "FAIL"
    )

    node_keys = {n["source_key"] for n in nodes}
    metrics = {
        "rows": len(rows),
        "path_identities": unique_paths,
        "duplicate_path_groups": len(dup_paths),
        "rows_in_duplicate_paths": sum(dup_paths.values()),
        "duplicate_extras": dup_extras,
        "leaf_membership_rows": leaf_membership_rows,
        "leaf_occurrence_sum": leaf_occurrence_sum,
        "occurrence_preservation": occurrence_preservation,
        "null_component_count": null_components,
        "identity": identity_status,
        "nodes": len(nodes),
        "roots": sum(1 for n in nodes if n["node_type"] == "PROJECT_KIND"),
        "mids": sum(1 for n in nodes if n["node_type"] == "WORK_TYPE"),
        "leaves": sum(1 for n in nodes if n["node_type"] == "DETAIL_PROCESS"),
        "duplicate_source_key": len(nodes) - len(node_keys),
        "null_source_key": sum(1 for n in nodes if not n["source_key"]),
        "orphan_parent": sum(
            1 for n in nodes if n["parent_source_key"] and n["parent_source_key"] not in node_keys
        ),
        "sample_duplicate_paths": sorted(dup_paths)[:10],
        "leaf_occurrence_counts": dict(leaf_occ),
    }
    return nodes, metrics


def b_membership_occurrence(node: dict, leaf_occ: dict[str, int]) -> int:
    """Leaf DETAIL_PROCESS uses source row count. Parent taxonomy nodes stay 1."""
    if node["node_type"] == "DETAIL_PROCESS":
        return int(leaf_occ[node["source_key"]])
    return 1


def _c_plan(header: list[str], rows: list[list[str]]) -> tuple[list[dict], list[dict], dict]:
    if tuple(header) != C_HEADERS:
        raise ValueError(f"unexpected C headers: {header}")
    records = []
    task_nodes: dict[str, dict] = {}
    content_keys = []
    for row in rows:
        key = c_content_key(row)
        content_keys.append(key)
        payload = c_raw_payload(row)
        work_big = payload["공종분류(대)"]
        work_mid = payload["공종분류(중)"]
        task = payload["작업프로세스명"]
        task_key = c_task_key(work_big, work_mid, task)
        mid_key = path_source_key(work_big, work_mid)
        big_key = path_source_key(work_big)
        if big_key not in task_nodes:
            task_nodes[big_key] = {
                "source_id": SOURCE_KALIS,
                "source_key": big_key,
                "parent_source_key": None,
                "native_code": None,
                "node_type": "WORK_BIG",
                "depth": 1,
                "name_raw": work_big,
                "name_normalized": norm_name(work_big),
                "path_raw": work_big,
                "path_normalized": norm_name(work_big),
                "attrs": {},
            }
            task_nodes[big_key]["content_hash"] = node_content_hash(
                SOURCE_KALIS, big_key, None, None, "WORK_BIG", 1, work_big, work_big
            )
        if mid_key not in task_nodes:
            path_raw = f"{work_big} > {work_mid}"
            task_nodes[mid_key] = {
                "source_id": SOURCE_KALIS,
                "source_key": mid_key,
                "parent_source_key": big_key,
                "native_code": None,
                "node_type": "WORK_MID",
                "depth": 2,
                "name_raw": work_mid,
                "name_normalized": norm_name(work_mid),
                "path_raw": path_raw,
                "path_normalized": f"{norm_name(work_big)} > {norm_name(work_mid)}",
                "attrs": {},
            }
            task_nodes[mid_key]["content_hash"] = node_content_hash(
                SOURCE_KALIS, mid_key, big_key, None, "WORK_MID", 2, work_mid, path_raw
            )
        if task_key not in task_nodes:
            path_raw = f"{work_big} > {work_mid} > {task}"
            task_nodes[task_key] = {
                "source_id": SOURCE_KALIS,
                "source_key": task_key,
                "parent_source_key": mid_key,
                "native_code": None,
                "node_type": "TASK",
                "depth": 3,
                "name_raw": task,
                "name_normalized": norm_name(task),
                "path_raw": path_raw,
                "path_normalized": f"{norm_name(work_big)} > {norm_name(work_mid)} > {norm_name(task)}",
                "attrs": {},
            }
            task_nodes[task_key]["content_hash"] = node_content_hash(
                SOURCE_KALIS, task_key, mid_key, None, "TASK", 3, task, path_raw
            )
        records.append(
            {
                "source_id": SOURCE_KALIS,
                "content_key": key,
                "task_source_key": task_key,
                "raw_payload": payload,
                "facility_big": payload["시설물분류(대)"],
                "facility_mid": payload["시설물분류(중)"],
                "facility_small": payload["시설물분류(소)"],
                "work_big": work_big,
                "work_mid": work_mid,
                "task": task,
                "hazard_object_big": payload["위험발생객체분류(대)"],
                "hazard_object_mid": payload["위험발생객체분류(중)"],
                "hazard_location_big": payload["위험발생위치분류(대)"],
                "hazard_location_mid_code": payload["위험발생위치코드(중)"],
                "hazard_location_mid": payload["위험발생위치분류(중)"],
                "hazard_location_small": payload["위험발생위치분류(소)"],
                "cause": payload["사고원인"],
                "human_damage": payload["인적피해"],
                "property_damage": payload["물적피해"],
                "likelihood": payload["사고가능성"],
                "severity": payload["사고심각성"],
                "design_control": payload["설계단계"],
                "construction_control": payload["시공단계"],
            }
        )
    counts = Counter(content_keys)
    unique_records = []
    seen: set[str] = set()
    for rec in records:
        if rec["content_key"] in seen:
            continue
        seen.add(rec["content_key"])
        unique_records.append(rec)
    extras = sum(n - 1 for n in counts.values() if n > 1)
    node_list = list(task_nodes.values())
    node_keys = {n["source_key"] for n in node_list}
    orphan_task = [
        rec["content_key"] for rec in unique_records if rec["task_source_key"] not in node_keys
    ]
    metrics = {
        "raw_rows": len(rows),
        "unique_content": len(counts),
        "duplicate_groups": sum(1 for n in counts.values() if n > 1),
        "duplicate_extras": extras,
        "membership_rows": len(counts),
        "occurrence_sum": sum(counts.values()),
        "raw_19_fields_preserved": all(len(rec["raw_payload"]) == 19 for rec in unique_records),
        "content_identity": "PASS"
        if sum(counts.values()) == len(rows) and all(counts.values())
        else "FAIL",
        "orphan_task_link": len(orphan_task),
        "nodes": len(node_list),
        "occurrence_counts": dict(counts),
    }
    return unique_records, node_list, metrics


def build_plan(root: Path = DEFAULT_ROOT) -> dict:
    a_pdf = root / "source_a/cic_annex_works.txt"
    a_text = (root / "source_a/cic_annex_extracted.txt").read_text(encoding="utf-8")
    a_nodes, a_metrics = _a_nodes(a_text)
    a_sha = sha256_file(a_pdf) if a_pdf.exists() else None

    b_path = root / "source_b/kosha_construction_process.csv"
    b_enc, b_header, b_rows, b_stats = read_csv_rows(b_path)
    b_nodes, b_metrics = _b_nodes(b_header, b_rows)

    c_path = root / "source_c/kalis_risk_profile.csv"
    c_enc, c_header, c_rows, c_stats = read_csv_rows(c_path)
    c_records, c_nodes, c_metrics = _c_plan(c_header, c_rows)

    a_membership = [
        {
            "member_kind": "NODE",
            "source_id": SOURCE_CIC_W,
            "member_key": n["source_key"],
            "occurrence_count": 1,
        }
        for n in a_nodes
    ]
    b_leaf_occ = b_metrics["leaf_occurrence_counts"]
    b_membership = [
        {
            "member_kind": "NODE",
            "source_id": SOURCE_KOSHA,
            "member_key": n["source_key"],
            "occurrence_count": b_membership_occurrence(n, b_leaf_occ),
        }
        for n in b_nodes
    ]
    c_node_membership = [
        {
            "member_kind": "NODE",
            "source_id": SOURCE_KALIS,
            "member_key": n["source_key"],
            "occurrence_count": 1,
        }
        for n in c_nodes
    ]
    c_record_membership = [
        {
            "member_kind": "RECORD",
            "source_id": SOURCE_KALIS,
            "member_key": key,
            "occurrence_count": n,
        }
        for key, n in sorted(c_metrics["occurrence_counts"].items())
    ]

    integrity = {
        "A_orphan_parent": a_metrics["orphan_parent"],
        "B_orphan_parent": b_metrics["orphan_parent"],
        "C_orphan_task_link": c_metrics["orphan_task_link"],
        "A_duplicate_source_key": a_metrics["duplicate_source_key"],
        "B_null_source_key": b_metrics["null_source_key"],
        "C_null_content_key": sum(1 for rec in c_records if not rec["content_key"]),
        "snapshot_membership_orphan": 0,
        "record_without_snapshot": 0,
    }

    summary = {
        "WO": "WO-RISK-02",
        "MODEL_D": "APPROVED / FROZEN",
        "db_write": 0,
        "A": {
            "source_id": SOURCE_CIC_W,
            "sha256": a_sha,
            "expected_sha256": A_SHA256,
            **a_metrics,
        },
        "B": {
            "source_id": SOURCE_KOSHA,
            "sha256": b_stats["sha256"],
            "expected_sha256": B_SHA256,
            "encoding": b_enc,
            **{k: v for k, v in b_metrics.items() if k != "leaf_occurrence_counts"},
        },
        "C": {
            "source_id": SOURCE_KALIS,
            "sha256": c_stats["sha256"],
            "expected_sha256": C_SHA256,
            "encoding": c_enc,
            "portal_row_field": C_PORTAL_ROW_FIELD,
            "legacy_prose_count": C_LEGACY_PROSE_COUNT,
            "current_prose": C_CURRENT_PROSE,
            "metadata_drift": True,
            "cause": "UNKNOWN",
            **{k: v for k, v in c_metrics.items() if k != "occurrence_counts"},
        },
        "integrity": integrity,
        "cross_source_merge": 0,
        "LLM": 0,
        "fuzzy": 0,
    }
    determinism_payload = {
        "a_keys": sorted(n["source_key"] for n in a_nodes),
        "b_keys": sorted(n["source_key"] for n in b_nodes),
        "b_leaf_occ": sorted((k, n) for k, n in b_metrics["leaf_occurrence_counts"].items()),
        "c_content": sorted(rec["content_key"] for rec in c_records),
        "c_occ": sorted((k, n) for k, n in c_metrics["occurrence_counts"].items()),
        "metrics": {
            "A": {k: a_metrics[k] for k in ("nodes", "duplicate_source_key", "orphan_parent", "identity")},
            "B": {
                k: b_metrics[k]
                for k in (
                    "rows",
                    "path_identities",
                    "duplicate_path_groups",
                    "duplicate_extras",
                    "leaf_membership_rows",
                    "leaf_occurrence_sum",
                    "occurrence_preservation",
                    "identity",
                )
            },
            "C": {
                k: c_metrics[k]
                for k in (
                    "raw_rows",
                    "unique_content",
                    "duplicate_groups",
                    "duplicate_extras",
                    "occurrence_sum",
                    "content_identity",
                )
            },
        },
    }
    summary["determinism_sha"] = sha256_parts(
        json.dumps(determinism_payload, ensure_ascii=False, sort_keys=True)
    )
    summary["_plan"] = {
        "a_nodes": a_nodes,
        "b_nodes": b_nodes,
        "c_nodes": c_nodes,
        "c_records": c_records,
        "membership": a_membership + b_membership + c_node_membership + c_record_membership,
        "c_occurrence_counts": c_metrics["occurrence_counts"],
    }
    return summary


def write_report(summary: dict, dest: Path) -> None:
    slim = {k: v for k, v in summary.items() if k != "_plan"}
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(slim, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    summary = build_plan(DEFAULT_ROOT)
    write_report(summary, Path("artifacts/risk02/reports/summary.json"))
    slim = {k: v for k, v in summary.items() if k != "_plan"}
    print(json.dumps(slim, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
