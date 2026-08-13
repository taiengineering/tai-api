from __future__ import annotations

from datetime import date
from typing import Optional

from dateutil.relativedelta import relativedelta

from db.supabase_client import get_supabase
from schemas.inspection_sets import ManualInspectionSetBody
from services.inspection_sets_helpers import UNIT_KO, _build_items_for_set, _get_delta
from .errors import InspectionSetsSvcError


def get_sets_list(factory_id, source, anchor_confirmed, page, size) -> dict:
    supabase = get_supabase()
    query = supabase.table("inspection_sets").select(
        "id, company_id, factory_id, inspection_set_name, inspection_set_code, "
        "inspection_category, legal_rule_id, law_name, law_article, "
        "obligation_type, obligation_summary, cycle_unit, cycle_value, "
        "cycle_base_type, cycle_base_guide, anchor_type, schedule_anchor_date, "
        "last_inspection_date, next_planned_date, anchor_confirmed, description, source, "
        "is_active, status_code, assignee_user_id, created_at, updated_at",
        count="exact",
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
    # 파이프라인 정합 (2026-08-13): 격리된 master_building_legal_rules JOIN 제거.
    #   obligation_type/obligation_summary 는 LEG 파이프라인이 채운 inspection_sets
    #   자체 컬럼에서 서빙한다(값 생성 없음). penalty/form 계열은 LEG 파이프라인 산출이
    #   아니므로 응답 계약 유지를 위해 빈값으로 노출(소비처가 미표시).
    for item in items:
        item["obligation_type"] = item.get("obligation_type") or "OTHER"
        item["obligation_summary"] = item.get("obligation_summary") or ""
        item["penalty_summary"] = ""
        item["form_name"] = ""
        item["form_url"] = ""
        item["remarks"] = ""
        item["online_system"] = ""
        item["system_url"] = ""
        item["cycle_base_guide_rule"] = item.get("cycle_base_guide") or ""
    return {"status": "success", "data": {"items": items, "total": res.count or 0, "page": page, "size": size, "total_pages": ((res.count or 0) + size - 1) // size if res.count else 0}}


def create_manual_set(body: ManualInspectionSetBody) -> dict:
    supabase = get_supabase()
    if not (body.inspection_set_name or "").strip():
        raise InspectionSetsSvcError(422, "점검 세트명은 필수입니다.")
    fac_res = supabase.table("factories").select("company_id").eq("id", body.factory_id).limit(1).execute()
    company_id = fac_res.data[0].get("company_id") if fac_res.data else None
    guide = f"마지막 점검일로부터 {body.cycle_value}{UNIT_KO.get(body.cycle_unit, body.cycle_unit)}마다"
    res = supabase.table("inspection_sets").insert({
        "factory_id": body.factory_id, "company_id": company_id, "inspection_set_name": body.inspection_set_name.strip(),
        "inspection_category": body.inspection_category, "template_id": body.template_id, "cycle_value": body.cycle_value,
        "cycle_unit": body.cycle_unit, "cycle_base_type": body.cycle_base_type, "cycle_base_guide": guide,
        "custom_description": body.description, "source": "MANUAL", "status_code": "PENDING_ANCHOR",
        "anchor_confirmed": False, "is_active": True,
    }).execute()
    if not res.data:
        raise InspectionSetsSvcError(500, "점검 세트 생성 실패")
    return {"status": "success", "message": f'"{body.inspection_set_name}" 점검 세트 생성 완료', "data": {"inspection_set_id": res.data[0]["id"]}}


def get_preview_schedule(factory_id: str, months: int) -> dict:
    supabase = get_supabase()
    sets_res = supabase.table("inspection_sets").select(
        "id, inspection_set_name, cycle_unit, cycle_value, schedule_anchor_date, "
        "schedule_end_date, anchor_confirmed, next_planned_date"
    ).eq("factory_id", factory_id).eq("anchor_confirmed", True).eq("is_active", True).execute()
    sets = sets_res.data or []
    today = date.today()
    end_date = today + relativedelta(months=months)
    preview = []
    for iset in sets:
        cu = (iset.get("cycle_unit") or "year").lower()
        cv = int(iset.get("cycle_value") or 1)
        delta = _get_delta(cu, cv)
        a_str = iset.get("schedule_anchor_date")
        if not a_str:
            continue
        cursor = date.fromisoformat(iset["next_planned_date"]) if iset.get("next_planned_date") else date.fromisoformat(a_str) + delta
        end_str = iset.get("schedule_end_date")
        eff_end = min(end_date, date.fromisoformat(end_str) if end_str else end_date)
        while cursor <= eff_end:
            preview.append({"inspection_set_id": iset["id"], "inspection_set_name": iset.get("inspection_set_name") or "", "planned_date": cursor.isoformat(), "is_actual": False, "cycle": f"{cv} {cu}"})
            cursor += delta
    preview.sort(key=lambda x: x["planned_date"])
    return {"status": "success", "data": {"factory_id": factory_id, "from": today.isoformat(), "to": end_date.isoformat(), "months": months, "count": len(preview), "preview": preview}}


def generate_all_items(factory_id: Optional[str], dry_run: bool) -> dict:
    supabase = get_supabase()
    q = supabase.table("inspection_sets").select("id, inspection_set_name, legal_rule_id, factory_id").not_.is_("legal_rule_id", "null").eq("is_active", True)
    if factory_id:
        q = q.eq("factory_id", factory_id)
    sets = q.execute().data or []
    if not sets:
        return {"status": "success", "message": "처리할 점검세트가 없습니다.", "data": {"total_sets": 0, "created": 0, "skipped": 0, "failed": 0}}
    set_ids = [s["id"] for s in sets]
    existing_set_ids = set()
    for i in range(0, len(set_ids), 100):
        for row in (supabase.table("inspection_set_items").select("inspection_set_id").in_("inspection_set_id", set_ids[i:i + 100]).execute().data or []):
            existing_set_ids.add(row["inspection_set_id"])
    rule_ids = list({s["legal_rule_id"] for s in sets if s.get("legal_rule_id")})
    rules_map = {}
    for i in range(0, len(rule_ids), 100):
        for rule in (supabase.table("master_building_legal_rules").select("rule_id, obligation_summary, obligation_type, law_name, law_article").in_("rule_id", rule_ids[i:i + 100]).eq("is_active", True).execute().data or []):
            rules_map[rule["rule_id"]] = rule
    created = skipped = failed = 0
    preview_rows = []
    for iset in sets:
        set_id = iset["id"]
        if set_id in existing_set_ids:
            skipped += 1
            continue
        rule = rules_map.get(iset.get("legal_rule_id"))
        if not rule:
            skipped += 1
            continue
        item_rows = _build_items_for_set(iset, rule)
        preview_rows.extend(item_rows)
        if dry_run:
            created += len(item_rows)
            continue
        try:
            supabase.table("inspection_set_items").insert(item_rows).execute()
            created += len(item_rows)
        except Exception:
            failed += 1
    return {"status": "success", "message": f"{'[DRY RUN] ' if dry_run else ''}총 {len(sets)}개 처리 — 생성 {created}건, 스킵 {skipped}건, 실패 {failed}건", "data": {"total_sets": len(sets), "created": created, "skipped": skipped, "failed": failed, "dry_run": dry_run, **({'preview': preview_rows[:20]} if dry_run else {})}}


def generate_items_for_set(inspection_set_id: str) -> dict:
    supabase = get_supabase()
    set_res = supabase.table("inspection_sets").select("id, inspection_set_name, legal_rule_id, factory_id").eq("id", inspection_set_id).limit(1).execute()
    if not set_res.data:
        raise InspectionSetsSvcError(404, "점검세트를 찾을 수 없습니다.")
    iset = set_res.data[0]
    rule_id = iset.get("legal_rule_id")
    if not rule_id:
        raise InspectionSetsSvcError(422, "legal_rule_id가 없는 점검세트입니다.")
    if supabase.table("inspection_set_items").select("id").eq("inspection_set_id", inspection_set_id).limit(1).execute().data:
        return {"status": "skipped", "message": "이미 항목이 존재합니다.", "data": {"inspection_set_id": inspection_set_id, "created": 0}}
    rule_res = supabase.table("master_building_legal_rules").select("rule_id, obligation_summary, obligation_type, law_name, law_article").eq("rule_id", rule_id).eq("is_active", True).limit(1).execute()
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
