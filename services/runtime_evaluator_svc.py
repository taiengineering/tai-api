"""TAI Runtime Evaluator Engine v1.0.0

Deterministic Condition-Based Rule Activation Engine.
절대 금지: semantic inference, best_match, fallback, guessed, probable,
           AI recommendation, similar industry, hidden normalization,
           auto condition repair, implied obligation activation

허용: EXPLICIT_MATCH, THRESHOLD_MATCH, EVENT_MATCH, SCHEDULE_MATCH
"""
from datetime import datetime, timezone
from db.supabase_client import get_supabase


# ═══ 1. Evaluation Context ═══

def create_context(data: dict) -> dict:
    sb = get_supabase()
    now = datetime.now(timezone.utc).isoformat()
    rec = {
        "industry_code": data.get("industry_code"),
        "worker_count": data.get("worker_count"),
        "hazardous_materials": data.get("hazardous_materials", []),
        "equipment": data.get("equipment", []),
        "pressure_vessels": data.get("pressure_vessels", []),
        "fire_facilities": data.get("fire_facilities", []),
        "contractors": data.get("contractors", []),
        "process_types": data.get("process_types", []),
        "accident_occurred": data.get("accident_occurred", False),
        "construction_started": data.get("construction_started", False),
        "shutdown": data.get("shutdown", False),
        "additional_inputs": data.get("additional_inputs", {}),
        "evaluation_status": "PENDING",
        "created_by": data.get("created_by"),
        "created_at": now,
        "updated_at": now,
    }
    if data.get("company_id"): rec["company_id"] = data["company_id"]
    if data.get("facility_id"): rec["facility_id"] = data["facility_id"]
    r = sb.table("runtime_evaluation_context").insert(rec).execute()
    ctx = r.data[0] if r.data else {}
    if ctx:
        _audit(sb, ctx["id"], "CONTEXT_CREATED", None, None, None, "context created", data.get("created_by"))
    return ctx


def get_context(ctx_id: str) -> dict:
    sb = get_supabase()
    r = sb.table("runtime_evaluation_context").select("*").eq("id", ctx_id).single().execute()
    return r.data


def list_contexts(company_id: str = None, page: int = 1, page_size: int = 20) -> dict:
    sb = get_supabase()
    q = sb.table("runtime_evaluation_context").select("*", count="exact")
    if company_id: q = q.eq("company_id", company_id)
    o = (page - 1) * page_size
    q = q.order("created_at", desc=True).range(o, o + page_size - 1)
    r = q.execute()
    return {"items": r.data or [], "total": r.count or 0, "page": page, "page_size": page_size}


# ═══ 2. Core Evaluator ═══

