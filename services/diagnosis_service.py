"""법령진단서비스 — 결과 출력까지만.

법령진단은 판단 엔진이 아니다.
결과를 출력할 뿐, 반복설정/스케줄/업무/위반을 확정하지 않는다.
"""
import json
import os
from datetime import datetime, timezone

from services.compiler_core_svc import fetch_compiler_candidates


def _get_sb():
    from supabase import create_client
    return create_client(os.environ.get('SUPABASE_URL',''),
                         os.environ.get('SUPABASE_SERVICE_ROLE_KEY',''))


class DiagnosisService:
    """법령진단서비스 핵심. Input → Compiler Core → Candidate 출력."""

    @staticmethod
    def evaluate(sb, factory_id: str, input_data: dict) -> dict:
        """[1] 법령진단 실행. 결과 출력까지만."""
        now = datetime.now(timezone.utc).isoformat()

        # Session 생성
        session = sb.table('diagnosis_session').insert({
            'factory_id': factory_id,
            'diagnosis_status': 'PROCESSING',
            'input_snapshot': json.dumps(input_data),
            'created_at': now,
        }).execute()
        sid = session.data[0]['id']

        try:
            core = fetch_compiler_candidates(sb, factory_id)
            applicability = core["applicability_candidates"]
            tasks = core["task_candidates"]
            schedules = core["schedule_candidates"]
            penalties = core["penalty_candidates"]
            residuals = core["residuals"]

            # ── Candidate 저장 ──
            obligations = []
            prohibitions = []
            TYPE_MAP = {
                'REPORT':'REPORT','INSTALL':'GENERAL','APPOINTMENT':'APPOINTMENT',
                'INSPECTION':'INSPECTION','EDUCATION':'EDUCATION','RECORD':'RECORD',
                'MEASUREMENT':'MEASUREMENT','PRESERVATION':'PRESERVATION',
                'SUBMIT':'REPORT','MAINTAIN':'GENERAL'
            }

            for t in tasks:
                ctype = 'OBLIGATION'
                tt = (t.get('task_type') or '')
                key = tt.split('_TASK_CANDIDATE')[0].split(':')[0].strip()
                sub = TYPE_MAP.get(key, 'GENERAL')
                dc = sb.table('diagnosis_candidate').insert({
                    'session_id': sid,
                    'candidate_type': ctype,
                    'sub_type': sub,
                    'title_candidate': f"{t.get('task_type','')}: {t.get('source_action_family','')}",
                    'source_law': t.get('obligation_family'),
                    'status': 'CANDIDATE' if t.get('status')!='NEEDS_HUMAN_REVIEW' else 'NEEDS_HUMAN_REVIEW',
                }).execute()
                obligations.append(dc.data[0] if dc.data else {})

            for a in applicability:
                sb.table('diagnosis_candidate').insert({
                    'session_id': sid,
                    'candidate_type': 'APPLICABILITY',
                    'title_candidate': f"Applicability: {a.get('applicability_status','')}",
                    'status': 'CANDIDATE',
                }).execute()

            # Schedule Hints 저장
            for s in schedules:
                freq = 'PERIODIC' if 'PERIODIC' in (s.get('schedule_type') or '') else 'UNKNOWN'
                if 'YEARLY' in (s.get('schedule_type') or ''): freq = 'YEARLY'
                sb.table('diagnosis_schedule_hint').insert({
                    'session_id': sid,
                    'frequency_family': freq,
                    'trigger_family': s.get('source_relation_type', 'UNKNOWN'),
                    'deadline_family': 'UNKNOWN',
                    'raw_text': s.get('source_family'),
                    'status': 'CANDIDATE',
                }).execute()

            # Penalty Links
            for p in penalties[:50]:
                sb.table('diagnosis_penalty_link').insert({
                    'session_id': sid,
                    'penalty_type': p.get('obligation_family'),
                    'penalty_family': p.get('obligation_family'),
                    'status': 'PENALTY_LINK_CANDIDATE',
                }).execute()

            # Missing data 수집
            missing = []
            if not input_data.get('employee_count'): missing.append('employee_count')
            if not input_data.get('industry_code'): missing.append('industry_code')
            if not input_data.get('equipment_list'): missing.append('equipment_list')

            # Validation
            has_unknown = any(s.get('status')=='NEEDS_HUMAN_REVIEW' for s in tasks)
            val_status = 'AMBIGUOUS' if has_unknown else ('UNRESOLVED' if residuals else 'PASS')

            # Session 업데이트
            diag_status = 'COMPLETED_WITH_CANDIDATES' if (obligations or applicability) else 'COMPLETED_CLEAN'
            if has_unknown: diag_status = 'NEEDS_HUMAN_REVIEW'

            sb.table('diagnosis_session').update({
                'diagnosis_status': diag_status,
                'validation_status': val_status,
                'validation_issues': json.dumps([{'type':'NEEDS_REVIEW','count':sum(1 for t in tasks if t.get('status')=='NEEDS_HUMAN_REVIEW')}]) if has_unknown else None,
                'missing_data': json.dumps(missing) if missing else None,
                'total_applicability': len(applicability),
                'total_obligations': len(obligations),
                'total_prohibitions': len(prohibitions),
                'total_penalties': min(len(penalties),50),
                'total_residuals': len(residuals),
                'completed_at': datetime.now(timezone.utc).isoformat(),
            }).eq('id', sid).execute()

            return {
                'diagnosis_id': sid,
                'facility_id': factory_id,
                'diagnosis_status': diag_status,
                'compiler_version': core['compiler_version'],
                'applicability_candidates': applicability,
                'obligation_candidates': [o for o in obligations if o],
                'prohibition_candidates': prohibitions,
                'penalty_candidates': penalties[:50],
                'schedule_candidate_hints': schedules,
                'missing_data': missing,
                'residuals': residuals,
                'human_review_queue': [t for t in tasks if t.get('status')=='NEEDS_HUMAN_REVIEW'],
                'validation': {'status': val_status, 'issues': []},
            }

        except Exception as e:
            sb.table('diagnosis_session').update({
                'diagnosis_status': 'FAILED',
                'validation_issues': json.dumps({'error': str(e)}),
                'completed_at': datetime.now(timezone.utc).isoformat(),
            }).eq('id', sid).execute()
            raise

    @staticmethod
    def get_session(sb, session_id: str) -> dict:
        s = sb.table('diagnosis_session').select('*').eq('id', session_id).execute()
        if not s.data: return None
        session = s.data[0]
        candidates = sb.table('diagnosis_candidate').select('*').eq('session_id', session_id).execute()
        penalties = sb.table('diagnosis_penalty_link').select('*').eq('session_id', session_id).execute()
        hints = sb.table('diagnosis_schedule_hint').select('*').eq('session_id', session_id).execute()
        return {
            'session': session,
            'candidates': candidates.data or [],
            'penalty_links': penalties.data or [],
            'schedule_hints': hints.data or [],
        }

    @staticmethod
    def list_sessions(sb, factory_id: str = None, limit: int = 20) -> dict:
        q = sb.table('diagnosis_session').select('*', count='exact')
        if factory_id: q = q.eq('factory_id', factory_id)
        q = q.order('created_at', desc=True).limit(limit)
        r = q.execute()
        return {'data': r.data or [], 'count': r.count}
