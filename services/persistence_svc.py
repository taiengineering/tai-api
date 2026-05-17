"""TAI Persistence & Drift Control Engine v1.0.0
장기 운영 deterministic consistency 유지.
금지: semantic repair, auto schedule repair, inferred reactivation,
      hidden normalization, auto conflict resolve
"""
import hashlib,json
from datetime import datetime,timezone
from db.supabase_client import get_supabase
from services import runtime_evaluator_svc as evaluator


# ═══ 2. Snapshot Versioning (immutable) ═══

def create_snapshot(facility_id, eval_ctx_id=None):
    """evaluation 결과를 immutable snapshot으로 저장. overwrite 금지."""
    sb = get_supabase()
    if not eval_ctx_id: raise ValueError("evaluation_context_id required")
    result = evaluator.get_result(eval_ctx_id)
    if not result: raise ValueError("evaluation result not found")
    summary = {
        "rules": len(result.get("rules", [])),
        "tasks": len(result.get("tasks", [])),
        "documents": len(result.get("documents", [])),
        "schedules": len(result.get("schedules", [])),
        "penalties": len(result.get("penalties", [])),
        "conflicts": len(result.get("conflicts", [])),
    }
    snapshot_data = {
        "rules": [r.get("id") for r in result.get("rules", []) if r.get("status") == "ACTIVE"],
        "tasks": [t.get("id") for t in result.get("tasks", []) if t.get("status") == "ACTIVE"],
        "documents": [d.get("id") for d in result.get("documents", []) if d.get("status") == "ACTIVE"],
        "schedules": [s.get("id") for s in result.get("schedules", []) if s.get("status") == "ACTIVE"],
        "penalties": [p.get("id") for p in result.get("penalties", []) if p.get("status") == "POTENTIAL"],
        "unknowns": [r.get("id") for r in result.get("rules", []) if r.get("status") == "UNKNOWN"],
    }
    rh = hashlib.sha256(json.dumps(snapshot_data, sort_keys=True, default=str).encode()).hexdigest()[:16]
    # version
    ver_r = sb.table("runtime_activation_snapshot").select("runtime_version").eq("facility_id", facility_id).order("runtime_version", desc=True).limit(1).execute()
    ver = (ver_r.data[0]["runtime_version"] + 1) if ver_r.data else 1
    rec = {
        "facility_id": facility_id, "evaluation_context_id": eval_ctx_id,
        "runtime_version": ver, "activation_snapshot": snapshot_data, "result_hash": rh,
        "rules_active": len(snapshot_data["rules"]), "tasks_active": len(snapshot_data["tasks"]),
        "documents_active": len(snapshot_data["documents"]), "schedules_active": len(snapshot_data["schedules"]),
        "penalties_potential": len(snapshot_data["penalties"]), "conflicts_count": summary["conflicts"],
        "unknowns_count": len(snapshot_data["unknowns"]), "is_immutable": True,
    }
    r = sb.table("runtime_activation_snapshot").insert(rec).execute()
    snap = r.data[0] if r.data else {}
    # version record
    if snap:
        sb.table("runtime_runtime_version").insert({"facility_id": facility_id, "version_number": ver, "snapshot_id": snap["id"], "trigger_reason": "evaluation"}).execute()
        _p_audit(sb, facility_id, None, "SNAPSHOT_CREATED", {"version": ver, "hash": rh})
        _p_audit(sb, facility_id, None, "VERSION_INCREMENTED", {"version": ver})
    return snap


# ═══ 3. Diff Engine (실제 변화만 기록) ═══

