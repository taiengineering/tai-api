from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, Optional

from dateutil.relativedelta import relativedelta

from db.supabase_client import get_supabase
from schemas.inspection_sets import (
    AnchorBody,
    AnchorBulkPatchBody,
    BulkAnchorBody,
    InspectionSetPatchBody,
    ManualInspectionSetBody,
)
from services.inspection_sets_helpers import (
    UNIT_KO,
    _build_items_for_set,
    _build_law_engine_row,
    _build_next_schedule_row,
    _get_delta,
    _meets_4_conditions,
)


class InspectionSetsSvcError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail


def run_generate_law_engine(factory_id: str, supabase) -> dict:
    sets_res = supabase.table("inspection_sets").select(
        "id, factory_id, company_id, schedule_anchor_date, cycle_unit, cycle_value, "
        "assignee_user_id, description, legal_rule_code, legal_rule_id, "
        "law_name, law_article, inspection_category"
    ).eq("factory_id", factory_id).eq("is_active", True).execute()
    all_sets = sets_res.data or []
    if not all_sets:
        return {"total_sets": 0, "created": 0, "skipped_dup": 0, "skipped_no_condition": 0}
    existing_res = supabase.table("work_schedules").select("inspection_set_id") \
        .eq("factory_id", factory_id) \
        .eq("source_type", "LAW_ENGINE") \
        .eq("status_code", "PENDING") \
        .execute()
    existing_ids = {
        r["inspection_set_id"] for r in (existing_res.data or []) if r.get("inspection_set_id")
    }
    rows = []
    skipped_dup = 0
    skipped_no_cond = 0
    for iset in all_sets:
        set_id = iset["id"]
        if set_id in existing_ids:
            skipped_dup += 1
            continue
        if not _meets_4_conditions(iset):
            skipped_no_cond += 1
            continue
        rows.append(_build_law_engine_row(iset))
        existing_ids.add(set_id)
    created = 0
    for i in range(0, len(rows), 20):
        res = supabase.table("work_schedules").insert(rows[i:i + 20]).execute()
        created += len(res.data or [])
    return {
        "total_sets": len(all_sets),
        "created": created,
        "skipped_dup": skipped_dup,
        "skipped_no_condition": skipped_no_cond,
    }


def get_sets_list(factory_id, source, anchor_confirmed, page, size) -> dict:
    supabase = get_supabase()
    query = supabase.table("inspection_sets").select(
        "id, company_id, factory_id, inspection_set_name, inspection_set_code, "
        "inspection_category, "
        "legal_rule_id, law_name, law_article, cycle_unit, cycle_value, "
        "cycle_base_type, cycle_base_guide, anchor_type, "
        "schedule_anchor_date, last_inspection_date, next_planned_date, anchor_confirmed, "
        "description, source, is_active, status_code, "
        "assignee_user_id, created_at, updated_at",
        count="exact"
    )
    if factory_id:
        query = query.eq("factory_id", factory_id)
    if source:
        query = query.eq("source", source)
    if anchor_confirmed is not None:
        query = query.eq("anchor_confirmed", anchor_confirmed)
    offset = (page - 1) * size
    res = query.order("created_at", desc=True).range(offset, offset + size - 1).execute()
    items = res.data or []
    rule_ids = list({r["legal_rule_id"] for r in items if r.get("legal_rule_id")})
    rules_map = {}
    if rule_ids:
        for i in range(0, len(rule_ids), 100):
            chunk = rule_ids[i:i+100]
            r_res = supabase.table("master_building_legal_rules").select(
                "rule_id, obligation_type, obligation_summary, "
                "penalty_summary, form_name, form_url, remarks, "
                "cycle_base_guide, online_system, system_url"
            ).in_("rule_id", chunk).execute()
            for row in (r_res.data or []):
                rules_map[row["rule_id"]] = row
    for item in items:
        rule_id = item.get("legal_rule_id")
        rule_row = rules_map.get(rule_id, {}) if rule_id else {}
        item["obligation_type"] = rule_row.get("obligation_type") or "OTHER"
        item["obligation_summary"] = rule_row.get("obligation_summary") or ""
        item["penalty_summary"] = rule_row.get("penalty_summary") or ""
        item["form_name"] = rule_row.get("form_name") or ""
        item["form_url"] = rule_row.get("form_url") or ""
        item["remarks"] = rule_row.get("remarks") or ""
        item["online_system"] = rule_row.get("online_system") or ""
        item["system_url"] = rule_row.get("system_url") or ""
        item["cycle_base_guide_rule"] = rule_row.get("cycle_base_guide") or ""
    return {
        "status": "success",
        "data": {
            "items": items,
            "total": res.count or 0,
            "page": page,
            "size": size,
            "total_pages": ((res.count or 0) + size - 1) // size if res.count else 0,
        },
    }


