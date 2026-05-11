"""Residual Intelligence API Router.

FastAPI 라우터 — Residual, Pattern, Cluster, Review Queue, Registry API.
절대 원칙: 자동 해석 금지. 사람 승인 전 registry 반영 금지.
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
import os

router = APIRouter(prefix="/api/v1/residual-intelligence", tags=["Residual Intelligence"])


def _get_sb():
    from supabase import create_client
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    return create_client(url, key)


# ---- Schemas ----

class ResidualCreate(BaseModel):
    law_id: Optional[str] = None
    law_name: Optional[str] = None
    article_no: Optional[str] = None
    paragraph_no: Optional[str] = None
    item_no: Optional[str] = None
    part_id: Optional[str] = None
    source_text: str
    residual_text: Optional[str] = None
    source_span_start: Optional[int] = None
    source_span_end: Optional[int] = None
    residual_type: str

class FailedReasonCreate(BaseModel):
    failed_reason: str

class ReviewDecisionCreate(BaseModel):
    decision: str
    reviewer_id: Optional[str] = None
    review_comment: Optional[str] = None

class RegistryUpdateApply(BaseModel):
    decision_id: str
    registry_name: str
    new_entry: dict
    approved_by: Optional[str] = None

class ReprocessEnqueue(BaseModel):
    residual_id: str
    reason: str
    target_pipeline_stage: str = 'FAMILY_GROUPING'


# ---- Residuals ----

@router.post("/residuals")
async def create_residual(body: ResidualCreate):
    from services.residual_intelligence import ResidualStore
    sb = _get_sb()
    return ResidualStore.create(sb, body.model_dump())

@router.get("/residuals")
async def list_residuals(
    law_id: Optional[str] = None,
    residual_type: Optional[str] = None,
    status: Optional[str] = None,
    offset: int = 0, limit: int = 50
):
    from services.residual_intelligence import ResidualStore
    sb = _get_sb()
    return ResidualStore.list_residuals(sb, law_id, residual_type, status, offset, limit)

@router.get("/residuals/{residual_id}")
async def get_residual(residual_id: str):
    from services.residual_intelligence import ResidualStore
    sb = _get_sb()
    result = ResidualStore.get(sb, residual_id)
    if not result:
        raise HTTPException(404, "Residual not found")
    return result

@router.post("/residuals/{residual_id}/failed-reasons")
async def add_failed_reason(residual_id: str, body: FailedReasonCreate):
    from services.residual_intelligence import ResidualStore
    sb = _get_sb()
    ResidualStore.add_failed_reason(sb, residual_id, body.failed_reason)
    return {"status": "ok"}


# ---- Patterns ----

@router.post("/patterns/mine")
async def mine_patterns():
    from services.residual_intelligence import PatternMiner
    sb = _get_sb()
    count = PatternMiner.mine(sb)
    return {"patterns_mined": count}

@router.get("/patterns")
async def list_patterns(offset: int = 0, limit: int = 50):
    sb = _get_sb()
    result = sb.table('residual_patterns').select('*', count='exact').order(
        'occurrence_count', desc=True).range(offset, offset + limit - 1).execute()
    return {'data': result.data, 'count': result.count}


# ---- Clusters ----

@router.post("/clusters/build")
async def build_clusters():
    from services.residual_intelligence import ClusterBuilder
    sb = _get_sb()
    count = ClusterBuilder.build(sb)
    return {"clusters_built": count}

@router.get("/clusters")
async def list_clusters(offset: int = 0, limit: int = 50):
    sb = _get_sb()
    result = sb.table('residual_clusters').select('*', count='exact').order(
        'occurrence_count', desc=True).range(offset, offset + limit - 1).execute()
    return {'data': result.data, 'count': result.count}

@router.get("/clusters/{cluster_id}")
async def get_cluster(cluster_id: str):
    sb = _get_sb()
    cluster = sb.table('residual_clusters').select('*').eq('id', cluster_id).execute()
    items = sb.table('residual_cluster_items').select('*, residuals(*)').eq(
        'cluster_id', cluster_id).execute()
    if not cluster.data:
        raise HTTPException(404, "Cluster not found")
    return {'cluster': cluster.data[0], 'items': items.data}


# ---- Registry Gaps ----

@router.post("/registry-gaps/detect")
async def detect_registry_gaps():
    from services.residual_intelligence import RegistryGapDetector
    sb = _get_sb()
    count = RegistryGapDetector.detect(sb)
    return {"gaps_detected": count}

@router.get("/registry-gaps")
async def list_registry_gaps(offset: int = 0, limit: int = 50):
    sb = _get_sb()
    result = sb.table('registry_gaps').select('*', count='exact').order(
        'occurrence_count', desc=True).range(offset, offset + limit - 1).execute()
    return {'data': result.data, 'count': result.count}


# ---- Review Queue ----

@router.get("/review-queue")
async def list_review_queue(
    status: Optional[str] = None,
    review_type: Optional[str] = None,
    offset: int = 0, limit: int = 50
):
    from services.residual_intelligence import ReviewQueueManager
    sb = _get_sb()
    return ReviewQueueManager.list_queue(sb, status, review_type, offset, limit)

@router.post("/review-queue/{review_item_id}/decision")
async def submit_decision(review_item_id: str, body: ReviewDecisionCreate):
    from services.residual_intelligence import HumanDecisionStore
    sb = _get_sb()
    return HumanDecisionStore.submit_decision(
        sb, review_item_id, body.decision, body.reviewer_id, body.review_comment)


# ---- Registry Updates ----

@router.post("/registry-updates/apply")
async def apply_registry_update(body: RegistryUpdateApply):
    from services.residual_intelligence import ControlledRegistryUpdater
    sb = _get_sb()
    return ControlledRegistryUpdater.apply_update(
        sb, body.decision_id, body.registry_name, body.new_entry, body.approved_by)


# ---- Reprocessing ----

@router.post("/reprocessing-queue/enqueue")
async def enqueue_reprocessing(body: ReprocessEnqueue):
    from services.residual_intelligence import ReprocessingQueue
    sb = _get_sb()
    return ReprocessingQueue.enqueue(sb, body.residual_id, body.reason, body.target_pipeline_stage)

@router.get("/reprocessing-queue")
async def list_reprocessing(limit: int = 50):
    from services.residual_intelligence import ReprocessingQueue
    sb = _get_sb()
    return ReprocessingQueue.list_pending(sb, limit)


# ---- Coverage ----

@router.get("/coverage")
async def get_coverage_summary():
    from services.residual_intelligence import CoverageAnalyzer
    sb = _get_sb()
    return CoverageAnalyzer.get_summary(sb)

@router.get("/coverage/{law_id}")
async def get_coverage_by_law(law_id: str):
    from services.residual_intelligence import CoverageAnalyzer
    sb = _get_sb()
    result = CoverageAnalyzer.get_by_law(sb, law_id)
    if not result:
        raise HTTPException(404, "Coverage not found")
    return result


# ---- Dashboard ----

@router.get("/dashboard")
async def get_dashboard():
    from services.residual_intelligence import ResidualDashboard
    sb = _get_sb()
    return ResidualDashboard.get_metrics(sb)


# ---- Audit Logs ----

@router.get("/audit-logs")
async def list_audit_logs(
    entity_type: Optional[str] = None,
    offset: int = 0, limit: int = 50
):
    sb = _get_sb()
    q = sb.table('ri_audit_logs').select('*', count='exact')
    if entity_type: q = q.eq('entity_type', entity_type)
    q = q.range(offset, offset + limit - 1).order('created_at', desc=True)
    result = q.execute()
    return {'data': result.data, 'count': result.count}
