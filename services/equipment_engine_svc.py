from __future__ import annotations

from datetime import date
from typing import Optional

from dateutil.relativedelta import relativedelta
from fastapi import HTTPException

from services.equipment_helpers import CATEGORY_MAP, DELTA_MAP, _build_schedules_for_repair, _enrich_asset_row, _now_iso


def run_get_equipment_stats(supabase, version: str, current: dict):
    from services.company_scope import _require_admin
    _require_admin(current, supabase)

    res = supabase.table("engine_equipment_summary").select(
        "source_facility_category, top_band, needs_review, process_count"
    ).execute()
    rows = res.data or []

    total = len(rows)
    cat_count: dict = {}
    band_count = {"MUST": 0, "CORE": 0, "OPTIONAL": 0, "REFERENCE": 0}
    review_count = 0
    total_mappings = 0

    for row in rows:
        cat = row.get("source_facility_category") or ""
        band = row.get("top_band") or ""
        cat_count[cat] = cat_count.get(cat, 0) + 1
        if band in band_count:
            band_count[band] += 1
        if row.get("needs_review"):
            review_count += 1
        total_mappings += row.get("process_count") or 0

    model_res = supabase.table("equipment_model_master").select("id", count="exact").limit(0).execute()
    asset_total_res = supabase.table("equipment_assets").select("id", count="exact").limit(0).execute()
    asset_no_model_res = (
        supabase.table("equipment_assets").select("id", count="exact").is_("equipment_model_id", "null").limit(0).execute()
    )
    asset_no_insp_res = (
        supabase.table("equipment_assets").select("id", count="exact").is_("last_inspection_date", "null").limit(0).execute()
    )
    legal_target_res = supabase.table("master_legal_inspection_target").select("id", count="exact").limit(0).execute()
    legal_rows = supabase.table("master_legal_inspection_target").select("equipment_name").execute()
    legal_names = [r.get("equipment_name", "") for r in (legal_rows.data or []) if r.get("equipment_name")]
    unmapped_count = 0
    for lname in legal_names:
        chk = supabase.table("equipment_assets").select("id", count="exact").ilike("asset_name", f"%{lname[:6]}%").limit(0).execute()
        if (chk.count or 0) == 0:
            unmapped_count += 1

    return {
        "status": "success",
        "data": {
            "total_mapping_rows": total_mappings,
            "unique_equipment": total,
            "model_master_total": model_res.count or 0,
            "needs_review_count": review_count,
            "band_distribution": band_count,
            "category_distribution": {
                k: {"count": v, "label": CATEGORY_MAP.get(k, k)} for k, v in sorted(cat_count.items(), key=lambda x: -x[1])
            },
            "asset_registered_total": asset_total_res.count or 0,
            "asset_no_model": asset_no_model_res.count or 0,
            "asset_no_inspection": asset_no_insp_res.count or 0,
            "legal_inspection_target_count": legal_target_res.count or 0,
            "legal_inspection_unmapped": unmapped_count,
            "version": version,
        },
    }


def _empty_asset_page(page: int, page_size: int) -> dict:
    return {
        "status": "success",
        "data": {"items": [], "total": 0, "page": page, "page_size": page_size, "total_pages": 0},
    }


def _resolve_asset_scope(supabase, current: dict):
    """equipment_assets(factory_id 전용) 스코프 필터 결정.

    반환:
      None          → ALL, 필터 없음
      {"factory_id": id}      → 단일 factory
      {"factory_id__in": [...]} → 여러 factory
      "DENY"        → 빈 결과 반환

    FACTORY/TEAM/ASSIGNED: 토큰 factory_id가 자기 회사 소속인지 교차검증.
    PLATFORM 및 미정의 scope: 전사 조회 금지 → DENY.
    """
    from services.company_scope import _scope, _is_admin, _via_factory, DENY

    tier = _scope(supabase, current.get("role_code"))

    if _is_admin(tier):
        return None

    cid = current.get("company_id")
    if not cid:
        return "DENY"

    if tier == "COMPANY":
        filt = _via_factory(supabase, cid)
        if filt is DENY:
            return "DENY"
        return filt  # {"factory_id__in": [...]}

    if tier in ("FACTORY", "TEAM", "ASSIGNED"):
        fid = current.get("factory_id")
        if not fid:
            return "DENY"
        # factory가 자기 company 소속인지 교차검증
        f = supabase.table("factories").select("company_id").eq("id", fid).limit(1).execute()
        if not f.data or f.data[0].get("company_id") != cid:
            return "DENY"
        return {"factory_id": fid}

    # PLATFORM(031/032/033) 및 미정의 → 전사 조회 금지
    return "DENY"


def run_list_assets(
    supabase,
    page: int,
    page_size: int,
    search: Optional[str],
    has_model: Optional[bool],
    no_inspection: Optional[bool],
    is_legal_target: Optional[bool],
    equipment_type_code: Optional[str],
    current: dict,
):
    scope = _resolve_asset_scope(supabase, current)
    if scope == "DENY":
        return _empty_asset_page(page, page_size)

    def _apply_filters(q):
        # 테넌트 스코프 필터 (최우선)
        if scope is not None:
            for col, val in scope.items():
                if col.endswith("__in"):
                    q = q.in_(col[:-4], val)
                else:
                    q = q.eq(col, val)
        # 기존 검색·필터
        if search:
            q = q.ilike("asset_name", f"%{search.strip()}%")
        if has_model is True:
            q = q.not_.is_("equipment_model_id", "null")
        elif has_model is False:
            q = q.is_("equipment_model_id", "null")
        if no_inspection is True:
            q = q.is_("last_inspection_date", "null")
        elif no_inspection is False:
            q = q.not_.is_("last_inspection_date", "null")
        if is_legal_target is not None:
            q = q.eq("is_legal_target", is_legal_target)
        if equipment_type_code:
            q = q.eq("equipment_type_code", equipment_type_code)
        return q

    count_q = _apply_filters(supabase.table("equipment_assets").select("id", count="exact"))
    total = (count_q.limit(0).execute().count) or 0
    offset = (page - 1) * page_size
    data_q = _apply_filters(supabase.table("equipment_assets").select("*"))
    data_q = data_q.order("created_at", desc=True).range(offset, offset + page_size - 1)
    res = data_q.execute()
    items = [_enrich_asset_row(dict(r)) for r in (res.data or [])]
    return {
        "status": "success",
        "data": {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if total else 0,
        },
    }


