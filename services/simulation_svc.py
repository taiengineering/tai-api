"""TAI Operational Scenario Simulation Engine v1.0.0
Deterministic Runtime Verification. AI 예측 금지.
절대 금지: semantic/fallback/guessed/probable/AI/inferred
"""
import hashlib,json,time
from datetime import datetime,timezone
from db.supabase_client import get_supabase
from services import runtime_evaluator_svc as evaluator

def create_scenario(data):
    sb=get_supabase()
    rec={"scenario_name":data["scenario_name"],"industry_code":data.get("industry_code"),"worker_count":data.get("worker_count"),"hazardous_materials":data.get("hazardous_materials",[]),"pressure_vessels":data.get("pressure_vessels",[]),"fire_facilities":data.get("fire_facilities",[]),"contractor_exists":data.get("contractor_exists",False),"construction_started":data.get("construction_started",False),"accident_occurred":data.get("accident_occurred",False),"shutdown":data.get("shutdown",False),"facility_types":data.get("facility_types",[]),"equipment":data.get("equipment",[]),"additional_inputs":data.get("additional_inputs",{}),"status":"PENDING","created_by":data.get("created_by")}
    r=sb.table("runtime_simulation_scenario").insert(rec).execute();sc=r.data[0] if r.data else{}
    if sc:_sim_audit(sb,sc["id"],"SCENARIO_CREATED",{"name":data["scenario_name"]})
    return sc

def run_simulation(scenario_id):
    sb=get_supabase();sc=sb.table("runtime_simulation_scenario").select("*").eq("id",scenario_id).single().execute()
    if not sc.data:raise ValueError("scenario not found")
    s=sc.data
    if s["status"] not in("PENDING","COMPLETED"):raise ValueError(f"invalid status: {s['status']}")
    sb.table("runtime_simulation_scenario").update({"status":"RUNNING"}).eq("id",scenario_id).execute()
    _sim_audit(sb,scenario_id,"SIMULATION_STARTED",{});t0=time.time()
    try:
        ctx_data={"industry_code":s.get("industry_code"),"worker_count":s.get("worker_count"),"hazardous_materials":s.get("hazardous_materials",[]),"equipment":s.get("equipment",[]),"pressure_vessels":s.get("pressure_vessels",[]),"fire_facilities":s.get("fire_facilities",[]),"contractors":["contractor"] if s.get("contractor_exists") else [],"process_types":s.get("facility_types",[]),"accident_occurred":s.get("accident_occurred",False),"construction_started":s.get("construction_started",False),"shutdown":s.get("shutdown",False),"additional_inputs":s.get("additional_inputs",{}),"created_by":"simulation"}
        ctx=evaluator.create_context(ctx_data);ctx_id=ctx["id"]
        _sim_audit(sb,scenario_id,"CONTEXT_CREATED",{"context_id":ctx_id})
        result=evaluator.evaluate(ctx_id)
        _sim_audit(sb,scenario_id,"EVALUATION_EXECUTED",{"context_id":ctx_id})
        act=result.get("activations",{})
        for ri in act.get("rules",[]):sb.table("runtime_simulation_activation_snapshot").insert({"scenario_id":scenario_id,"activation_type":"RULE","target_id":ri.get("rule_candidate_id"),"activation_status":ri.get("status","UNKNOWN"),"activation_reason":ri.get("activation_reason",""),"matched_condition":ri.get("matched_condition",{}),"source_trace":ri.get("source_trace",{})}).execute()
        for ti in act.get("tasks",[]):sb.table("runtime_simulation_activation_snapshot").insert({"scenario_id":scenario_id,"activation_type":"TASK","target_id":ti.get("task_candidate_id"),"activation_status":ti.get("status","UNKNOWN"),"activation_reason":ti.get("activation_reason","")}).execute()
        for di in act.get("documents",[]):sb.table("runtime_simulation_activation_snapshot").insert({"scenario_id":scenario_id,"activation_type":"DOCUMENT","target_id":di.get("document_requirement_id"),"activation_status":di.get("status","UNKNOWN"),"activation_reason":di.get("activation_reason","")}).execute()
        for si in act.get("schedules",[]):sb.table("runtime_simulation_activation_snapshot").insert({"scenario_id":scenario_id,"activation_type":"SCHEDULE","target_id":si.get("schedule_candidate_id"),"activation_status":si.get("status","UNKNOWN"),"activation_reason":si.get("activation_reason","")}).execute()
        for pi in act.get("penalties",[]):sb.table("runtime_simulation_activation_snapshot").insert({"scenario_id":scenario_id,"activation_type":"PENALTY","target_id":pi.get("penalty_candidate_id"),"activation_status":pi.get("status","UNKNOWN"),"activation_reason":pi.get("activation_reason","")}).execute()
        _sim_audit(sb,scenario_id,"SNAPSHOT_SAVED",{})
        for ci in act.get("conflicts",[]):
            sb.table("runtime_simulation_conflict_snapshot").insert({"scenario_id":scenario_id,"conflict_type":ci.get("conflict_type","UNKNOWN"),"item_a":{"id":str(ci.get("item_a_id","")),"type":ci.get("item_a_type","")},"item_b":{"id":str(ci.get("item_b_id","")),"type":ci.get("item_b_type","")},"detail":ci.get("detail",{}),"status":"NEEDS_HUMAN_REVIEW"}).execute()
            _sim_audit(sb,scenario_id,"CONFLICT_DETECTED",ci.get("detail",{}))
        summary=result.get("summary",{});hash_input=json.dumps(summary,sort_keys=True);det_hash=hashlib.sha256(hash_input.encode()).hexdigest()[:16]
        elapsed=int((time.time()-t0)*1000)
        sb.table("runtime_simulation_result").insert({"scenario_id":scenario_id,"evaluation_context_id":ctx_id,"activated_rules_count":summary.get("rules_active",0),"activated_tasks_count":summary.get("tasks_active",0),"activated_documents_count":summary.get("documents_active",0),"activated_schedules_count":summary.get("schedules_active",0),"activated_penalties_count":summary.get("penalties_potential",0),"conflicts_count":summary.get("conflicts",0),"unknowns_count":summary.get("rules_unknown",0),"ambiguities_count":summary.get("rules_ambiguous",0),"result_snapshot":summary,"deterministic_hash":det_hash,"execution_ms":elapsed}).execute()
        sb.table("runtime_simulation_scenario").update({"status":"COMPLETED","evaluation_context_id":ctx_id}).eq("id",scenario_id).execute()
        _sim_audit(sb,scenario_id,"SIMULATION_COMPLETED",{"hash":det_hash,"ms":elapsed})
        return{"scenario_id":scenario_id,"context_id":ctx_id,"status":"COMPLETED","deterministic_hash":det_hash,"execution_ms":elapsed,"summary":summary}
    except Exception as e:
        sb.table("runtime_simulation_scenario").update({"status":"FAILED"}).eq("id",scenario_id).execute()
        _sim_audit(sb,scenario_id,"SIMULATION_FAILED",{"error":str(e)});raise

