"""TAI 문서엔진 API v1.0.0
Prefix: /document-engine
"""
from fastapi import APIRouter,HTTPException,Query
from typing import Optional
from schemas.document_engine import DocumentCreateIn,DocumentUpdateIn,StatusChangeIn,EvidenceLinkIn,GenerateDocumentIn
from services import document_engine_svc as svc

router=APIRouter(prefix="/document-engine",tags=["문서엔진"])

@router.get("/schemas")
def list_schemas(document_family:Optional[str]=Query(None),form_type:Optional[str]=Query(None),status:Optional[str]=Query(None),page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100)):
    return{"status":"success","data":svc.list_form_schemas(document_family,form_type,status,page,page_size)}

@router.get("/schemas/{schema_id}")
def get_schema_detail(schema_id:str):
    r=svc.get_form_schema_detail(schema_id)
    if not r:raise HTTPException(404,"schema not found")
    return{"status":"success","data":r}

@router.post("/documents")
def create_document(body:DocumentCreateIn):
    try:return{"status":"success","data":svc.create_document(body.form_schema_id,body.factory_id,body.company_id,body.created_by)}
    except ValueError as e:raise HTTPException(400,str(e))

@router.get("/documents")
def list_documents(factory_id:Optional[str]=Query(None),company_id:Optional[str]=Query(None),status:Optional[str]=Query(None),page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100)):
    return{"status":"success","data":svc.list_documents(factory_id,company_id,status,page,page_size)}

@router.get("/documents/{doc_id}")
def get_document(doc_id:str):
    r=svc.get_document(doc_id)
    if not r:raise HTTPException(404,"document not found")
    return{"status":"success","data":r}

@router.patch("/documents/{doc_id}")
def update_document(doc_id:str,body:DocumentUpdateIn):
    try:return{"status":"success","data":svc.update_document(doc_id,body.runtime_data_json,body.evidence_links,body.updated_by)}
    except ValueError as e:raise HTTPException(400,str(e))

@router.post("/documents/{doc_id}/status")
def change_status(doc_id:str,body:StatusChangeIn):
    try:return{"status":"success","data":svc.change_status(doc_id,body.to_status,body.actor_id,body.comment)}
    except ValueError as e:raise HTTPException(400,str(e))

@router.get("/transitions")
def list_transitions():
    return{"status":"success","data":svc.get_transitions()}

@router.post("/documents/{doc_id}/evidence")
def add_evidence(doc_id:str,body:EvidenceLinkIn):
    d=svc.get_document(doc_id)
    if not d:raise HTTPException(404,"document not found")
    return{"status":"success","data":svc.link_evidence(doc_id,body.evidence_type,body.storage_path,body.file_name,body.file_size,body.mime_type,body.linked_field_id,body.uploaded_by)}

@router.get("/documents/{doc_id}/evidence")
def list_evidence(doc_id:str):
    return{"status":"success","data":svc.list_evidence(doc_id)}

@router.post("/documents/{doc_id}/generate")
def generate_document(doc_id:str,body:GenerateDocumentIn):
    try:return{"status":"success","data":svc.generate_document(doc_id,body.export_type)}
    except ValueError as e:raise HTTPException(400,str(e))

@router.get("/documents/{doc_id}/generated")
def list_generated(doc_id:str):
    return{"status":"success","data":svc.list_generated(doc_id)}

@router.get("/metrics")
def get_metrics():
    return{"status":"success","data":svc.get_metrics()}

@router.get("/metrics/factory/{factory_id}")
def get_factory_metrics(factory_id:str):
    return{"status":"success","data":svc.get_metrics_by_factory(factory_id)}

@router.get("/documents/{doc_id}/audit-log")
def get_audit_log(doc_id:str):
    return{"status":"success","data":svc.get_audit_log(doc_id)}
