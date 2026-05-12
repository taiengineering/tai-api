"""TAI Persistence & Drift Control Engine v1.0.0
장기 운영 deterministic consistency 유지.
금지: semantic repair, auto schedule repair, inferred reactivation, hidden normalization
"""
import hashlib,json
from datetime import datetime,timezone
from db.supabase_client import get_supabase
from services import runtime_evaluator_svc as evaluator

def create_snapshot(facility_id,eval_ctx_id=None):
    sb=get_supabase()
    if not eval_ctx_id:raise ValueError("evaluation_context_id required")
    result=evaluator.get_result(eval_ctx_id)
    if not result:raise ValueError("evaluation result not found")
    sd={"rules":[r.get("id") for r in result.get("rules",[]) if r.get("status")=="ACTIVE"],"tasks":[t.get("id") for t in result.get("tasks",[]) if t.get("status")=="ACTIVE"],"documents":[d.get("id") for d in result.get("documents",[]) if d.get("status")=="ACTIVE"],"schedules":[s.get("id") for s in result.get("schedules",[]) if s.get("status")=="ACTIVE"],"penalties":[p.get("id") for p in result.get("penalties",[]) if p.get("status")=="POTENTIAL"],"unknowns":[r.get("id") for r in result.get("rules",[]) if r.get("status")=="UNKNOWN"]}
    rh=hashlib.sha256(json.dumps(sd,sort_keys=True,default=str).encode()).hexdigest()[:16]
    vr=sb.table("runtime_activation_snapshot").select("runtime_version").eq("facility_id",facility_id).order("runtime_version",desc=True).limit(1).execute()
    ver=(vr.data[0]["runtime_version"]+1) if vr.data else 1
    rec={"facility_id":facility_id,"evaluation_context_id":eval_ctx_id,"runtime_version":ver,"activation_snapshot":sd,"result_hash":rh,"rules_active":len(sd["rules"]),"tasks_active":len(sd["tasks"]),"documents_active":len(sd["documents"]),"schedules_active":len(sd["schedules"]),"penalties_potential":len(sd["penalties"]),"conflicts_count":len(result.get("conflicts",[])),"unknowns_count":len(sd["unknowns"]),"is_immutable":True}
    r=sb.table("runtime_activation_snapshot").insert(rec).execute();snap=r.data[0] if r.data else{}
    if snap:
        sb.table("runtime_runtime_version").insert({"facility_id":facility_id,"version_number":ver,"snapshot_id":snap["id"],"trigger_reason":"evaluation"}).execute()
        _p_audit(sb,facility_id,None,"SNAPSHOT_CREATED",{"version":ver,"hash":rh})
    return snap

def compute_diff(facility_id,current_snapshot_id):
    sb=get_supabase();cur=sb.table("runtime_activation_snapshot").select("*").eq("id",current_snapshot_id).single().execute()
    if not cur.data:raise ValueError("current snapshot not found")
    pr=sb.table("runtime_activation_snapshot").select("*").eq("facility_id",facility_id).lt("runtime_version",cur.data["runtime_version"]).order("runtime_version",desc=True).limit(1).execute()
    prev=pr.data[0] if pr.data else None;cs=cur.data.get("activation_snapshot",{});ps=prev.get("activation_snapshot",{}) if prev else{}
    diff={"facility_id":facility_id,"previous_snapshot_id":prev["id"] if prev else None,"current_snapshot_id":current_snapshot_id}
    for k in["rules","tasks","documents","schedules"]:diff[f"new_{k}"]=[x for x in cs.get(k,[]) if x not in ps.get(k,[])];diff[f"removed_{k}"]=[x for x in ps.get(k,[]) if x not in cs.get(k,[])]
    diff["new_conflicts"]=[];diff["removed_conflicts"]=[];diff["has_changes"]=any(diff[f"new_{k}"] or diff[f"removed_{k}"] for k in["rules","tasks","documents","schedules"])
    r=sb.table("runtime_activation_diff").insert(diff).execute();_p_audit(sb,facility_id,None,"DIFF_COMPUTED",{"has_changes":diff["has_changes"]})
    return r.data[0] if r.data else diff

