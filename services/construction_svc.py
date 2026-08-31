from datetime import date, datetime
from typing import Dict, List, Optional

import httpx

from services.construction_helpers import map_site_type_to_construction_type
from utils.logger import get_logger
from services.time import business_today, now_kst, serialize_business_datetime

log = get_logger(__name__)
FCM_URL = "https://fcm.googleapis.com/fcm/send"


def create_factory_for_site(supabase, site: dict, now_iso_fn) -> Optional[str]:
    try:
        contract_eok = float(site.get("contract_amount") or 0)
        site_type_raw = (site.get("site_type") or "BUILDING").upper()
        construction_type_label = map_site_type_to_construction_type(site_type_raw)

        factory_data = {
            "name": site.get("site_name", ""),
            "company_id": site.get("company_id"),
            "site_type": "CONSTRUCTION",
            "sector": "CONSTRUCTION",
            "construction_amount": contract_eok * 100_000_000,
            "employee_count": site.get("direct_workers") or site.get("total_workers") or 0,
            "subcontractor_worker_count": site.get("subcon_workers") or 0,
            "construction_type": construction_type_label,
            "site_address": site.get("site_address"),
            "status_code": "ACTIVE",
            "is_active": True,
            "created_at": now_iso_fn(),
            "updated_at": now_iso_fn(),
        }
        res = supabase.table("factories").insert(factory_data).execute()
        if res.data:
            factory_id = res.data[0]["id"]
            supabase.table("construction_sites").update(
                {"factory_id": factory_id, "updated_at": now_iso_fn()}
            ).eq("id", site["id"]).execute()
            return factory_id
    except Exception as e:
        log.error("[CONSTRUCTION] factories 자동생성 실패 (무시): %s", e, exc_info=True)
    return None


def run_diagnosis(supabase, factory_id: str, site: dict) -> dict:
    contract_eok = float(site.get("contract_amount") or 0)
    direct = int(site.get("direct_workers") or 0)
    subcon = int(site.get("subcon_workers") or 0)
    site_type_raw = site.get("site_type") or "BUILDING"

    from services.legal_context import _input_to_facility_context
    from services.legal_engine_svc import (
        ENGINE_VERSION,
        _evaluate_facility_conditions_db,
        get_construction_summary as _get_construction_summary,
    )
    from services.legal_format import _classify_rules_db, format_rule_result_db
    from services.legal_helpers import get_sector_groups

    sector_raw = "CONSTRUCTION"
    sector_groups = get_sector_groups(sector_raw)
    rules_res = (
        supabase.table("master_building_legal_rules")
        .select("*")
        .eq("is_active", True)
        .in_("sector", sector_groups)
        .eq("diagnosis_stage", 1)
        .execute()
    )
    all_rules = rules_res.data or []

    inp = {
        "contract_amount_eok": contract_eok,
        "direct_workers": direct,
        "subcon_workers": subcon,
        "construction_type": site_type_raw,
    }
    facility_ctx = _input_to_facility_context(sector_raw, inp)
    evaluated_at = serialize_business_datetime(now_kst())
    applicable, not_applicable = _evaluate_facility_conditions_db(facility_ctx, all_rules, sector_raw)

    triggered: Dict[str, List] = {
        "appointment": [],
        "inspection": [],
        "notify": [],
        "report": [],
        "action": [],
        "not_applicable": [],
    }
    _classify_rules_db(applicable, triggered)
    for r in not_applicable:
        triggered["not_applicable"].append(format_rule_result_db(r))

    total_applicable = sum(len(triggered[k]) for k in ("appointment", "inspection", "notify", "report", "action"))
    result_data = {
        "factory_id": factory_id,
        "sector": sector_raw,
        "sector_groups": sector_groups,
        "step": 1,
        "engine_version": ENGINE_VERSION,
        "evaluated_at": evaluated_at,
        "facility_context": facility_ctx,
        "appointment_required": triggered["appointment"],
        "inspection_required": triggered["inspection"],
        "action_required": triggered["action"],
        "report_required": triggered["report"] + triggered["notify"],
        "applicable_count": total_applicable,
        "construction_summary": _get_construction_summary(facility_ctx),
        "summary": {
            "total": total_applicable,
            "appointment": len(triggered["appointment"]),
            "inspection": len(triggered["inspection"]),
            "action": len(triggered["action"]),
            "report": len(triggered["report"]),
            "notify": len(triggered["notify"]),
        },
    }

    try:
        (
            supabase.table("factory_diagnosis_results")
            .update({"is_latest": False})
            .eq("factory_id", factory_id)
            .eq("sector", sector_raw)
            .eq("is_latest", True)
            .execute()
        )
    except Exception:
        pass

    save_res = supabase.table("factory_diagnosis_results").insert(
        {
            "factory_id": factory_id,
            "sector": sector_raw,
            "diagnosis_stage": 1,
            "input_data": inp,
            "result_data": result_data,
            "rule_count": total_applicable,
            "is_latest": True,
        }
    ).execute()

    diagnosis_id = save_res.data[0]["id"] if save_res.data else None

    if diagnosis_id:
        supabase.table("construction_sites").update(
            {
                "diagnosis_step1_id": diagnosis_id,
                "last_diagnosis_at": serialize_business_datetime(now_kst()),
                "diagnosis_applicable_count": total_applicable,
                "updated_at": serialize_business_datetime(now_kst()),
            }
        ).eq("factory_id", factory_id).execute()

    return {
        "applicable_count": total_applicable,
        "diagnosis_id": diagnosis_id,
        "result_data": result_data,
        "by_obligation_type": result_data["summary"],
        "applicable_rules": applicable,
    }


