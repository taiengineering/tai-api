"""Residual Intelligence — Service Layer.

12개 모듈: ResidualCollector, ResidualStore, ResidualClassifier, PatternMiner,
ClusterBuilder, RegistryGapDetector, ReviewQueueManager, HumanDecisionStore,
ControlledRegistryUpdater, ReprocessingQueue, CoverageAnalyzer, AuditLogger.

절대 원칙: 자동 해석 금지. 사람 승인 전 registry 반영 금지.
"""
import os, json
from datetime import datetime, timezone
from typing import Optional, List
from uuid import uuid4
from services.time import now_kst, serialize_external_utc


def _now():
    return serialize_external_utc(now_kst())


def _get_pool():
    """DB connection pool (lazy)."""
    from supabase import create_client
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    return create_client(url, key)


class AuditLogger:
    """[12] 모든 변경 기록. 삭제 금지."""
    @staticmethod
    def log(sb, entity_type: str, entity_id: str, action: str,
            before_data=None, after_data=None, actor_type='SYSTEM', actor_id=None):
        sb.table('ri_audit_logs').insert({
            'entity_type': entity_type,
            'entity_id': entity_id,
            'action': action,
            'before_data': json.dumps(before_data) if before_data else None,
            'after_data': json.dumps(after_data) if after_data else None,
            'actor_type': actor_type,
            'actor_id': actor_id,
        }).execute()


class ResidualCollector:
    """[1] 파싱 실패 항목 수집."""
    @staticmethod
    def collect_from_existing(sb):
        """residual_candidate 테이블에서 residuals로 이전."""
        result = sb.rpc('collect_residuals_from_existing', {}).execute()
        return result.data


class ResidualStore:
    """[2] Residual CRUD. source_span 필수."""
    @staticmethod
    def create(sb, data: dict) -> dict:
        if not data.get('source_text'):
            raise ValueError('source_text 필수')
        data['id'] = str(uuid4())
        data['status'] = 'NEW'
        result = sb.table('residuals').insert(data).execute()
        AuditLogger.log(sb, 'residual', data['id'], 'CREATED', after_data=data)
        return result.data[0] if result.data else data

    @staticmethod
    def get(sb, residual_id: str) -> Optional[dict]:
        result = sb.table('residuals').select('*').eq('id', residual_id).execute()
        return result.data[0] if result.data else None

    @staticmethod
    def list_residuals(sb, law_id=None, residual_type=None, status=None,
                       offset=0, limit=50) -> dict:
        q = sb.table('residuals').select('*', count='exact')
        if law_id: q = q.eq('law_id', law_id)
        if residual_type: q = q.eq('residual_type', residual_type)
        if status: q = q.eq('status', status)
        q = q.range(offset, offset + limit - 1).order('created_at', desc=True)
        result = q.execute()
        return {'data': result.data, 'count': result.count}

    @staticmethod
    def add_failed_reason(sb, residual_id: str, failed_reason: str):
        data = {'residual_id': residual_id, 'failed_reason': failed_reason}
        sb.table('residual_failed_reasons').insert(data).execute()
        AuditLogger.log(sb, 'residual_failed_reason', residual_id,
                        'FAILED_REASON_ADDED', after_data=data)


class ResidualClassifier:
    """[3] Residual 유형 후보 분류. 의미 확정 금지."""
    TYPES = [
        'ABSTRACT_REQUIREMENT','BROAD_OBLIGATION','UNRESOLVED_REFERENCE',
        'UNRESOLVED_ATTACHMENT','UNMATCHED_ACTION','UNMATCHED_SCOPE',
        'UNMATCHED_CONDITION','UNMATCHED_EXCEPTION','UNMATCHED_NUMERIC',
        'AMBIGUOUS_RELATION','REGISTRY_GAP','STRUCTURAL_PARSE_FAILURE',
        'HUMAN_REVIEW_REQUIRED'
    ]


class PatternMiner:
    """[4] 반복 패턴 분석. 의미 부여 금지."""
    @staticmethod
    def mine(sb) -> int:
        # residual_text 기준 집계
        sb.table('residual_patterns').delete().neq('id', '00000000-0000-0000-0000-000000000000').execute()
        # residual_abstract_pattern 데이터를 residual_patterns로 복사
        existing = sb.table('residual_abstract_pattern').select(
            'pattern_text, pattern_type').execute()
        if not existing.data:
            return 0
        from collections import Counter
        counter = Counter()
        law_counter = {}
        for row in existing.data:
            pt = row['pattern_text']
            counter[pt] += 1
        # residual_patterns INSERT
        patterns = []
        for pt, cnt in counter.items():
            ptype = next((r['pattern_type'] for r in existing.data if r['pattern_text'] == pt), 'UNKNOWN')
            patterns.append({
                'pattern_text': pt, 'pattern_type': ptype,
                'occurrence_count': cnt, 'related_law_count': 0,
                'status': 'PATTERN_CANDIDATE'
            })
        if patterns:
            sb.table('residual_patterns').insert(patterns).execute()
        AuditLogger.log(sb, 'residual_patterns', None, 'PATTERN_MINED',
                        after_data={'count': len(patterns)})
        return len(patterns)


