from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict

from db.supabase_client import get_supabase
from schemas.inspection_sets import AnchorBody, AnchorBulkPatchBody, BulkAnchorBody, InspectionSetPatchBody
from services.inspection_sets_helpers import _build_next_schedule_row
from .errors import InspectionSetsSvcError
from services.time import now_kst, serialize_business_datetime


def set_anchor_bulk(body: BulkAnchorBody) -> dict:
    supabase = get_supabase()
    sets_res = supabase.table("inspection_sets").select(
        "id, factory_id, company_id, cycle_value, cycle_unit, inspection_set_name, inspection_category, source"
    ).eq("factory_id", body.factory_id).eq("status_code", "PENDING_ANCHOR").eq("is_active", True).execute()
    sets = sets_res.data or []
    if not sets:
        return {"status": "success", "message": "처리할 PENDING_ANCHOR 상태 점검세트가 없습니다.", "data": {"total_sets": 0, "total_created": 0, "results": []}}
    anchor = date.fromisoformat(body.anchor_date)
    results, total_created = [], 0
    for iset in sets:
        try:
            row, planned = _build_next_schedule_row(iset, anchor)
            supabase.table("inspection_sets").update({"schedule_anchor_date": anchor.isoformat(), "next_planned_date": planned.isoformat(), "anchor_confirmed": True, "status_code": "ACTIVE", "updated_at": serialize_business_datetime(now_kst())}).eq("id", iset["id"]).execute()
            supabase.table("work_schedules").delete().eq("inspection_set_id", iset["id"]).eq("status_code", "SCHEDULED").execute()
            r = supabase.table("work_schedules").insert(row).execute()
            c = len(r.data or [])
            total_created += c
            results.append({"id": iset["id"], "name": iset.get("inspection_set_name"), "next_planned_date": planned.isoformat(), "created": c})
        except Exception as e:
            results.append({"id": iset["id"], "name": iset.get("inspection_set_name"), "error": str(e)})
    return {"status": "success", "message": f"{len(sets)}개 세트 처리, 총 {total_created}개 일정 생성", "data": {"factory_id": body.factory_id, "anchor_date": anchor.isoformat(), "total_sets": len(sets), "total_created": total_created, "results": results}}


def bulk_update_anchors(body: AnchorBulkPatchBody) -> dict:
    supabase = get_supabase()
    updated_count, errors = 0, []
    for item in body.items:
        try:
            res = supabase.table("inspection_sets").select("id, cycle_value, cycle_unit, factory_id, company_id, inspection_set_name, inspection_category, source").eq("id", item.id).limit(1).execute()
            if not res.data:
                errors.append({"id": item.id, "reason": "점검 세트를 찾을 수 없습니다."})
                continue
            iset = res.data[0]
            anchor = date.fromisoformat(item.schedule_anchor_date)
            row, planned = _build_next_schedule_row(iset, anchor)
            upd = {"schedule_anchor_date": anchor.isoformat(), "next_planned_date": planned.isoformat(), "anchor_confirmed": True, "status_code": "ACTIVE", "updated_at": serialize_business_datetime(now_kst())}
            if item.last_inspection_date:
                upd["last_inspection_date"] = item.last_inspection_date
            supabase.table("inspection_sets").update(upd).eq("id", item.id).execute()
            try:
                supabase.table("work_schedules").delete().eq("inspection_set_id", item.id).eq("status_code", "SCHEDULED").execute()
                supabase.table("work_schedules").insert(row).execute()
            except Exception:
                pass
            updated_count += 1
        except Exception as e:
            errors.append({"id": item.id, "reason": str(e)})
    return {"status": "success", "data": {"updated": updated_count, "failed": len(errors), "errors": errors}}


