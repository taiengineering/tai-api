"""TAI Operational Scenario Simulation Engine v1.0.0
Deterministic Runtime Verification. AI 예측 금지.
절대 금지: semantic/fallback/guessed/probable/AI/inferred
"""
import hashlib, json, time
from datetime import datetime, timezone
from db.supabase_client import get_supabase
from services import runtime_evaluator_svc as evaluator


def create_scenario(data: dict) -> dict:
    sb = get_supabase()
    rec = {
        "scenario_name": data["scenario_name"],
        "industry_code": data.get("industry_code"),
        "worker_count": data.get("worker_count"),
        "hazardous_materials": data.get("hazardous_materials", []),
        "pressure_vessels": data.get("pressure_vessels", []),
        "fire_facilities": data.get("fire_facilities", []),
        "contractor_exists": data.get("contractor_exists", False),
        "construction_started": data.get("construction_started", False),
        "accident_occurred": data.get("accident_occurred", False),
        "shutdown": data.get("shutdown", False),
        "facility_types": data.get("facility_types", []),
        "equipment": data.get("equipment", []),
        "additional_inputs": data.get("additional_inputs", {}),
        "status": "PENDING",
        "created_by": data.get("created_by"),
    }
    r = sb.table("runtime_simulation_scenario").insert(rec).execute()
    sc = r.data[0] if r.data else {}
    if sc:
        _sim_audit(sb, sc["id"], "SCENARIO_CREATED", {"name": data["scenario_name"]})
    return sc


def run_simulation(scenario_id: str) -> dict:
    """Deterministic simulation. semantic/fallback/guess 절대 금지."""
    sb = get_supabase()
    sc = sb.table("runtime_simulation_scenario").select("*").eq("id", scenario_id).single().execute()
    if not sc.data: raise ValueError("scenario not found")
    s = sc.data
    if s["status"] not in ("PENDING", "COMPLETED"): raise ValueError(f"invalid status: {s['status']}")

    sb.table("runtime_simulation_scenario").update({"status": "RUNNING"}).eq("id", scenario_id).execute()
    _sim_audit(sb, scenario_id, "SIMULATION_STARTED", {})
    t0 = time.time()

    try:
        # 1. evaluation context 생성
        ctx_data = {
            "industry_code": s.get("industry_code"),
            "worker_count": s.get("worker_count"),
            "hazardous_materials": s.get("hazardous_materials", []),
            "equipment": s.get("equipment", []),
            "pressure_vessels": s.get("pressure_vessels", []),
            "fire_facilities": s.get("fire_facilities", []),
            "contractors": ["contractor"] if s.get("contractor_exists") else [],
            "process_types": s.get("facility_types", []),
            "accident_occurred": s.get("accident_occurred", False),
            "construction_started": s.get("construction_started", False),
            "shutdown": s.get("shutdown", False),
            "additional_inputs": s.get("additional_inputs", {}),
            "created_by": "simulation",
        }
        ctx = evaluator.create_context(ctx_data)
        ctx_id = ctx["id"]
        _sim_audit(sb, scenario_id, "CONTEXT_CREATED", {"context_id": ctx_id})

        # 2. evaluate
        result = evaluator.evaluate(ctx_id)
        _sim_audit(sb, scenario_id, "EVALUATION_EXECUTED", {"context_id": ctx_id})

        # 3. activation snapshot 저장
        activations = result.get("activations", {})
        for r_item in activations.get("rules", []):
            sb.table("runtime_simulation_activation_snapshot").insert({
                "scenario_id": scenario_id,
                "activation_type": "RULE",
                "target_id": r_item.get("rule_candidate_id"),
                "activation_status": r_item.get("status", "UNKNOWN"),
                "activation_reason": r_item.get("activation_reason", ""),
                "matched_condition": r_item.get("matched_condition", {}),
                "source_trace": r_item.get("source_trace", {}),
            }).execute()
        for t_item in activations.get("tasks", []):
            sb.table("runtime_simulation_activation_snapshot").insert({
                "scenario_id": scenario_id,
                "activation_type": "TASK",
                "target_id": t_item.get("task_candidate_id"),
                "activation_status": t_item.get("status", "UNKNOWN"),
                "activation_reason": t_item.get("activation_reason", ""),
            }).execute()
        for d_item in activations.get("documents", []):
            sb.table("runtime_simulation_activation_snapshot").insert({
                "scenario_id": scenario_id,
                "activation_type": "DOCUMENT",
                "target_id": d_item.get("document_requirement_id"),
                "activation_status": d_item.get("status", "UNKNOWN"),
                "activation_reason": d_item.get("activation_reason", ""),
            }).execute()
        for s_item in activations.get("schedules", []):
            sb.table("runtime_simulation_activation_snapshot").insert({
                "scenario_id": scenario_id,
                "activation_type": "SCHEDULE",
                "target_id": s_item.get("schedule_candidate_id"),
                "activation_status": s_item.get("status", "UNKNOWN"),
                "activation_reason": s_item.get("activation_reason", ""),
            }).execute()
        for p_item in activations.get("penalties", []):
            sb.table("runtime_simulation_activation_snapshot").insert({
                "scenario_id": scenario_id,
                "activation_type": "PENALTY",
                "target_id": p_item.get("penalty_candidate_id"),
                "activation_status": p_item.get("status", "UNKNOWN"),
                "activation_reason": p_item.get("activation_reason", ""),
            }).execute()
        _sim_audit(sb, scenario_id, "SNAPSHOT_SAVED", {})

        # 4. conflict snapshot
        for c_item in activations.get("conflicts", []):
            sb.table("runtime_simulation_conflict_snapshot").insert({
                "scenario_id": scenario_id,
                "conflict_type": c_item.get("conflict_type", "UNKNOWN"),
                "item_a": {"id": str(c_item.get("item_a_id", "")), "type": c_item.get("item_a_type", "")},
                "item_b": {"id": str(c_item.get("item_b_id", "")), "type": c_item.get("item_b_type", "")},
                "detail": c_item.get("detail", {}),
                "status": "NEEDS_HUMAN_REVIEW",
            }).execute()
            _sim_audit(sb, scenario_id, "CONFLICT_DETECTED", c_item.get("detail", {}))

        # 5. deterministic hash
        summary = result.get("summary", {})
        hash_input = json.dumps(summary, sort_keys=True)
        det_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:16]

        elapsed = int((time.time() - t0) * 1000)

        # 6. result 저장
        res_rec = {
            "scenario_id": scenario_id,
            "evaluation_context_id": ctx_id,
            "activated_rules_count": summary.get("rules_active", 0),
            "activated_tasks_count": summary.get("tasks_active", 0),
            "activated_documents_count": summary.get("documents_active", 0),
            "activated_schedules_count": summary.get("schedules_active", 0),
            "activated_penalties_count": summary.get("penalties_potential", 0),
            "conflicts_count": summary.get("conflicts", 0),
            "unknowns_count": summary.get("rules_unknown", 0),
            "ambiguities_count": summary.get("rules_ambiguous", 0),
            "result_snapshot": summary,
            "deterministic_hash": det_hash,
            "execution_ms": elapsed,
        }
        sb.table("runtime_simulation_result").insert(res_rec).execute()

        sb.table("runtime_simulation_scenario").update({
            "status": "COMPLETED", "evaluation_context_id": ctx_id
        }).eq("id", scenario_id).execute()
        _sim_audit(sb, scenario_id, "SIMULATION_COMPLETED", {"hash": det_hash, "ms": elapsed})

        return {
            "scenario_id": scenario_id,
            "context_id": ctx_id,
            "status": "COMPLETED",
            "deterministic_hash": det_hash,
            "execution_ms": elapsed,
            "summary": summary,
        }

    except Exception as e:
        sb.table("runtime_simulation_scenario").update({"status": "FAILED"}).eq("id", scenario_id).execute()
        _sim_audit(sb, scenario_id, "SIMULATION_FAILED", {"error": str(e)})
        raise


