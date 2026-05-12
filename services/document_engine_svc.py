"""TAI 문서엔진 서비스 v1.1.0

Router = HTTP만, Service = 비즈니스 로직 (FastAPI import 금지)
절대 금지: auto fill, auto approve, inferred default,
           semantic match, fallback mapping, candidate→truth 승격

v1.1.0: Audit 수정 — field_key 검증, evidence 검증, generate audit 추가
"""
from datetime import datetime, timezone
from db.supabase_client import get_supabase

def list_form_schemas(document_family=None,form_type=None,status=None,page=1,page_size=20):
    sb=get_supabase();q=sb.table("runtime_form_schema").select("*",count="exact")
    if document_family:q=q.eq("document_family",document_family)
    if form_type:q=q.eq("form_type",form_type)
    if status:q=q.eq("status",status)
    o=(page-1)*page_size;q=q.order("document_family").order("form_name").range(o,o+page_size-1)
    r=q.execute();return{"items":r.data or[],"total":r.count or 0,"page":page,"page_size":page_size}

def get_form_schema_detail(schema_id):
    sb=get_supabase()
    s=sb.table("runtime_form_schema").select("*").eq("id",schema_id).single().execute()
    if not s.data:return None
    f=sb.table("runtime_field").select("*").eq("form_schema_id",schema_id).order("field_order").execute()
    c=sb.table("runtime_checklist_item").select("*").eq("form_schema_id",schema_id).order("item_order").execute()
    e=sb.table("runtime_evidence_field").select("*").eq("form_schema_id",schema_id).execute()
    return{"schema":s.data,"fields":f.data or[],"checklists":c.data or[],"evidence_fields":e.data or[]}

def create_document(form_schema_id,factory_id=None,company_id=None,created_by=None):
    sb=get_supabase()
    s=sb.table("runtime_form_schema").select("id,status").eq("id",form_schema_id).single().execute()
    if not s.data:raise ValueError(f"schema not found: {form_schema_id}")
    now=datetime.now(timezone.utc).isoformat()
    rec={"form_schema_id":form_schema_id,"runtime_data_json":{},"evidence_links":[],"status":"DRAFT","version":1,"created_at":now,"updated_at":now}
    if factory_id:rec["factory_id"]=factory_id
    if company_id:rec["company_id"]=company_id
    if created_by:rec["created_by"]=created_by
    r=sb.table("runtime_document_data").insert(rec).execute()
    d=r.data[0] if r.data else{}
    if d:_audit(sb,d["id"],"CREATED",created_by,None,d)
    return d

def get_document(doc_id):
    sb=get_supabase();r=sb.table("runtime_document_data").select("*").eq("id",doc_id).single().execute();return r.data

def list_documents(factory_id=None,company_id=None,status=None,page=1,page_size=20):
    sb=get_supabase()
    q=sb.table("runtime_document_data").select("id,form_schema_id,factory_id,company_id,status,version,created_at,updated_at",count="exact")
    if factory_id:q=q.eq("factory_id",factory_id)
    if company_id:q=q.eq("company_id",company_id)
    if status:q=q.eq("status",status)
    o=(page-1)*page_size;q=q.order("updated_at",desc=True).range(o,o+page_size-1)
    r=q.execute();return{"items":r.data or[],"total":r.count or 0,"page":page,"page_size":page_size}

def update_document(doc_id,runtime_data_json=None,evidence_links=None,updated_by=None):
    sb=get_supabase()
    b=sb.table("runtime_document_data").select("*").eq("id",doc_id).single().execute()
    if not b.data:raise ValueError("document not found")
    if b.data["status"]=="ARCHIVED":raise ValueError("ARCHIVED document cannot be modified")
    sid=b.data["form_schema_id"];now=datetime.now(timezone.utc).isoformat();u={"updated_at":now};ch={}
    if runtime_data_json is not None:
        _validate_field_keys(sb,sid,runtime_data_json);u["runtime_data_json"]=runtime_data_json;ch["runtime_data_json"]=True
    if evidence_links is not None:
        _validate_evidence_links(sb,sid,evidence_links);u["evidence_links"]=evidence_links;ch["evidence_links"]=True
    if updated_by:u["updated_by"]=updated_by
    r=sb.table("runtime_document_data").update(u).eq("id",doc_id).execute()
    d=r.data[0] if r.data else{}
    if d:_audit(sb,doc_id,"FIELD_EDIT",updated_by,b.data,d,ch)
    return d

def get_transitions():
    sb=get_supabase();r=sb.table("runtime_state_transition_rule").select("*").order("from_status").execute();return r.data or[]