def patch_set(inspection_set_id: str, body: InspectionSetPatchBody) -> dict:
    supabase = get_supabase()
    res = supabase.table("inspection_sets").select("id, cycle_value, cycle_unit, factory_id, company_id, inspection_set_name, inspection_category, source, schedule_anchor_date").eq("id", inspection_set_id).limit(1).execute()
    if not res.data:
        raise InspectionSetsSvcError(404, "점검세트를 찾을 수 없습니다.")
    iset = res.data[0]
    upd: Dict[str, Any] = {"updated_at": serialize_business_datetime(now_kst())}
    if body.is_active is not None:
        upd["is_active"] = body.is_active
    if body.last_inspection_date is not None:
        upd["last_inspection_date"] = body.last_inspection_date or None
    if body.assignee_user_id is not None:
        upd["assignee_user_id"] = body.assignee_user_id or None
    if body.description is not None:
        upd["description"] = body.description
    schedule_updated = False
    if body.schedule_anchor_date is not None:
        if body.schedule_anchor_date:
            anchor = date.fromisoformat(body.schedule_anchor_date)
            row, planned = _build_next_schedule_row(iset, anchor)
            upd.update({"schedule_anchor_date": body.schedule_anchor_date, "next_planned_date": planned.isoformat(), "anchor_confirmed": True, "status_code": "ACTIVE"})
            schedule_updated = True
        else:
            upd.update({"schedule_anchor_date": None, "next_planned_date": None, "anchor_confirmed": False, "status_code": "PENDING_ANCHOR"})
    result = supabase.table("inspection_sets").update(upd).eq("id", inspection_set_id).execute()
    if not result.data:
        raise InspectionSetsSvcError(500, "업데이트 실패")
    if schedule_updated:
        try:
            supabase.table("work_schedules").delete().eq("inspection_set_id", inspection_set_id).eq("status_code", "SCHEDULED").execute()
            supabase.table("work_schedules").insert(row).execute()
        except Exception:
            pass
    return {"status": "success", "message": "저장됐습니다.", "data": result.data[0] if result.data else {}}


def update_anchor(inspection_set_id: str, body: AnchorBody) -> dict:
    supabase = get_supabase()
    anchor_str = body.anchor_date or body.schedule_anchor_date
    if not anchor_str:
        raise InspectionSetsSvcError(422, "anchor_date 필수")
    res = supabase.table("inspection_sets").select("id, cycle_value, cycle_unit, factory_id, company_id, inspection_set_name, inspection_category, source, schedule_end_date").eq("id", inspection_set_id).limit(1).execute()
    if not res.data:
        raise InspectionSetsSvcError(404, "점검 세트를 찾을 수 없습니다.")
    iset = res.data[0]
    anchor = date.fromisoformat(anchor_str)
    row, planned = _build_next_schedule_row(iset, anchor)
    end_str = iset.get("schedule_end_date")
    if end_str and planned > date.fromisoformat(end_str):
        return {"status": "success", "message": "일정 종료일이 지나 생성 안 함.", "data": {"inspection_set_id": inspection_set_id, "anchor_date": anchor.isoformat(), "next_planned_date": planned.isoformat(), "anchor_confirmed": True, "created": 0}}
    upd = {"schedule_anchor_date": anchor.isoformat(), "next_planned_date": planned.isoformat(), "anchor_confirmed": True, "status_code": "ACTIVE", "updated_at": serialize_business_datetime(now_kst())}
    if body.last_inspection_date:
        upd["last_inspection_date"] = body.last_inspection_date
    result = supabase.table("inspection_sets").update(upd).eq("id", inspection_set_id).execute()
    if not result.data:
        raise InspectionSetsSvcError(500, "업데이트 실패")
    created = 0
    try:
        supabase.table("work_schedules").delete().eq("inspection_set_id", inspection_set_id).eq("status_code", "SCHEDULED").execute()
        created = len(supabase.table("work_schedules").insert(row).execute().data or [])
    except Exception:
        pass
    return {"status": "success", "message": f"{created}개 일정 생성됐습니다.", "data": {"inspection_set_id": inspection_set_id, "anchor_date": anchor.isoformat(), "next_planned_date": planned.isoformat(), "anchor_confirmed": True, "cycle": f"{iset.get('cycle_value')} {iset.get('cycle_unit')}", "created": created}}