def compute_diff(facility_id, current_snapshot_id):
    """snapshot 간 diff. semantic diff / guessed change 금지."""
    sb = get_supabase()
    cur = sb.table("runtime_activation_snapshot").select("*").eq("id", current_snapshot_id).single().execute()
    if not cur.data: raise ValueError("current snapshot not found")
    # 직전 snapshot
    prev_r = sb.table("runtime_activation_snapshot").select("*").eq("facility_id", facility_id).lt("runtime_version", cur.data["runtime_version"]).order("runtime_version", desc=True).limit(1).execute()
    prev = prev_r.data[0] if prev_r.data else None
    cur_snap = cur.data.get("activation_snapshot", {})
    prev_snap = prev.get("activation_snapshot", {}) if prev else {}
    diff = {
        "facility_id": facility_id,
        "previous_snapshot_id": prev["id"] if prev else None,
        "current_snapshot_id": current_snapshot_id,
        "new_rules": [x for x in cur_snap.get("rules", []) if x not in prev_snap.get("rules", [])],
        "removed_rules": [x for x in prev_snap.get("rules", []) if x not in cur_snap.get("rules", [])],
        "new_tasks": [x for x in cur_snap.get("tasks", []) if x not in prev_snap.get("tasks", [])],
        "removed_tasks": [x for x in prev_snap.get("tasks", []) if x not in cur_snap.get("tasks", [])],
        "new_documents": [x for x in cur_snap.get("documents", []) if x not in prev_snap.get("documents", [])],
        "removed_documents": [x for x in prev_snap.get("documents", []) if x not in cur_snap.get("documents", [])],
        "new_schedules": [x for x in cur_snap.get("schedules", []) if x not in prev_snap.get("schedules", [])],
        "removed_schedules": [x for x in prev_snap.get("schedules", []) if x not in cur_snap.get("schedules", [])],
    }
    diff["has_changes"] = any(diff[k] for k in ["new_rules","removed_rules","new_tasks","removed_tasks","new_documents","removed_documents","new_schedules","removed_schedules"])
    r = sb.table("runtime_activation_diff").insert(diff).execute()
    row = r.data[0] if r.data else diff
    _p_audit(sb, facility_id, None, "DIFF_COMPUTED", {"has_changes": diff["has_changes"]})
    return row


# ═══ 4. Incremental Re-Evaluation (부분 재평가, full rebuild 금지) ═══

def queue_re_evaluation(facility_id, trigger_type, trigger_detail=None):
    sb = get_supabase()
    affected = []
    if trigger_type in ("EQUIPMENT_ADDED","HAZARDOUS_MATERIAL_ADDED"): affected = ["rules","tasks","schedules","penalties"]
    elif trigger_type in ("WORKER_COUNT_CHANGED",): affected = ["rules","tasks"]
    elif trigger_type in ("CONTRACTOR_ADDED",): affected = ["rules","tasks","documents"]
    elif trigger_type in ("ACCIDENT_OCCURRED",): affected = ["rules","tasks","penalties","documents"]
    elif trigger_type in ("FACILITY_SHUTDOWN",): affected = ["rules","schedules"]
    elif trigger_type in ("CONSTRUCTION_STARTED",): affected = ["rules","tasks","schedules","documents"]
    elif trigger_type in ("SCHEDULE_EXPIRED",): affected = ["schedules"]
    else: affected = ["rules"]
    rec = {
        "facility_id": facility_id, "trigger_type": trigger_type,
        "trigger_detail": trigger_detail or {}, "affected_modules": affected, "status": "PENDING",
    }
    r = sb.table("runtime_re_evaluation_queue").insert(rec).execute()
    row = r.data[0] if r.data else rec
    _p_audit(sb, facility_id, row.get("id"), "RE_EVAL_QUEUED", {"trigger": trigger_type, "modules": affected})
    return row


def list_re_evaluation_queue(facility_id=None, status=None, page=1, page_size=20):
    sb = get_supabase()
    q = sb.table("runtime_re_evaluation_queue").select("*", count="exact")
    if facility_id: q = q.eq("facility_id", facility_id)
    if status: q = q.eq("status", status)
    o = (page-1)*page_size
    q = q.order("created_at", desc=True).range(o, o+page_size-1)
    r = q.execute()
    return {"items": r.data or [], "total": r.count or 0}


# ═══ 5. Schedule Persistence (중복 생성 금지) ═══

