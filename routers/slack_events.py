"""Slack Events API — R3 파일럿 릴레이 수신기.

WO-TAI-SLACK-BOT-UNIFIED-001-R3 (Alternative C: Slack Events Relay)

파일럿 범위:
- 비공개 릴레이 채널 1개 → 테스트 대상 채널 1개
- 텍스트 메시지, 승인된 발신자만 중계
- 모든 필수 설정 미설정 시 Fail Closed (발송 안 함)

환경변수:
- SLACK_SIGNING_SECRET       : Slack 서명 검증 (필수)
- SLACK_RELAY_APP_ID         : 허용할 Slack App api_app_id (필수, COR-05)
- SLACK_RELAY_TEAM_ID        : 허용할 Slack workspace team_id (필수, COR-05)
- SLACK_RELAY_ALLOWED_SENDER_IDS : 쉼표 구분 사용자 ID (미설정 시 Fail Closed)
- SLACK_RELAY_CHANNEL_MAP    : JSON {"relay_ch_id": "target_ch_id"} (미설정 시 Fail Closed)
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import JSONResponse

from services.slack_relay_svc import accept_relay_event, process_relay_event
from services.slack_signature_verifier import verify_slack_signing_secret

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/slack", tags=["slack-relay"])

_MAX_BODY_BYTES = 512 * 1024  # 512 KB


def _load_config() -> dict[str, Any]:
    return {
        "signing_secret": os.environ.get("SLACK_SIGNING_SECRET", "").strip(),
        "app_id": os.environ.get("SLACK_RELAY_APP_ID", "").strip(),
        "team_id": os.environ.get("SLACK_RELAY_TEAM_ID", "").strip(),
        "allowed_sender_ids": {
            s.strip()
            for s in os.environ.get("SLACK_RELAY_ALLOWED_SENDER_IDS", "").split(",")
            if s.strip()
        },
        "channel_map": _parse_channel_map(
            os.environ.get("SLACK_RELAY_CHANNEL_MAP", "")
        ),
    }


def _parse_channel_map(raw: str) -> dict[str, str]:
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("channel_map must be a dict")
        return {str(k): str(v) for k, v in parsed.items() if k and v}
    except Exception:
        logger.error("[RELAY] SLACK_RELAY_CHANNEL_MAP JSON 파싱 실패")
        return {}


@router.post("/events")
async def slack_events(request: Request, background_tasks: BackgroundTasks) -> JSONResponse:
    """Slack Events API 수신.

    서명 검증은 Fail Closed (실패 시 즉시 403).
    파일럿 설정 미비 시에도 200 ACK하되 발송하지 않음 (Fail Closed).
    """
    # 1. 본문 크기 제한
    content_length = int(request.headers.get("content-length", "0") or "0")
    if content_length > _MAX_BODY_BYTES:
        return JSONResponse({"error": "payload too large"}, status_code=400)

    raw = await request.body()
    if len(raw) > _MAX_BODY_BYTES:
        return JSONResponse({"error": "payload too large"}, status_code=400)

    # 2. 서명 검증 설정 확인 (Fail Closed)
    cfg = _load_config()
    signing_secret = cfg["signing_secret"]
    if not signing_secret:
        logger.error("[RELAY] SLACK_SIGNING_SECRET 미설정 — 500 반환")
        return JSONResponse({"error": "misconfigured"}, status_code=500)

    # 3. HMAC 서명 검증 (원본 바이트 기준, 서명 검증 전 JSON 파싱 금지)
    ts_header = request.headers.get("x-slack-request-timestamp")
    sig_header = request.headers.get("x-slack-signature")
    if not verify_slack_signing_secret(signing_secret, ts_header, sig_header, raw):
        logger.warning("[RELAY] 서명 검증 실패 — 403")
        return JSONResponse({"error": "invalid signature"}, status_code=403)

    # 4. JSON 파싱 (서명 검증 성공 후에만 실행)
    try:
        payload = json.loads(raw)
    except Exception:
        return JSONResponse({"error": "bad json"}, status_code=400)

    # 5. URL Verification (Slack App 등록 시 호출)
    if payload.get("type") == "url_verification":
        challenge = payload.get("challenge", "")
        logger.info("[RELAY] url_verification challenge 응답")
        return JSONResponse({"challenge": challenge})

    # 6. COR-05: event_callback 타입만 처리
    if payload.get("type") != "event_callback":
        return JSONResponse({"ok": True})

    # 7. COR-05: 모든 필수 설정 확인 (Fail Closed — 하나라도 누락 시 발송 차단)
    app_id_cfg = cfg["app_id"]
    team_id_cfg = cfg["team_id"]
    allowed_senders = cfg["allowed_sender_ids"]
    channel_map = cfg["channel_map"]
    if not app_id_cfg or not team_id_cfg or not allowed_senders or not channel_map:
        logger.warning("[RELAY] 필수 설정 미비(APP_ID/TEAM_ID/SENDERS/CHANNEL_MAP) — 접수 거부")
        return JSONResponse({"ok": True})

    # 8. COR-05: api_app_id 필수 하드 매칭
    if payload.get("api_app_id") != app_id_cfg:
        logger.warning("[RELAY] api_app_id 불일치 — ACK but discard (got=%s)", payload.get("api_app_id"))
        return JSONResponse({"ok": True})

    # 9. COR-05: team_id 필수 하드 매칭
    if payload.get("team_id") != team_id_cfg:
        logger.warning("[RELAY] team_id 불일치 — ACK but discard (got=%s)", payload.get("team_id"))
        return JSONResponse({"ok": True})

    # 10. 이벤트 타입 검증 (message, subtype 없음만 처리)
    event = payload.get("event") or {}
    if event.get("type") != "message" or event.get("subtype"):
        return JSONResponse({"ok": True})

    # 11. COR-05: bot_id 존재 시 무시 (봇 메시지 릴레이 차단)
    if event.get("bot_id"):
        logger.debug("[RELAY] bot_id 존재 — 봇 메시지 무시")
        return JSONResponse({"ok": True})

    # 12. 발신자 검증
    sender_id = event.get("user", "")
    if not sender_id or sender_id not in allowed_senders:
        logger.debug("[RELAY] 미승인 발신자 '%s' — 무시", sender_id)
        return JSONResponse({"ok": True})

    # 13. 릴레이 채널 검증 (서버 allowlist에서만 대상 채널 결정)
    relay_channel = event.get("channel", "")
    target_channel = channel_map.get(relay_channel)
    if not target_channel:
        logger.debug("[RELAY] 미등록 릴레이 채널 '%s' — 무시", relay_channel)
        return JSONResponse({"ok": True})

    # 14. 텍스트 메시지 추출 (빈 메시지 무시, 길이 제한)
    message_text = (event.get("text") or "").strip()
    if not message_text:
        return JSONResponse({"ok": True})
    message_text = message_text[:4000]

    # 15. COR-05: event_id 필수 (UUID 대체 금지)
    event_id = payload.get("event_id", "").strip()
    if not event_id:
        logger.warning("[RELAY] event_id 누락 — 접수 거부")
        return JSONResponse({"ok": True})
    source_ts = event.get("ts")

    # 16. DB 원자적 삽입 (ON CONFLICT event_id DO NOTHING)
    try:
        accepted = accept_relay_event(
            event_id=event_id,
            relay_channel=relay_channel,
            target_channel=target_channel,
            message_text=message_text,
            sender_id=sender_id,
            source_message_ts=source_ts,
        )
    except Exception:
        logger.exception("[RELAY] DB 이벤트 접수 실패 event_id=%s", event_id)
        return JSONResponse({"error": "db error"}, status_code=503)

    # 17. 신규 접수된 경우만 BackgroundTask로 즉시 전송 시도
    if accepted:
        background_tasks.add_task(process_relay_event, event_id)

    # Slack에 3초 이내 200 응답 (발송은 백그라운드)
    return JSONResponse({"ok": True})
