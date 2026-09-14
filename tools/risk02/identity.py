"""Deterministic RISK-02 identity helpers. No timestamps, UUIDs, or row numbers in hashes."""
from __future__ import annotations

import hashlib
from collections import Counter

from tools.risk01.analyze_3way import norm_name
from tools.risk02.contract import C_HEADERS, HASH_JOIN, SOURCE_KOSHA


def sha256_parts(*parts: str) -> str:
    return hashlib.sha256(HASH_JOIN.join(parts).encode("utf-8")).hexdigest()


def path_source_key(*raw_parts: str) -> str:
    return sha256_parts(*(norm_name(part) for part in raw_parts))


def node_content_hash(
    source_id: str,
    source_key: str,
    parent_source_key: str | None,
    native_code: str | None,
    node_type: str,
    depth: int,
    name_raw: str,
    path_raw: str,
) -> str:
    return sha256_parts(
        source_id,
        source_key,
        parent_source_key or "",
        native_code or "",
        node_type,
        str(depth),
        name_raw,
        path_raw,
    )


def c_content_key(fields: list[str] | tuple[str, ...]) -> str:
    if len(fields) != len(C_HEADERS):
        raise ValueError("C content hash requires all 19 source fields")
    return sha256_parts(*fields)


def c_raw_payload(fields: list[str] | tuple[str, ...]) -> dict[str, str]:
    return {header: fields[i] for i, header in enumerate(C_HEADERS)}


def b_path_tuple(root: str, mid: str, leaf: str) -> tuple[str, str, str]:
    return (norm_name(root), norm_name(mid), norm_name(leaf))


def b_row_identity(root: str, mid: str, leaf: str) -> dict:
    raw = (root, mid, leaf)
    normalized = b_path_tuple(root, mid, leaf)
    nulls = sum(1 for part in normalized if not part)
    return {
        "source_id": SOURCE_KOSHA,
        "source_key": path_source_key(*raw),
        "path_raw": " > ".join(raw),
        "path_normalized": " > ".join(normalized),
        "null_component_count": nulls,
        "row_number_excluded": True,
    }


def c_task_key(work_big: str, work_mid: str, task: str) -> str:
    return path_source_key(work_big, work_mid, task)


def aggregate_occurrences(keys: list[str]) -> dict:
    counts = Counter(keys)
    groups = {key: n for key, n in counts.items() if n > 1}
    extras = sum(n - 1 for n in groups.values())
    return {
        "unique": len(counts),
        "duplicate_groups": len(groups),
        "duplicate_extras": extras,
        "occurrence_sum": sum(counts.values()),
        "counts": dict(counts),
    }


def forbidden_identity_inputs(payload: dict) -> list[str]:
    banned = (
        "created_at",
        "updated_at",
        "downloaded_at",
        "id",
        "uuid",
        "row_number",
        "번호",
    )
    return [key for key in banned if key in payload]