def run_generate_schedules(supabase, factory_id: str, inspection_rules: list, company_id: Optional[str]) -> dict:
    existing = (
        supabase.table("work_schedules")
        .select("rule_code")
        .eq("factory_id", factory_id)
        .eq("source_type", "LEGAL")
        .eq("status_code", "PENDING")
        .execute()
    )
    existing_codes = {r["rule_code"] for r in (existing.data or []) if r.get("rule_code")}

    today_str = business_today().isoformat()
    rows = []
    for rule in inspection_rules:
        rule_id = (rule.get("rule_id") or rule.get("rule_code") or "").strip()
        if not rule_id or rule_id in existing_codes:
            continue
        rows.append(
            {
                "factory_id": factory_id,
                "company_id": company_id,
                "source_type": "LEGAL",
                "rule_code": rule_id,
                "description": (rule.get("obligation_summary") or rule.get("description") or "").strip(),
                "obligation_type": rule.get("obligation_type") or "INSPECT",
                "law_name": rule.get("law_name") or "",
                "law_article": rule.get("law_article") or "",
                "form_code": rule.get("form_code") or None,
                "planned_date": today_str,
                "status_code": "PENDING",
                "active_yn": True,
            }
        )
        existing_codes.add(rule_id)

    created = 0
    for i in range(0, len(rows), 20):
        sched_res = supabase.table("work_schedules").insert(rows[i : i + 20]).execute()
        created += len(sched_res.data or [])

    skipped = len(inspection_rules) - len(rows)
    return {"created": created, "skipped": skipped, "total_rules": len(inspection_rules)}


def auto_diagnose_and_schedule(supabase, factory_id: str, site: dict) -> dict:
    result = {"diagnosis": None, "schedules": None}
    try:
        diag = run_diagnosis(supabase, factory_id, site)
        result["diagnosis"] = {"applicable_count": diag["applicable_count"]}

        company_res = supabase.table("factories").select("company_id").eq("id", factory_id).single().execute()
        company_id = company_res.data.get("company_id") if company_res.data else None

        inspection_rules = diag["result_data"].get("inspection_required") or []
        action_rules = diag["result_data"].get("action_required") or []
        all_rules = inspection_rules + action_rules
        sched = run_generate_schedules(supabase, factory_id, all_rules, company_id)
        result["schedules"] = sched

        try:
            from routers.inspection_set_auto import auto_create_inspection_sets_from_diagnosis

            auto_create_inspection_sets_from_diagnosis(
                supabase,
                factory_id,
                company_id,
                diag.get("applicable_rules") or [],
            )
        except Exception as e:
            log.error("[AUTO_INSPECT_SETS] 현장등록 자동생성 실패 (무시): %s", e, exc_info=True)

    except Exception as e:
        log.error("[CONSTRUCTION] 자동진단/일정생성 실패 (무시): %s", e, exc_info=True)
    return result


