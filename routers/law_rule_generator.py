"""
AI 법령 룰 생성기 — law_rule_generator.py (라우터)
===================================================
엔드포인트 정의만 담당. 비즈니스 로직은 services/rule_gen_*.py 에 위임.

v1.7.0 (2026-04-21):
  [REFACTOR] 라우터 슬림화 (45KB→12KB). 서비스 레이어로 로직 위임.

v1.6.0 (2026-04-20):
  [FIX] POST /reparse-master — BackgroundTasks 비동기 전환 (서버 타임아웃 방지)
  [ADD] GET /reparse-master/status/{job_id}, GET /reparse-master/jobs

v1.5.0 (2026-04-05):
  [ADD] GET /drafts — has_condition 파라미터 추가
"""
import logging
import os

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from typing import Dict, List, Optional

from db.supabase_client import get_supabase
from schemas.rule_gen import (
    AutoParseAndApproveRequest,
    ParseArticleRequest,
    ParseBatchRequest,
    ReparseMasterRequest,
    ReviewDraftRequest,
    UpdateDraftRequest,
    ValidateMasterRequest,
)
from services.law_context_builder import build_full_context
from services.rule_gen_builders import _build_master_payload
from services.rule_gen_helpers import _extract_json_payload
from services.rule_gen_reparse import get_reparse_jobs, get_reparse_status, run_reparse_master
from services.rule_gen_svc import (
    _auto_approve_to_master,
    run_auto_parse_and_approve,
    run_bulk_approve_unregistered,
    run_parse_article,
    run_parse_batch,
    run_validate_master,
)

router = APIRouter(prefix="/law-rule-generator", tags=["AI룰생성"])

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-haiku-4-5-20251001"
CLAUDE_SONNET_MODEL = "claude-sonnet-4-20250514"
INTERNAL_SECRET = os.environ.get("INTERNAL_API_SECRET", "tai-internal-2026")

EXCLUDED_SECTORS = {
    "SPECIAL_FACILITY", "SPECIAL", "CONSTRUCTION_SPECIAL",
    "MANUFACTURING_SPECIAL", "CONSTRUCTION_MANUFACTURING_SPECIAL",
}

SUBMIT_ORG_LABELS = {
    "kosha": "한국산업안전보건공단 (관할 지역본부)",
    "local_gov": "관할 시·군·구청",
    "moel": "관할 지방고용노동관서",
    "me": "관할 지방환경관서",
    "kgs": "한국가스안전공사 (관할 지사)",
    "mlit": "관할 지방국토관리청",
    "nfa": "관할 소방서",
    "kesco": "한국전기안전공사 (관할 지사)",
}

# rule_gen_ai.py 에 있는 프롬프트/상수를 서비스에 전달하기 위한 re-export
from services.rule_gen_ai import call_claude  # noqa: E402 — 서비스 내부 호출용

_reparse_logger = logging.getLogger("reparse-master")

# ── 서비스 호출에 필요한 공통 kwargs ───────────────────────

# SYSTEM_PROMPT, USER_PROMPT_TEMPLATE, FEW_SHOT_RULE 은 라우터에서 보관하되
# 실제 로직은 서비스에 위임. 프롬프트 원문은 services/rule_gen_ai.py 참조.
# 아래 import는 라우터에서 서비스 함수로 전달하는 용도.
from routers._rule_gen_prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE, FEW_SHOT_RULE  # noqa: E402


def _svc_kwargs():
    """서비스 함수 공통 의존성 주입 kwargs."""
    return {
        "build_full_context_fn": build_full_context,
        "excluded_sectors": EXCLUDED_SECTORS,
        "user_prompt_template": USER_PROMPT_TEMPLATE,
        "few_shot_rule": FEW_SHOT_RULE,
        "system_prompt": SYSTEM_PROMPT,
        "claude_model": CLAUDE_MODEL,
        "extract_json_payload_fn": _extract_json_payload,
        "api_key": ANTHROPIC_API_KEY,
    }


# ── GET /laws ─────────────────────────────────────────────

@router.get("/laws")
async def get_laws(
    search: str = Query(""),
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
):
    supabase = get_supabase()
    q = supabase.table("law_master").select(
        "id, law_name, law_type_code, ministry_name, is_active", count="exact"
    ).eq("is_active", True)
    if search:
        q = q.ilike("law_name", f"%{search}%")
    offset = (page - 1) * page_size
    res = q.range(offset, offset + page_size - 1).order("law_name").execute()

    article_counts: Dict[str, int] = {}
    parsed_counts: Dict[str, int] = {}
    for r in (res.data or []):
        try:
            ver = supabase.table("law_version").select("id").eq("law_id", r["id"]).eq("is_current", True).limit(1).execute()
            if ver.data:
                vid = ver.data[0]["id"]
                ac = supabase.table("law_article").select("id", count="exact").eq("law_version_id", vid).execute()
                pc = supabase.table("law_article").select("id", count="exact").eq("law_version_id", vid).not_.is_("ai_parsed_at", "null").execute()
                article_counts[r["id"]] = ac.count or 0
                parsed_counts[r["id"]] = pc.count or 0
        except Exception:
            article_counts[r["id"]] = 0
            parsed_counts[r["id"]] = 0

    return {"status": "success", "data": {
        "items": [{**r, "article_count": article_counts.get(r["id"], 0), "parsed_count": parsed_counts.get(r["id"], 0)} for r in (res.data or [])],
        "total": res.count or 0, "page": page, "page_size": page_size,
    }}