def create_schedule_instance(facility_id, schedule_type, schedule_key, next_due_date=None, schedule_activation_id=None):
    """schedule instance 생성. 동일 facility+key 중복 차단."""
    sb = get_supabase()
    existing = sb.table("runtime_schedule_instance").select("id").eq("facility_id", facility_id).eq("schedule_key", schedule_key).eq("status", "ACTIVE").execute()
    if existing.data:
        _p_audit(sb, facility_id, None, "SCHEDULE_DUPLICATE_BLOCKED", {"key": schedule_key})
        raise ValueError(f"duplicate schedule: {schedule_key} already ACTIVE for facility")
    rec = {
        "facility_id": facility_id, "schedule_activation_id": schedule_activation_id,
        "schedule_type": schedule_type, "schedule_key": schedule_key,
        "next_due_date": next_due_date, "status": "ACTIVE",
    }
    r = sb.table("runtime_schedule_instance").insert(rec).execute()
    inst = r.data[0] if r.data else rec
    if inst.get("id"):
        sb.table("runtime_schedule_history").insert({"schedule_instance_id": inst["id"], "action": "CREATED", "detail": {"key": schedule_key}}).execute()
        _p_audit(sb, facility_id, None, "SCHEDULE_CREATED", {"key": schedule_key, "type": schedule_type})
    return inst


# ═══ 6. Drift Detector ═══

def check_drift(facility_id):
    """동일 입력 반복 평가 시 drift 검출. 동일이면 동일 결과."""
    sb = get_supabase()
    snaps = sb.table("runtime_activation_snapshot").select("id,result_hash,runtime_version").eq("facility_id", facility_id).order("runtime_version", desc=True).limit(2).execute()
    if not snaps.data or len(snaps.data) < 2:
        return {"facility_id": facility_id, "drift_detected": False, "reason": "insufficient snapshots"}
    cur = snaps.data[0]
    prev = snaps.data[1]
    drift = cur["result_hash"] != prev["result_hash"]
    rec = {
        "facility_id": facility_id,
        "previous_result_hash": prev["result_hash"],
        "current_result_hash": cur["result_hash"],
        "drift_detected": drift,
        "drift_detail": {"prev_version": prev["runtime_version"], "cur_version": cur["runtime_version"]},
    }
    sb.table("runtime_drift_detection_log").insert(rec).execute()
    action = "DRIFT_DETECTED" if drift else "DRIFT_CLEAR"
    _p_audit(sb, facility_id, None, action, {"prev_hash": prev["result_hash"], "cur_hash": cur["result_hash"]})
    return {"facility_id": facility_id, "drift_detected": drift, "prev_hash": prev["result_hash"], "cur_hash": cur["result_hash"]}


# ═══ 7. Long-Term Audit ═══

def get_facility_history(facility_id):
    sb = get_supabase()
    snaps = sb.table("runtime_activation_snapshot").select("id,runtime_version,result_hash,rules_active,tasks_active,created_at").eq("facility_id", facility_id).order("runtime_version").execute()
    diffs = sb.table("runtime_activation_diff").select("*").eq("facility_id", facility_id).order("created_at").execute()
    drift_logs = sb.table("runtime_drift_detection_log").select("*").eq("facility_id", facility_id).order("created_at").execute()
    schedules = sb.table("runtime_schedule_instance").select("*").eq("facility_id", facility_id).execute()
    versions = sb.table("runtime_runtime_version").select("*").eq("facility_id", facility_id).order("version_number").execute()
    audit = sb.table("runtime_re_evaluation_audit_log").select("*").eq("facility_id", facility_id).order("created_at", desc=True).limit(50).execute()
    return {
        "snapshots": snaps.data or [], "diffs": diffs.data or [],
        "drift_logs": drift_logs.data or [], "schedules": schedules.data or [],
        "versions": versions.data or [], "audit_log": audit.data or [],
    }


def _p_audit(sb, facility_id, re_eval_id, action, detail):
    try: sb.table("runtime_re_evaluation_audit_log").insert({"facility_id": facility_id, "re_evaluation_id": re_eval_id, "action": action, "detail": detail}).execute()
    except: pass