class ClusterBuilder:
    """[5] 반복 패턴 클러스터링. 검토 묶음일 뿐."""
    @staticmethod
    def build(sb) -> int:
        patterns = sb.table('residual_patterns').select('*').gte(
            'occurrence_count', 5).execute()
        if not patterns.data:
            return 0
        count = 0
        for p in patterns.data:
            cluster_id = str(uuid4())
            sb.table('residual_clusters').insert({
                'id': cluster_id,
                'cluster_name': f"CLUSTER_{p['pattern_type']}_{p['pattern_text'][:30]}",
                'representative_pattern': p['pattern_text'],
                'occurrence_count': p['occurrence_count'],
                'status': 'NEEDS_HUMAN_REVIEW'
            }).execute()
            # 패턴 status 업데이트
            sb.table('residual_patterns').update(
                {'status': 'CLUSTERED'}
            ).eq('id', p['id']).execute()
            count += 1
        AuditLogger.log(sb, 'residual_clusters', None, 'CLUSTERS_BUILT',
                        after_data={'count': count})
        return count


class RegistryGapDetector:
    """[6] Registry 부족 항목 탐지. 자동 추가 금지."""
    @staticmethod
    def detect(sb) -> int:
        sb.table('registry_gaps').delete().neq('id', '00000000-0000-0000-0000-000000000000').execute()
        # residual_registry_candidate 데이터 활용
        existing = sb.table('residual_registry_candidate').select('*').execute()
        if not existing.data:
            return 0
        gaps = []
        for r in existing.data:
            gaps.append({
                'target_registry': r.get('target_registry', 'FAMILY_REGISTRY'),
                'unmatched_token': r['pattern_text'],
                'occurrence_count': r['occurrence_count'],
                'status': 'EXPANSION_CANDIDATE'
            })
        if gaps:
            sb.table('registry_gaps').insert(gaps).execute()
        AuditLogger.log(sb, 'registry_gaps', None, 'GAPS_DETECTED',
                        after_data={'count': len(gaps)})
        return len(gaps)


class ReviewQueueManager:
    """[7] Human Review 큐 관리."""
    @staticmethod
    def enqueue_cluster(sb, cluster_id: str, reason: str = '') -> dict:
        data = {
            'review_type': 'CLUSTER_REVIEW',
            'cluster_id': cluster_id,
            'reason': reason,
            'status': 'PENDING_REVIEW'
        }
        result = sb.table('review_queue').insert(data).execute()
        AuditLogger.log(sb, 'review_queue', result.data[0]['id'] if result.data else None,
                        'ENQUEUED', after_data=data)
        return result.data[0] if result.data else data

    @staticmethod
    def enqueue_registry_gap(sb, gap_id: str, reason: str = '') -> dict:
        data = {
            'review_type': 'REGISTRY_EXPANSION_REVIEW',
            'registry_gap_id': gap_id,
            'reason': reason,
            'status': 'PENDING_REVIEW'
        }
        result = sb.table('review_queue').insert(data).execute()
        return result.data[0] if result.data else data

    @staticmethod
    def enqueue_residual(sb, residual_id: str, reason: str = '') -> dict:
        data = {
            'review_type': 'RESIDUAL_REVIEW',
            'residual_id': residual_id,
            'reason': reason,
            'status': 'PENDING_REVIEW'
        }
        result = sb.table('review_queue').insert(data).execute()
        # residual status 업데이트
        sb.table('residuals').update({'status': 'REVIEW_PENDING'}).eq('id', residual_id).execute()
        return result.data[0] if result.data else data

    @staticmethod
    def list_queue(sb, status=None, review_type=None, offset=0, limit=50) -> dict:
        q = sb.table('review_queue').select('*', count='exact')
        if status: q = q.eq('status', status)
        if review_type: q = q.eq('review_type', review_type)
        q = q.range(offset, offset + limit - 1).order('created_at', desc=True)
        result = q.execute()
        return {'data': result.data, 'count': result.count}


