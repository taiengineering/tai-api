"""MSDS Chemical Product orchestration — /me/msds/factories/{factory_id}/products.

factory_id 는 URL path에서 수신. factory 접근 권한은 role_data_scope tier 기반.
company_id 는 Product/Identifier field 아님 — factories 테이블을 통해 역참조.
기존 factory_materials / material_legal_master / leg-prod 불변.
"""
from __future__ import annotations

import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

from services.time import now_kst, serialize_external_utc

VALID_IDENTITY_STATUS = frozenset(["DRAFT", "CONFIRMED", "REVIEW_REQUIRED"])
VALID_STATUS_CODE = frozenset(["ACTIVE", "INACTIVE"])
VALID_CREATED_SOURCE = frozenset(["MANUAL", "PDF", "PHOTO", "EXCEL", "MIGRATION"])
VALID_IDENTIFIER_TYPE = frozenset([
    "GTIN", "EAN", "UPC", "BARCODE",
    "MANUFACTURER_CODE", "SUPPLIER_CODE", "INTERNAL_CODE",
    "QR_ALIAS", "OTHER",
])


class MsdsProductError(Exception):
    def __init__(self, status_code: int, code: str, detail: str):
        self.status_code = status_code
        self.code = code
        self.detail = detail
        super().__init__(detail)


def _now_iso() -> str:
    return serialize_external_utc(now_kst())


# ─── Normalization ────────────────────────────────────────────────────────────

def normalize_product_name(raw: str) -> str:
    """trim + casefold + collapse whitespace."""
    if not raw:
        raise MsdsProductError(400, "INVALID_PRODUCT_NAME", "product_name은 비어있을 수 없습니다.")
    s = raw.strip().casefold()
    s = re.sub(r"\s+", " ", s)
    if not s:
        raise MsdsProductError(400, "INVALID_PRODUCT_NAME", "product_name은 비어있을 수 없습니다.")
    return s


