"""Source-independent canonical identity and mapping proposal keys. No timestamps."""
from __future__ import annotations

from tools.risk02.identity import sha256_parts
from tools.risk03.contract import CONSUMER_ELIGIBLE_STATUS


def proposal_key(
    source_id: str,
    source_key: str,
    canonical_id: str | None,
    mapping_type: str,
) -> str:
    return sha256_parts(source_id, source_key, canonical_id or "", mapping_type)


def is_consumer_eligible(mapping_status: str) -> bool:
    return mapping_status == CONSUMER_ELIGIBLE_STATUS


def canonical_path(nodes_by_id: dict[str, dict], node: dict) -> str:
    parts: list[str] = []
    current: dict | None = node
    seen: set[str] = set()
    while current:
        node_id = current["id"]
        if node_id in seen:
            break
        seen.add(node_id)
        parts.append(current["name_normalized"])
        parent_id = current.get("parent_id")
        current = nodes_by_id.get(parent_id) if parent_id else None
    return " > ".join(reversed(parts))