def change_status(doc_id,to_status,actor_id=None,comment=None):
    sb=get_supabase()
    d=sb.table("runtime_document_data").select("*").eq("id",doc_id).single().execute()
    if not d.data:raise ValueError("document not found")
    fs=d.data["status"]
    rl=sb.table("runtime_state_transition_rule").select("*").eq("from_status",fs).eq("to_status",to_status).execute()
    if not rl.data:raise ValueError(f"transition not allowed: {fs} -> {to_status}")
    rr=rl.data[0]
    if rr["requires_reviewer"] and not actor_id:raise ValueError("reviewer_id required")
    if rr["requires_comment"] and not comment:raise ValueError("review_comment required")
    now=datetime.now(timezone.utc).isoformat();u={"status":to_status,"updated_at":now}
    if to_status=="SUBMITTED_FOR_REVIEW":u["submitted_at"]=now;u["submitted_by"]=actor_id if actor_id else None
    if to_status in("APPROVED_BY_HUMAN","REJECTED_BY_HUMAN","RETURNED_FOR_EDIT"):u["reviewed_at"]=now;u["reviewed_by"]=actor_id
    if comment:u["review_comment"]=comment
    if to_status=="ARCHIVED":u["archived_at"]=now
    r=sb.table("runtime_document_data").update(u).eq("id",doc_id).execute()
    af=r.data[0] if r.data else{}
    _audit(sb,doc_id,"STATUS_CHANGE",actor_id,d.data,af)
    if to_status in("APPROVED_BY_HUMAN","REJECTED_BY_HUMAN") and actor_id:
        act="APPROVE" if to_status=="APPROVED_BY_HUMAN" else "REJECT"
        _approval(sb,doc_id,actor_id,act,comment,d.data)
    return af

def link_evidence(doc_id,evidence_type,storage_path,file_name=None,file_size=None,mime_type=None,linked_field_id=None,uploaded_by=None):
    sb=get_supabase();rec={"document_data_id":doc_id,"evidence_type":evidence_type,"storage_path":storage_path,"status":"LINKED"}
    if file_name:rec["file_name"]=file_name
    if file_size is not None:rec["file_size"]=file_size
    if mime_type:rec["mime_type"]=mime_type
    if linked_field_id:rec["linked_field_id"]=linked_field_id
    if uploaded_by:rec["uploaded_by"]=uploaded_by
    r=sb.table("evidence_vault_link").insert(rec).execute();ev=r.data[0] if r.data else{}
    if ev:_audit(sb,doc_id,"EVIDENCE_UPLOAD",uploaded_by,None,ev)
    return ev

def list_evidence(doc_id):
    sb=get_supabase();r=sb.table("evidence_vault_link").select("*").eq("document_data_id",doc_id).order("uploaded_at",desc=True).execute();return r.data or[]

def generate_document(doc_id,export_type="HTML"):
    sb=get_supabase();d=sb.table("runtime_document_data").select("*").eq("id",doc_id).single().execute()
    if not d.data:raise ValueError("document not found")
    rec={"runtime_document_id":doc_id,"form_schema_id":d.data.get("form_schema_id"),"export_type":export_type,"status":"GENERATED"}
    r=sb.table("generated_document").insert(rec).execute();g=r.data[0] if r.data else{}
    if g:_audit(sb,doc_id,"CREATED",None,None,g)
    return g

def list_generated(doc_id):
    sb=get_supabase();r=sb.table("generated_document").select("*").eq("runtime_document_id",doc_id).order("created_at",desc=True).execute();return r.data or[]

def get_metrics():
    sb=get_supabase();r=sb.table("v_runtime_metrics").select("*").execute();return r.data or[]

def get_metrics_by_factory(factory_id):
    sb=get_supabase();r=sb.table("v_runtime_metrics_by_factory").select("*").eq("factory_id",factory_id).execute();return r.data or[]

def get_audit_log(doc_id):
    sb=get_supabase();r=sb.table("runtime_lifecycle_audit_log").select("*").eq("runtime_document_id",doc_id).order("created_at",desc=True).execute();return r.data or[]

def _validate_field_keys(sb,schema_id,data_json):
    if not data_json:return
    r=sb.table("runtime_field").select("field_key").eq("form_schema_id",schema_id).execute()
    allowed={x["field_key"] for x in(r.data or[]) if x.get("field_key")}
    if not allowed:return
    unknown=set(data_json.keys())-allowed
    if unknown:raise ValueError(f"unknown field_keys: {sorted(unknown)}")

def _validate_evidence_links(sb,schema_id,links):
    if not links:return
    fids=[el.get("linked_field_id") for el in links if isinstance(el,dict) and el.get("linked_field_id")]
    if not fids:return
    r=sb.table("runtime_evidence_field").select("id").eq("form_schema_id",schema_id).execute()
    allowed={str(x["id"]) for x in(r.data or[])}
    unknown=set(fids)-allowed
    if unknown:raise ValueError(f"unknown evidence field_ids: {sorted(unknown)}")

def _audit(sb,doc_id,action,actor_id,before,after,field_changes=None):
    try:sb.table("runtime_lifecycle_audit_log").insert({"runtime_document_id":doc_id,"action":action,"actor_id":actor_id,"before_state":before,"after_state":after,"field_changes":field_changes,"rollback_available":True}).execute()
    except:pass

def _approval(sb,doc_id,reviewer_id,action,comment,doc_data):
    try:sb.table("runtime_document_approval").insert({"runtime_document_id":doc_id,"reviewer_id":reviewer_id,"review_action":action,"review_comment":comment,"runtime_snapshot":doc_data.get("runtime_data_json"),"evidence_snapshot":doc_data.get("evidence_links"),"source_trace_snapshot":{},"rollback_available":True}).execute()
    except:pass
