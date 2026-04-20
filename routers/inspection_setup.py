from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from db.supabase_client import get_supabase

router = APIRouter(prefix="/inspection-checklist", tags=["점검항목 세팅"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_tier(plan_code: str) -> int:
    if not plan_code:
        return 1
    upper = plan_code.upper()
    m = re.search(r"L([1-4])", upper)
    if m:
        return int(m.group(1))
    # legacy naming fallback
    if any(k in upper for k in ("PRO", "PREMIUM", "ENTERPRISE", "L4", "L3")):
        return 3
    if any(k in upper for k in ("BUSINESS", "STANDARD", "L2")):
        return 2
    return 1


def _is_construction_plan(plan_code: str) -> bool:
    return "CONSTRUCTION" in (plan_code or "").upper()


def _resolve_plan_code(supabase, company_id: str) -> str:
    # 1) contracts 최신 활성 계약 우선
    try:
        c_res = (
            supabase.table("contracts")
            .select("plan_code, status_code, is_active, created_at")
            .eq("company_id", company_id)
            .eq("is_active", True)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if c_res.data:
            return (c_res.data[0].get("plan_code") or "").strip()
    except Exception:
        pass

    # 2) companies.subscription/plan_code fallback
    try:
        comp_res = (
            supabase.table("companies")
            .select("subscription, plan_code")
            .eq("id", company_id)
            .limit(1)
            .execute()
        )
        if comp_res.data:
            row = comp_res.data[0]
            if isinstance(row.get("subscription"), dict):
                code = (row["subscription"].get("plan_code") or "").strip()
                if code:
                    return code
            code = (row.get("plan_code") or "").strip()
            if code:
                return code
    except Exception:
        pass

    # 3) price_saas_plan과의 강한 조인 데이터가 없으면 빈값
    return ""


@router.get("/prefill")
async def get_prefill(
    equipment_std: str = Query(...),
    company_id: str = Query(...),
    cycle: Optional[str] = Query(None),
):
    supabase = get_supabase()
    plan_code = _resolve_plan_code(supabase, company_id)
    tier = _extract_tier(plan_code)
    allow_prefill = tier >= 2 or _is_construction_plan(plan_code)

    if not allow_prefill:
        return {
            "status": "success",
            "data": {
                "equipment_std": equipment_std,
                "equipment_name_ko": None,
                "source": "MANUAL",
                "items": [],
                "total": 0,
                "plan_code": plan_code,
                "tier": tier,
            },
        }

    q = (
        supabase.table("inspection_master")
        .select(
            "id, equipment_std, equipment_name_ko, inspection_item, cycle, legal_basis, check_method, "
            "check_type, risk_type, pass_description, fail_action, is_mandatory, threshold_value, unit"
        )
        .eq("equipment_std", equipment_std)
    )
    if cycle:
        q = q.eq("cycle", cycle)
    q = q.order("inspection_item")
    res = q.execute()
    rows = res.data or []

    items: List[Dict[str, Any]] = []
    for row in rows:
        items.append(
            {
                "master_item_id": row.get("id"),
                "item_name": row.get("inspection_item"),
                "check_type": row.get("check_type") or "BOOLEAN",
                "risk_type": row.get("risk_type"),
                "cycle": row.get("cycle"),
                "is_mandatory": bool(row.get("is_mandatory")),
                "legal_basis": row.get("legal_basis"),
                "check_method": row.get("check_method"),
                "pass_description": row.get("pass_description"),
                "fail_action": row.get("fail_action"),
                "threshold_value": row.get("threshold_value"),
                "unit": row.get("unit"),
            }
        )

    return {
        "status": "success",
        "data": {
            "equipment_std": equipment_std,
            "equipment_name_ko": rows[0].get("equipment_name_ko") if rows else None,
            "source": "TEMPLATE",
            "items": items,
            "total": len(items),
            "plan_code": plan_code,
            "tier": tier,
        },
    }


@router.post("/setup")
async def setup_inspection_checklist(body: dict):
    supabase = get_supabase()
    inspection_set_id = body.get("inspection_set_id")
    equipment_asset_id = body.get("equipment_asset_id")
    items = body.get("items") or []

    if not inspection_set_id:
        raise HTTPException(status_code=400, detail="inspection_set_id 필수")
    if not isinstance(items, list):
        raise HTTPException(status_code=400, detail="items는 배열이어야 합니다.")

    set_res = (
        supabase.table("inspection_sets")
        .select("id, factory_id, company_id")
        .eq("id", inspection_set_id)
        .limit(1)
        .execute()
    )
    if not set_res.data:
        raise HTTPException(status_code=404, detail="inspection_set_id를 찾을 수 없습니다.")
    set_row = set_res.data[0]

    # 기존 항목 soft delete
    supabase.table("inspection_set_items").update(
        {"is_active": False, "updated_at": _now_iso()}
    ).eq("inspection_set_id", inspection_set_id).eq("is_active", True).execute()

    insert_rows: List[Dict[str, Any]] = []
    now = _now_iso()
    for idx, item in enumerate(items, start=1):
        if not item.get("item_name"):
            continue
        source = (item.get("source") or ("TEMPLATE" if item.get("master_item_id") else "MANUAL")).upper()
        if source not in {"TEMPLATE", "MANUAL"}:
            source = "MANUAL"
        insert_rows.append(
            {
                "inspection_set_id": inspection_set_id,
                "equipment_asset_id": equipment_asset_id,
                "item_seq": int(item.get("item_seq") or idx),
                "item_name": item.get("item_name"),
                "is_required": bool(item.get("is_required", False)),
                "description": item.get("pass_description") or item.get("description"),
                "check_type": item.get("check_type") or "BOOLEAN",
                "risk_type": item.get("risk_type"),
                "pass_description": item.get("pass_description"),
                "fail_action": item.get("fail_action"),
                "source": source,
                "master_item_id": item.get("master_item_id"),
                "threshold_value": item.get("threshold_value"),
                "unit": item.get("unit"),
                "check_method": item.get("check_method"),
                "is_active": True,
                "created_at": now,
            }
        )

    created = 0
    for i in range(0, len(insert_rows), 100):
        res = supabase.table("inspection_set_items").insert(insert_rows[i : i + 100]).execute()
        created += len(res.data or [])

    supabase.table("inspection_sets").update(
        {"status_code": "ACTIVE", "updated_at": now}
    ).eq("id", inspection_set_id).execute()

    return {
        "status": "success",
        "data": {
            "inspection_set_id": inspection_set_id,
            "factory_id": set_row.get("factory_id"),
            "company_id": set_row.get("company_id"),
            "created": created,
        },
    }