class HumanDecisionStore:
    """[8] 사람 검토 결과 저장."""
    @staticmethod
    def submit_decision(sb, review_item_id: str, decision: str,
                        reviewer_id: str = None, comment: str = None) -> dict:
        data = {
            'review_item_id': review_item_id,
            'decision': decision,
            'reviewer_id': reviewer_id,
            'review_comment': comment,
            'approved_at': _now() if decision not in ('NEED_MORE_SOURCE','ESCALATE_TO_LEGAL_EXPERT') else None
        }
        result = sb.table('human_review_decisions').insert(data).execute()
        # review_queue status 업데이트
        new_status = 'APPROVED' if decision not in ('NEED_MORE_SOURCE','ESCALATE_TO_LEGAL_EXPERT','KEEP_AS_UNKNOWN','REJECT_AS_NON_ACTIONABLE') else (
            'NEED_MORE_SOURCE' if decision == 'NEED_MORE_SOURCE' else
            'ESCALATED' if decision == 'ESCALATE_TO_LEGAL_EXPERT' else 'REJECTED'
        )
        sb.table('review_queue').update({'status': new_status}).eq('id', review_item_id).execute()
        AuditLogger.log(sb, 'human_review_decision', result.data[0]['id'] if result.data else None,
                        'DECISION_SUBMITTED', after_data=data)
        return result.data[0] if result.data else data


class ControlledRegistryUpdater:
    """[9] 사람 승인된 항목만 registry 반영. 자동 확장 금지."""
    @staticmethod
    def apply_update(sb, decision_id: str, registry_name: str,
                     new_entry: dict, approved_by: str = None) -> dict:
        # 승인 확인
        decision = sb.table('human_review_decisions').select('*').eq('id', decision_id).execute()
        if not decision.data:
            raise ValueError('Decision not found')
        d = decision.data[0]
        if d['decision'] not in ('CREATE_NEW_FAMILY','CREATE_NEW_REGISTRY_ENTRY','MAP_TO_EXISTING_FAMILY','LINK_TO_REFERENCE','LINK_TO_ATTACHMENT'):
            raise ValueError(f"Decision {d['decision']} is not an approval for registry update")

        version_id = f"v_{now_kst().strftime('%Y%m%d_%H%M%S')}_{str(uuid4())[:8]}"
        data = {
            'registry_name': registry_name,
            'new_entry': json.dumps(new_entry),
            'source_review_decision_id': decision_id,
            'version_id': version_id,
            'approved_by': approved_by,
            'rollback_available': True,
            'rollback_data': json.dumps({'previous_state': 'before_update'}),
        }
        result = sb.table('registry_updates').insert(data).execute()
        AuditLogger.log(sb, 'registry_update', result.data[0]['id'] if result.data else None,
                        'REGISTRY_UPDATED', after_data=data)
        return result.data[0] if result.data else data


class ReprocessingQueue:
    """[10] 영향 받은 residual만 재처리. 전체 재처리 금지."""
    @staticmethod
    def enqueue(sb, residual_id: str, reason: str,
                target_stage: str = 'FAMILY_GROUPING') -> dict:
        data = {
            'residual_id': residual_id,
            'reason': reason,
            'target_pipeline_stage': target_stage,
            'status': 'PENDING'
        }
        result = sb.table('reprocessing_queue').insert(data).execute()
        return result.data[0] if result.data else data

    @staticmethod
    def list_pending(sb, limit=50) -> list:
        result = sb.table('reprocessing_queue').select('*').eq(
            'status', 'PENDING').limit(limit).execute()
        return result.data


class CoverageAnalyzer:
    """[11] Coverage 지표. 정확도 점수 아님."""
    @staticmethod
    def get_by_law(sb, law_id: str) -> Optional[dict]:
        result = sb.table('residual_coverage').select('*').eq('law_id', law_id).execute()
        return result.data[0] if result.data else None

    @staticmethod
    def get_summary(sb) -> dict:
        result = sb.table('residual_coverage').select('*').execute()
        if not result.data:
            return {'total_laws': 0, 'avg_coverage': 0}
        ratios = [r['coverage_ratio'] for r in result.data if r.get('coverage_ratio')]
        return {
            'total_laws': len(result.data),
            'avg_coverage': sum(float(r) for r in ratios) / len(ratios) if ratios else 0,
            'min_coverage': min(float(r) for r in ratios) if ratios else 0,
            'max_coverage': max(float(r) for r in ratios) if ratios else 0,
        }


# Dashboard
class ResidualDashboard:
    """Dashboard metrics."""
    @staticmethod
    def get_metrics(sb) -> dict:
        residual_count = sb.table('residuals').select('id', count='exact').execute().count or 0
        pending_review = sb.table('review_queue').select('id', count='exact').eq('status', 'PENDING_REVIEW').execute().count or 0
        patterns = sb.table('residual_patterns').select('pattern_text,occurrence_count').order('occurrence_count', desc=True).limit(10).execute()
        gaps = sb.table('registry_gaps').select('unmatched_token,occurrence_count').order('occurrence_count', desc=True).limit(10).execute()
        coverage = CoverageAnalyzer.get_summary(sb)

        return {
            'total_residual_count': residual_count,
            'pending_review_count': pending_review,
            'top_patterns': patterns.data or [],
            'top_registry_gaps': gaps.data or [],
            'coverage': coverage,
        }