def create_manual_set(body: ManualInspectionSetBody) -> dict:
    supabase = get_supabase()
    if not (body.inspection_set_name or "").strip():
        raise InspectionSetsSvcError(422, "점검 세트명은 필수입니다.")
    fac_res = supabase.table("factories").select("company_id").eq(
        "id", body.factory_id
    ).limit(1).execute()
    company_id = fac_res.data[0].get("company_id") if fac_res.data else None
    guide = f"마지막 점검일로부터 {body.cycle_value}{UNIT_KO.get(body.cycle_unit, body.cycle_unit)}마다"
    res = supabase.table("inspection_sets").insert({
        "factory_id": body.factory_id, "company_id": company_id,
        "inspection_set_name": body.inspection_set_name.strip(),
        "inspection_category": body.inspection_category,
        "template_id": body.template_id,
        "cycle_value": body.cycle_value, "cycle_unit": body.cycle_unit,
        "cycle_base_type": body.cycle_base_type, "cycle_base_guide": guide,
        "custom_description": body.description,
        "source": "MANUAL", "status_code": "PENDING_ANCHOR",
        "anchor_confirmed": False, "is_active": True,
    }).execute()
    if not res.data:
        raise InspectionSetsSvcError(500, "점검 세트 생성 실패")
    return {"status": "success", "message": f'"{body.inspection_set_name}" 점검 세트 생성 완료', "data": {"inspection_set_id": res.data[0]["id"]}}


def get_preview_schedule(factory_id: str, months: int) -> dict:
    supabase = get_supabase()
    sets_res = supabase.table("inspection_sets").select(
        "id, inspection_set_name, cycle_unit, cycle_value, "
        "schedule_anchor_date, schedule_end_date, anchor_confirmed, next_planned_date"
    ).eq("factory_id", factory_id).eq("anchor_confirmed", True).eq("is_active", True).execute()
    sets = sets_res.data or []
    today = date.today()
    end_date = today + relativedelta(months=months)
    preview = []
    for iset in sets:
        cu = (iset.get("cycle_unit") or "year").lower()
        cv = int(iset.get("cycle_value") or 1)
        delta = _get_delta(cu, cv)
        name = iset.get("inspection_set_name") or ""
        a_str = iset.get("schedule_anchor_date")
        if not a_str:
            continue
        cursor = date.fromisoformat(iset["next_planned_date"]) if iset.get("next_planned_date") else date.fromisoformat(a_str) + delta
        end_str = iset.get("schedule_end_date")
        eff_end = min(end_date, date.fromisoformat(end_str) if end_str else end_date)
        while cursor <= eff_end:
            preview.append({"inspection_set_id": iset["id"], "inspection_set_name": name, "planned_date": cursor.isoformat(), "is_actual": False, "cycle": f"{cv} {cu}"})
            cursor += delta
    preview.sort(key=lambda x: x["planned_date"])
    return {"status": "success", "data": {"factory_id": factory_id, "from": today.isoformat(), "to": end_date.isoformat(), "months": months, "count": len(preview), "preview": preview}}