def normalize_manufacturer(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    s = raw.strip().casefold()
    s = re.sub(r"\s+", " ", s)
    return s if s else None


def normalize_identifier(raw: str) -> str:
    """trim + collapse whitespace. leading zero 보존 (numeric cast 금지)."""
    s = raw.strip()
    s = re.sub(r"\s+", " ", s)
    return s


# ─── Factory Scope Guard ──────────────────────────────────────────────────────

def _resolve_scope_strict(sb, role_code) -> Optional[str]:
    """role_data_scope strict 조회. 미정의/lookup 실패/빈 scope → None (fail-closed용).

    company_scope._scope()의 silent TEAM fallback을 우회하여 명시적 scope만 신뢰.
    """
    if not role_code:
        return None
    try:
        res = (
            sb.table("role_data_scope")
            .select("scope_type")
            .eq("role_code", role_code)
            .limit(1)
            .execute()
        )
        if not res.data or not res.data[0].get("scope_type"):
            return None
        return res.data[0]["scope_type"]
    except Exception:
        return None


def _require_factory_scope(sb, current_user: Dict[str, Any], factory_id: str) -> str:
    """role_data_scope strict 조회 기반 factory 접근 검증. 검증된 factory_id 반환.

    tier 별 최종 계약:
      ALL      — factory 존재 확인만 (플랫폼 관리자)
      COMPANY  — factory.company_id == user.company_id
      FACTORY  — factory_id == user.factory_id AND 동일 company
      TEAM     — factory_id == user.factory_id AND 동일 company (team_id 컬럼 없음)
      ASSIGNED — factory_id == user.factory_id AND 동일 company; 미배정 → DENY
      그 외(PLATFORM/unknown/lookup 실패) — fail-closed (404)
    """
    tier = _resolve_scope_strict(sb, current_user.get("role_code"))

    if tier is None:
        # role 미정의 / lookup 실패 / scope_type 없음 → fail-closed (silent TEAM 불허)
        raise MsdsProductError(404, "FACTORY_NOT_FOUND", "시설을 찾을 수 없습니다.")

    if tier == "ALL":
        res = sb.table("factories").select("id").eq("id", factory_id).limit(1).execute()
        if not res.data:
            raise MsdsProductError(404, "FACTORY_NOT_FOUND", "시설을 찾을 수 없습니다.")
        return factory_id

    company_id = current_user.get("company_id")
    if not company_id:
        raise MsdsProductError(403, "NO_COMPANY", "회사 정보가 없습니다.")

    if tier == "COMPANY":
        res = (
            sb.table("factories")
            .select("id")
            .eq("id", factory_id)
            .eq("company_id", company_id)
            .limit(1)
            .execute()
        )
        if not res.data:
            raise MsdsProductError(404, "FACTORY_NOT_FOUND", "시설을 찾을 수 없습니다.")
        return factory_id

    if tier in ("FACTORY", "TEAM"):
        user_fid = current_user.get("factory_id")
        if not user_fid or factory_id != user_fid:
            raise MsdsProductError(404, "FACTORY_NOT_FOUND", "시설을 찾을 수 없습니다.")
        res = (
            sb.table("factories")
            .select("id")
            .eq("id", factory_id)
            .eq("company_id", company_id)
            .limit(1)
            .execute()
        )
        if not res.data:
            raise MsdsProductError(404, "FACTORY_NOT_FOUND", "시설을 찾을 수 없습니다.")
        return factory_id

    if tier == "ASSIGNED":
        user_fid = current_user.get("factory_id")
        if not user_fid:
            # factory_id scoped resource — 미배정 ASSIGNED는 DENY (company fallback 금지)
            raise MsdsProductError(404, "FACTORY_NOT_FOUND", "시설을 찾을 수 없습니다.")
        if factory_id != user_fid:
            raise MsdsProductError(404, "FACTORY_NOT_FOUND", "시설을 찾을 수 없습니다.")
        res = (
            sb.table("factories")
            .select("id")
            .eq("id", factory_id)
            .eq("company_id", company_id)
            .limit(1)
            .execute()
        )
        if not res.data:
            raise MsdsProductError(404, "FACTORY_NOT_FOUND", "시설을 찾을 수 없습니다.")
        return factory_id

    # PLATFORM 등 알 수 없는 tier → fail-closed
    raise MsdsProductError(404, "FACTORY_NOT_FOUND", "시설을 찾을 수 없습니다.")


# ─── Duplicate Candidate Detection ───────────────────────────────────────────

def _check_identifier_duplicates(
    sb, factory_id: str, product_name: str,
    manufacturer_name: Optional[str],
    identifiers: Optional[List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """Create 요청에 대한 중복 후보 탐색 (factory 기준). 자동 merge 없음."""
    candidates = []

    if identifiers:
        for ident in identifiers:
            itype = ident.get("identifier_type", "")
            inorm = normalize_identifier(ident.get("identifier_value", ""))
            res = (
                sb.table("chemical_product_identifiers")
                .select("chemical_product_id, identifier_type, identifier_normalized")
                .eq("factory_id", factory_id)
                .eq("identifier_type", itype)
                .eq("identifier_normalized", inorm)
                .eq("is_active", True)
                .execute()
            )
            for row in (res.data or []):
                pid = row["chemical_product_id"]
                if not any(c["product_id"] == pid for c in candidates):
                    prod_res = (
                        sb.table("chemical_products")
                        .select("id, product_name, manufacturer_name")
                        .eq("id", pid)
                        .eq("factory_id", factory_id)
                        .limit(1)
                        .execute()
                    )
                    if prod_res.data:
                        p = prod_res.data[0]
                        candidates.append({
                            "product_id": p["id"],
                            "reason": "EXACT_IDENTIFIER",
                            "product_name": p["product_name"],
                            "manufacturer_name": p.get("manufacturer_name"),
                        })

    pnorm = normalize_product_name(product_name)
    mnorm = normalize_manufacturer(manufacturer_name)

    if mnorm is not None:
        res = (
            sb.table("chemical_products")
            .select("id, product_name, manufacturer_name")
            .eq("factory_id", factory_id)
            .eq("product_name_normalized", pnorm)
            .eq("manufacturer_normalized", mnorm)
            .eq("status_code", "ACTIVE")
            .execute()
        )
        for row in (res.data or []):
            pid = row["id"]
            if not any(c["product_id"] == pid for c in candidates):
                candidates.append({
                    "product_id": pid,
                    "reason": "POSSIBLE_DUPLICATE_NAME_MFR",
                    "product_name": row["product_name"],
                    "manufacturer_name": row.get("manufacturer_name"),
                })

    return candidates


# ─── Product CRUD ─────────────────────────────────────────────────────────────

def _get_product_or_404(sb, factory_id: str, product_id: str) -> Dict[str, Any]:
    res = (
        sb.table("chemical_products")
        .select("*")
        .eq("id", product_id)
        .eq("factory_id", factory_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise MsdsProductError(404, "PRODUCT_NOT_FOUND", "제품을 찾을 수 없습니다.")
    return res.data[0]


def create_product(
    sb,
    current_user: Dict[str, Any],
    factory_id: str,
    product_name: str,
    manufacturer_name: Optional[str] = None,
    identifiers: Optional[List[Dict[str, Any]]] = None,
    created_source: str = "MANUAL",
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Product 생성. (product_row, duplicate_candidates) 반환."""
    _require_factory_scope(sb, current_user, factory_id)
    user_id = current_user.get("id")

    if created_source not in VALID_CREATED_SOURCE:
        raise MsdsProductError(400, "INVALID_CREATED_SOURCE", f"created_source '{created_source}'는 허용되지 않습니다.")

    pnorm = normalize_product_name(product_name)
    mnorm = normalize_manufacturer(manufacturer_name)

    candidates = _check_identifier_duplicates(
        sb, factory_id, product_name, manufacturer_name, identifiers
    )

    now = _now_iso()
    row = {
        "factory_id": factory_id,
        "product_name": product_name.strip(),
        "product_name_normalized": pnorm,
        "manufacturer_name": manufacturer_name.strip() if manufacturer_name else None,
        "manufacturer_normalized": mnorm,
        "identity_status": "DRAFT",
        "status_code": "ACTIVE",
        "created_source": created_source,
        "created_by": user_id,
        "updated_by": user_id,
        "created_at": now,
        "updated_at": now,
    }

    res = sb.table("chemical_products").insert(row).execute()
    if not res.data:
        raise MsdsProductError(500, "PRODUCT_CREATE_FAILED", "제품 생성에 실패했습니다.")
    product = res.data[0]

    if identifiers:
        for ident in identifiers:
            _add_identifier_row(sb, factory_id, product["id"], ident, user_id)

    ident_res = (
        sb.table("chemical_product_identifiers")
        .select("*")
        .eq("chemical_product_id", product["id"])
        .execute()
    )
    product["identifiers"] = ident_res.data or []

    return product, candidates


def _product_ids_by_identifier_q(sb, factory_id: str, qnorm: str) -> List[str]:
    """identifier_normalized ILIKE %qnorm% (factory-scoped, active only)."""
    res = (
        sb.table("chemical_product_identifiers")
        .select("chemical_product_id")
        .eq("factory_id", factory_id)
        .eq("is_active", True)
        .ilike("identifier_normalized", f"%{qnorm}%")
        .execute()
    )
    return list({row["chemical_product_id"] for row in (res.data or [])})


def list_products(
    sb,
    current_user: Dict[str, Any],
    factory_id: str,
    status: Optional[str] = None,
    identity_status: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> Dict[str, Any]:
    """Product 목록 (factory-scoped). q 있으면 name/manufacturer/identifier 검색 후 pagination."""
    _require_factory_scope(sb, current_user, factory_id)

    if q and q.strip():
        qnorm = normalize_product_name(q)

        name_res = (
            sb.table("chemical_products")
            .select("id")
            .eq("factory_id", factory_id)
            .ilike("product_name_normalized", f"%{qnorm}%")
            .execute()
        )
        mfr_res = (
            sb.table("chemical_products")
            .select("id")
            .eq("factory_id", factory_id)
            .ilike("manufacturer_normalized", f"%{qnorm}%")
            .execute()
        )
        ident_ids = _product_ids_by_identifier_q(sb, factory_id, qnorm)

        matched_ids = list({
            *(r["id"] for r in (name_res.data or [])),
            *(r["id"] for r in (mfr_res.data or [])),
            *ident_ids,
        })

        if not matched_ids:
            return {"items": [], "total": 0}

        all_res = (
            sb.table("chemical_products")
            .select("*")
            .eq("factory_id", factory_id)
            .in_("id", matched_ids)
            .order("created_at", desc=True)
            .execute()
        )
        rows = all_res.data or []
        if status:
            rows = [r for r in rows if r.get("status_code") == status]
        if identity_status:
            rows = [r for r in rows if r.get("identity_status") == identity_status]

        total = len(rows)
        items = rows[offset: offset + limit]
        return {"items": items, "total": total}

    query = (
        sb.table("chemical_products")
        .select("*")
        .eq("factory_id", factory_id)
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
    )
    if status:
        query = query.eq("status_code", status)
    if identity_status:
        query = query.eq("identity_status", identity_status)

    res = query.execute()
    items = res.data or []

    count_query = (
        sb.table("chemical_products")
        .select("id", count="exact")
        .eq("factory_id", factory_id)
    )
    if status:
        count_query = count_query.eq("status_code", status)
    if identity_status:
        count_query = count_query.eq("identity_status", identity_status)
    count_res = count_query.execute()
    total = count_res.count if hasattr(count_res, "count") and count_res.count is not None else len(items)

    return {"items": items, "total": total}


def get_product(sb, current_user: Dict[str, Any], factory_id: str, product_id: str) -> Dict[str, Any]:
    _require_factory_scope(sb, current_user, factory_id)
    product = _get_product_or_404(sb, factory_id, product_id)

    ident_res = (
        sb.table("chemical_product_identifiers")
        .select("*")
        .eq("chemical_product_id", product_id)
        .execute()
    )
    product["identifiers"] = ident_res.data or []
    return product


def update_product(
    sb,
    current_user: Dict[str, Any],
    factory_id: str,
    product_id: str,
    patch: Dict[str, Any],
) -> Dict[str, Any]:
    _require_factory_scope(sb, current_user, factory_id)
    _get_product_or_404(sb, factory_id, product_id)

    forbidden = {"factory_id", "company_id", "created_source", "created_by", "id"}
    for key in forbidden:
        patch.pop(key, None)

    if "identity_status" in patch and patch["identity_status"] not in VALID_IDENTITY_STATUS:
        raise MsdsProductError(400, "INVALID_IDENTITY_STATUS", f"identity_status '{patch['identity_status']}'는 허용되지 않습니다.")

    if "status_code" in patch and patch["status_code"] not in VALID_STATUS_CODE:
        raise MsdsProductError(400, "INVALID_STATUS_CODE", f"status_code '{patch['status_code']}'는 허용되지 않습니다.")

    if "product_name" in patch:
        patch["product_name"] = patch["product_name"].strip()
        patch["product_name_normalized"] = normalize_product_name(patch["product_name"])

    if "manufacturer_name" in patch:
        patch["manufacturer_name"] = patch["manufacturer_name"].strip() if patch["manufacturer_name"] else None
        patch["manufacturer_normalized"] = normalize_manufacturer(patch["manufacturer_name"])

    patch["updated_by"] = current_user.get("id")
    patch["updated_at"] = _now_iso()

    res = (
        sb.table("chemical_products")
        .update(patch)
        .eq("id", product_id)
        .eq("factory_id", factory_id)
        .execute()
    )
    if not res.data:
        raise MsdsProductError(500, "PRODUCT_UPDATE_FAILED", "제품 수정에 실패했습니다.")
    return res.data[0]


def deactivate_product(sb, current_user: Dict[str, Any], factory_id: str, product_id: str) -> Dict[str, Any]:
    _require_factory_scope(sb, current_user, factory_id)
    product = _get_product_or_404(sb, factory_id, product_id)
    if product["status_code"] == "INACTIVE":
        return product
    return update_product(sb, current_user, factory_id, product_id, {"status_code": "INACTIVE"})


def reactivate_product(sb, current_user: Dict[str, Any], factory_id: str, product_id: str) -> Dict[str, Any]:
    _require_factory_scope(sb, current_user, factory_id)
    product = _get_product_or_404(sb, factory_id, product_id)
    if product["status_code"] == "ACTIVE":
        return product
    return update_product(sb, current_user, factory_id, product_id, {"status_code": "ACTIVE"})


# ─── Identifier ───────────────────────────────────────────────────────────────

def _add_identifier_row(
    sb, factory_id: str, product_id: str, ident: Dict[str, Any], user_id: Optional[str]
) -> Dict[str, Any]:
    itype = ident.get("identifier_type", "")
    if itype not in VALID_IDENTIFIER_TYPE:
        raise MsdsProductError(400, "INVALID_IDENTIFIER_TYPE", f"identifier_type '{itype}'는 허용되지 않습니다.")
    ival = ident.get("identifier_value", "")
    if not ival or not ival.strip():
        raise MsdsProductError(400, "INVALID_IDENTIFIER_VALUE", "identifier_value는 비어있을 수 없습니다.")

    inorm = normalize_identifier(ival)

    source = ident.get("created_source", "MANUAL")
    if source not in VALID_CREATED_SOURCE:
        source = "MANUAL"

    now = _now_iso()
    row = {
        "factory_id": factory_id,
        "chemical_product_id": product_id,
        "identifier_type": itype,
        "identifier_value": ival.strip(),
        "identifier_normalized": inorm,
        "issuer_name": ident.get("issuer_name"),
        "is_primary": bool(ident.get("is_primary", False)),
        "is_active": True,
        "created_source": source,
        "created_at": now,
        "updated_at": now,
    }

    res = sb.table("chemical_product_identifiers").insert(row).execute()
    if not res.data:
        raise MsdsProductError(500, "IDENTIFIER_CREATE_FAILED", "식별코드 추가에 실패했습니다.")
    return res.data[0]


def list_identifiers(sb, current_user: Dict[str, Any], factory_id: str, product_id: str) -> List[Dict[str, Any]]:
    _require_factory_scope(sb, current_user, factory_id)
    _get_product_or_404(sb, factory_id, product_id)
    res = (
        sb.table("chemical_product_identifiers")
        .select("*")
        .eq("chemical_product_id", product_id)
        .execute()
    )
    return res.data or []


def add_identifier(
    sb, current_user: Dict[str, Any], factory_id: str, product_id: str, ident: Dict[str, Any]
) -> Dict[str, Any]:
    _require_factory_scope(sb, current_user, factory_id)
    _get_product_or_404(sb, factory_id, product_id)
    user_id = current_user.get("id")
    return _add_identifier_row(sb, factory_id, product_id, ident, user_id)


def deactivate_identifier(
    sb, current_user: Dict[str, Any], factory_id: str, product_id: str, identifier_id: str
) -> Dict[str, Any]:
    _require_factory_scope(sb, current_user, factory_id)
    _get_product_or_404(sb, factory_id, product_id)

    res = (
        sb.table("chemical_product_identifiers")
        .select("*")
        .eq("id", identifier_id)
        .eq("chemical_product_id", product_id)
        .eq("factory_id", factory_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise MsdsProductError(404, "IDENTIFIER_NOT_FOUND", "식별코드를 찾을 수 없습니다.")

    now = _now_iso()
    upd = (
        sb.table("chemical_product_identifiers")
        .update({"is_active": False, "updated_at": now})
        .eq("id", identifier_id)
        .eq("chemical_product_id", product_id)
        .eq("factory_id", factory_id)
        .execute()
    )
    if not upd.data:
        raise MsdsProductError(500, "IDENTIFIER_UPDATE_FAILED", "식별코드 비활성화에 실패했습니다.")
    return upd.data[0]
