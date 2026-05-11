"""SaaS 반복설정 서비스.
SaaS는 자동 의무등록기가 아니다.
진단 결과 중 반복관리 후보를 승인받아 운영설정까지 한다.
"""
import os, json
from datetime import datetime, timezone

def _get_sb():
    from supabase import create_client
    return create_client(os.environ.get('SUPABASE_URL',''), os.environ.get('SUPABASE_SERVICE_ROLE_KEY',''))

class SaaSSetupService:
    RECURRING_TYPES = {'INSPECTION','EDUCATION','REPORT','MEASUREMENT','PRESERVATION','PERMIT_RENEWAL','PRE_WORK_CHECK'}

    @staticmethod
    def extract_setup_candidates(sb, session_id):
        session = sb.table('diagnosis_session').select('*').eq('id', session_id).execute()
        if not session.data: raise ValueError('Session not found')
        s = session.data[0]
        if s['diagnosis_status'] not in ('COMPLETED_WITH_CANDIDATES','NEEDS_HUMAN_REVIEW'):
            return {'candidates': [], 'reason': f"Status {s['diagnosis_status']}"}
        candidates = sb.table('diagnosis_candidate').select('*').eq('session_id', session_id).eq('candidate_type', 'OBLIGATION').execute()
        hints = sb.table('diagnosis_schedule_hint').select('*').eq('session_id', session_id).execute()
        hint_map = {h.get('related_candidate_id'): h for h in (hints.data or [])}
        setup_candidates = []
        for c in (candidates.data or []):
            sub = c.get('sub_type', '')
            if sub not in SaaSSetupService.RECURRING_TYPES: continue
            if c.get('status') in ('UNKNOWN','UNRESOLVED','AMBIGUOUS','NEEDS_HUMAN_REVIEW'): continue
            hint = hint_map.get(c['id'], {})
            freq = hint.get('frequency_family', 'UNKNOWN')
            trigger = hint.get('trigger_family', 'UNKNOWN')
            setup_type = 'RECURRING_TASK' if freq in ('YEARLY','MONTHLY','WEEKLY','DAILY','PERIODIC') else ('EVENT_BASED_TASK' if trigger not in ('UNKNOWN','') else ('RECORD_RETENTION' if sub=='PRESERVATION' else 'DEADLINE_TRACKING'))
            ssc = sb.table('saas_setup_candidate').insert({'session_id': session_id, 'related_candidate_id': c['id'], 'setup_type': setup_type, 'task_title_candidate': c.get('title_candidate',''), 'frequency_candidate': json.dumps({'family': freq, 'status': 'CANDIDATE'}), 'trigger_candidate': json.dumps({'family': trigger, 'status': 'CANDIDATE'}), 'deadline_candidate': json.dumps({'family': hint.get('deadline_family','UNKNOWN'), 'status': 'CANDIDATE'}), 'source_trace': json.dumps({'law_name': c.get('source_law',''), 'article': c.get('source_article','')}), 'approval_status': 'PENDING_USER_APPROVAL'}).execute()
            setup_candidates.append(ssc.data[0] if ssc.data else {})
        return {'session_id': session_id, 'total_extracted': len(setup_candidates), 'candidates': setup_candidates}

    @staticmethod
    def approve(sb, setup_id, user_id=None):
        before = sb.table('saas_setup_candidate').select('approval_status').eq('id', setup_id).execute()
        if not before.data: raise ValueError('Not found')
        if before.data[0]['approval_status'] != 'PENDING_USER_APPROVAL': raise ValueError('Cannot approve')
        sb.table('saas_setup_candidate').update({'approval_status': 'APPROVED_FOR_SAAS_SETUP', 'approved_at': datetime.now(timezone.utc).isoformat(), 'approved_by': user_id}).eq('id', setup_id).execute()
        return {'setup_id': setup_id, 'status': 'APPROVED_FOR_SAAS_SETUP'}

    @staticmethod
    def reject(sb, setup_id, reason=None):
        sb.table('saas_setup_candidate').update({'approval_status': 'REJECTED_BY_USER'}).eq('id', setup_id).execute()
        return {'setup_id': setup_id, 'status': 'REJECTED_BY_USER'}

    @staticmethod
    def request_more_data(sb, setup_id):
        sb.table('saas_setup_candidate').update({'approval_status': 'NEEDS_MORE_DATA'}).eq('id', setup_id).execute()
        return {'setup_id': setup_id, 'status': 'NEEDS_MORE_DATA'}

    @staticmethod
    def register_to_runtime(sb, setup_id, user_id=None):
        ssc = sb.table('saas_setup_candidate').select('*').eq('id', setup_id).execute()
        if not ssc.data: raise ValueError('Not found')
        c = ssc.data[0]
        if c['approval_status'] != 'APPROVED_FOR_SAAS_SETUP': raise ValueError('Not approved')
        log = sb.table('saas_registration_log').insert({'setup_candidate_id': setup_id, 'registered_entity_type': c['setup_type'], 'source_trace': c.get('source_trace'), 'rollback_available': True, 'registered_by': user_id}).execute()
        return {'setup_id': setup_id, 'registration_id': log.data[0]['id'] if log.data else None, 'status': 'REGISTERED'}

    @staticmethod
    def list_candidates(sb, session_id=None, status=None, limit=50):
        q = sb.table('saas_setup_candidate').select('*', count='exact')
        if session_id: q = q.eq('session_id', session_id)
        if status: q = q.eq('approval_status', status)
        r = q.order('created_at', desc=True).limit(limit).execute()
        return {'data': r.data or [], 'count': r.count}