def run_patch_asset(supabase, asset_id: str, body, current: dict):
    from services.company_scope import _scope, _is_admin
    from services.permission_guard import has_permission

    # 1. 작업권한 확인 (DB 조회 전)
    if not has_permission(current.get("role_code"), "EQUIPMENT_UPDATE"):
        raise HTTPException(status_code=403, detail="권한이 없습니다")

    # 2. 자산 조회 (소유권 검증용)
    asset_check = (
        supabase.table("equipment_assets")
        .select("id, factory_id")
        .eq("id", asset_id)
        .limit(1)
        .execute()
    )
    if not asset_check.data:
        raise LookupError("자산을 찾을 수 없습니다.")

    checked_factory_id = asset_check.data[0].get("factory_id")

    # 3. 소유권 검증
    tier = _scope(supabase, current.get("role_code"))
    if not _is_admin(tier):
        if not checked_factory_id:
            # factory_id 없는 자산 — 비-ALL 수정 불가
            raise HTTPException(status_code=404, detail="자산을 찾을 수 없습니다")
        # factory의 회사 소속 확인
        f_res = (
            supabase.table("factories")
            .select("company_id")
            .eq("id", checked_factory_id)
            .limit(1)
            .execute()
        )
        if not f_res.data or f_res.data[0].get("company_id") != current.get("company_id"):
            raise HTTPException(status_code=404, detail="자산을 찾을 수 없습니다")
        # FACTORY/TEAM/ASSIGNED: 자기 factory만
        if tier in ("FACTORY", "TEAM", "ASSIGNED"):
            if checked_factory_id != current.get("factory_id"):
                raise HTTPException(status_code=404, detail="자산을 찾을 수 없습니다")

    # 4. 업데이트 데이터 구성
    update_data = {}
    if body.last_inspection_date is not None:
        update_data["last_inspection_date"] = body.last_inspection_date.isoformat()
    if body.next_inspection_date is not None:
        update_data["next_inspection_date"] = body.next_inspection_date.isoformat()
    if body.is_legal_target is not None:
        update_data["is_legal_target"] = body.is_legal_target
    if body.is_operating is not None:
        update_data["is_operating"] = body.is_operating
    if body.model_id and not body.equipment_model_id:
        update_data["equipment_model_id"] = body.model_id
    elif body.equipment_model_id:
        update_data["equipment_model_id"] = body.equipment_model_id

    if not update_data:
        raise ValueError("수정할 항목이 없습니다.")

    update_data["updated_at"] = _now_iso()

    # 5. TOCTOU 방어: 검증된 factory_id를 UPDATE 조건에 포함
    update_q = supabase.table("equipment_assets").update(update_data).eq("id", asset_id)
    if checked_factory_id:
        update_q = update_q.eq("factory_id", checked_factory_id)
    res = update_q.execute()

    if not res.data:
        raise LookupError("자산을 찾을 수 없습니다.")

    asset = res.data[0]
    repair_result = {"schedules_reset": 0, "sets_processed": 0}
    if body.is_operating is True and body.repair_date:
        try:
            repair_date = date.fromisoformat(body.repair_date)
            end_date = repair_date + relativedelta(years=1)
            factory_id = asset.get("factory_id")
            if factory_id:
                sets_res = (
                    supabase.table("inspection_sets")
                    .select("id, factory_id, company_id, cycle_value, cycle_unit, inspection_set_name, inspection_category")
                    .eq("factory_id", factory_id)
                    .eq("source", "MANUAL")
                    .eq("status_code", "ACTIVE")
                    .eq("is_active", True)
                    .execute()
                )
                sets = sets_res.data or []
                total_created = 0
                for iset in sets:
                    try:
                        (
                            supabase.table("work_schedules")
                            .delete()
                            .eq("inspection_set_id", iset["id"])
                            .eq("status_code", "SCHEDULED")
                            .execute()
                        )
                        rows = _build_schedules_for_repair(iset, repair_date, end_date)
                        next_date = repair_date + (
                            DELTA_MAP.get((iset.get("cycle_unit") or "year").lower(), lambda v: relativedelta(years=v))(
                                int(iset.get("cycle_value") or 1)
                            )
                        )
                        (
                            supabase.table("inspection_sets")
                            .update(
                                {
                                    "schedule_anchor_date": repair_date.isoformat(),
                                    "schedule_end_date": end_date.isoformat(),
                                    "next_planned_date": next_date.isoformat(),
                                }
                            )
                            .eq("id", iset["id"])
                            .execute()
                        )
                        for i in range(0, len(rows), 20):
                            r = supabase.table("work_schedules").insert(rows[i : i + 20]).execute()
                            total_created += len(r.data or [])
                    except Exception:
                        pass
                repair_result = {
                    "schedules_reset": total_created,
                    "sets_processed": len(sets),
                    "repair_date": repair_date.isoformat(),
                    "end_date": end_date.isoformat(),
                }
        except Exception:
            pass
    return {"status": "success", "data": {**asset, "repair_result": repair_result}}