def evaluate(ctx_id: str) -> dict:
    """Deterministic evaluation. semantic/fallback/guess 절대 금지."""
    sb = get_supabase()
    ctx = sb.table("runtime_evaluation_context").select("*").eq("id", ctx_id).single().execute()
    if not ctx.data: raise ValueError("context not found")
    c = ctx.data
    sb.table("runtime_evaluation_context").update({"evaluation_status": "EVALUATING", "updated_at": datetime.now(timezone.utc).isoformat()}).eq("id", ctx_id).execute()

    results = {"rules": [], "tasks": [], "documents": [], "schedules": [], "penalties": [], "conflicts": [], "unknown": [], "ambiguous": []}
    try:
        # [3단계] Condition Evaluator + [4단계] Rule Activation
        rules = _evaluate_rules(sb, ctx_id, c)
        results["rules"] = rules

        # [9단계] Event Trigger
        events = _evaluate_events(sb, ctx_id, c)
        results["rules"].extend(events)

        # [5단계] Task Activation (활성 rule 기반만)
        active_rules = [r for r in results["rules"] if r.get("status") == "ACTIVE"]
        for ar in active_rules:
            tasks = _activate_tasks(sb, ctx_id, ar)
            results["tasks"].extend(tasks)

        # [6단계] Document Activation (활성 task 기반만)
        active_tasks = [t for t in results["tasks"] if t.get("status") == "ACTIVE"]
        for at in active_tasks:
            docs = _activate_documents(sb, ctx_id, at)
            results["documents"].extend(docs)

        # [7단계] Schedule Activation
        for ar in active_rules:
            scheds = _activate_schedules(sb, ctx_id, ar)
            results["schedules"].extend(scheds)

        # [8단계] Penalty Activation
        for ar in active_rules:
            pens = _activate_penalties(sb, ctx_id, ar)
            results["penalties"].extend(pens)

        # [10단계] Conflict Detection
        conflicts = _detect_conflicts(sb, ctx_id, results)
        results["conflicts"] = conflicts

        # [11단계] UNKNOWN/AMBIGUOUS 수집
        results["unknown"] = [r for r in results["rules"] if r.get("status") == "UNKNOWN"]
        results["ambiguous"] = [r for r in results["rules"] if r.get("status") == "AMBIGUOUS"]

        sb.table("runtime_evaluation_context").update({"evaluation_status": "COMPLETED", "updated_at": datetime.now(timezone.utc).isoformat()}).eq("id", ctx_id).execute()
        _audit(sb, ctx_id, "EVALUATION_COMPLETED", None, None, None, f"rules={len(results['rules'])} tasks={len(results['tasks'])} docs={len(results['documents'])}", "system")

    except Exception as e:
        sb.table("runtime_evaluation_context").update({"evaluation_status": "FAILED", "updated_at": datetime.now(timezone.utc).isoformat()}).eq("id", ctx_id).execute()
        _audit(sb, ctx_id, "EVALUATION_FAILED", None, None, None, str(e), "system")
        raise

    return {
        "context_id": ctx_id,
        "status": "COMPLETED",
        "summary": {
            "rules_active": len([r for r in results["rules"] if r.get("status") == "ACTIVE"]),
            "rules_not_activated": len([r for r in results["rules"] if r.get("status") == "NOT_ACTIVATED"]),
            "rules_unknown": len(results["unknown"]),
            "rules_ambiguous": len(results["ambiguous"]),
            "tasks_active": len(results["tasks"]),
            "documents_active": len(results["documents"]),
            "schedules_active": len(results["schedules"]),
            "penalties_potential": len(results["penalties"]),
            "conflicts": len(results["conflicts"]),
        },
        "activations": results,
    }


# ═══ 3. Rule Activation (EXPLICIT/THRESHOLD only) ═══

def _evaluate_rules(sb, ctx_id, ctx):
    """rule_candidate + executable_draft 조건 평가. semantic 금지."""
    activated = []
    # executable_draft의 조건 평가
    drafts = sb.table("executable_draft").select("id,rule_candidate_id,condition_json,status").eq("status", "CANDIDATE").limit(500).execute()
    for d in (drafts.data or []):
        cond = d.get("condition_json") or {}
        match_result = _match_condition(ctx, cond)
        act_type = match_result["type"]
        act_status = match_result["status"]
        reason = match_result["reason"]

        rec = {
            "evaluation_context_id": ctx_id,
            "rule_candidate_id": d.get("rule_candidate_id"),
            "activation_type": act_type if act_status == "ACTIVE" else "EXPLICIT_MATCH",
            "activation_reason": reason,
            "matched_condition": cond,
            "status": act_status,
            "source_trace": {"draft_id": str(d["id"])},
        }
        r = sb.table("runtime_rule_activation").insert(rec).execute()
        row = r.data[0] if r.data else rec
        activated.append(row)

        log_action = "RULE_ACTIVATED" if act_status == "ACTIVE" else ("RULE_UNKNOWN" if act_status == "UNKNOWN" else "RULE_NOT_ACTIVATED")
        _audit(sb, ctx_id, log_action, "rule", d.get("rule_candidate_id"), cond, reason, "system")
    return activated


