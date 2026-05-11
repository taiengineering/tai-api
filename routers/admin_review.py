"""Admin Legal Review API Router.

12개 엔드포인트. 사람 승인 전 registry 반영 금지.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import os

router = APIRouter(prefix="/api/v1/admin", tags=["Admin Legal Review"])


def _get_sb():
    from supabase import create_client
    return create_client(os.environ.get("SUPABASE_URL", ""),
                         os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""))


# ---- Schemas ----

class ApproveRequest(BaseModel):
    action: str
    actor_id: Optional[str] = None
    comment: Optional[str] = None
    extra_data: Optional[dict] = None

class FamilyCreateRequest(BaseModel):
    family_name: str
    family_type: str
    description: str
    source_examples: list
    approved_by: Optional[str] = None
    review_id: Optional[str] = None

class TokenAddRequest(BaseModel):
    raw_token: str
    canonical_token: str
    target_registry: str
    linked_family: str
    source_examples: list
    approved_by: Optional[str] = None
    review_id: Optional[str] = None

class ReprocessRequest(BaseModel):
    residual_id: str
    pipeline_stage: str = 'FAMILY_GROUPING'
    reason: str = ''
    review_id: Optional[str] = None
    actor_id: Optional[str] = None

class RollbackRequest(BaseModel):
    version_id: str
    actor_id: Optional[str] = None

class ReferenceLinkRequest(BaseModel):
    from_entity_type: str
    from_entity_id: str
    to_article_ref: str
    actor_id: Optional[str] = None
    review_id: Optional[str] = None


# ---- Review Queue ----

@router.get("/review-queue")
async def list_review_queue(
    status: Optional[str] = None,
    review_type: Optional[str] = None,
    offset: int = 0, limit: int = 50
):
    from services.admin_review import AdminReviewService
    return AdminReviewService.list_queue(_get_sb(), status, review_type, offset, limit)

@router.get("/review-queue/{review_id}")
async def get_review_detail(review_id: str):
    from services.admin_review import AdminReviewService
    result = AdminReviewService.get_detail(_get_sb(), review_id)
    if not result:
        raise HTTPException(404, "Review item not found")
    return result

@router.post("/review/{review_id}/approve")
async def approve_review(review_id: str, body: ApproveRequest):
    from services.admin_review import AdminReviewService
    return AdminReviewService.approve(
        _get_sb(), review_id, body.action, body.actor_id,
        body.comment, body.extra_data)

@router.post("/review/{review_id}/reject")
async def reject_review(review_id: str, body: ApproveRequest):
    body.action = 'REJECT_NON_ACTIONABLE'
    from services.admin_review import AdminReviewService
    return AdminReviewService.approve(
        _get_sb(), review_id, body.action, body.actor_id, body.comment)


# ---- Family ----

@router.post("/family/create")
async def create_family(body: FamilyCreateRequest):
    from services.admin_review import FamilyService
    return FamilyService.create(
        _get_sb(), body.family_name, body.family_type, body.description,
        body.source_examples, body.approved_by, body.review_id)


# ---- Registry Token ----

@router.post("/registry/add-token")
async def add_registry_token(body: TokenAddRequest):
    from services.admin_review import RegistryTokenService
    return RegistryTokenService.add_token(
        _get_sb(), body.raw_token, body.canonical_token, body.target_registry,
        body.linked_family, body.source_examples, body.approved_by, body.review_id)


# ---- Reference/Attachment Link ----

@router.post("/reference/link")
async def create_reference_link(body: ReferenceLinkRequest):
    from services.admin_review import AdminAudit
    sb = _get_sb()
    AdminAudit.log(sb, body.actor_id, 'REFERENCE_LINKED',
                   body.from_entity_type, body.from_entity_id,
                   after_data={'to_article_ref': body.to_article_ref})
    sb.table('registry_versions').insert({
        'registry_name': 'REFERENCE_REGISTRY',
        'version_no': 1, 'change_type': 'REFERENCE_LINKED',
        'changed_by': body.actor_id, 'review_decision_id': body.review_id,
        'after_state': '{"ref": "' + body.to_article_ref + '"}',
        'rollback_available': True,
    }).execute()
    return {'status': 'linked', 'to_article_ref': body.to_article_ref}

@router.post("/attachment/link")
async def create_attachment_link(body: ReferenceLinkRequest):
    from services.admin_review import AdminAudit
    sb = _get_sb()
    AdminAudit.log(sb, body.actor_id, 'ATTACHMENT_LINKED',
                   body.from_entity_type, body.from_entity_id,
                   after_data={'to_article_ref': body.to_article_ref})
    sb.table('registry_versions').insert({
        'registry_name': 'ATTACHMENT_REGISTRY',
        'version_no': 1, 'change_type': 'ATTACHMENT_LINKED',
        'changed_by': body.actor_id, 'review_decision_id': body.review_id,
        'after_state': '{"attachment": "' + body.to_article_ref + '"}',
        'rollback_available': True,
    }).execute()
    return {'status': 'linked', 'to_article_ref': body.to_article_ref}


# ---- Rule Approval ----

@router.post("/rule/approve")
async def approve_rule(body: ApproveRequest):
    """[8] Rule Candidate 승인. source span/trace 확인 필수."""
    from services.admin_review import AdminAudit
    sb = _get_sb()
    if not body.extra_data or not body.extra_data.get('rule_candidate_id'):
        raise HTTPException(400, 'rule_candidate_id 필수')
    rc_id = body.extra_data['rule_candidate_id']
    AdminAudit.log(sb, body.actor_id, 'RULE_APPROVED', 'rule_candidate', rc_id,
                   after_data={'approved': True, 'comment': body.comment})
    sb.table('registry_versions').insert({
        'registry_name': 'RULE_REGISTRY',
        'version_no': 1, 'change_type': 'RULE_APPROVED',
        'changed_by': body.actor_id,
        'after_state': '{"rule_candidate_id": "' + rc_id + '"}',
        'rollback_available': True,
    }).execute()
    return {'rule_candidate_id': rc_id, 'status': 'approved'}


# ---- Reprocessing ----

@router.post("/reprocessing/trigger")
async def trigger_reprocessing(body: ReprocessRequest):
    from services.admin_review import ReprocessingService
    return ReprocessingService.trigger(
        _get_sb(), body.residual_id, body.pipeline_stage,
        body.reason, body.review_id, body.actor_id)


# ---- Rollback ----

@router.post("/rollback")
async def execute_rollback(body: RollbackRequest):
    from services.admin_review import RollbackService
    return RollbackService.rollback(_get_sb(), body.version_id, body.actor_id)


# ---- Audit ----

@router.get("/audit-logs")
async def list_audit_logs(
    action: Optional[str] = None,
    entity_type: Optional[str] = None,
    offset: int = 0, limit: int = 50
):
    sb = _get_sb()
    q = sb.table('admin_audit_logs').select('*', count='exact')
    if action: q = q.eq('action', action)
    if entity_type: q = q.eq('entity_type', entity_type)
    q = q.range(offset, offset + limit - 1).order('created_at', desc=True)
    result = q.execute()
    return {'data': result.data, 'count': result.count}
