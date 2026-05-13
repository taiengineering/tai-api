"""TAI Slack Dispatcher v1.0.0
모든 이벤트를 Slack 3채널로 분리 발송.

채널:
- #tai-alert   : CRITICAL/HIGH (즉시 확인)
- #tai-ops     : 운영 이벤트 (점검/제출/overdue/리뷰)
- #tai-engine  : 엔진 변경/drift/regression/publish

환경변수:
- SLACK_BOT_TOKEN       : Slack Bot OAuth Token
- SLACK_CH_ALERT        : #tai-alert 채널 ID
- SLACK_CH_OPS          : #tai-ops 채널 ID
- SLACK_CH_ENGINE       : #tai-engine 채널 ID
- SLACK_WEBHOOK_ENABLED : true/false (default: true)
"""
import os
import logging
from typing import Optional

import httpx

logger = logging.getLogger("slack_dispatcher")

# 채널 라우팅
CHANNEL_ALERT = "alert"
CHANNEL_OPS = "ops"
CHANNEL_ENGINE = "engine"

# severity → 채널 매핑
SEVERITY_CHANNEL = {
    "CRITICAL": CHANNEL_ALERT,
    "HIGH": CHANNEL_ALERT,
    "WARNING": CHANNEL_OPS,
    "INFO": CHANNEL_OPS,
}

# event_type → 채널 오버라이드 (엔진 관련은 engine 채널)
ENGINE_EVENTS = {
    "OBLIGATION_DRIFT_DETECTED", "COMPLETENESS_DRIFT_DETECTED",
    "MANDATORY_DRIFT_DETECTED", "AI_CONTAMINATION_DETECTED",
    "UNSUPPORTED_INFERENCE_DETECTED", "CHECKLIST_EXPLOSION_DETECTED",
    "EXPLAINABILITY_LOSS_DETECTED", "REGRESSION_FAILURE",
    "GRAPH_INCONSISTENCY", "DETERMINISTIC_VALIDATION_FAILED",
    "ENGINE_RELEASE_PUBLISHED", "ENGINE_RELEASE_ROLLED_BACK",
    "ENGINE_PUBLISH_BLOCKED", "LEGAL_CHANGE_DETECTED",
    "OPERATIONAL_IMPACT_SIMULATED", "HIGH_IMPACT_LAW_CHANGE",
    "ACTIVATION_DRIFT_DETECTED", "ROLLBACK_TRIGGERED",
    "RUNTIME_CONTAMINATION_DETECTED",
}

# severity → 이모지
SEVERITY_EMOJI = {
    "CRITICAL": "\ud83d\udd34",
    "HIGH": "\ud83d\udfe0",
    "WARNING": "\ud83d\udfe1",
    "INFO": "\u2705",
}


def _get_channel_id(channel_type: str) -> Optional[str]:
    """\ud658\uacbd\ubcc0\uc218\uc5d0\uc11c \ucc44\ub110 ID \uc870\ud68c"""
    mapping = {
        CHANNEL_ALERT: os.environ.get("SLACK_CH_ALERT", "").strip(),
        CHANNEL_OPS: os.environ.get("SLACK_CH_OPS", "").strip(),
        CHANNEL_ENGINE: os.environ.get("SLACK_CH_ENGINE", "").strip(),
    }
    ch = mapping.get(channel_type, "")
    if not ch:
        # fallback: 기존 SLACK_CHANNEL_ID
        ch = os.environ.get("SLACK_CHANNEL_ID", "").strip()
    return ch or None


def _resolve_channel(event_type: str, severity: str) -> str:
    """이벤트 타입+severity 기반 채널 결정"""
    if event_type in ENGINE_EVENTS:
        # 엔진 이벤트이지만 CRITICAL은 alert으로도
        if severity in ("CRITICAL", "HIGH"):
            return CHANNEL_ALERT
        return CHANNEL_ENGINE
    return SEVERITY_CHANNEL.get(severity, CHANNEL_OPS)


async def send_slack(
    event_type: str,
    severity: str,
    title: str,
    detail: str = "",
    channel_override: Optional[str] = None,
):
    """이벤트를 Slack으로 발송.

    Args:
        event_type: 이벤트 타입 (e.g. WORK_OVERDUE)
        severity: CRITICAL/HIGH/WARNING/INFO
        title: 메시지 제목
        detail: 상세 내용 (선택)
        channel_override: 채널 강제 지정 (alert/ops/engine)
    """
    enabled = os.environ.get("SLACK_WEBHOOK_ENABLED", "true").strip().lower()
    if enabled != "true":
        logger.debug(f"Slack disabled, skip: {event_type}")
        return

    token = os.environ.get("SLACK_BOT_TOKEN", "").strip()
    if not token:
        logger.warning("SLACK_BOT_TOKEN not set, skip slack dispatch")
        return

    channel_type = channel_override or _resolve_channel(event_type, severity)
    channel_id = _get_channel_id(channel_type)
    if not channel_id:
        logger.warning(f"No channel ID for {channel_type}, skip")
        return

    emoji = SEVERITY_EMOJI.get(severity, "\u2139\ufe0f")
    text = f"{emoji} *[{severity}]* {title}"
    if detail:
        text += f"\n> {detail}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://slack.com/api/chat.postMessage",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json; charset=utf-8",
                },
                json={
                    "channel": channel_id,
                    "text": text,
                    "unfurl_links": False,
                },
            )
            if resp.status_code == 200:
                body = resp.json()
                if not body.get("ok"):
                    logger.error(f"Slack API error: {body.get('error')}")
            else:
                logger.error(f"Slack HTTP {resp.status_code}")
    except Exception as e:
        logger.exception(f"Slack dispatch failed: {e}")


def send_slack_sync(
    event_type: str,
    severity: str,
    title: str,
    detail: str = "",
    channel_override: Optional[str] = None,
):
    """동기 버전 (FastAPI 라우터에서 사용)"""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # FastAPI 내부에서 호출 시
            asyncio.ensure_future(send_slack(event_type, severity, title, detail, channel_override))
        else:
            loop.run_until_complete(send_slack(event_type, severity, title, detail, channel_override))
    except RuntimeError:
        # 이벤트 루프 없을 때
        asyncio.run(send_slack(event_type, severity, title, detail, channel_override))


# === 편의 함수 ===

def alert(title: str, detail: str = ""):
    """CRITICAL alert 발송"""
    send_slack_sync("MANUAL_ALERT", "CRITICAL", title, detail, CHANNEL_ALERT)


def ops(title: str, detail: str = ""):
    """운영 이벤트 발송"""
    send_slack_sync("OPS_EVENT", "INFO", title, detail, CHANNEL_OPS)


def engine(title: str, detail: str = ""):
    """엔진 이벤트 발송"""
    send_slack_sync("ENGINE_EVENT", "INFO", title, detail, CHANNEL_ENGINE)