def _match_condition(ctx, cond):
    """명시 조건 매칭. semantic/fallback/guess 절대 금지."""
    if not cond:
        return {"type": "EXPLICIT_MATCH", "status": "UNKNOWN", "reason": "no condition defined"}

    # worker_count threshold
    wc_min = cond.get("worker_count_min")
    wc = ctx.get("worker_count")
    if wc_min is not None:
        if wc is None:
            return {"type": "THRESHOLD_MATCH", "status": "UNKNOWN", "reason": f"worker_count not provided, threshold={wc_min}"}
        if wc < wc_min:
            return {"type": "THRESHOLD_MATCH", "status": "NOT_ACTIVATED", "reason": f"worker_count {wc} < {wc_min}"}

    # industry_code exact match
    ind_codes = cond.get("industry_codes", [])
    if ind_codes:
        ic = ctx.get("industry_code")
        if not ic:
            return {"type": "EXPLICIT_MATCH", "status": "UNKNOWN", "reason": "industry_code not provided"}
        if ic not in ind_codes:
            return {"type": "EXPLICIT_MATCH", "status": "NOT_ACTIVATED", "reason": f"industry_code {ic} not in {ind_codes}"}

    # equipment exists
    req_equip = cond.get("requires_equipment", [])
    if req_equip:
        user_equip = ctx.get("equipment") or []
        if not user_equip:
            return {"type": "EXPLICIT_MATCH", "status": "UNKNOWN", "reason": "equipment not provided"}
        if not any(e in user_equip for e in req_equip):
            return {"type": "EXPLICIT_MATCH", "status": "NOT_ACTIVATED", "reason": f"required equipment {req_equip} not found"}

    # pressure_vessel
    if cond.get("requires_pressure_vessel"):
        pv = ctx.get("pressure_vessels") or []
        if not pv:
            return {"type": "EXPLICIT_MATCH", "status": "NOT_ACTIVATED", "reason": "no pressure vessels"}

    # hazardous_material
    if cond.get("requires_hazardous_material"):
        hm = ctx.get("hazardous_materials") or []
        if not hm:
            return {"type": "EXPLICIT_MATCH", "status": "NOT_ACTIVATED", "reason": "no hazardous materials"}

    # fire_facility
    if cond.get("requires_fire_facility"):
        ff = ctx.get("fire_facilities") or []
        if not ff:
            return {"type": "EXPLICIT_MATCH", "status": "NOT_ACTIVATED", "reason": "no fire facilities"}

    # 모든 조건 통과
    return {"type": "EXPLICIT_MATCH", "status": "ACTIVE", "reason": "all conditions met"}


# ═══ 9. Event Trigger ═══

def _evaluate_events(sb, ctx_id, ctx):
    """EVENT_MATCH: 명시 입력 이벤트 기반만. inferred event 금지."""
    events = []
    event_flags = [
        ("accident_occurred", "사고 발생"),
        ("construction_started", "건설공사 개시"),
        ("shutdown", "사업장 폐쇄/중지"),
    ]
    for flag, label in event_flags:
        if ctx.get(flag) is True:
            rec = {
                "evaluation_context_id": ctx_id,
                "activation_type": "EVENT_MATCH",
                "activation_reason": f"event: {label}",
                "matched_condition": {flag: True},
                "status": "ACTIVE",
                "source_trace": {"event_flag": flag},
            }
            r = sb.table("runtime_rule_activation").insert(rec).execute()
            row = r.data[0] if r.data else rec
            events.append(row)
            _audit(sb, ctx_id, "EVENT_TRIGGERED", "event", None, {flag: True}, label, "system")
    return events


# ═══ 5. Task Activation (rule 활성 시만) ═══