def prepare_inspection_payload(raw_data: dict, now_iso_fn) -> dict:
    data = dict(raw_data)
    checklist = data.get("checklist_items") or []
    if isinstance(checklist, list):
        bad_items = [
            item
            for item in checklist
            if isinstance(item, dict) and item.get("result") in ("bad", "fail", "이상", "FAIL")
        ]
        defect_count = len(bad_items)
        data["defect_count"] = defect_count
        if "overall_result" not in data or not data["overall_result"]:
            data["overall_result"] = "ISSUE" if defect_count > 0 else "PASS"

    if "inspection_date" in data and isinstance(data["inspection_date"], datetime):
        data["inspection_date"] = data["inspection_date"].isoformat()
    if "corrective_deadline" in data and isinstance(data["corrective_deadline"], date):
        data["corrective_deadline"] = data["corrective_deadline"].isoformat()
    data["created_at"] = now_iso_fn()
    data["updated_at"] = now_iso_fn()
    return data


def normalize_date_fields(data: dict, field_names: tuple[str, ...]) -> dict:
    out = dict(data)
    for key in field_names:
        if key in out and isinstance(out[key], date):
            out[key] = out[key].isoformat()
    return out


def create_record(supabase, table_name: str, data: dict, now_iso_fn, fail_message: str):
    payload = dict(data)
    payload["created_at"] = now_iso_fn()
    payload["updated_at"] = now_iso_fn()
    res = supabase.table(table_name).insert(payload).execute()
    if not res.data:
        raise ValueError(fail_message)
    return res.data[0]


def get_record_or_none(supabase, table_name: str, record_id: str):
    res = supabase.table(table_name).select("*").eq("id", record_id).limit(1).execute()
    return res.data[0] if res.data else None


def update_record(supabase, table_name: str, record_id: str, data: dict, now_iso_fn):
    payload = dict(data)
    payload["updated_at"] = now_iso_fn()
    res = supabase.table(table_name).update(payload).eq("id", record_id).execute()
    return res.data[0] if res.data else None


def soft_delete_record(supabase, table_name: str, record_id: str, now_iso_fn):
    res = (
        supabase.table(table_name)
        .update({"is_active": False, "updated_at": now_iso_fn()})
        .eq("id", record_id)
        .execute()
    )
    return res.data[0] if res.data else None


def apply_table_filters(q, filters: dict):
    for key, value in filters.items():
        if value is None:
            continue
        if key.endswith("__ilike"):
            q = q.ilike(key.replace("__ilike", ""), value)
        elif key.endswith("__gte"):
            q = q.gte(key.replace("__gte", ""), value)
        elif key.endswith("__lte"):
            q = q.lte(key.replace("__lte", ""), value)
        elif key.endswith("__in"):
            q = q.in_(key.replace("__in", ""), value)
        else:
            q = q.eq(key, value)
    return q


def count_table_rows(supabase, table_name: str, filters: dict) -> int:
    q = apply_table_filters(
        supabase.table(table_name).select("id", count="exact"),
        filters,
    )
    res = q.limit(0).execute()
    return res.count or 0


