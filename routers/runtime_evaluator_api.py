"""TAI Runtime Evaluator API v1.0.0
Prefix: /runtime-evaluator
Deterministic Condition-Based Activation Only.
"""
from fastapi import APIRouter,HTTPException,Query
from typing import Optional
from schemas.runtime_evaluator import EvaluationContextIn,EvaluateIn
from services import runtime_evaluator_svc as svc

router=APIRouter(prefix="/runtime-evaluator",tags=["런타임 평가엔진"])

@router.post("/contexts")
def create_context(body:EvaluationContextIn):
    try:return{"status":"success","data":svc.create_context(body.dict())}
    except ValueError as e:raise HTTPException(400,str(e))

@router.get("/contexts")
def list_contexts(company_id:Optional[str]=Query(None),page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100)):
    return{"status":"success","data":svc.list_contexts(company_id,page,page_size)}

@router.get("/contexts/{ctx_id}")
def get_context(ctx_id:str):
    r=svc.get_context(ctx_id)
    if not r:raise HTTPException(404,"context not found")
    return{"status":"success","data":r}

@router.post("/evaluate")
def evaluate(body:EvaluateIn):
    try:return{"status":"success","data":svc.evaluate(body.context_id)}
    except ValueError as e:raise HTTPException(400,str(e))

@router.get("/results/{ctx_id}")
def get_result(ctx_id:str):
    r=svc.get_result(ctx_id)
    if not r:raise HTTPException(404,"result not found")
    return{"status":"success","data":r}

@router.get("/results/{ctx_id}/conflicts")
def get_conflicts(ctx_id:str):
    return{"status":"success","data":svc.get_conflicts(ctx_id)}

@router.get("/results/{ctx_id}/audit")
def get_audit(ctx_id:str):
    return{"status":"success","data":svc.get_audit(ctx_id)}