def verify_deterministic(scenario_id):
    r1=run_simulation(scenario_id);sb=get_supabase()
    sb.table("runtime_simulation_scenario").update({"status":"PENDING"}).eq("id",scenario_id).execute()
    r2=run_simulation(scenario_id)
    match=r1["deterministic_hash"]==r2["deterministic_hash"]
    action="DETERMINISTIC_CHECK_PASS" if match else "DETERMINISTIC_CHECK_FAIL"
    _sim_audit(sb,scenario_id,action,{"hash_1":r1["deterministic_hash"],"hash_2":r2["deterministic_hash"]})
    return{"scenario_id":scenario_id,"deterministic":match,"hash_run_1":r1["deterministic_hash"],"hash_run_2":r2["deterministic_hash"],"run_1_ms":r1["execution_ms"],"run_2_ms":r2["execution_ms"]}

def get_scenario(scenario_id):
    sb=get_supabase();r=sb.table("runtime_simulation_scenario").select("*").eq("id",scenario_id).single().execute();return r.data

def list_scenarios(page=1,page_size=20):
    sb=get_supabase();q=sb.table("runtime_simulation_scenario").select("*",count="exact")
    o=(page-1)*page_size;q=q.order("created_at",desc=True).range(o,o+page_size-1);r=q.execute()
    return{"items":r.data or[],"total":r.count or 0,"page":page,"page_size":page_size}

def get_result(scenario_id):
    sb=get_supabase()
    res=sb.table("runtime_simulation_result").select("*").eq("scenario_id",scenario_id).order("created_at",desc=True).execute()
    snaps=sb.table("runtime_simulation_activation_snapshot").select("*").eq("scenario_id",scenario_id).execute()
    conflicts=sb.table("runtime_simulation_conflict_snapshot").select("*").eq("scenario_id",scenario_id).execute()
    audit=sb.table("runtime_simulation_audit_log").select("*").eq("scenario_id",scenario_id).order("created_at").execute()
    return{"results":res.data or[],"activation_snapshots":snaps.data or[],"conflict_snapshots":conflicts.data or[],"audit_log":audit.data or[]}

def _sim_audit(sb,scenario_id,action,detail):
    try:sb.table("runtime_simulation_audit_log").insert({"scenario_id":scenario_id,"action":action,"detail":detail}).execute()
    except:pass