def _activate_tasks(sb, ctx_id, rule_act):
    """task_candidate 활성. standalone task inference 금지."""
    rid = rule_act.get("rule_candidate_id")
    if not rid: return []
    tasks_r = sb.table("task_candidate").select("id,task_type,source_action_family,obligation_family,status").limit(50).execute()
    activated = []
    for t in (tasks_r.data or []):
        rec = {
            "evaluation_context_id": ctx_id,
            "rule_activation_id": rule_act["id"],
            "task_candidate_id": t["id"],
            "task_type": t.get("task_type"),
            "task_title": t.get("source_action_family", ""),
            "activation_reason": f"rule {rid} activated",
            "status": "ACTIVE" if t.get("status") != "NEEDS_HUMAN_REVIEW" else "UNKNOWN",
            "source_trace": {"rule_candidate_id": str(rid), "task_candidate_id": str(t["id"])},
        }
        r = sb.table("runtime_task_activation").insert(rec).execute()
        row = r.data[0] if r.data else rec
        activated.append(row)
        _audit(sb, ctx_id, "TASK_ACTIVATED", "task", t["id"], None, rec["activation_reason"], "system")
    return activated


# ═══ 6. Document Activation (binding 기반만) ═══

def _activate_documents(sb, ctx_id, task_act):
    """document_requirement_candidate binding 기반. semantic document recommendation 금지."""
    tid = task_act.get("task_candidate_id")
    if not tid: return []
    # requirement 연결 조회 (requirement_family 기반)
    reqs = sb.table("document_requirement_candidate").select("id,requirement_family,document_name,form_type").limit(20).execute()
    activated = []
    for req in (reqs.data or []):
        rec = {
            "evaluation_context_id": ctx_id,
            "task_activation_id": task_act["id"],
            "document_requirement_id": req["id"],
            "activation_reason": f"task {tid} requires document {req.get('document_name','')}",
            "status": "ACTIVE",
            "source_trace": {"task_candidate_id": str(tid), "requirement_id": str(req["id"])},
        }
        r = sb.table("runtime_document_activation").insert(rec).execute()
        row = r.data[0] if r.data else rec
        activated.append(row)
        _audit(sb, ctx_id, "DOCUMENT_ACTIVATED", "document", req["id"], None, rec["activation_reason"], "system")
    return activated


# ═══ 7. Schedule Activation (explicit rule 기반만) ═══

def _activate_schedules(sb, ctx_id, rule_act):
    """schedule_candidate 활성. inferred deadline / guessed recurrence 금지."""
    rid = rule_act.get("rule_candidate_id")
    if not rid: return []
    scheds = sb.table("schedule_candidate").select("id,schedule_type,source_family,status").limit(20).execute()
    activated = []
    TYPE_MAP = {"DAILY": "DAILY", "WEEKLY": "WEEKLY", "MONTHLY": "MONTHLY", "QUARTERLY": "QUARTERLY",
                "YEARLY": "ANNUAL", "ANNUAL": "ANNUAL", "PERIODIC": "MONTHLY", "EVENT": "EVENT_TRIGGERED"}
    for s in (scheds.data or []):
        st = s.get("schedule_type", "UNKNOWN")
        mapped = TYPE_MAP.get(st, "UNKNOWN")
        rec = {
            "evaluation_context_id": ctx_id,
            "rule_activation_id": rule_act["id"],
            "schedule_candidate_id": s["id"],
            "schedule_type": mapped,
            "activation_reason": f"rule {rid} schedule: {st}",
            "status": "ACTIVE" if mapped != "UNKNOWN" else "UNKNOWN",
            "source_trace": {"rule_candidate_id": str(rid), "schedule_candidate_id": str(s["id"])},
        }
        r = sb.table("runtime_schedule_activation").insert(rec).execute()
        row = r.data[0] if r.data else rec
        activated.append(row)
        _audit(sb, ctx_id, "SCHEDULE_ACTIVATED", "schedule", s["id"], None, rec["activation_reason"], "system")
    return activated


# ═══ 8. Penalty Activation (가능성만, 자동 처벌 금지) ═══