# ── GET /laws/{law_id}/articles ───────────────────────────

@router.get("/laws/{law_id}/articles")
async def get_articles(law_id: str):
    supabase = get_supabase()
    ver = supabase.table("law_version").select("id").eq("law_id", law_id).eq("is_current", True).limit(1).execute()
    if not ver.data:
        raise HTTPException(status_code=404, detail="현재 버전 없음")
    arts = supabase.table("law_article").select(
        "id, article_no, article_sub_no, article_title, article_text, ai_parsed_at"
    ).eq("law_version_id", ver.data[0]["id"]).order("article_no_sort").execute()
    articles = []
    for a in (arts.data or []):
        dr = supabase.table("law_rule_drafts").select("id, status").eq("article_id", a["id"]).execute()
        di = dr.data or []
        a["draft_count"] = len(di)
        a["has_approved"] = any(d["status"] == "APPROVED" for d in di)
        a["has_pending"] = any(d["status"] == "PENDING" for d in di)
        a["needs_review"] = any(d["status"] == "NEEDS_REVIEW" for d in di)
        a["is_parsed"] = a.get("ai_parsed_at") is not None
        articles.append(a)
    return {"status": "success", "data": articles}


# ── POST /parse ───────────────────────────────────────────

@router.post("/parse")
async def parse_article(body: ParseArticleRequest):
    supabase = get_supabase()
    try:
        return await run_parse_article(supabase, body, **_svc_kwargs())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))


# ── POST /parse-batch ────────────────────────────────────

@router.post("/parse-batch")
async def parse_batch(body: ParseBatchRequest):
    supabase = get_supabase()
    try:
        return await run_parse_batch(supabase, body, **_svc_kwargs())
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── POST /auto-parse-and-approve ─────────────────────────

@router.post("/auto-parse-and-approve")
async def auto_parse_and_approve(body: AutoParseAndApproveRequest):
    supabase = get_supabase()
    try:
        return await run_auto_parse_and_approve(supabase, body, INTERNAL_SECRET, **_svc_kwargs())
    except PermissionError:
        raise HTTPException(status_code=403, detail="내부 전용 엔드포인트")
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── POST /bulk-approve-unregistered ──────────────────────

@router.post("/bulk-approve-unregistered")
async def bulk_approve_unregistered(
    secret: str = Query(...),
    limit: int = Query(default=200, le=500),
):
    supabase = get_supabase()
    try:
        return run_bulk_approve_unregistered(supabase, secret, INTERNAL_SECRET, limit, EXCLUDED_SECTORS)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Forbidden")


# ── POST /validate-master ────────────────────────────────

@router.post("/validate-master")
async def validate_master(body: Optional[ValidateMasterRequest] = None):
    body = body or ValidateMasterRequest()
    sector = (body.sector or "ALL").strip().upper()
    supabase = get_supabase()
    return run_validate_master(supabase, sector, SUBMIT_ORG_LABELS)


# ── POST /reparse-master ─────────────────────────────────

@router.post("/reparse-master")
async def reparse_master(body: ReparseMasterRequest, background_tasks: BackgroundTasks):
    supabase = get_supabase()
    try:
        return run_reparse_master(
            supabase, body, background_tasks,
            get_supabase_fn=get_supabase,
            build_full_context_fn=build_full_context,
            validate_master_runner=run_validate_master,
            submit_org_labels=SUBMIT_ORG_LABELS,
            sonnet_model=CLAUDE_SONNET_MODEL,
            api_key=ANTHROPIC_API_KEY,
            extract_json_payload_fn=_extract_json_payload,
            logger=_reparse_logger,
            internal_secret=INTERNAL_SECRET,
        )
    except PermissionError:
        raise HTTPException(status_code=403, detail="내부 전용 엔드포인트")


