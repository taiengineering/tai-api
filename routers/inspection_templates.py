"""
수동 점검 템플릿 — safety_templates + inspection_sets(MANUAL) 연동
프론트: tadmin/inspection-custom.html
"""
import json
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Query

from db.supabase_client import get_supabase

router = APIRouter(prefix="/inspection-templates", tags=["inspection_templates"])

_CYCLE_MAP = {
    "일일": "day",
    "daily": "day",
    "주간": "week",
    "weekly": "week",
    "월간": "month",
    "monthly": "month",
    "분기": "quarter",
    "quarterly": "quarter",
    "반기": "half_year",
    "half_year": "half_year",
    "연간": "year",
    "yearly": "year",
}


def _to_cycle_unit(raw: Optional[str]) -> str:
    if not raw:
        return "month"
    s = str(raw).strip()
    if s.lower() in ("day", "week", "month", "quarter", "half_year", "year"):
        return s.lower()
    return _CYCLE_MAP.get(s, "month")


def _factory_company_id(supabase, factory_id: str) -> Optional[str]:
    res = (
        supabase.table("factories")
        .select("company_id")
        .eq("id", factory_id)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    return rows[0].get("company_id") if rows else None


@router.get("")
def list_inspection_templates(factory_id: str = Query(..., description="시설 ID")):
    supabase = get_supabase()
    items: List[Dict[str, Any]] = []
    try:
        st = (
            supabase.table("safety_templates")
            .select("id, factory_id, template_name, created_at, inspection_set_id")
            .eq("factory_id", factory_id)
            .order("created_at", desc=True)
            .execute()
        )
        items = st.data or []
    except Exception:
        items = []
    if not items:
        alt = (
            supabase.table("inspection_sets")
            .select("id, inspection_set_name, factory_id, created_at, description, inspection_set_code")
            .eq("factory_id", factory_id)
            .eq("source", "MANUAL")
            .execute()
        )
        for r in alt.data or []:
            desc = r.get("description") or ""
            if "manual_template_items" in desc or (r.get("inspection_set_code") or "").startswith("MANUAL-TPL"):
                items.append(
                    {
                        "id": r["id"],
                        "template_name": r.get("inspection_set_name"),
                        "factory_id": r.get("factory_id"),
                        "created_at": r.get("created_at"),
                        "inspection_set_id": r["id"],
                        "_from_sets_only": True,
                    }
                )
    return {"status": "success", "data": {"items": items}}


@router.post("/manual")
def save_manual_template(body: Dict[str, Any] = Body(...)):
    """
    safety_templates + inspection_sets(MANUAL) 동시 등록.
    items: [{ name, item_type, cycle, risk_level, criteria, method }]
    """
    factory_id = body.get("factory_id")
    template_name = (body.get("template_name") or "").strip()
    items: List[Dict[str, Any]] = body.get("items") or []
    if not factory_id:
        raise HTTPException(status_code=400, detail="factory_id는 필수입니다.")
    if not template_name:
        raise HTTPException(status_code=400, detail="템플릿명(template_name)은 필수입니다.")
    if not items:
        raise HTTPException(status_code=400, detail="점검 항목이 1개 이상 필요합니다.")

    supabase = get_supabase()
    company_id = _factory_company_id(supabase, factory_id)
    if not company_id:
        raise HTTPException(status_code=404, detail="시설 또는 회사 정보를 찾을 수 없습니다.")

    code = f"MANUAL-TPL-{uuid.uuid4().hex[:12]}"
    payload = {
        "manual_template_items": items,
        "template_name": template_name,
    }
    desc_str = json.dumps(payload, ensure_ascii=False)

    first_cycle = _to_cycle_unit((items[0] or {}).get("cycle"))
    ins_row = {
        "company_id": company_id,
        "factory_id": factory_id,
        "inspection_set_name": template_name,
        "inspection_set_code": code,
        "law_name": "수동 점검 템플릿",
        "law_article": "",
        "cycle_unit": first_cycle,
        "cycle_value": 1,
        "description": desc_str,
        "source": "MANUAL",
        "is_active": True,
        "status_code": "PENDING",
        "anchor_confirmed": False,
    }

    set_res = supabase.table("inspection_sets").insert(ins_row).execute()
    set_rows = set_res.data or []
    if not set_rows:
        raise HTTPException(status_code=500, detail="inspection_sets 등록에 실패했습니다.")
    set_id = set_rows[0].get("id")

    tpl_result = None
    try:
        tpl_ins = {
            "factory_id": factory_id,
            "company_id": company_id,
            "template_name": template_name,
            "items_json": items,
            "inspection_set_id": set_id,
        }
        tpl_res = supabase.table("safety_templates").insert(tpl_ins).execute()
        tpl_result = tpl_res.data[0] if tpl_res.data else None
    except Exception:
        tpl_result = None

    return {
        "status": "success",
        "data": {
            "inspection_set": set_rows[0],
            "safety_template": tpl_result,
            "message": "저장됐습니다."
            + ("" if tpl_result else " (safety_templates 테이블 없음 — inspection_sets만 저장)"),
        },
    }


@router.get("/{template_id}")
def get_inspection_template(template_id: str):
    supabase = get_supabase()
    try:
        st = (
            supabase.table("safety_templates")
            .select("*")
            .eq("id", template_id)
            .limit(1)
            .execute()
        )
        if st.data:
            row = st.data[0]
            items = row.get("items_json") or row.get("body") or []
            if isinstance(items, str):
                try:
                    items = json.loads(items)
                except Exception:
                    items = []
            return {
                "status": "success",
                "data": {
                    "id": row.get("id"),
                    "template_name": row.get("template_name"),
                    "factory_id": row.get("factory_id"),
                    "items": items,
                    "inspection_set_id": row.get("inspection_set_id"),
                },
            }
    except Exception:
        pass

    res = (
        supabase.table("inspection_sets")
        .select("*")
        .eq("id", template_id)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="템플릿을 찾을 수 없습니다.")
    row = rows[0]
    items: List[Any] = []
    desc = row.get("description") or ""
    try:
        if desc.strip().startswith("{"):
            j = json.loads(desc)
            items = j.get("manual_template_items") or []
    except Exception:
        items = []
    return {
        "status": "success",
        "data": {
            "id": row.get("id"),
            "template_name": row.get("inspection_set_name"),
            "factory_id": row.get("factory_id"),
            "items": items,
            "inspection_set_id": row.get("id"),
        },
    }