def verify_deterministic(scenario_id: str) -> dict:
    """동일 시나리오 2회 실행 → 동일 hash 확인."""
    r1 = run_simulation(scenario_id)
    # scenario 상태 초기화 (재실행 가능하도록)
    sb = get_supabase()
    sb.table("runtime_simulation_scenario").update({"status": "PENDING"}).eq("id", scenario_id).execute()
    r2 = run_simulation(scenario_id)

    match = r1["deterministic_hash"] == r2["deterministic_hash"]
    action = "DETERMINISTIC_CHECK_PASS" if match else "DETERMINISTIC_CHECK_FAIL"
    _sim_audit(sb, scenario_id, action, {"hash_1": r1["deterministic_hash"], "hash_2": r2["deterministic_hash"]})

    return {
        "scenario_id": scenario_id,
        "deterministic": match,
        "hash_run_1": r1["deterministic_hash"],
        "hash_run_2": r2["deterministic_hash"],
        "run_1_ms": r1["execution_ms"],
        "run_2_ms": r2["execution_ms"],
    }


def get_scenario(scenario_id: str) -> dict:
    sb = get_supabase()
    sc = sb.table("runtime_simulation_scenario").select("*").eq("id", scenario_id).single().execute()
    return sc.data

def list_scenarios(page=1, page_size=20) -> dict:
    sb = get_supabase()
    q = sb.table("runtime_simulation_scenario").select("*", count="exact")
    o = (page-1)*page_size
    q = q.order("created_at", desc=True).range(o, o+page_size-1)
    r = q.execute()
    return {"items": r.data or [], "total": r.count or 0, "page": page, "page_size": page_size}

def get_result(scenario_id: str) -> dict:
    sb = get_supabase()
    res = sb.table("runtime_simulation_result").select("*").eq("scenario_id", scenario_id).order("created_at", desc=True).execute()
    snaps = sb.table("runtime_simulation_activation_snapshot").select("*").eq("scenario_id", scenario_id).execute()
    conflicts = sb.table("runtime_simulation_conflict_snapshot").select("*").eq("scenario_id", scenario_id).execute()
    audit = sb.table("runtime_simulation_audit_log").select("*").eq("scenario_id", scenario_id).order("created_at").execute()
    return {
        "results": res.data or [],
        "activation_snapshots": snaps.data or [],
        "conflict_snapshots": conflicts.data or [],
        "audit_log": audit.data or [],
    }

def _sim_audit(sb, scenario_id, action, detail):
    try:
        sb.table("runtime_simulation_audit_log").insert({
            "scenario_id": scenario_id, "action": action, "detail": detail,
        }).execute()
    except: pass
