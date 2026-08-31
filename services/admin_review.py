"""Admin Legal Review Service.

사람이 검토하고 승인한 것만 Registry/Rule로 추가된다.
자동 학습/확장/생성 금지.
"""
import os, json
from datetime import datetime, timezone
from uuid import uuid4
from services.time import now_kst, serialize_external_utc


def _get_sb():
    from supabase import create_client
    return create_client(os.environ.get("SUPABASE_URL", ""),
                         os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""))


class AdminAudit:
    """[12] 모든 행동 audit."""
    @staticmethod
    def log(sb, actor_id, action, entity_type, entity_id,
            before_data=None, after_data=None):
        sb.table('admin_audit_logs').insert({
            'actor_id': actor_id,
            'action': action,
            'entity_type': entity_type,
            'entity_id': str(entity_id) if entity_id else None,
            'before_data': json.dumps(before_data) if before_data else None,
            'after_data': json.dumps(after_data) if after_data else None,
        }).execute()


class AdminReviewService:
    """[3~5] Admin Review Queue + 승인 액션."""

    @staticmethod
    def list_queue(sb, status=None, review_type=None, offset=0, limit=50):
        q = sb.table('admin_review_queue').select('*', count='exact')
        if status: q = q.eq('status', status)
        if review_type: q = q.eq('review_type', review_type)
        q = q.range(offset, offset + limit - 1).order('occurrence_count', desc=True)
        result = q.execute()
        return {'data': result.data, 'count': result.count}

    @staticmethod
    def get_detail(sb, review_id):
        """[4] 검토 상세 — 원문, span, failed_reason, 관련 candidate 등."""
        item = sb.table('admin_review_queue').select('*').eq('id', review_id).execute()
        if not item.data:
            return None
        r = item.data[0]

        # 관련 audit history
        audits = sb.table('admin_audit_logs').select('*').eq(
            'entity_id', review_id).order('created_at', desc=True).limit(20).execute()

        return {
            'review': r,
            'audit_history': audits.data or [],
        }

    @staticmethod
    def approve(sb, review_id, action, actor_id, comment=None, extra_data=None):
        """[5] 승인 액션 10종."""
        VALID_ACTIONS = [
            'KEEP_AS_UNKNOWN','MAP_TO_EXISTING_FAMILY','CREATE_NEW_FAMILY',
            'ADD_REGISTRY_TOKEN','CREATE_REFERENCE_LINK','CREATE_ATTACHMENT_LINK',
            'APPROVE_RULE_CANDIDATE','REJECT_NON_ACTIONABLE',
            'ESCALATE_TO_LEGAL_EXPERT','REQUEST_MORE_SOURCE'
        ]
        if action not in VALID_ACTIONS:
            raise ValueError(f'Invalid action: {action}')

        # 상태 결정
        status_map = {
            'KEEP_AS_UNKNOWN': 'APPROVED', 'MAP_TO_EXISTING_FAMILY': 'APPROVED',
            'CREATE_NEW_FAMILY': 'APPROVED', 'ADD_REGISTRY_TOKEN': 'APPROVED',
            'CREATE_REFERENCE_LINK': 'APPROVED', 'CREATE_ATTACHMENT_LINK': 'APPROVED',
            'APPROVE_RULE_CANDIDATE': 'APPROVED', 'REJECT_NON_ACTIONABLE': 'REJECTED',
            'ESCALATE_TO_LEGAL_EXPERT': 'ESCALATED', 'REQUEST_MORE_SOURCE': 'NEED_MORE_DATA',
        }
        new_status = status_map[action]

        # before
        before = sb.table('admin_review_queue').select('status').eq('id', review_id).execute()
        before_status = before.data[0]['status'] if before.data else None

        # update
        sb.table('admin_review_queue').update({
            'status': new_status,
            'updated_at': serialize_external_utc(now_kst())
        }).eq('id', review_id).execute()

        # audit
        audit_action = 'REVIEW_APPROVED' if new_status == 'APPROVED' else (
            'REVIEW_REJECTED' if new_status == 'REJECTED' else action.upper())
        AdminAudit.log(sb, actor_id, audit_action, 'admin_review_queue', review_id,
                       before_data={'status': before_status},
                       after_data={'status': new_status, 'action': action,
                                   'comment': comment, 'extra': extra_data})

        return {'review_id': review_id, 'action': action, 'new_status': new_status}