def set_anchor_bulk(body: BulkAnchorBody) -> dict:
    supabase = get_supabase()
    sets_res = supabase.table("inspection_sets").select(
        "id, factory_id, company_id, cycle_value, cycle_unit, "
        "inspection_set_name, inspection_category, source"
    ).eq("factory_id", body.factory_id).eq("status_code", "PENDING_ANCHOR").eq("is_active", True).execute()
    sets = sets_res.data or []
    if not sets:
        return {"status": "success", "message": "처리할 PENDING_ANCHOR 상태 점검세트가 없습니다.", "data": {"total_sets": 0, "total_created": 0, "results": []}}
    anchor = date.fromisoformat(body.anchor_date)
    results, total_created = [], 0
    for iset in sets:
        try:
            row, planned = _build_next_schedule_row(iset, anchor)
            supabase.table("inspection_sets").update({
                "schedule_anchor_date": anchor.isoformat(),
                "next_planned_date": planned.isoformat(),
                "anchor_confirmed": True, "status_code": "ACTIVE",
                "updated_at": datetime.now().isoformat(),
            }).eq("id", iset["id"]).execute()
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
            res = supabase.table("inspection_sets").select(
                "id, cycle_value, cycle_unit, factory_id, company_id, inspection_set_name, inspection_category, source"
            ).eq("id", item.id).limit(1).execute()
            if not res.data:
                errors.append({"id": item.id, "reason": "점검 세트를 찾을 수 없습니다."})
                continue
            iset = res.data[0]
            anchor = date.fromisoformat(item.schedule_anchor_date)
            row, planned = _build_next_schedule_row(iset, anchor)
            upd = {"schedule_anchor_date": anchor.isoformat(), "next_planned_date": planned.isoformat(), "anchor_confirmed": True, "status_code": "ACTIVE", "updated_at": datetime.now().isoformat()}
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


def generate_all_items(factory_id: Optional[str], dry_run: bool) -> dict:
    supabase = get_supabase()
    q = supabase.table("inspection_sets").select(
        "id, inspection_set_name, legal_rule_id, factory_id"
    ).not_.is_("legal_rule_id", "null").eq("is_active", True)
    if factory_id:
        q = q.eq("factory_id", factory_id)
    sets = q.execute().data or []
    if not sets:
        return {"status": "success", "message": "처리할 점검세트가 없습니다.", "data": {"total_sets": 0, "created": 0, "skipped": 0, "failed": 0}}
    set_ids = [s["id"] for s in sets]
    existing_set_ids = set()
    for i in range(0, len(set_ids), 100):
        for row in (supabase.table("inspection_set_items").select("inspection_set_id").in_("inspection_set_id", set_ids[i:i+100]).execute().data or []):
            existing_set_ids.add(row["inspection_set_id"])
    rule_ids = list({s["legal_rule_id"] for s in sets if s.get("legal_rule_id")})
    rules_map = {}
    for i in range(0, len(rule_ids), 100):
        for rule in (supabase.table("master_building_legal_rules").select(
            "rule_id, obligation_summary, obligation_type, law_name, law_article"
        ).in_("rule_id", rule_ids[i:i+100]).eq("is_active", True).execute().data or []):
            rules_map[rule["rule_id"]] = rule
    created, skipped, failed, preview_rows = 0, 0, 0, []
    for iset in sets:
        set_id = iset["id"]
        rule_id = iset.get("legal_rule_id")
        if set_id in existing_set_ids:
            skipped += 1
            continue
        rule = rules_map.get(rule_id)
        if not rule:
            skipped += 1
            continue
        item_rows = _build_items_for_set(iset, rule)
        preview_rows.extend(item_rows)
        if not dry_run:
            try:
                supabase.table("inspection_set_items").insert(item_rows).execute()
                created += len(item_rows)
            except Exception:
                failed += 1
        else:
            created += len(item_rows)
    return {"status": "success", "message": f"{'[DRY RUN] ' if dry_run else ''}총 {len(sets)}개 처리 — 생성 {created}건, 스킵 {skipped}건, 실패 {failed}건", "data": {"total_sets": len(sets), "created": created, "skipped": skipped, "failed": failed, "dry_run": dry_run, **({"preview": preview_rows[:20]} if dry_run else {})}}


