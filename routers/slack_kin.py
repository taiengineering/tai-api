"""
Slack × 네이버 지식인 반자동: 인터랙티브 버튼 → Playwright 초안 입력.

- Slack Interactions URL 로 이 라우트를 등록: POST /slack/kin/interactions
  (동일 핸들러) POST /slack/kin/approve
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any
from urllib.parse import parse_qs

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from supabase import create_client

from services.kin_draft_safety import validate_draft_for_playwright
from services.slack_signature_verifier import verify_slack_signing_secret

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/slack/kin", tags=["slack-kin"])


def _json_response(data: dict[str, Any]) -> JSONResponse:
    return JSONResponse(content=data)


async def _notify_slack_done(response_url: str | None, *, ok: bool, detail: str = "") -> None:
    """완료 안내 (response_url 또는 chat.postMessage)."""
    text_ok = (
        "답변 입력이 완료되었습니다. 네이버 창에서 최종 등록을 진행해 주세요."
    )
    text_fail = f"답변 입력 중 오류가 발생했습니다. {detail}" if detail else text_ok
    payload = {
        "response_type": "ephemeral",
        "text": text_ok if ok else text_fail,
        "replace_original": False,
    }
    if response_url:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                await client.post(response_url, json=payload)
            return
        except Exception as e:
            logger.exception("response_url 전송 실패: %s", e)

    token = os.environ.get("SLACK_BOT_TOKEN", "").strip()
    channel = os.environ.get("SLACK_CHANNEL_ID", "").strip()
    if not token or not channel:
        logger.warning("SLACK_BOT_TOKEN/SLACK_CHANNEL_ID 없음 — 완료 알림 스킵")
        return
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            await client.post(
                "https://slack.com/api/chat.postMessage",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json; charset=utf-8",
                },
                json={
                    "channel": channel,
                    "text": payload["text"],
                },
            )
    except Exception as e:
        logger.exception("chat.postMessage 실패: %s", e)


def _supabase():
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY 필요")
    return create_client(url, key)


def _fetch_log(log_id: str) -> dict[str, Any] | None:
    sb = _supabase()
    r = (
        sb.table("naver_kin_log")
        .select("id, question_link, draft_answer, status")
        .eq("id", log_id)
        .limit(1)
        .execute()
    )
    rows = r.data or []
    return rows[0] if rows else None


async def _run_approve_pipeline(log_id: str, response_url: str | None) -> None:
    try:
        row = _fetch_log(log_id)
        if not row:
            await _notify_slack_done(response_url, ok=False, detail="DB에서 로그를 찾을 수 없습니다.")
            return
        link = (row.get("question_link") or "").strip()
        draft = row.get("draft_answer") or ""
        if not link or not draft:
            await _notify_slack_done(
                response_url,
                ok=False,
                detail="question_link 또는 draft_answer 가 비어 있습니다.",
            )
            return

        final_text, warnings = validate_draft_for_playwright(draft)
        if warnings:
            logger.info("Draft warnings: %s", warnings)

        # Playwright는 승인 시에만 로드 (API 기동 메모리·임포트 분리)
        from services.kin_playwright_runner import fill_kin_answer_editor

        await fill_kin_answer_editor(link, final_text)
        await _notify_slack_done(response_url, ok=True)
    except Exception as e:
        logger.exception("승인 파이프라인 실패: %s", e)
        await _notify_slack_done(response_url, ok=False, detail=str(e)[:400])


async def _handle_payload(payload: dict[str, Any]) -> JSONResponse:
    """버튼 action 처리."""
    actions = payload.get("actions") or []
    if not actions:
        return _json_response({"text": "알 수 없는 요청입니다.", "response_type": "ephemeral"})

    act = actions[0]
    action_id = act.get("action_id") or ""
    raw_val = act.get("value") or "{}"

    try:
        meta = json.loads(raw_val)
    except json.JSONDecodeError:
        meta = {}

    log_id = str(meta.get("log_id") or "").strip()
    if not log_id:
        return _json_response(
            {"text": "log_id가 없습니다.", "response_type": "ephemeral"}
        )

    response_url = payload.get("response_url")

    if action_id == "kin_approve":
        # 즉시 ACK — Slack 3초 제한. Playwright는 백그라운드 태스크(전용 워커·표시 장비 권장).
        asyncio.create_task(_run_approve_pipeline(log_id, response_url))
        return _json_response(
            {
                "response_type": "ephemeral",
                "text": "답변 입력을 시작했습니다. 완료되면 알림을 보냅니다.",
                "replace_original": False,
            }
        )

    if action_id == "kin_edit":
        return _json_response(
            {
                "response_type": "ephemeral",
                "text": (
                    "수정: Supabase `naver_kin_log` 의 `draft_answer` 를 수정한 뒤 "
                    "다시 알림을 보내거나 관리 콘솔에서 처리해 주세요."
                ),
            }
        )

    if action_id == "kin_delete":
        try:
            sb = _supabase()
            sb.table("naver_kin_log").update({"status": "SKIP"}).eq("id", log_id).execute()
        except Exception as e:
            logger.exception(e)
            return _json_response(
                {
                    "response_type": "ephemeral",
                    "text": f"삭제(SKIP) 처리 실패: {e}"[:2000],
                }
            )
        return _json_response(
            {
                "response_type": "ephemeral",
                "text": "해당 건을 SKIP 으로 표시했습니다.",
            }
        )

    return _json_response({"text": "지원하지 않는 액션입니다.", "response_type": "ephemeral"})


async def _slack_interactions_handler(request: Request) -> JSONResponse:
    raw = await request.body()
    signing_secret = os.environ.get("SLACK_SIGNING_SECRET", "").strip()
    if not signing_secret:
        logger.error("SLACK_SIGNING_SECRET 미설정")
        return JSONResponse({"error": "misconfigured"}, status_code=500)

    ts = request.headers.get("x-slack-request-timestamp")
    sig = request.headers.get("x-slack-signature")
    if not verify_slack_signing_secret(signing_secret, ts, sig, raw):
        return JSONResponse({"error": "invalid signature"}, status_code=403)

    form = parse_qs(raw.decode("utf-8"))
    payload_list = form.get("payload") or []
    if not payload_list:
        return JSONResponse({"error": "missing payload"}, status_code=400)
    try:
        payload = json.loads(payload_list[0])
    except json.JSONDecodeError:
        return JSONResponse({"error": "bad payload"}, status_code=400)

    return await _handle_payload(payload)


@router.post("/interactions")
async def slack_interactions(request: Request) -> JSONResponse:
    """Slack Interactions 엔드포인트 (승인/수정/삭제 버튼)."""
    return await _slack_interactions_handler(request)


@router.post("/approve")
async def slack_approve_alias(request: Request) -> JSONResponse:
    """
    [승인] 버튼이 호출하는 URL 로 동일하게 설정 가능한 별칭.
    Slack 대시보드의 Interactions Request URL 에 `/slack/kin/interactions` 또는 본 경로를 지정.
    """
    return await _slack_interactions_handler(request)


@router.get("/health")
def slack_kin_health() -> PlainTextResponse:
    return PlainTextResponse("ok", status_code=200)
