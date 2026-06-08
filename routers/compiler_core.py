"""Deterministic Legal Compiler Core API.

기존 Runtime이 호출할 신규 Compiler Core 인터페이스.
Candidate만 반환. Truth 확정 금지.

기존 Runtime(inspection_schedule, overdue_checker 등)이
이 API를 통해 법령 판단 결과를 소비한다.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import os

router = APIRouter(prefix="/api/v1/compiler", tags=["Legal Compiler Core"])


def _get_sb():
    from supabase import create_client
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    return create_client(url, key)


# ---- Schemas ----

class FacilityEvaluateRequest(BaseModel):
    factory_id: str

class CandidateItem(BaseModel):
    id: str
    type: str
    family: Optional[str] = None
    status: str
    source_text: Optional[str] = None
    source_article: Optional[str] = None


# ============================================================
# [4단계] POST /compiler/evaluate-facility
# Runtime이 호출하는 핵심 API.
# 시설 데이터 기반 Candidate 반환.
# ============================================================

@router.post("/evaluate-facility")
async def evaluate_facility(body: FacilityEvaluateRequest):
    """Runtime이 호출하는 Compiler Core.
    Candidate만 반환. 법적 확정 금지.
    """
    from services.compiler_core_svc import fetch_compiler_candidates

    sb = _get_sb()
    try:
        core = fetch_compiler_candidates(sb, body.factory_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        'factory_id': core['factory_id'],
        'compiler_version': core['compiler_version'],
        'warning': core['warning'],
        'applicability_candidates': core['applicability_candidates'],
        'task_candidates': core['task_candidates'],
        'schedule_candidates': core['schedule_candidates'],
        'penalty_relations': core['penalty_relations'],
        'review_queue': core['review_queue'],
        'compliance_package': core['compliance_package'],
    }


# ============================================================
# GET /compiler/task-candidates/{factory_id}
# ============================================================

@router.get("/task-candidates/{factory_id}")
async def get_task_candidates(factory_id: str, status: Optional[str] = None):
    sb = _get_sb()
    q = sb.table('task_candidate').select(
        '*, task_candidate_relation(relation_type, family_name, raw_token)'
    ).eq('factory_id', factory_id)
    if status:
        q = q.eq('status', status)
    result = q.order('task_type').execute()
    return {'data': result.data or [], 'count': len(result.data or [])}


# ============================================================
# GET /compiler/schedule-candidates/{factory_id}
# ============================================================

@router.get("/schedule-candidates/{factory_id}")
async def get_schedule_candidates(factory_id: str):
    sb = _get_sb()
    result = sb.table('schedule_candidate').select('*').eq(
        'factory_id', factory_id).execute()
    return {'data': result.data or [], 'count': len(result.data or [])}


# ============================================================
# GET /compiler/penalty-map/{factory_id}
# ============================================================

@router.get("/penalty-map/{factory_id}")
async def get_penalty_map(factory_id: str):
    """Facility의 Task와 연결된 Penalty Candidate 조회."""
    sb = _get_sb()
    # task의 draft → rule_candidate → penalty_obligation_relation
    tasks = sb.table('task_candidate').select(
        'id, draft_id, task_type'
    ).eq('factory_id', factory_id).execute()

    if not tasks.data:
        return {'data': [], 'count': 0}

    draft_ids = list(set(t['draft_id'] for t in tasks.data if t.get('draft_id')))
    if not draft_ids:
        return {'data': [], 'count': 0}

    # draft → rule_candidate → penalty relation
    penalties = sb.table('penalty_obligation_relation').select(
        '*, penalty_candidate!inner(penalty_family, raw_token, source_text, violation_trigger)'
    ).execute()

    return {
        'factory_id': factory_id,
        'task_count': len(tasks.data),
        'penalty_relations': penalties.data[:100] if penalties.data else [],
        'warning': 'Penalty relations are CANDIDATES only. Not legal conclusions.'
    }


# ============================================================
# GET /compiler/source-trace/{part_id}
# [14단계] Source Trace 조회
# ============================================================

@router.get("/source-trace/{part_id}")
async def get_source_trace(part_id: str):
    """Candidate의 원문 trace 조회. Runtime UI에서 표시."""
    sb = _get_sb()

    # Part 원문
    part = sb.table('law_article_part').select(
        'id, article_id, part_no, part_text'
    ).eq('id', part_id).execute()
    if not part.data:
        raise HTTPException(404, "Part not found")

    p = part.data[0]

    # Article 정보
    article = sb.table('law_article').select(
        'id, law_id, article_no, article_title'
    ).eq('id', p['article_id']).execute()

    law_info = None
    if article.data:
        law = sb.table('law_master').select(
            'id, law_name, law_name_short'
        ).eq('id', article.data[0]['law_id']).execute()
        law_info = law.data[0] if law.data else None

    # 관련 Candidate
    rc = sb.table('rule_candidate').select('id, status').eq('part_id', part_id).execute()
    et = sb.table('evidence_token').select(
        'id, token_type, raw_token'
    ).eq('part_id', part_id).limit(20).execute()

    return {
        'part': p,
        'article': article.data[0] if article.data else None,
        'law': law_info,
        'rule_candidates': rc.data or [],
        'evidence_tokens': et.data or [],
    }


# ============================================================
# GET /compiler/coverage-summary
# ============================================================

@router.get("/coverage-summary")
async def get_coverage_summary():
    sb = _get_sb()
    result = sb.table('residual_coverage').select('*').execute()
    if not result.data:
        return {'total_laws': 0}
    ratios = [float(r['coverage_ratio']) for r in result.data if r.get('coverage_ratio')]
    return {
        'total_laws': len(result.data),
        'avg_part_coverage': round(sum(ratios)/len(ratios), 4) if ratios else 0,
        'min_coverage': min(ratios) if ratios else 0,
        'max_coverage': max(ratios) if ratios else 0,
    }


# ============================================================
# GET /compiler/health
# ============================================================

@router.get("/health")
async def compiler_health():
    """Compiler Core 상태 확인."""
    sb = _get_sb()
    counts = {}
    for tbl in ['rule_candidate','executable_draft','facility_applicability',
                'task_candidate','schedule_candidate','penalty_candidate',
                'compliance_package','residuals']:
        try:
            r = sb.table(tbl).select('id', count='exact').execute()
            counts[tbl] = r.count or 0
        except Exception:
            counts[tbl] = -1

    return {
        'status': 'operational',
        'compiler_version': 'v3.0-deterministic',
        'philosophy': 'All outputs are Candidates. Truth requires Human Review.',
        'table_counts': counts,
    }