def generate_schedules_all() -> dict:
    supabase = get_supabase()
    factories_res = supabase.table("factories").select("id").eq("is_active", True).execute()
    factories = factories_res.data or []
    total_created = 0
    total_skipped_d = 0
    total_skipped_c = 0
    processed = 0
    results = []
    for fac in factories:
        factory_id = fac["id"]
        r = run_generate_law_engine(factory_id, supabase)
        if r["total_sets"] == 0:
            continue
        processed += 1
        total_created += r["created"]
        total_skipped_d += r["skipped_dup"]
        total_skipped_c += r["skipped_no_condition"]
        results.append({"factory_id": factory_id, "total_sets": r["total_sets"], "created": r["created"], "skipped_dup": r["skipped_dup"], "skipped_no_condition": r["skipped_no_condition"]})
    return {"status": "success", "message": f"공장 {processed}개 처리 — LAW_ENGINE 스케줄 총 {total_created}건 생성", "data": {"total_factories": len(factories), "processed": processed, "total_created": total_created, "total_skipped_duplicate": total_skipped_d, "total_skipped_no_condition": total_skipped_c, "results": results}}


def generate_schedules_for_factory(factory_id: str, mode: str, force: bool) -> dict:
    supabase = get_supabase()
    if mode == "law_engine":
        r = run_generate_law_engine(factory_id, supabase)
        return {"status": "success", "message": f"{r['total_sets']}개 세트 처리 — LAW_ENGINE 스케줄 {r['created']}건 생성", "data": {"factory_id": factory_id, "mode": "law_engine", "total_sets": r["total_sets"], "created": r["created"], "skipped_duplicate": r["skipped_dup"], "skipped_no_condition": r["skipped_no_condition"]}}
    sets_res = supabase.table("inspection_sets").select(
        "id, factory_id, company_id, cycle_value, cycle_unit, "
        "inspection_set_name, inspection_category, source, "
        "schedule_anchor_date, next_planned_date"
    ).eq("factory_id", factory_id).eq("anchor_confirmed", True).eq("is_active", True).execute()
    sets = sets_res.data or []
    if not sets:
        return {"status": "success", "message": "생성할 점검세트가 없습니다 (기준일 미설정 또는 없음)", "data": {"factory_id": factory_id, "mode": "anchor", "total": 0, "created": 0, "skipped": 0}}
    created, skipped, results = 0, 0, []
    for iset in sets:
        set_id = iset["id"]
        name = iset.get("inspection_set_name") or ""
        anchor_str = iset.get("schedule_anchor_date")
        if not anchor_str:
            skipped += 1
            results.append({"id": set_id, "name": name, "status": "skipped", "reason": "기준일 없음"})
            continue
        existing = supabase.table("work_schedules").select("id").eq("inspection_set_id", set_id).eq("status_code", "SCHEDULED").limit(1).execute()
        if existing.data and not force:
            skipped += 1
            results.append({"id": set_id, "name": name, "status": "skipped", "reason": "이미 스케줄 존재"})
            continue
        try:
            anchor = date.fromisoformat(anchor_str)
            row, planned = _build_next_schedule_row(iset, anchor)
            if force and existing.data:
                supabase.table("work_schedules").delete().eq("inspection_set_id", set_id).eq("status_code", "SCHEDULED").execute()
            r = supabase.table("work_schedules").insert(row).execute()
            c = len(r.data or [])
            created += c
            results.append({"id": set_id, "name": name, "status": "created", "planned_date": planned.isoformat()})
        except Exception as e:
            results.append({"id": set_id, "name": name, "status": "error", "reason": str(e)})
    return {"status": "success", "message": f"{len(sets)}개 처리 — 생성 {created}건, 스킵 {skipped}건", "data": {"factory_id": factory_id, "mode": "anchor", "total": len(sets), "created": created, "skipped": skipped, "results": results}}


