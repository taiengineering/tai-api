# routers/byulpyo.py — 별표 데이터 API
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional
from db.database import get_supabase

router = APIRouter(prefix="/byulpyo", tags=["별표 데이터"])


# ── 안전인증·자율안전확인 ─────────────────────────────────────

class SafetyCertItem(BaseModel):
    cert_code: str
    category: str
    item_name: str
    item_name_detail: Optional[str] = None
    legal_basis: Optional[str] = None
    cert_type: str = "CERT"
    inspection_cycle: Optional[str] = None
    issuing_agency: Optional[str] = "한국산업안전보건공단"
    notes: Optional[str] = None


@router.post("/safety-cert/import")
def import_safety_cert(items: List[SafetyCertItem]):
    sb = get_supabase()
    res = sb.table("master_safety_certification").upsert(
        [i.dict() for i in items], on_conflict="cert_code"
    ).execute()
    return {"status": "success", "count": len(res.data)}


@router.get("/safety-cert")
def list_safety_cert(cert_type: str = None):
    sb = get_supabase()
    q = sb.table("master_safety_certification").select("*").eq("is_active", True)
    if cert_type:
        q = q.eq("cert_type", cert_type)
    return {"status": "success", "data": q.order("cert_code").execute().data}


# ── 위험물 ────────────────────────────────────────────────────

class DangerousGoodsItem(BaseModel):
    goods_code: str
    hazard_class: int
    hazard_class_name: str
    item_name: str
    designated_qty: Optional[float] = None
    designated_unit: Optional[str] = None
    storage_standard: Optional[str] = None
    legal_basis: Optional[str] = "위험물안전관리법 시행령 별표 1"
    notes: Optional[str] = None


@router.post("/dangerous-goods/import")
def import_dangerous_goods(items: List[DangerousGoodsItem]):
    sb = get_supabase()
    res = sb.table("master_dangerous_goods").upsert(
        [i.dict() for i in items], on_conflict="goods_code"
    ).execute()
    return {"status": "success", "count": len(res.data)}


@router.get("/dangerous-goods")
def list_dangerous_goods(hazard_class: int = None):
    sb = get_supabase()
    q = sb.table("master_dangerous_goods").select("*").eq("is_active", True)
    if hazard_class:
        q = q.eq("hazard_class", hazard_class)
    return {"status": "success", "data": q.order("goods_code").execute().data}


# ── 안전관리자 선임기준 ───────────────────────────────────────

class SafetyManagerItem(BaseModel):
    criteria_code: str
    manager_type: str
    industry_category: str
    ksic_codes: Optional[str] = None
    min_workers: Optional[int] = None
    max_workers: Optional[int] = None
    required_count: int = 1
    qualification: Optional[str] = None
    legal_basis: Optional[str] = None
    notes: Optional[str] = None


@router.post("/safety-manager/import")
def import_safety_manager(items: List[SafetyManagerItem]):
    sb = get_supabase()
    res = sb.table("master_safety_manager_criteria").upsert(
        [i.dict() for i in items], on_conflict="criteria_code"
    ).execute()
    return {"status": "success", "count": len(res.data)}


@router.get("/safety-manager")
def list_safety_manager(manager_type: str = None):
    sb = get_supabase()
    q = sb.table("master_safety_manager_criteria").select("*").eq("is_active", True)
    if manager_type:
        q = q.eq("manager_type", manager_type)
    return {"status": "success", "data": q.order("criteria_code").execute().data}


# ── 법정검사 대상 ─────────────────────────────────────────────

class LegalInspectionItem(BaseModel):
    target_code: str
    equipment_name: str
    equipment_std: Optional[str] = None
    inspection_type: Optional[str] = None
    cycle_value: Optional[int] = None
    cycle_unit: Optional[str] = None
    cycle_desc: Optional[str] = None
    issuing_agency: Optional[str] = "한국산업안전보건공단"
    legal_basis: Optional[str] = "산업안전보건법 제93조"
    penalty_summary: Optional[str] = None
    notes: Optional[str] = None


@router.post("/legal-inspection/import")
def import_legal_inspection(items: List[LegalInspectionItem]):
    sb = get_supabase()
    res = sb.table("master_legal_inspection_target").upsert(
        [i.dict() for i in items], on_conflict="target_code"
    ).execute()
    return {"status": "success", "count": len(res.data)}


@router.get("/legal-inspection")
def list_legal_inspection():
    sb = get_supabase()
    return {
        "status": "success",
        "data": sb.table("master_legal_inspection_target")
        .select("*").eq("is_active", True).order("target_code").execute().data,
    }


# ── 통계 ──────────────────────────────────────────────────────

@router.get("/stats")
def byulpyo_stats():
    sb = get_supabase()
    return {
        "status": "success",
        "data": {
            "safety_cert": sb.table("master_safety_certification")
                .select("id", count="exact").eq("cert_type", "CERT").execute().count,
            "self_cert": sb.table("master_safety_certification")
                .select("id", count="exact").eq("cert_type", "SELF").execute().count,
            "dangerous_goods": sb.table("master_dangerous_goods")
                .select("id", count="exact").execute().count,
            "safety_manager": sb.table("master_safety_manager_criteria")
                .select("id", count="exact").execute().count,
            "legal_inspection": sb.table("master_legal_inspection_target")
                .select("id", count="exact").execute().count,
        },
    }