class FamilyService:
    """[6] Family 생성 — 사람 승인 필수."""
    @staticmethod
    def create(sb, family_name, family_type, description,
               source_examples, approved_by, review_id=None):
        VALID_TYPES = ['ACTION_FAMILY','CONDITION_FAMILY','FREQUENCY_FAMILY',
                       'DEADLINE_FAMILY','TRIGGER_FAMILY','PENALTY_FAMILY',
                       'EXCEPTION_FAMILY','ATTACHMENT_FAMILY']
        if family_type not in VALID_TYPES:
            raise ValueError(f'Invalid family_type: {family_type}')
        if not source_examples:
            raise ValueError('source_examples 필수')

        version_id = f"v_{now_kst().strftime('%Y%m%d_%H%M%S')}"
        data = {
            'family_name': family_name, 'family_type': family_type,
            'description': description, 'source_examples': json.dumps(source_examples),
            'approved_by': approved_by, 'version_id': version_id,
        }

        # token_family_registry에 추가
        sb.table('token_family_registry').insert({
            'family_name': family_name,
            'token_pattern': family_name,
            'description': description,
        }).execute()

        # registry_versions
        sb.table('registry_versions').insert({
            'registry_name': 'FAMILY_REGISTRY',
            'version_no': 1, 'change_type': 'FAMILY_LINKED',
            'changed_by': approved_by, 'review_decision_id': review_id,
            'after_state': json.dumps(data), 'rollback_available': True,
        }).execute()

        AdminAudit.log(sb, approved_by, 'FAMILY_CREATED', 'token_family_registry',
                       None, after_data=data)
        return data


class RegistryTokenService:
    """[7] Registry Token 추가 — source_examples 필수."""
    @staticmethod
    def add_token(sb, raw_token, canonical_token, target_registry,
                  linked_family, source_examples, approved_by, review_id=None):
        if not source_examples:
            raise ValueError('source_examples 없는 token 추가 금지')

        version_id = f"v_{now_kst().strftime('%Y%m%d_%H%M%S')}"
        data = {
            'raw_token': raw_token, 'canonical_token': canonical_token,
            'target_registry': target_registry, 'linked_family': linked_family,
            'source_examples': json.dumps(source_examples),
            'approved_by': approved_by, 'version_id': version_id,
        }

        sb.table('token_family_registry').insert({
            'family_name': linked_family,
            'token_pattern': canonical_token,
            'description': f'Admin added: {raw_token}',
        }).execute()

        sb.table('registry_versions').insert({
            'registry_name': target_registry,
            'version_no': 1, 'change_type': 'TOKEN_ADDED',
            'changed_by': approved_by, 'review_decision_id': review_id,
            'after_state': json.dumps(data), 'rollback_available': True,
        }).execute()

        AdminAudit.log(sb, approved_by, 'TOKEN_ADDED', 'token_family_registry',
                       None, after_data=data)
        return data


class RollbackService:
    """[11] Rollback."""
    @staticmethod
    def rollback(sb, version_id, actor_id):
        ver = sb.table('registry_versions').select('*').eq('id', version_id).execute()
        if not ver.data:
            raise ValueError('Version not found')
        v = ver.data[0]
        if not v.get('rollback_available'):
            raise ValueError('Rollback not available')

        sb.table('registry_versions').update({
            'rollback_available': False
        }).eq('id', version_id).execute()

        AdminAudit.log(sb, actor_id, 'ROLLBACK_EXECUTED', 'registry_versions',
                       version_id, before_data=v.get('after_state'),
                       after_data={'rolled_back': True})
        return {'version_id': version_id, 'status': 'rolled_back'}


class ReprocessingService:
    """[9] 재처리 — 영향 받은 residual만."""
    @staticmethod
    def trigger(sb, residual_id, pipeline_stage, reason, review_id, actor_id):
        data = {
            'target_residual_id': residual_id,
            'target_pipeline_stage': pipeline_stage,
            'reason': reason,
            'triggered_by_review_id': review_id,
            'status': 'PENDING',
        }
        result = sb.table('admin_reprocessing_queue').insert(data).execute()
        AdminAudit.log(sb, actor_id, 'REPROCESSING_TRIGGERED',
                       'admin_reprocessing_queue',
                       result.data[0]['id'] if result.data else None,
                       after_data=data)
        return result.data[0] if result.data else data