def _activate_penalties(sb, ctx_id, rule_act):
    """penalty_candidate 연결. auto violation / auto punishment 금지."""
    rid = rule_act.get("rule_candidate_id")
    if not rid: return []
    pens = sb.table("penalty_obligation_relation").select("id,penalty_candidate_id,obligation_family,status").limit(20).execute()
    activated = []
    for p in (pens.data or []):
        rec = {
            "evaluation_context_id": ctx_id,
            "rule_activation_id": rule_act["id"],
            "penalty_candidate_id": p.get("penalty_candidate_id"),
            "penalty_type": p.get("obligation_family"),
            "activation_reason": f"rule {rid} penalty potential",
            "status": "POTENTIAL",
            "source_trace": {"rule_candidate_id": str(rid), "penalty_relation_id": str(p["id"])},
        }
        r = sb.table("runtime_penalty_activation").insert(rec).execute()
        row = r.data[0] if r.data else rec
        activated.append(row)
        _audit(sb, ctx_id, "PENALTY_ACTIVATED", "penalty", p.get("penalty_candidate_id"), None, rec["activation_reason"], "system")
    return activated


# ═══ 10. Conflict Detection (자동 resolve 금지) ═══

def _detect_conflicts(sb, ctx_id, results):
    """conflict 검출. 자동 resolve 절대 금지. NEEDS_HUMAN_REVIEW 유지."""
    conflicts = []
    # duplicate task 검출
    task_types = {}
    for t in results.get("tasks", []):
        tt = t.get("task_type", "")
        if tt in task_types:
            rec = {
                "evaluation_context_id": ctx_id,
                "conflict_type": "DUPLICATE_TASK",
                "item_a_id": task_types[tt].get("id"),
                "item_a_type": "task",
                "item_b_id": t.get("id"),
                "item_b_type": "task",
                "detail": {"task_type": tt},
                "status": "NEEDS_HUMAN_REVIEW",
            }
            r = sb.table("runtime_conflict_queue").insert(rec).execute()
            row = r.data[0] if r.data else rec
            conflicts.append(row)
            _audit(sb, ctx_id, "CONFLICT_DETECTED", "conflict", None, None, f"duplicate task: {tt}", "system")
        else:
            task_types[tt] = t
    return conflicts


# ═══ Result Queries ═══

def get_result(ctx_id: str) -> dict:
    sb = get_supabase()
    ctx = sb.table("runtime_evaluation_context").select("*").eq("id", ctx_id).single().execute()
    if not ctx.data: return None
    rules = sb.table("runtime_rule_activation").select("*").eq("evaluation_context_id", ctx_id).execute()
    tasks = sb.table("runtime_task_activation").select("*").eq("evaluation_context_id", ctx_id).execute()
    docs = sb.table("runtime_document_activation").select("*").eq("evaluation_context_id", ctx_id).execute()
    scheds = sb.table("runtime_schedule_activation").select("*").eq("evaluation_context_id", ctx_id).execute()
    pens = sb.table("runtime_penalty_activation").select("*").eq("evaluation_context_id", ctx_id).execute()
    conflicts = sb.table("runtime_conflict_queue").select("*").eq("evaluation_context_id", ctx_id).execute()
    audit = sb.table("runtime_evaluator_audit_log").select("*").eq("evaluation_context_id", ctx_id).order("created_at", desc=True).execute()
    return {
        "context": ctx.data,
        "rules": rules.data or [],
        "tasks": tasks.data or [],
        "documents": docs.data or [],
        "schedules": scheds.data or [],
        "penalties": pens.data or [],
        "conflicts": conflicts.data or [],
        "audit_log": audit.data or [],
    }

def get_conflicts(ctx_id: str) -> list:
    sb = get_supabase()
    r = sb.table("runtime_conflict_queue").select("*").eq("evaluation_context_id", ctx_id).execute()
    return r.data or []

def get_audit(ctx_id: str) -> list:
    sb = get_supabase()
    r = sb.table("runtime_evaluator_audit_log").select("*").eq("evaluation_context_id", ctx_id).order("created_at", desc=True).execute()
    return r.data or []


# ═══ 12. Audit ═══

def _audit(sb, ctx_id, action, target_type, target_id, matched_cond, reason, actor):
    try:
        sb.table("runtime_evaluator_audit_log").insert({
            "evaluation_context_id": ctx_id,
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "matched_condition": matched_cond,
            "activation_reason": reason,
            "actor_id": actor,
        }).execute()
    except: pass
