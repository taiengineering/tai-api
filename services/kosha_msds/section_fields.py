"""CHEM Domain helpers for kosha_msds_sections payload fields.

Shared by Search, MSDS public page, CHEM detail, and SEO consumers.
This module has no Search-specific dependency: it only maps a
section payload to a named official field.

Section 1 (getChemDetail01) official product name:

    msdsItemCode     = A02
    msdsItemNameKor  = 제품명
    itemDetail       = actual product name
"""
from __future__ import annotations

import json
from typing import Any, Iterable, Optional


PRODUCT_NAME_ITEM_CODE = "A02"


def extract_product_name(section1_payload: Any) -> Optional[str]:
    """Return Section 1 A02 `itemDetail`, or None if absent/blank.

    Accepts the stored `payload_json` shape (item array) and the
    common wrappers (`{"items": [...]}` / JSON text). Does not
    invent a name and does not look at Search fields.
    """
    for item in _iter_items(section1_payload):
        code = item.get("msdsItemCode")
        if code is None:
            continue
        if str(code).strip() != PRODUCT_NAME_ITEM_CODE:
            continue
        detail = item.get("itemDetail")
        if detail is None:
            return None
        text = str(detail).strip()
        return text or None
    return None


def _iter_items(payload: Any) -> Iterable[dict]:
    if payload is None:
        return ()
    if isinstance(payload, str):
        raw = payload.strip()
        if not raw:
            return ()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return ()
    if isinstance(payload, list):
        return (item for item in payload if isinstance(item, dict))
    if isinstance(payload, dict):
        nested = payload.get("items")
        if isinstance(nested, list):
            return (item for item in nested if isinstance(item, dict))
        if payload.get("msdsItemCode") is not None:
            return (payload,)
    return ()