def queue_re_evaluation(facility_id,trigger_type,trigger_detail=None):
    sb=get_supabase();AM={"EQUIPMENT_ADDED":["rules","tasks","schedules","penalties"],"WORKER_COUNT_CHANGED":["rules","tasks"],"CONTRACTOR_ADDED":["rules","tasks","documents"],"ACCIDENT_OCCURRED":["rules","tasks","penalties","documents"],"FACILITY_SHUTDOWN":["rules","schedules"],"CONSTRUCTION_STARTED":["rules","tasks","schedules","documents"],"SCHEDULE_EXPIRED":["schedules"],"HAZARDOUS_MATERIAL_ADDED":["rules","tasks","schedules","penalties"],"MANUAL_REQUEST":["rules"]}
    affected=AM.get(trigger_type,["rules"]);rec={"facility_id":facility_id,"trigger_type":trigger_type,"trigger_detail":trigger_detail or{},"affected_modules":affected,"status":"PENDING"}
    r=sb.table("runtime_re_evaluation_queue").insert(rec).execute();row=r.data[0] if r.data else rec
    _p_audit(sb,facility_id,row.get("id"),"RE_EVAL_QUEUED",{"trigger":trigger_type});return row

def list_re_evaluation_queue(facility_id=None,status=None,page=1,page_size=20):
    sb=get_supabase();q=sb.table("runtime_re_evaluation_queue").select("*",count="exact")
    if facility_id:q=q.eq("facility_id",facility_id)
    if status:q=q.eq("status",status)
    o=(page-1)*page_size;q=q.order("created_at",desc=True).range(o,o+page_size-1);r=q.execute()
    return{"items":r.data or[],"total":r.count or 0}

def create_schedule_instance(facility_id,schedule_type,schedule_key,next_due_date=None,schedule_activation_id=None):
    sb=get_supabase();ex=sb.table("runtime_schedule_instance").select("id").eq("facility_id",facility_id).eq("schedule_key",schedule_key).eq("status","ACTIVE").execute()
    if ex.data:_p_audit(sb,facility_id,None,"SCHEDULE_DUPLICATE_BLOCKED",{"key":schedule_key});raise ValueError(f"duplicate schedule: {schedule_key}")
    rec={"facility_id":facility_id,"schedule_activation_id":schedule_activation_id,"schedule_type":schedule_type,"schedule_key":schedule_key,"next_due_date":next_due_date,"status":"ACTIVE"}
    r=sb.table("runtime_schedule_instance").insert(rec).execute();inst=r.data[0] if r.data else rec
    if inst.get("id"):sb.table("runtime_schedule_history").insert({"schedule_instance_id":inst["id"],"action":"CREATED","detail":{"key":schedule_key}}).execute();_p_audit(sb,facility_id,None,"SCHEDULE_CREATED",{"key":schedule_key})
    return inst

def check_drift(facility_id):
    sb=get_supabase();snaps=sb.table("runtime_activation_snapshot").select("id,result_hash,runtime_version").eq("facility_id",facility_id).order("runtime_version",desc=True).limit(2).execute()
    if not snaps.data or len(snaps.data)<2:return{"facility_id":facility_id,"drift_detected":False,"reason":"insufficient snapshots"}
    cur=snaps.data[0];prev=snaps.data[1];drift=cur["result_hash"]!=prev["result_hash"]
    sb.table("runtime_drift_detection_log").insert({"facility_id":facility_id,"previous_result_hash":prev["result_hash"],"current_result_hash":cur["result_hash"],"drift_detected":drift,"drift_detail":{"prev_v":prev["runtime_version"],"cur_v":cur["runtime_version"]}}).execute()
    _p_audit(sb,facility_id,None,"DRIFT_DETECTED" if drift else "DRIFT_CLEAR",{"prev":prev["result_hash"],"cur":cur["result_hash"]})
    return{"facility_id":facility_id,"drift_detected":drift,"prev_hash":prev["result_hash"],"cur_hash":cur["result_hash"]}

def get_facility_history(facility_id):
    sb=get_supabase()
    return{
        "snapshots":sb.table("runtime_activation_snapshot").select("id,runtime_version,result_hash,rules_active,tasks_active,created_at").eq("facility_id",facility_id).order("runtime_version").execute().data or[],
        "diffs":sb.table("runtime_activation_diff").select("*").eq("facility_id",facility_id).order("created_at").execute().data or[],
        "drift_logs":sb.table("runtime_drift_detection_log").select("*").eq("facility_id",facility_id).order("created_at").execute().data or[],
        "schedules":sb.table("runtime_schedule_instance").select("*").eq("facility_id",facility_id).execute().data or[],
        "versions":sb.table("runtime_runtime_version").select("*").eq("facility_id",facility_id).order("version_number").execute().data or[],
        "audit_log":sb.table("runtime_re_evaluation_audit_log").select("*").eq("facility_id",facility_id).order("created_at",desc=True).limit(50).execute().data or[],
    }

def _p_audit(sb,fid,reid,action,detail):
    try:sb.table("runtime_re_evaluation_audit_log").insert({"facility_id":fid,"re_evaluation_id":reid,"action":action,"detail":detail}).execute()
    except:pass
