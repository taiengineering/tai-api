"""Canonical source_content_hash. Timestamps and local ids are excluded."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Optional

from services.kosha_msds.contract import ALLOWED_SECTIONS, LIST_IDENTITY_FIELDS
from services.kosha_msds.parse import canonical_section_items, normalize_optional


def _list_identity(item: Mapping[str, Optional[str]]) -> dict[str, Optional[str]]:
    return {field: normalize_optional(item.get(field)) for field in LIST_IDENTITY_FIELDS}


def canonical_payload(
    chem_id: str,
    list_item: Mapping[str, Optional[str]],
    sections: Mapping[str, list[dict[str, Optional[str]]]],
) -> dict[str, Any]:
    section_map: dict[str, Any] = {}
    for n in ALLOWED_SECTIONS:
        key = f"{n:02d}"
        section_map[key] = canonical_section_items(list(sections.get(key, [])))
    return {
        "chemId": chem_id,
        "list": _list_identity(list_item),
        "sections": section_map,
    }


def source_content_hash(
    chem_id: str,
    list_item: Mapping[str, Optional[str]],
    sections: Mapping[str, list[dict[str, Optional[str]]]],
) -> str:
    payload = canonical_payload(chem_id, list_item, sections)
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def section_hash(items: list[dict[str, Optional[str]]]) -> str:
    text = json.dumps(
        canonical_section_items(items),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
