"""SaaS 반복설정 서비스.

SaaS는 자동 의무등록기가 아니다.
진단 결과 중 반복관리 후보를 승인받아 운영설정까지 한다.
"""
import os, json
from datetime import datetime, timezone
from services.time import now_kst, serialize_external_utc


def _get_sb():
    from supabase import create_client
    return create_client(os.environ.get('SUPABASE_URL',''),
                         os.environ.get('SUPABASE_SERVICE_ROLE_KEY',''))


class SaaSSetupService:
    """SaaS 반복설정 후보 추출 + 승인 + 등록."""

    # ── [4] 반복설정 후보 추출 조건 ──
    RECURRING_TYPES = {'INSPECTION','EDUCATION','REPORT','MEASUREMENT',
                       'PRESERVATION','PERMIT_RENEWAL','PRE_WORK_CHECK'}
    HOLD_STATUSES = {'UNKNOWN','UNRESOLVED','AMBIGUOUS','NEEDS_HUMAN_REVIEW'}

    @staticmethod
    def extract_setup_candidates(sb, session_id: str) -> dict:
        """진단 결과에서 반복관리 후보 추출. 자동 등록 금지."""
        # 진단 세션 확인
        session = sb.table('diagnosis_session').select('*').eq('id', session_id).execute()
        if not session.data:
            raise ValueError('Session not found')
        s = session.data[0]
        if s['diagnosis_status'] not in ('COMPLETED_WITH_CANDIDATES','NEEDS_HUMAN_REVIEW'):
            return {'candidates': [], 'reason': f"Status {s['diagnosis_status']} — no candidates"}

        # Obligation candidates 조회
        candidates = sb.table('diagnosis_candidate').select('*').eq(
            'session_id', session_id
        ).eq('candidate_type', 'OBLIGATION').execute()

        # Schedule hints 조회
        hints = sb.table('diagnosis_schedule_hint').select('*').eq(
            'session_id', session_id).execute()
        hint_map = {h.get('related_candidate_id'): h for h in (hints.data or [])}

        setup_candidates = []
        for c in (candidates.data or []):
            sub = c.get('sub_type', '')

            # [4] 반복관리 대상 확인
            if sub not in SaaSSetupService.RECURRING_TYPES:
                continue

            # [4] 보류 조건 확인
            if c.get('status') in SaaSSetupService.HOLD_STATUSES:
                continue

            # Setup type 결정
            hint = hint_map.get(c['id'], {})
            freq = hint.get('frequency_family', 'UNKNOWN')
            trigger = hint.get('trigger_family', 'UNKNOWN')

            if freq in ('YEARLY','MONTHLY','WEEKLY','DAILY','PERIODIC'):
                setup_type = 'RECURRING_TASK'
            elif trigger not in ('UNKNOWN',''):
                setup_type = 'EVENT_BASED_TASK'
            elif sub == 'PRESERVATION':
                setup_type = 'RECORD_RETENTION'
            else:
                setup_type = 'DEADLINE_TRACKING'

            ssc = sb.table('saas_setup_candidate').insert({
                'session_id': session_id,
                'related_candidate_id': c['id'],
                'setup_type': setup_type,
                'task_title_candidate': c.get('title_candidate', ''),
                'frequency_candidate': json.dumps({
                    'family': freq,
                    'raw_text': hint.get('raw_text'),
                    'status': 'CANDIDATE'
                }),
                'trigger_candidate': json.dumps({
                    'family': trigger,
                    'status': 'CANDIDATE'
                }),
                'deadline_candidate': json.dumps({
                    'family': hint.get('deadline_family', 'UNKNOWN'),
                    'status': 'CANDIDATE'
                }),
                'source_trace': json.dumps({
                    'law_name': c.get('source_law', ''),
                    'article': c.get('source_article', ''),
                    'source_text': c.get('source_text', ''),
                }),
                'approval_status': 'PENDING_USER_APPROVAL',
            }).execute()
            setup_candidates.append(ssc.data[0] if ssc.data else {})

        return {
            'session_id': session_id,
            'total_extracted': len(setup_candidates),
            'candidates': setup_candidates,
        }

    @staticmethod
    def approve(sb, setup_id: str, user_id: str = None) -> dict:
        """[7] 사용자 승인. 승인 후에만 SaaS 등록 가능."""
        before = sb.table('saas_setup_candidate').select('approval_status').eq('id', setup_id).execute()
        if not before.data:
            raise ValueError('Setup candidate not found')
        if before.data[0]['approval_status'] != 'PENDING_USER_APPROVAL':
            raise ValueError(f"Cannot approve: current status {before.data[0]['approval_status']}")

        sb.table('saas_setup_candidate').update({
            'approval_status': 'APPROVED_FOR_SAAS_SETUP',
            'approved_at': serialize_external_utc(now_kst()),
            'approved_by': user_id,
        }).eq('id', setup_id).execute()
        return {'setup_id': setup_id, 'status': 'APPROVED_FOR_SAAS_SETUP'}

    @staticmethod
    def reject(sb, setup_id: str, reason: str = None) -> dict:
        sb.table('saas_setup_candidate').update({
            'approval_status': 'REJECTED_BY_USER',
        }).eq('id', setup_id).execute()
        return {'setup_id': setup_id, 'status': 'REJECTED_BY_USER'}

    @staticmethod
    def request_more_data(sb, setup_id: str) -> dict:
        sb.table('saas_setup_candidate').update({
            'approval_status': 'NEEDS_MORE_DATA',
        }).eq('id', setup_id).execute()
        return {'setup_id': setup_id, 'status': 'NEEDS_MORE_DATA'}

    @staticmethod
    def register_to_runtime(sb, setup_id: str, user_id: str = None) -> dict:
        """[8] 승인된 항목만 Runtime에 등록. rollback 가능."""
        ssc = sb.table('saas_setup_candidate').select('*').eq('id', setup_id).execute()
        if not ssc.data:
            raise ValueError('Not found')
        c = ssc.data[0]
        if c['approval_status'] != 'APPROVED_FOR_SAAS_SETUP':
            raise ValueError(f"Not approved: {c['approval_status']}")

        # Registration log (실제 Runtime 등록은 기존 시스템이 처리)
        log = sb.table('saas_registration_log').insert({
            'setup_candidate_id': setup_id,
            'registered_entity_type': c['setup_type'],
            'source_trace': c.get('source_trace'),
            'rollback_available': True,
            'registered_by': user_id,
        }).execute()

        return {
            'setup_id': setup_id,
            'registration_id': log.data[0]['id'] if log.data else None,
            'status': 'REGISTERED',
            'rollback_available': True,
        }

    @staticmethod
    def list_candidates(sb, session_id: str = None, status: str = None, limit: int = 50) -> dict:
        q = sb.table('saas_setup_candidate').select('*', count='exact')
        if session_id: q = q.eq('session_id', session_id)
        if status: q = q.eq('approval_status', status)
        q = q.order('created_at', desc=True).limit(limit)
        r = q.execute()
        return {'data': r.data or [], 'count': r.count}
