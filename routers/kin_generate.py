"""
POST /kin/generate  — 어드민 수동 Gemini 생성 엔드포인트
POST /kin/collect   — 어드민 수동 수집 엔드포인트

어드민에서 호출하면 naver_monitor.py 의 step_collect / step_generate 를 직접 실행합니다.
"""
from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from supabase import create_client

# naver_monitor.py 루트에 있으므로 직접 import
from naver_monitor import (
    step_collect,
    step_generate,
    supabase_dashboard_link,
    slack_env_ready,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/kin", tags=["kin-manual"])


def _sb():
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    if not url or not key:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_KEY 필요")
    return create_client(url, key)


def _gemini_key() -> str:
    k = os.environ.get("GEMINI_API_KEY", "").strip()
    if not k:
        raise RuntimeError("GEMINI_API_KEY 필요")
    return k


@router.post("/generate")
async def manual_generate(limit: int = 5):
    """
    DB에서 draft_answer=NULL 인 DRAFT 건을 지정 건수만큼 Gemini 초안 생성.
    어드민 수동 실행 전용.
    limit: 처리할 최대 건수 (기본 5, 최대 20)
    """
    limit = max(1, min(limit, 20))
    try:
        sb        = _sb()
        gemini    = _gemini_key()
        dashboard = supabase_dashboard_link(os.environ.get("SUPABASE_URL", ""))

        # step_generate의 limit 파라미터는 test=True일 때만 1로 고정됨
        # 직접 pending 조회 후 limit 적용
        r = (
            sb.table("naver_kin_log")
            .select("*")
            .eq("status", "DRAFT")
            .is_("draft_answer", "null")
            .order("created_at", desc=False)
            .limit(limit)
            .execute()
        )
        pending = r.data or []

        if not pending:
            return JSONResponse({"ok": True, "message": "처리할 항목 없음", "pending": 0})

        # naver_monitor의 step_generate를 직접 호출하기 위해
        # pending 건들을 1건씩 처리 (동일 로직)
        from naver_monitor import (
            load_active_prompt,
            search_law_data,
            build_prompt,
            call_gemini,
            send_slack,
        )

        prompt_cfg = load_active_prompt(sb)
        slack_ok   = slack_env_ready()
        token      = os.environ.get("SLACK_BOT_TOKEN", "").strip()
        channel    = os.environ.get("SLACK_CHANNEL_ID", "").strip()

        stats = {"pending": len(pending), "generated": 0, "failed": 0, "slack_sent": 0}

        for row in pending:
            row_id  = row["id"]
            title   = row.get("question_title") or ""
            desc    = row.get("question_description") or ""
            keyword = row.get("search_keyword") or ""

            logger.info("[manual/generate] 처리: %s", title[:60])

            try:
                law_data = search_law_data(sb, keyword)
            except Exception as e:
                logger.warning("법령 조회 실패: %s", e)
                law_data = {"rules": [], "revisions": [], "precedents": []}

            prompt = build_prompt(title, desc, law_data, prompt_cfg)
            draft  = call_gemini(prompt, gemini)

            if not draft:
                stats["failed"] += 1
                continue

            try:
                sb.table("naver_kin_log").update({
                    "draft_answer":  draft,
                    "matched_rules": law_data,
                }).eq("id", row_id).execute()
                stats["generated"] += 1
                logger.info("[manual/generate] 완료: %s", title[:60])
            except Exception as e:
                logger.error("업데이트 실패: %s", e)
                stats["failed"] += 1
                continue

            if slack_ok:
                row["draft_answer"] = draft
                send_slack(token, channel, row, dashboard)
                stats["slack_sent"] += 1

        return JSONResponse({"ok": True, **stats})

    except Exception as e:
        logger.exception("manual generate 오류: %s", e)
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.post("/collect")
async def manual_collect():
    """
    활성 키워드 세트로 네이버 질문 수집 (5건/키워드).
    어드민 수동 실행 전용.
    """
    try:
        sb     = _sb()
        naver_id     = os.environ.get("NAVER_CLIENT_ID", "").strip()
        naver_secret = os.environ.get("NAVER_CLIENT_SECRET", "").strip()
        if not naver_id or not naver_secret:
            return JSONResponse({"ok": False, "error": "NAVER_CLIENT_ID/SECRET 미설정"}, status_code=500)

        result = step_collect(sb, naver_id, naver_secret, test=False)
        return JSONResponse({"ok": True, **result})

    except Exception as e:
        logger.exception("manual collect 오류: %s", e)
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.get("/pending-count")
async def pending_count():
    """초안 미생성 DRAFT 건수 조회."""
    try:
        sb = _sb()
        r  = (
            sb.table("naver_kin_log")
            .select("id", count="exact")
            .eq("status", "DRAFT")
            .is_("draft_answer", "null")
            .execute()
        )
        return JSONResponse({"ok": True, "count": r.count or 0})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
