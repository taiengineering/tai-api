"""Deterministic seed-proposal keys. Not TAI canonical identity."""
from __future__ import annotations

from tools.risk02.identity import sha256_parts
from tools.risk03.contract import SOURCE_NODE_KIND_TO_CANONICAL


def seed_proposal_key(source_id: str, source_key: str, proposed_node_kind: str) -> str:
    return sha256_parts(source_id, source_key, proposed_node_kind)


def proposed_kind(source_node: dict) -> str:
    return SOURCE_NODE_KIND_TO_CANONICAL[source_node["node_type"]]


def parent_path(path_normalized: str) -> str:
    parts = [part for part in (path_normalized or "").split(" > ") if part]
    return " > ".join(parts[:-1]) if len(parts) > 1 else ""
