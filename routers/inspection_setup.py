"""
routers/inspection_setup.py — v1.3.0
점검항목 세팅 (prefill + setup)

v1.3.0 (2026-08-20)
  [SEC] 인증·회사 스코프 (Wave3, 직접MCP)
    - 전 엔드포인트 로그인 필수(get_current_user).
    - GET /prefill: 쿼리 company_id 를 토큰과 대조(_ensure_own_company) — 타사 플랜 probe 차단(P13).
    - POST /setup: 대상 inspection_set 의 company_id 소유확인 후 저장.

v1.2.0 (2026-04-20)
  [FIX] _resolve_plan_code: contracts 우선 → payments(status_code=SUCCESS, service_status=ACTIVE) 우선
  [FIX] _extract_tier: CUSTOM/PREMIUM 플랜 tier 3 처리 (기존엔 1로 떨어져 프리필 누락)
  [FIX] is_active 컬럼 누락 시 KeyError 방어

v1.1.0 (2026-04-19)
  초기 구현 — GET /inspection-checklist/prefill, POST /inspection-checklist/setup
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from services.company_scope import _ensure_own_company

router = APIRouter(prefix="/inspection-checklist", tags=["점검항목 세팅"])

# ── L1 판별 키워드 (이 중 하나라도 포함 → tier=1, 프리필 없음)
_L1_KEYWORDS = {"STARTER", "BASIC"}

# ── L2 판별 키워드
_L2_KEYWORDS = {"BUSINESS", "STANDARD"}

# ── L3+ 판별 키워드
_L3_KEYWORDS = {"PRO", "PREMIUM", "ENTERPRISE", "CUSTOM"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_tier(plan_code: str) -> int:
    """plan_code 문자열에서 tier(1~4) 추출.
    실제 DB 플랜코드 기준:
      L1: STARTER, BASIC
      L2: BUSINESS, STANDARD
      L3: PRO, PREMIUM, ENTERPRISE, CUSTOM
    """
    if not plan_code:
        return 1
    upper = plan_code.upper()
    if any(k in upper for k in _L3_KEYWORDS):
        return 3
    if any(k in upper for k in _L2_KEYWORDS):
        return 2
    # STARTER, BASIC 또는 미매칭 → L1
    return 1


def _is_construction_plan(plan_code: str) -> bool:
    return "CONSTRUCTION" in (plan_code or "").upper()


def _resolve_plan_code(supabase, company_id: str) -> str:
    """회사의 현재 활성 플랜 코드를 반환.
    우선순위:
      1) payments (status_code=SUCCESS, service_status=ACTIVE) — 실제 결제 기준
      2) contracts (is_active=True) — 계약 기준
      3) 빈 문자열 (→ tier=1)
    """
    # 1) payments 테이블 — 가장 신뢰도 높은 소스
    try:
        pay_res = (
            supabase.table("payments")
            .select("plan_code, paid_at")
            .eq("company_id", company_id)
            .eq("status_code", "SUCCESS")
            .eq("service_status", "ACTIVE")
            .order("paid_at", desc=True)
            .limit(1)
            .execute()
        )
        if pay_res.data:
            code = (pay_res.data[0].get("plan_code") or "").strip()
            if code:
                return code
    except Exception:
        pass

    # 2) contracts 테이블 fallback
    try:
        c_res = (
            supabase.table("contracts")
            .select("plan_code")
            .eq("company_id", company_id)
            .eq("is_active", True)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if c_res.data:
            code = (c_res.data[0].get("plan_code") or "").strip()
            if code:
                return code
    except Exception:
        pass

    return ""


# ── GET /inspection-checklist/prefill ─────────────────────────────────────────

@router.get("/prefill")
async def get_prefill(
    equipment_std: str = Query(..., description="설비 표준코드 (inspection_master.equipment_std)"),
    company_id: str = Query(..., description="회사 UUID"),
    cycle: Optional[str] = Query(None, description="점검 주기 필터 (선택)"),
    current: dict = Depends(get_current_user),
):
    """플랜 tier에 따라 추천 점검항목 반환.

    - tier=1(STARTER/BASIC) → 빈 배열 (안전관리자가 직접 입력)
    - tier=2+(BUSINESS/STANDARD/PRO/CUSTOM) → inspection_master 기반 프리필
    - CONSTRUCTION 플랜 → tier 무관 항상 프리필
    """
    supabase = get_supabase()
    # ── 회사 스코프 (P13): 쿼리 company_id 를 토큰과 대조 ──
    _ensure_own_company(company_id, current, supabase, "회사를 찾을 수 없습니다.")

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
                "prefill_available": False,
            },
        }

    q = (
        supabase.table("inspection_master")
        .select(
            "id, equipment_std, equipment_name_ko, inspection_item, cycle, legal_basis, "
            "check_method, check_type, risk_type, pass_description, fail_action, "
            "is_mandatory, threshold_value, unit"
        )
        .eq("equipment_std", equipment_std)
        .eq("is_active", True)
    )
    if cycle:
        q = q.eq("cycle", cycle)
    q = q.order("inspection_item")
    res = q.execute()
    rows = res.data or []

    items: List[Dict[str, Any]] = [
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
            "source": "TEMPLATE",
        }
        for row in rows
    ]

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
            "prefill_available": True,
        },
    }


# ── POST /inspection-checklist/setup ──────────────────────────────────────────

@router.post("/setup")
async def setup_inspection_checklist(body: dict, current: dict = Depends(get_current_user)):
    """점검항목 일괄 저장.

    - 기존 is_active=True 항목 soft delete → 신규 INSERT
    - inspection_sets.status_code → ACTIVE 업데이트
    """
    supabase = get_supabase()
    inspection_set_id: str | None = body.get("inspection_set_id")
    equipment_asset_id: str | None = body.get("equipment_asset_id")
    items: list = body.get("items") or []
    confirmed_by: str | None = body.get("confirmed_by")  # user_id (선택)

    if not inspection_set_id:
        raise HTTPException(status_code=400, detail="inspection_set_id 필수")
    if not isinstance(items, list):
        raise HTTPException(status_code=400, detail="items는 배열이어야 합니다.")

    # 세트 존재 확인
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

    # ── 회사 스코프 (P13): 대상 세트 소유확인 ──
    _ensure_own_company(set_row.get("company_id"), current, supabase, "inspection_set_id를 찾을 수 없습니다.")

    now = _now_iso()

    # 기존 항목 soft delete
    supabase.table("inspection_set_items").update(
        {"is_active": False, "updated_at": now}
    ).eq("inspection_set_id", inspection_set_id).eq("is_active", True).execute()

    # 신규 INSERT 준비
    insert_rows: List[Dict[str, Any]] = []
    for idx, item in enumerate(items, start=1):
        if not item.get("item_name"):
            continue
        raw_source = (item.get("source") or (
            "TEMPLATE" if item.get("master_item_id") else "MANUAL"
        )).upper()
        source = raw_source if raw_source in {"TEMPLATE", "MANUAL"} else "MANUAL"

        insert_rows.append(
            {
                "inspection_set_id": inspection_set_id,
                "equipment_asset_id": equipment_asset_id,
                "item_seq": int(item.get("item_seq") or idx),
                "item_name": item["item_name"],
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
                "updated_at": now,
                **({"created_by": confirmed_by} if confirmed_by else {}),
            }
        )

    # 100건씩 배치 INSERT
    created = 0
    for i in range(0, len(insert_rows), 100):
        res = supabase.table("inspection_set_items").insert(insert_rows[i: i + 100]).execute()
        created += len(res.data or [])

    # 세트 상태 → ACTIVE
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
            "deleted_previous": True,
        },
    }
