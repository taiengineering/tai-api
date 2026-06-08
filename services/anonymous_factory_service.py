"""Anonymous / consumer diagnosis via Compiler Core (temp factory lifecycle).

Phase 2: replaces runtime_metadata_resolution path for consumer step1.
Creates a short-lived factories row, on-demand facility_applicability evaluation,
fetches compiler candidates, converts to legacy step1 JSON, then cleans up.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

from schemas.legal_engine import DiagnoseStep1Body
from services.compiler_core_svc import COMPILER_VERSION, fetch_compiler_candidates
from services.facility_applicability_eval import evaluate_draft_for_facility
from services.input_normalizer import normalize_input
from services.legal_context import _input_to_facility_context
from services.legal_helpers import get_sector_groups
from services.legal_rules import get_construction_summary, normalize_sector_db, risk_level

log = logging.getLogger(__name__)

ANONYMOUS_COMPILER_ENGINE_VERSION = "v3.0-compiler-core-anonymous"
RULE_VERSION_COMPILER = "compiler_core:facility_applicability:v1"

_DRAFT_PAGE = 1000
_INSERT_CHUNK = 200
_PERSIST_STATUSES = frozenset({"MATCH_CANDIDATE", "POSSIBLE_CANDIDATE"})

_TASK_TYPE_TO_BUCKET: Dict[str, Tuple[str, str]] = {
    "APPOINTMENT": ("appointment", "선임"),
    "DESIGNATE": ("appointment", "선임"),
    "REPORT": ("report", "신고"),
    "NOTIFY": ("notify", "보고"),
    "SUBMIT": ("report", "신고"),
    "INSPECTION": ("inspection", "점검"),
    "INSPECT": ("inspection", "점검"),
    "MEASURE": ("inspection", "점검"),
    "INSTALL": ("action", "조치"),
    "MAINTAIN": ("action", "조치"),
    "EDUCATION": ("action", "조치"),
    "RECORD": ("action", "조치"),
    "PRESERVATION": ("action", "조치"),
}

_ACTION_TO_TASK: Dict[str, str] = {
    "INSPECT_FAMILY": "INSPECTION_TASK_CANDIDATE",
    "REPORT_FAMILY": "REPORT_TASK_CANDIDATE",
    "TRAINING_FAMILY": "TRAINING_TASK_CANDIDATE",
    "APPOINT_FAMILY": "APPOINTMENT_TASK_CANDIDATE",
    "RECORD_FAMILY": "RECORD_TASK_CANDIDATE",
    "PRESERVE_FAMILY": "PRESERVE_TASK_CANDIDATE",
    "INSTALL_FAMILY": "INSTALL_TASK_CANDIDATE",
    "MANAGE_FAMILY": "MANAGE_TASK_CANDIDATE",
    "NOTIFY_FAMILY": "NOTIFY_TASK_CANDIDATE",
    "MEASURE_FAMILY": "MEASURE_TASK_CANDIDATE",
    "VERIFY_FAMILY": "VERIFY_TASK_CANDIDATE",
    "DESIGNATE_FAMILY": "DESIGNATE_TASK_CANDIDATE",
    "EXECUTE_FAMILY": "EXECUTE_TASK_CANDIDATE",
    "PUBLISH_FAMILY": "PUBLISH_TASK_CANDIDATE",
    "CONSULT_FAMILY": "CONSULT_TASK_CANDIDATE",
    "PROVIDE_FAMILY": "PROVIDE_TASK_CANDIDATE",
    "REPAIR_FAMILY": "REPAIR_TASK_CANDIDATE",
    "REPLACE_FAMILY": "REPLACE_TASK_CANDIDATE",
    "CANCEL_FAMILY": "CANCEL_TASK_CANDIDATE",
    "CORRECT_FAMILY": "CORRECT_TASK_CANDIDATE",
    "PREVENT_FAMILY": "PREVENT_TASK_CANDIDATE",
    "PROCESS_FAMILY": "PROCESS_TASK_CANDIDATE",
    "REQUEST_FAMILY": "REQUEST_TASK_CANDIDATE",
}

_OBLIGATION_FAMILIES = frozenset(
    {
        "MANDATORY_FAMILY",
        "PERMISSIVE_FAMILY",
        "MANDATORY_ITEM_FAMILY",
        "PROHIBITION_FAMILY",
    }
)


def _bucket_for_task_type(task_type: str) -> Tuple[str, str]:
    tt = (task_type or "ACTION").upper()
    if tt in _TASK_TYPE_TO_BUCKET:
        return _TASK_TYPE_TO_BUCKET[tt]
    for prefix, bucket in _TASK_TYPE_TO_BUCKET.items():
        if tt.startswith(prefix):
            return bucket
    return ("action", "조치")


def _merge_body_input(body: DiagnoseStep1Body) -> Dict[str, Any]:
    inp = dict(body.input or {})
    for k, v in {
        "building_use_type": body.building_use_type,
        "employee_count": body.employee_count,
        "floor_area": body.floor_area,
        "worker_count": body.worker_count,
        "total_floor_area": body.total_floor_area,
        "electric_capacity": body.electric_capacity,
        "floor_count": body.floor_count,
        "contract_amount_eok": body.contract_amount_eok,
        "ksic_major": body.ksic_major,
        "facility_type": body.facility_type,
        "elevator_count": body.elevator_count,
        "gas_capacity_kg": body.gas_capacity_kg,
        "gas_capacity_m3": body.gas_capacity_m3,
        "boiler_capacity_kw": body.boiler_capacity_kw,
        "annual_energy_toe": body.annual_energy_toe,
        "has_high_pressure_gas": body.has_high_pressure_gas,
        "has_boiler": body.has_boiler,
        "has_hazardous_material": body.has_hazardous_material,
        "has_chemical_substance": body.has_chemical_substance,
        "construction_type": body.construction_type,
        "direct_workers": body.direct_workers,
        "subcon_workers": body.subcon_workers,
        "electrical_capacity_kw": body.electrical_capacity_kw,
        "has_tunnel_bridge": body.has_tunnel_bridge,
        "has_blasting": body.has_blasting,
        "has_crane": body.has_crane,
        "has_high_work": body.has_high_work,
    }.items():
        if v is not None and k not in inp:
            inp[k] = v
    return inp


def normalize_consumer_inp(body: DiagnoseStep1Body) -> Dict[str, Any]:
    """
    Consumer path: merge body fields → normalize_input → legal_context-ready dict.

    Defends legal_context float() parsing from unit strings (e.g. 800kVA, 78억).
    """
    base = _merge_body_input(body)
    sector = body.sector.strip().upper()
    norm = normalize_input({**base, "sector": sector})
    merged = {**base, **norm}
    if sector == "CONSTRUCTION":
        won = norm.get("contract_amount") or norm.get("construction_amount")
        if won is not None:
            merged["contract_amount_eok"] = float(won) / 100_000_000.0
    return merged


def prepare_step1_body_for_compiler(body: DiagnoseStep1Body) -> DiagnoseStep1Body:
    """Persist normalized values into body.input before compiler step1."""
    norm = normalize_consumer_inp(body)
    payload_input = dict(body.input or {})
    for key, val in norm.items():
        if key == "sector":
            continue
        payload_input[key] = val
    return body.model_copy(update={"input": payload_input})


def _resolve_site_type(sector_raw: str, inp: Dict[str, Any], ctx: Dict[str, Any]) -> str:
    """Layer 1→2: site_type = facility/building use (not sector enum)."""
    use = str(
        inp.get("building_use_type")
        or inp.get("facility_type")
        or ctx.get("building_use_code")
        or ""
    ).strip()
    if use:
        return use
    if sector_raw == "CONSTRUCTION":
        return str(ctx.get("construction_type") or "").strip()
    if sector_raw == "MANUFACTURING":
        return str(ctx.get("ksic_code") or "").strip()
    return ""


def create_temp_factory(supabase, body: DiagnoseStep1Body) -> str:
    """Consumer input → short-lived factories row (is_active=false)."""
    sector_raw = body.sector.strip().upper()
    inp = normalize_consumer_inp(body)
    ctx = _input_to_facility_context(sector_raw, inp)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    building_use_code = str(
        inp.get("building_use_type") or inp.get("facility_type") or ctx.get("building_use_code") or ""
    ).strip()
    site_type = _resolve_site_type(sector_raw, inp, ctx)
    sector_db = normalize_sector_db(sector_raw)
    row: Dict[str, Any] = {
        "name": f"[ANON]{sector_raw}-{ts}"[:200],
        "sector": sector_db,
        "site_type": site_type or None,
        "is_active": False,
        "status_code": "ANON_TEMP",
        "employee_count": int(ctx.get("worker_count") or ctx.get("employee_count") or 0),
        "building_area": float(ctx.get("building_area") or ctx.get("total_floor_area") or 0),
        "electrical_capacity_kw": float(
            ctx.get("electrical_capacity_kw") or ctx.get("electric_capacity") or 0
        ),
        "transformer_capacity_kva": float(ctx.get("transformer_capacity_kva") or 0),
        "gas_capacity_kg": float(ctx.get("gas_capacity_kg") or 0),
        "construction_amount": float(ctx.get("construction_amount") or 0),
        "subcontractor_worker_count": int(
            ctx.get("subcontractor_worker_count") or ctx.get("subcon_workers") or 0
        ),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    ksic = str(ctx.get("ksic_code") or "").strip()
    if ksic:
        row["ksic_code"] = ksic
    construction_type = str(ctx.get("construction_type") or "").strip()
    if construction_type:
        row["construction_type"] = construction_type
    if building_use_code:
        row["building_use_code"] = building_use_code
    floor_count = int(ctx.get("floor_count") or 0)
    if floor_count > 0:
        row["floor_count"] = floor_count
    gas_m3 = float(ctx.get("gas_capacity_m3") or 0)
    if gas_m3 > 0:
        row["gas_capacity_m3"] = gas_m3
    boiler_kw = float(ctx.get("boiler_capacity_kw") or 0)
    if boiler_kw > 0:
        row["boiler_capacity_kw"] = boiler_kw
    elevator_count = int(ctx.get("elevator_count") or 0)
    if elevator_count > 0:
        row["elevator_count"] = elevator_count
    annual_toe = float(ctx.get("annual_energy_toe") or 0)
    if annual_toe > 0:
        row["annual_energy_toe"] = annual_toe
    is_haz = ctx.get("is_hazardous_material")
    if is_haz is not None:
        row["is_hazardous_material"] = bool(is_haz)
    res = supabase.table("factories").insert(row).execute()
    if not res.data:
        raise RuntimeError("임시 시설(factories) 생성 실패")
    return str(res.data[0]["id"])


def _load_draft_slot_groups(supabase) -> Tuple[Dict[str, List[Dict]], Dict[str, List[Dict]]]:
    """Paginate draft_slot → numeric / scope groups keyed by draft_id."""
    numerics: Dict[str, List[Dict[str, Any]]] = {}
    scopes: Dict[str, List[Dict[str, Any]]] = {}
    offset = 0
    while True:
        res = (
            supabase.table("draft_slot")
            .select("draft_id, part_id, section, binding_field, operator, value, unit, family_name")
            .not_.is_("binding_field", "null")
            .in_("section", ["IF_NUMERIC", "IF_SCOPE"])
            .range(offset, offset + _DRAFT_PAGE - 1)
            .execute()
        )
        chunk = res.data or []
        if not chunk:
            break
        for row in chunk:
            draft_id = str(row.get("draft_id") or "")
            if not draft_id:
                continue
            section = (row.get("section") or "").upper()
            if section == "IF_NUMERIC":
                if not row.get("operator") or row.get("value") is None:
                    continue
                numerics.setdefault(draft_id, []).append(
                    {
                        "part_id": str(row.get("part_id") or ""),
                        "binding_field": row.get("binding_field"),
                        "operator": row.get("operator"),
                        "value": row.get("value"),
                        "unit": row.get("unit"),
                        "family": row.get("family_name"),
                    }
                )
            elif section == "IF_SCOPE":
                scopes.setdefault(draft_id, []).append(
                    {
                        "part_id": str(row.get("part_id") or ""),
                        "binding_field": row.get("binding_field"),
                        "family": row.get("family_name"),
                    }
                )
        if len(chunk) < _DRAFT_PAGE:
            break
        offset += _DRAFT_PAGE
    return numerics, scopes


def evaluate_single_factory(supabase, factory_id: str) -> Dict[str, int]:
    """
    On-demand facility_applicability for one factory (Compiler Core materialize).

    Uses facility_applicability_eval pure logic; persists MATCH/POSSIBLE rows only.
    """
    fac_res = supabase.table("factories").select("*").eq("id", factory_id).limit(1).execute()
    if not fac_res.data:
        raise LookupError(f"factory not found: {factory_id}")
    facility = fac_res.data[0]

    numerics, scopes = _load_draft_slot_groups(supabase)
    all_draft_ids = set(numerics.keys()) | set(scopes.keys())

    rows: List[Dict[str, Any]] = []
    for draft_id in all_draft_ids:
        evaluated = evaluate_draft_for_facility(
            facility,
            draft_id,
            numerics.get(draft_id, []),
            scopes.get(draft_id, []),
        )
        if not evaluated:
            continue
        overall, part_id, check_results = evaluated
        if overall not in _PERSIST_STATUSES:
            continue
        rows.append(
            {
                "factory_id": factory_id,
                "draft_id": draft_id,
                "part_id": part_id,
                "applicability_status": overall,
                "match_details": {"checks": len(check_results)},
            }
        )

    inserted = 0
    for i in range(0, len(rows), _INSERT_CHUNK):
        batch = rows[i : i + _INSERT_CHUNK]
        if not batch:
            continue
        supabase.table("facility_applicability").insert(batch).execute()
        inserted += len(batch)

    return {
        "drafts_evaluated": len(all_draft_ids),
        "applicability_inserted": inserted,
    }


def cleanup_temp_factory(supabase, factory_id: str) -> None:
    """Remove temp applicability rows and factories record."""
    fid = (factory_id or "").strip()
    if not fid:
        return
    try:
        supabase.table("facility_applicability").delete().eq("factory_id", fid).execute()
    except Exception as exc:
        log.warning("facility_applicability cleanup failed factory_id=%s: %s", fid, exc)
    try:
        supabase.table("factories").delete().eq("id", fid).execute()
    except Exception as exc:
        log.warning("factories cleanup failed factory_id=%s: %s", fid, exc)


def _load_draft_fallback_context(
    supabase,
    draft_ids: List[str],
) -> Dict[str, Dict[str, Any]]:
    """Batch-read executable_draft, law_master, draft_slot for fallback rule rows."""
    unique = [
        d
        for d in dict.fromkeys(str(x).strip() for x in draft_ids if x and str(x).strip())
    ]
    if not unique or supabase is None:
        return {}

    ctx: Dict[str, Dict[str, Any]] = {d: {} for d in unique}
    articles_by_draft: Dict[str, str] = {}

    for i in range(0, len(unique), _INSERT_CHUNK):
        chunk = unique[i : i + _INSERT_CHUNK]
        try:
            res = (
                supabase.table("executable_draft")
                .select("id, article_id, rule_candidate_id, part_id")
                .in_("id", chunk)
                .execute()
            )
        except Exception as exc:
            log.warning("executable_draft batch fetch failed: %s", exc)
            continue
        for row in res.data or []:
            did = str(row.get("id") or "")
            if not did:
                continue
            ctx[did]["article_id"] = row.get("article_id")
            ctx[did]["rule_candidate_id"] = row.get("rule_candidate_id")
            ctx[did]["part_id"] = row.get("part_id")
            if row.get("article_id"):
                articles_by_draft[did] = str(row["article_id"])

    article_meta: Dict[str, Dict[str, Any]] = {}
    article_ids = list(dict.fromkeys(articles_by_draft.values()))
    for i in range(0, len(article_ids), _INSERT_CHUNK):
        chunk = article_ids[i : i + _INSERT_CHUNK]
        try:
            res = (
                supabase.table("law_article")
                .select("id, law_id, article_no, article_title")
                .in_("id", chunk)
                .execute()
            )
        except Exception as exc:
            log.warning("law_article batch fetch failed: %s", exc)
            continue
        for row in res.data or []:
            article_meta[str(row["id"])] = row

    law_ids = list(
        dict.fromkeys(str(r.get("law_id")) for r in article_meta.values() if r.get("law_id"))
    )
    law_names: Dict[str, str] = {}
    for i in range(0, len(law_ids), _INSERT_CHUNK):
        chunk = law_ids[i : i + _INSERT_CHUNK]
        try:
            res = (
                supabase.table("law_master")
                .select("id, law_name")
                .in_("id", chunk)
                .execute()
            )
        except Exception as exc:
            log.warning("law_master batch fetch failed: %s", exc)
            continue
        for row in res.data or []:
            law_names[str(row["id"])] = (row.get("law_name") or "").strip()

    for did, aid in articles_by_draft.items():
        am = article_meta.get(aid) or {}
        law_name = law_names.get(str(am.get("law_id") or ""), "")
        art_no = am.get("article_no") or ""
        art_title = (am.get("article_title") or "").strip()
        ctx[did]["law_name"] = law_name
        ctx[did]["law_article"] = str(art_no) if art_no else ""
        ctx[did]["description"] = art_title or law_name

    slots_by_draft: Dict[str, List[Dict[str, Any]]] = {}
    for i in range(0, len(unique), _INSERT_CHUNK):
        chunk = unique[i : i + _INSERT_CHUNK]
        try:
            res = (
                supabase.table("draft_slot")
                .select("draft_id, section, family_name, raw_token")
                .in_("draft_id", chunk)
                .eq("section", "THEN_ACTION")
                .execute()
            )
        except Exception as exc:
            log.warning("draft_slot batch fetch failed: %s", exc)
            continue
        for row in res.data or []:
            did = str(row.get("draft_id") or "")
            if did:
                slots_by_draft.setdefault(did, []).append(row)

    for did, slots in slots_by_draft.items():
        obligation = ""
        for slot in slots:
            fam = slot.get("family_name") or ""
            if fam in _OBLIGATION_FAMILIES:
                obligation = fam
        for slot in slots:
            fam = slot.get("family_name") or ""
            if fam not in _ACTION_TO_TASK:
                continue
            ctx[did]["task_type"] = _ACTION_TO_TASK[fam]
            ctx[did]["source_action_family"] = fam
            token = (slot.get("raw_token") or "").strip()
            if token:
                ctx[did]["description"] = token
            break
        ctx[did]["obligation_family"] = obligation

    return ctx


def _rule_row_flags(bucket: str) -> Dict[str, bool]:
    return {
        "appointment_required": bucket == "appointment",
        "inspection_required": bucket == "inspection",
        "action_required": bucket == "action",
        "report_required": bucket == "report",
        "notify_required": bucket == "notify",
    }


def _task_to_rule_row(task: Dict[str, Any], sector_raw: str) -> Dict[str, Any]:
    task_type = (task.get("task_type") or "ACTION").upper()
    bucket, cat_label = _bucket_for_task_type(task_type)
    title = f"{task.get('task_type', '')}: {task.get('source_action_family', '')}".strip(": ")
    fam = (task.get("obligation_family") or "").strip()
    obl_type = task_type if task_type in ("APPOINT", "INSPECT", "REPORT", "NOTIFY", "ACTION") else "ACTION"
    return {
        "rule_id": str(task.get("id") or ""),
        "rule_type": task_type,
        "law_name": fam or "Compiler Candidate",
        "law_article": "",
        "obligation_summary": title or fam or "의무 후보",
        "remarks": title,
        "description": title or fam,
        "category": cat_label,
        "obligation_type": obl_type,
        "sector": sector_raw,
        "diagnosis_stage": 1,
        "schedule_type": "ON_DEMAND",
        "penalty_summary": "",
        **_rule_row_flags(bucket),
        "_bucket": bucket,
    }


def _applicability_to_rule_row(
    applicability: Dict[str, Any],
    sector_raw: str,
    draft_ctx: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    draft_id = str(applicability.get("draft_id") or "")
    meta = draft_ctx.get(draft_id) or {}
    task_type = (meta.get("task_type") or "ACTION").upper()
    bucket, cat_label = _bucket_for_task_type(task_type)
    source_fam = meta.get("source_action_family") or ""
    fam = (meta.get("obligation_family") or "").strip()
    law_name = (meta.get("law_name") or "").strip() or fam or "Compiler Candidate"
    desc = (meta.get("description") or "").strip()
    title = f"{task_type}: {source_fam}".strip(": ") if source_fam else (desc or law_name)
    obl_type = task_type if task_type in ("APPOINT", "INSPECT", "REPORT", "NOTIFY", "ACTION") else "ACTION"
    return {
        "rule_id": str(applicability.get("id") or draft_id),
        "rule_type": task_type,
        "law_name": law_name,
        "law_article": meta.get("law_article") or "",
        "obligation_summary": title or fam or "의무 후보",
        "remarks": title,
        "description": desc or title or fam,
        "category": cat_label,
        "obligation_type": obl_type,
        "sector": sector_raw,
        "diagnosis_stage": 1,
        "schedule_type": "ON_DEMAND",
        "penalty_summary": "",
        **_rule_row_flags(bucket),
        "_bucket": bucket,
    }


def _compiler_result_to_step1_format(
    compiler: Dict[str, Any],
    *,
    sector_raw: str,
    facility_ctx: Dict[str, Any],
    evaluated_at: str,
    supabase=None,
) -> Dict[str, Any]:
    """Compiler Core / DiagnosisService-shaped dict → legacy step1 result_data."""
    sector_db = normalize_sector_db(sector_raw)
    sector_groups = get_sector_groups(sector_db)
    tasks = compiler.get("task_candidates") or []
    applicability = compiler.get("applicability_candidates") or []

    rules_from_tasks = [_task_to_rule_row(t, sector_raw) for t in tasks]
    if not rules_from_tasks and applicability:
        draft_ids = [str(a.get("draft_id") or "") for a in applicability]
        draft_ctx = _load_draft_fallback_context(supabase, draft_ids)
        rules_from_tasks = [
            _applicability_to_rule_row(a, sector_raw, draft_ctx) for a in applicability
        ]

    triggered: Dict[str, List] = {
        "appointment": [],
        "inspection": [],
        "notify": [],
        "report": [],
        "action": [],
        "not_applicable": [],
    }
    for row in rules_from_tasks:
        bucket = row.pop("_bucket", "action")
        triggered[bucket].append(row)

    rules_table: List[Dict[str, Any]] = []
    for key, label in [
        ("appointment", "선임"),
        ("inspection", "점검"),
        ("action", "조치"),
        ("report", "신고"),
        ("notify", "보고"),
    ]:
        for row in triggered[key]:
            rules_table.append({"category": label, **row})

    total_applicable = sum(len(triggered[k]) for k in ("appointment", "inspection", "notify", "report", "action"))
    law_names = sorted({x.get("law_name") for x in rules_from_tasks if x.get("law_name")})
    appointment_n = len(triggered["appointment"])
    risk = risk_level(total_applicable, appointment_n)

    key_obligations: List[str] = []
    for x in rules_from_tasks[:20]:
        t = (x.get("obligation_summary") or x.get("remarks") or "").strip()
        if t and t not in key_obligations:
            key_obligations.append(t)

    obligations: List[Dict[str, Any]] = []
    for key, label in [("appointment", "선임"), ("inspection", "점검"), ("action", "조치")]:
        if triggered[key]:
            obligations.append({"category": key, "label": label, "items": triggered[key]})
    if triggered["report"]:
        obligations.append({"category": "report", "label": "신고", "items": triggered["report"]})
    if triggered["notify"]:
        obligations.append({"category": "notify", "label": "보고", "items": triggered["notify"]})

    risk_reason = f"적용 법령 {len(law_names)}개, 법적 의무 {total_applicable}건 (Compiler Core Candidate)"

    result: Dict[str, Any] = {
        "sector": sector_raw,
        "sector_groups": sector_groups,
        "step": 1,
        "engine_version": ANONYMOUS_COMPILER_ENGINE_VERSION,
        "rule_version": RULE_VERSION_COMPILER,
        "evaluated_at": evaluated_at,
        "facility_context": facility_ctx,
        "risk_level": risk,
        "risk_reason": risk_reason,
        "applicable_law_categories": law_names,
        "appointment_required_flag": appointment_n > 0,
        "key_obligations": key_obligations,
        "law_badges": law_names,
        "obligations": obligations,
        "rules_table": rules_table,
        "rules": rules_table,
        "appointment_required": triggered["appointment"],
        "inspection_required": triggered["inspection"],
        "action_required": triggered["action"],
        "report_required": triggered["report"] + triggered["notify"],
        "not_applicable": [],
        "not_applicable_total": 0,
        "total_rules_checked": total_applicable + len(applicability),
        "applicable_count": total_applicable,
        "article_mapping_stats": {
            "total_rules": total_applicable,
            "mapped_rules": 0,
            "coverage_pct": 0.0,
        },
        "inspection_schedule_ready": {
            "periodic_count": 0,
            "before_work_count": 0,
            "on_demand_count": len(triggered["inspection"]),
            "periodic": [],
            "before_work": [],
        },
        "summary": {
            "total": total_applicable,
            "appointment": len(triggered["appointment"]),
            "inspection": len(triggered["inspection"]),
            "action": len(triggered["action"]),
            "report": len(triggered["report"]),
            "notify": len(triggered["notify"]),
            "form_linked": 0,
        },
        "compiler_core": {
            "compiler_version": compiler.get("compiler_version") or COMPILER_VERSION,
            "warning": compiler.get("warning"),
            "applicability_count": len(applicability),
            "task_count": len(tasks),
            "schedule_count": len(compiler.get("schedule_candidates") or []),
            "applicability_candidates": applicability,
            "task_candidates": tasks,
            "schedule_candidates": compiler.get("schedule_candidates") or [],
        },
    }
    if sector_raw == "CONSTRUCTION":
        result["construction_summary"] = get_construction_summary(facility_ctx)
    return result


def run_anonymous_diagnosis(
    supabase,
    body: DiagnoseStep1Body,
    allowed_sectors: FrozenSet[str],
) -> Dict[str, Any]:
    """Full orchestration: temp factory → evaluate → fetch → format → cleanup."""
    sector_raw = body.sector.strip().upper()
    if sector_raw not in allowed_sectors:
        raise ValueError(
            "sector는 BUILDING, MANUFACTURING, CONSTRUCTION, SPECIAL_FACILITY 중 하나여야 합니다."
        )

    inp = normalize_consumer_inp(body)
    facility_ctx = _input_to_facility_context(sector_raw, inp)
    evaluated_at = datetime.now(timezone.utc).isoformat()

    factory_id: Optional[str] = None
    try:
        factory_id = create_temp_factory(supabase, body)
        evaluate_single_factory(supabase, factory_id)
        compiler = fetch_compiler_candidates(supabase, factory_id)
        return _compiler_result_to_step1_format(
            compiler,
            sector_raw=sector_raw,
            facility_ctx=facility_ctx,
            evaluated_at=evaluated_at,
            supabase=supabase,
        )
    finally:
        if factory_id:
            cleanup_temp_factory(supabase, factory_id)