def patch_set(inspection_set_id: str, body: InspectionSetPatchBody) -> dict:
    supabase = get_supabase()
    res = supabase.table("inspection_sets").select(
        "id, cycle_value, cycle_unit, factory_id, company_id, "
        "inspection_set_name, inspection_category, source, schedule_anchor_date"
    ).eq("id", inspection_set_id).limit(1).execute()
    if not res.data:
        raise InspectionSetsSvcError(404, "점검세트를 찾을 수 없습니다.")
    iset = res.data[0]
    upd: Dict[str, Any] = {"updated_at": datetime.now().isoformat()}
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
        a_str = body.schedule_anchor_date
        if a_str:
            anchor = date.fromisoformat(a_str)
            row, planned = _build_next_schedule_row(iset, anchor)
            upd.update({"schedule_anchor_date": a_str, "next_planned_date": planned.isoformat(), "anchor_confirmed": True, "status_code": "ACTIVE"})
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
    res = supabase.table("inspection_sets").select(
        "id, cycle_value, cycle_unit, factory_id, company_id, inspection_set_name, inspection_category, source, schedule_end_date"
    ).eq("id", inspection_set_id).limit(1).execute()
    if not res.data:
        raise InspectionSetsSvcError(404, "점검 세트를 찾을 수 없습니다.")
    iset = res.data[0]
    anchor = date.fromisoformat(anchor_str)
    row, planned = _build_next_schedule_row(iset, anchor)
    end_str = iset.get("schedule_end_date")
    if end_str and planned > date.fromisoformat(end_str):
        return {"status": "success", "message": "일정 종료일이 지나 생성 안 함.", "data": {"inspection_set_id": inspection_set_id, "anchor_date": anchor.isoformat(), "next_planned_date": planned.isoformat(), "anchor_confirmed": True, "created": 0}}
    upd = {"schedule_anchor_date": anchor.isoformat(), "next_planned_date": planned.isoformat(), "anchor_confirmed": True, "status_code": "ACTIVE", "updated_at": datetime.now().isoformat()}
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


def generate_items_for_set(inspection_set_id: str) -> dict:
    supabase = get_supabase()
    set_res = supabase.table("inspection_sets").select(
        "id, inspection_set_name, legal_rule_id, factory_id"
    ).eq("id", inspection_set_id).limit(1).execute()
    if not set_res.data:
        raise InspectionSetsSvcError(404, "점검세트를 찾을 수 없습니다.")
    iset = set_res.data[0]
    rule_id = iset.get("legal_rule_id")
    if not rule_id:
        raise InspectionSetsSvcError(422, "legal_rule_id가 없는 점검세트입니다.")
    if supabase.table("inspection_set_items").select("id").eq("inspection_set_id", inspection_set_id).limit(1).execute().data:
        return {"status": "skipped", "message": "이미 항목이 존재합니다.", "data": {"inspection_set_id": inspection_set_id, "created": 0}}
    rule_res = supabase.table("master_building_legal_rules").select(
        "rule_id, obligation_summary, obligation_type, law_name, law_article"
    ).eq("rule_id", rule_id).eq("is_active", True).limit(1).execute()
    if not rule_res.data:
        raise InspectionSetsSvcError(404, f"법령룰 없음 (rule_id={rule_id})")
    rule = rule_res.data[0]
    item_rows = _build_items_for_set(iset, rule)
    ins_res = supabase.table("inspection_set_items").insert(item_rows).execute()
    created = len(ins_res.data or [])
    return {"status": "success", "message": f"{created}개 점검 항목 생성됐습니다.", "data": {"inspection_set_id": inspection_set_id, "inspection_set_name": iset.get("inspection_set_name"), "rule_id": rule_id, "obligation_type": rule.get("obligation_type"), "created": created, "items": ins_res.data or []}}


def get_company_sets(company_id: str) -> dict:
    supabase = get_supabase()
    return {"status": "success", "data": supabase.table("inspection_sets").select("*").eq("company_id", company_id).order("created_at", desc=True).execute().data}


def get_factory_sets(factory_id: str) -> dict:
    supabase = get_supabase()
    return {"status": "success", "data": supabase.table("inspection_sets").select("*").eq("factory_id", factory_id).order("created_at", desc=True).execute().data}


def get_set_by_id(inspection_set_id: str) -> dict:
    supabase = get_supabase()
    result = supabase.table("inspection_sets").select("*").eq("id", inspection_set_id).single().execute()
    if not result.data:
        raise InspectionSetsSvcError(404, "점검세트를 찾을 수 없습니다")
    return {"status": "success", "data": result.data}