def inspection_result_summary(supabase, filters: dict) -> dict:
    """§63-③: overall_result PASS·ISSUE·FAIL 집계(필터 조건 동일, 결과별 breakdown)."""
    active = {k: v for k, v in filters.items() if v is not None}
    base = {k: v for k, v in active.items() if k != "overall_result"}
    total = count_table_rows(supabase, "construction_inspections", active)
    pass_count = count_table_rows(
        supabase, "construction_inspections", {**base, "overall_result": "PASS"}
    )
    issue_count = count_table_rows(
        supabase, "construction_inspections", {**base, "overall_result": "ISSUE"}
    )
    fail_count = count_table_rows(
        supabase, "construction_inspections", {**base, "overall_result": "FAIL"}
    )
    corrective_count = count_table_rows(
        supabase, "construction_inspections", {**base, "corrective_status": "IN_PROGRESS"}
    )
    return {
        "total": total,
        "pass": pass_count,
        "issue": issue_count,
        "fail": fail_count,
        "corrective_in_progress": corrective_count,
    }


def inspector_name_map(supabase, inspector_ids: list) -> dict:
    ids = sorted({i for i in inspector_ids if i})
    if not ids:
        return {}
    res = supabase.table("users").select("id, name").in_("id", ids).execute()
    return {row["id"]: (row.get("name") or "") for row in (res.data or [])}


def run_list_query(
    supabase,
    table_name: str,
    filters: dict,
    page: int,
    size: int,
    order_by: list,
):
    offset = (page - 1) * size
    q = apply_table_filters(
        supabase.table(table_name).select("*", count="exact"),
        filters,
    )
    for order in order_by:
        if isinstance(order, tuple):
            q = q.order(order[0], desc=bool(order[1]))
        else:
            q = q.order(order)
    res = q.range(offset, offset + size - 1).execute()
    return {"items": res.data or [], "total": res.count or 0, "page": page, "size": size}


async def send_fcm_inspection_alert(supabase, site_id: str, inspection_id: str, defect_count: int):
    import os

    fcm_server_key = os.getenv("FCM_SERVER_KEY", "")
    if not fcm_server_key:
        return
    try:
        site_res = supabase.table("construction_sites").select("site_name, manager_id").eq("id", site_id).limit(1).execute()
        if not site_res.data:
            return
        site = site_res.data[0]
        manager_id = site.get("manager_id")
        if not manager_id:
            return
        user_res = supabase.table("users").select("fcm_token, name").eq("id", manager_id).limit(1).execute()
        if not user_res.data or not user_res.data[0].get("fcm_token"):
            return
        fcm_token = user_res.data[0]["fcm_token"]
        site_name = site.get("site_name", "현장")
        payload = {
            "to": fcm_token,
            "notification": {
                "title": f"⚠️ [{site_name}] 점검 이상 발생",
                "body": f"이상 항목 {defect_count}건 감지. 즉시 확인이 필요합니다.",
                "sound": "default",
            },
            "data": {
                "type": "INSPECTION_FAIL",
                "site_id": site_id,
                "inspection_id": inspection_id,
                "defect_count": str(defect_count),
            },
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                FCM_URL,
                json=payload,
                headers={"Authorization": f"key={fcm_server_key}", "Content-Type": "application/json"},
            )
    except Exception as e:
        log.warning("[FCM] 점검 알림 발송 실패 (무시): %s", e)


from db.supabase_client import get_supabase as _health_get_supabase
from services.health_registry import register_probe


async def _probe_construction():
    sb = _health_get_supabase()
    r = sb.table("construction_sites").select("id", count="exact").limit(1).execute()
    return {"sites_count": r.count or 0}


register_probe(
    "construction",
    _probe_construction,
    critical=False,
    desc_ko="건설 관리",
    meta={
        "impacts": [
            {"name": "건설 현장관리", "page": "safe > 건설관리 > 현장관리"},
            {"name": "건설 점검", "page": "safe > 건설관리 > 점검관리"},
        ],
        "fix_links": [
            {"name": "Supabase DB", "url": "https://supabase.com/dashboard/project/vwlahtguyggrhvslabax"},
        ],
        "api": "GET /construction/sites",
        "code": "services/construction_svc.py",
    },
)