@router.get("/reparse-master/status/{job_id}")
async def reparse_master_status(job_id: str):
    supabase = get_supabase()
    try:
        return get_reparse_status(supabase, job_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/reparse-master/jobs")
async def reparse_master_jobs(limit: int = Query(default=10, le=50)):
    supabase = get_supabase()
    return get_reparse_jobs(supabase, limit)


# ── GET /stats ────────────────────────────────────────────

@router.get("/stats")
async def get_stats():
    supabase = get_supabase()
    res = supabase.table("law_rule_drafts").select("status, sector, obligation_type, ai_confidence").execute()
    rows = res.data or []

    status_cnt: Dict[str, int] = {}
    sector_cnt: Dict[str, int] = {}
    obtype_cnt: Dict[str, int] = {}
    conf_sum, conf_cnt = 0, 0
    for r in rows:
        s = r.get("status") or "PENDING"
        sc = r.get("sector") or "UNKNOWN"
        ot = r.get("obligation_type") or "UNKNOWN"
        if sc.upper() not in EXCLUDED_SECTORS:
            status_cnt[s] = status_cnt.get(s, 0) + 1
            sector_cnt[sc] = sector_cnt.get(sc, 0) + 1
            obtype_cnt[ot] = obtype_cnt.get(ot, 0) + 1
            if r.get("ai_confidence") is not None:
                conf_sum += r["ai_confidence"]
                conf_cnt += 1
    master_res = supabase.table("master_building_legal_rules").select("source_api", count="exact").eq("source_api", "AI_GENERATED").execute()
    return {"status": "success", "data": {
        "model": CLAUDE_MODEL,
        "total_drafts": len(rows),
        "status_breakdown": status_cnt,
        "sector_breakdown": sector_cnt,
        "obtype_breakdown": obtype_cnt,
        "avg_confidence": round(conf_sum / conf_cnt, 1) if conf_cnt else 0,
        "approved_in_master": master_res.count or 0,
        "needs_review": status_cnt.get("NEEDS_REVIEW", 0),
    }}


# ── GET /drafts ───────────────────────────────────────────

@router.get("/drafts")
async def get_drafts(
    status: str = Query(""),
    sector: str = Query(""),
    ob_type: str = Query(""),
    law_name: str = Query(""),
    confidence_min: int = Query(0),
    has_condition: str = Query("", description="true | false | '' (전체)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    supabase = get_supabase()
    q = supabase.table("law_rule_drafts").select("*", count="exact")
    if status:
        q = q.eq("status", status)
    if sector:
        q = q.eq("sector", sector)
    if ob_type:
        q = q.eq("obligation_type", ob_type)
    if law_name:
        q = q.ilike("law_name", f"%{law_name}%")
    if confidence_min:
        q = q.gte("ai_confidence", confidence_min)
    if has_condition == "false":
        q = q.is_("condition_code", "null")
    elif has_condition == "true":
        q = q.not_.is_("condition_code", "null")
    q = q.not_.in_("sector", list(EXCLUDED_SECTORS))
    offset = (page - 1) * page_size
    res = q.order("created_at", desc=True).range(offset, offset + page_size - 1).execute()
    return {"status": "success", "data": {
        "items": res.data or [], "total": res.count or 0,
        "page": page, "page_size": page_size,
    }}


@router.get("/drafts/{draft_id}")
async def get_draft(draft_id: str):
    supabase = get_supabase()
    res = supabase.table("law_rule_drafts").select("*").eq("id", draft_id).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="초안 없음")
    return {"status": "success", "data": res.data}


@router.patch("/drafts/{draft_id}")
async def update_draft(draft_id: str, body: UpdateDraftRequest):
    supabase = get_supabase()
    from datetime import datetime, timezone
    data = body.model_dump(exclude_none=True)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    data["status"] = "MODIFIED"
    res = supabase.table("law_rule_drafts").update(data).eq("id", draft_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="초안 없음")
    return {"status": "success", "data": res.data[0]}


@router.post("/drafts/{draft_id}/approve")
async def approve_draft(draft_id: str, body: Optional[ReviewDraftRequest] = None):
    supabase = get_supabase()
    body = body or ReviewDraftRequest()
    from datetime import datetime, timezone

    dr = supabase.table("law_rule_drafts").select("*").eq("id", draft_id).single().execute()
    if not dr.data:
        raise HTTPException(status_code=404, detail="초안 없음")
    d = dr.data

    if (d.get("sector") or "").upper() in EXCLUDED_SECTORS:
        raise HTTPException(status_code=400, detail="특수시설 섹터는 현재 master 등록 불가")

    rule_id = body.rule_id or d.get("draft_rule_id") or f"AI-{draft_id[:8].upper()}"
    if supabase.table("master_building_legal_rules").select("rule_id").eq("rule_id", rule_id).execute().data:
        rule_id = rule_id + "-V2"

    ins = supabase.table("master_building_legal_rules").insert(_build_master_payload(d, rule_id)).execute()
    if not ins.data:
        raise HTTPException(status_code=500, detail="master 등록 실패")

    supabase.table("law_rule_drafts").update({
        "status": "APPROVED", "registered_rule_id": rule_id,
        "reviewer_note": body.reviewer_note,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", draft_id).execute()

    return {"status": "success", "rule_id": rule_id,
            "message": f"master에 {rule_id}로 등록됐습니다.", "data": ins.data[0]}


@router.post("/drafts/{draft_id}/reject")
async def reject_draft(draft_id: str, body: Optional[ReviewDraftRequest] = None):
    supabase = get_supabase()
    body = body or ReviewDraftRequest()
    from datetime import datetime, timezone
    res = supabase.table("law_rule_drafts").update({
        "status": "REJECTED",
        "reviewer_note": body.reviewer_note,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", draft_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="초안 없음")
    return {"status": "success", "message": "거부 처리 완료"}
