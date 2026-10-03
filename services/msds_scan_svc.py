"""MSDS Barcode / QR Scan Resolver — WO-MSDS-04C-IMPLEMENTATION-001.

Exact-match product lookup by scan identifier. No DB writes. No msds_intakes creation.
Factory-scoped only. Cross-factory isolation enforced.

scan_kind:
  BARCODE — GTIN/EAN/UPC/BARCODE identifier types, symbology-dependent priority
  QR      — QR_ALIAS only, opaque string exact match

Result states:
  MATCHED    — exactly one ACTIVE product found
  NOT_FOUND  — no matching identifier in this factory
  AMBIGUOUS  — same normalized value maps to multiple ACTIVE products
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.msds_product_svc import MsdsProductError, _require_factory_scope, normalize_identifier

_VALID_SCAN_KIND = frozenset(["BARCODE", "QR"])

# Max candidates returned for AMBIGUOUS (not a full product dump)
_AMBIGUOUS_MAX = 20

# Identifier type priority lists by symbology
_BARCODE_SYMBOLOGY_TYPES: Dict[str, List[str]] = {
    # EAN family
    "EAN_13":     ["EAN", "GTIN", "BARCODE"],
    "EAN_8":      ["EAN", "GTIN", "BARCODE"],
    # UPC family
    "UPC_A":      ["UPC", "GTIN", "BARCODE"],
    "UPC_E":      ["UPC", "GTIN", "BARCODE"],
    # GTIN / ITF-14
    "GTIN_14":    ["GTIN", "BARCODE"],
    "ITF_14":     ["GTIN", "BARCODE"],
    # Generic — broadest search
    "CODE_128":   ["BARCODE", "GTIN", "EAN", "UPC"],
    "CODE_39":    ["BARCODE", "GTIN", "EAN", "UPC"],
    "ITF":        ["BARCODE", "GTIN", "EAN", "UPC"],
    "CODABAR":    ["BARCODE", "GTIN", "EAN", "UPC"],
    "DATA_MATRIX": ["BARCODE", "GTIN", "EAN", "UPC"],
    "UNKNOWN":    ["BARCODE", "GTIN", "EAN", "UPC"],
}
_BARCODE_DEFAULT_TYPES: List[str] = ["BARCODE", "GTIN", "EAN", "UPC"]

_QR_TYPES: List[str] = ["QR_ALIAS"]


def _resolve_identifier_types(scan_kind: str, symbology: Optional[str]) -> List[str]:
    if scan_kind == "QR":
        return _QR_TYPES
    sym = (symbology or "").strip().upper()
    return _BARCODE_SYMBOLOGY_TYPES.get(sym, _BARCODE_DEFAULT_TYPES)


def _validate_scan_input(scan_kind: str, raw_value: str) -> None:
    if scan_kind not in _VALID_SCAN_KIND:
        raise MsdsProductError(422, "INVALID_SCAN_KIND", f"scan_kind은 BARCODE 또는 QR만 허용됩니다. 받은 값: {scan_kind!r}")

    if not raw_value or not raw_value.strip():
        raise MsdsProductError(422, "SCAN_VALUE_EMPTY", "raw_value는 비어있을 수 없습니다.")

    # Control-character / NUL guard
    if any(ord(c) < 32 and c not in ("\t",) for c in raw_value):
        raise MsdsProductError(422, "SCAN_VALUE_INVALID", "raw_value에 허용되지 않는 제어 문자가 포함되어 있습니다.")

    max_len = 2048 if scan_kind == "QR" else 256
    if len(raw_value) > max_len:
        raise MsdsProductError(422, "SCAN_VALUE_TOO_LONG", f"raw_value가 최대 길이 {max_len}자를 초과합니다.")


def _lookup_identifiers(
    sb,
    factory_id: str,
    normalized_value: str,
    identifier_types: List[str],
) -> List[Dict[str, Any]]:
    """Exact match against chemical_product_identifiers. ACTIVE only."""
    try:
        res = (
            sb.table("chemical_product_identifiers")
            .select("id, chemical_product_id, identifier_type, identifier_value, identifier_normalized")
            .eq("factory_id", factory_id)
            .eq("identifier_normalized", normalized_value)
            .in_("identifier_type", identifier_types)
            .eq("is_active", True)
            .execute()
        )
    except Exception as e:
        raise MsdsProductError(500, "SCAN_LOOKUP_FAILED", f"식별자 조회 중 오류가 발생했습니다: {str(e)[:200]}")
    return res.data or []


def _get_active_product(sb, factory_id: str, product_id: str) -> Optional[Dict[str, Any]]:
    """Return ACTIVE product row or None. Never raise."""
    try:
        res = (
            sb.table("chemical_products")
            .select("id, product_name, manufacturer_name, identity_status, status_code")
            .eq("id", product_id)
            .eq("factory_id", factory_id)
            .eq("status_code", "ACTIVE")
            .limit(1)
            .execute()
        )
        return res.data[0] if res.data else None
    except Exception:
        return None


def _get_current_msds_summary(sb, factory_id: str, product_id: str) -> Dict[str, Any]:
    """Return {status, current_version_id, version_no} without raising."""
    try:
        res = (
            sb.table("customer_msds_versions")
            .select("id, version_no")
            .eq("chemical_product_id", product_id)
            .eq("factory_id", factory_id)
            .eq("is_current", True)
            .eq("record_status", "ACTIVE")
            .limit(1)
            .execute()
        )
        if res.data:
            row = res.data[0]
            return {"status": "AVAILABLE", "current_version_id": row["id"], "version_no": row["version_no"]}
    except Exception:
        pass
    return {"status": "MISSING", "current_version_id": None, "version_no": None}


def resolve_scan(
    sb,
    current_user: Dict[str, Any],
    factory_id: str,
    scan_kind: str,
    raw_value: str,
    symbology: Optional[str] = None,
) -> Dict[str, Any]:
    """Resolve a barcode/QR scan to a chemical product.

    Returns a dict with state MATCHED | NOT_FOUND | AMBIGUOUS.
    No DB writes. No msds_intakes creation.
    """
    # 1. Input validation
    _validate_scan_input(scan_kind, raw_value)

    # 2. Factory scope guard (raises MsdsProductError on failure)
    _require_factory_scope(sb, current_user, factory_id)

    # 3. Normalize
    normalized_value = normalize_identifier(raw_value)
    identifier_types = _resolve_identifier_types(scan_kind, symbology)

    scan_summary = {
        "scan_kind": scan_kind,
        "raw_value": raw_value,
        "normalized_value": normalized_value,
        "symbology": symbology,
        "identifier_types_considered": identifier_types,
    }

    # 4. Exact identifier lookup
    identifier_rows = _lookup_identifiers(sb, factory_id, normalized_value, identifier_types)

    if not identifier_rows:
        return {
            "state": "NOT_FOUND",
            "scan": scan_summary,
            "product": None,
            "matched_identifiers": [],
            "msds": None,
        }

    # 5. Collect distinct ACTIVE products
    seen_product_ids: Dict[str, List[Dict[str, Any]]] = {}
    for row in identifier_rows:
        pid = row["chemical_product_id"]
        seen_product_ids.setdefault(pid, []).append({
            "id": row["id"],
            "identifier_type": row["identifier_type"],
            "identifier_value": row["identifier_value"],
        })

    active_products: List[Dict[str, Any]] = []
    active_identifier_map: Dict[str, List[Dict[str, Any]]] = {}
    for pid, ident_rows in seen_product_ids.items():
        product = _get_active_product(sb, factory_id, pid)
        if product:
            active_products.append(product)
            active_identifier_map[pid] = ident_rows

    if not active_products:
        # All matching identifiers belong to INACTIVE products
        return {
            "state": "NOT_FOUND",
            "scan": scan_summary,
            "product": None,
            "matched_identifiers": [],
            "msds": None,
        }

    # 6. AMBIGUOUS — multiple distinct ACTIVE products
    if len(active_products) > 1:
        candidates = [
            {
                "product_id": p["id"],
                "product_name": p["product_name"],
                "manufacturer_name": p.get("manufacturer_name"),
            }
            for p in active_products[:_AMBIGUOUS_MAX]
        ]
        return {
            "state": "AMBIGUOUS",
            "scan": scan_summary,
            "candidates": candidates,
        }

    # 7. MATCHED
    product = active_products[0]
    pid = product["id"]
    msds = _get_current_msds_summary(sb, factory_id, pid)

    return {
        "state": "MATCHED",
        "scan": scan_summary,
        "product": {
            "id": product["id"],
            "product_name": product["product_name"],
            "manufacturer_name": product.get("manufacturer_name"),
            "identity_status": product.get("identity_status"),
            "status_code": product["status_code"],
        },
        "matched_identifiers": active_identifier_map[pid],
        "msds": msds,
    }
