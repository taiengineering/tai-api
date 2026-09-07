"""TAI Slack Dispatcher v1.1.0
모든 이벤트를 Slack 채널로 분리 발송. WO-SLACK-EVENT-HUB-001 로 event_type 라우팅과
Block Kit 인자를 추가. 기존 severity 기반 라우팅은 회귀 없이 유지.

채널:
- #tai-alert     : CRITICAL/HIGH (즉시 확인)
- #tai-ops       : 운영 이벤트 (점검/제출/overdue/리뷰)
- #tai-engine    : 엔진 변경/drift/regression/publish
- INQUIRY        : 문의/피드백 인박스 (INQUIRY_CREATED · TAI_WISH_CREATED)
- APPROVAL       : 결재/견적요청 (APPROVAL_CREATED · QUOTE_MANUAL_REQUESTED)
- FREE_DIAGNOSIS : 익명 무료진단 완료 (FREE_DIAGNOSIS_COMPLETED)

환경변수:
- SLACK_BOT_TOKEN1        : Slack Bot OAuth Token (우선)
- SLACK_BOT_TOKEN         : Slack Bot OAuth Token (폴백)
- SLACK_CH_ALERT          : #tai-alert 채널 ID
- SLACK_CH_OPS            : #tai-ops 채널 ID
- SLACK_CH_ENGINE         : #tai-engine 채널 ID
- SLACK_CH_APPROVAL       : APPROVAL 채널 ID
- SLACK_CH_INQUIRY        : INQUIRY 채널 ID (fallback: SLACK_CHANNEL_ID_INBOX)
- SLACK_CH_FREE_DIAGNOSIS : FREE_DIAGNOSIS 채널 ID
- SLACK_WEBHOOK_ENABLED   : true/false (default: true)
"""
import os
import logging
from typing import List, Optional

import httpx

logger = logging.getLogger("slack_dispatcher")

# 채널 라우팅
CHANNEL_ALERT = "alert"
CHANNEL_OPS = "ops"
CHANNEL_ENGINE = "engine"
CHANNEL_INQUIRY = "inquiry"
CHANNEL_APPROVAL = "approval"
CHANNEL_FREE_DIAGNOSIS = "free_diagnosis"

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

# WO-SLACK-EVENT-HUB-001: event_type → 채널 매핑 (severity 무관, 최우선).
EVENT_TYPE_CHANNEL = {
    "INQUIRY_CREATED":         CHANNEL_INQUIRY,
    "TAI_WISH_CREATED":        CHANNEL_INQUIRY,
    "APPROVAL_CREATED":        CHANNEL_APPROVAL,
    "QUOTE_MANUAL_REQUESTED":  CHANNEL_APPROVAL,
    "FREE_DIAGNOSIS_COMPLETED": CHANNEL_FREE_DIAGNOSIS,
}

# severity → 이모지
SEVERITY_EMOJI = {
    "CRITICAL": "🔴",
    "HIGH": "🟠",
    "WARNING": "🟡",
    "INFO": "✅",
}


def _get_channel_id(channel_type: str) -> Optional[str]:
    """환경변수에서 채널 ID 조회. INQUIRY 만 SLACK_CHANNEL_ID_INBOX backward-fallback 허용.
    나머지(APPROVAL/FREE_DIAGNOSIS)는 env 부재 시 발송 skip → send_slack 이 warning 로그 남김."""
    mapping = {
        CHANNEL_ALERT:          os.environ.get("SLACK_CH_ALERT", "").strip(),
        CHANNEL_OPS:            os.environ.get("SLACK_CH_OPS", "").strip(),
        CHANNEL_ENGINE:         os.environ.get("SLACK_CH_ENGINE", "").strip(),
        CHANNEL_APPROVAL:       os.environ.get("SLACK_CH_APPROVAL", "").strip(),
        CHANNEL_INQUIRY:        os.environ.get("SLACK_CH_INQUIRY", "").strip(),
        CHANNEL_FREE_DIAGNOSIS: os.environ.get("SLACK_CH_FREE_DIAGNOSIS", "").strip(),
    }
    ch = mapping.get(channel_type, "")
    if ch:
        return ch
    # INQUIRY 는 SLACK_CHANNEL_ID_INBOX 로 backward-compatible fallback.
    if channel_type == CHANNEL_INQUIRY:
        ch = os.environ.get("SLACK_CHANNEL_ID_INBOX", "").strip()
        if ch:
            return ch
    # 기존 3채널(alert/ops/engine) 의 legacy fallback: SLACK_CHANNEL_ID
    if channel_type in (CHANNEL_ALERT, CHANNEL_OPS, CHANNEL_ENGINE):
        ch = os.environ.get("SLACK_CHANNEL_ID", "").strip()
        if ch:
            return ch
    return None


def _resolve_channel(event_type: str, severity: str) -> str:
    """이벤트 타입+severity 기반 채널 결정.
    우선순위: EVENT_TYPE_CHANNEL(신규 5종) > ENGINE_EVENTS(기존) > SEVERITY_CHANNEL(기존)."""
    if event_type in EVENT_TYPE_CHANNEL:
        return EVENT_TYPE_CHANNEL[event_type]
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
    blocks: Optional[List[dict]] = None,
):
    """이벤트를 Slack으로 발송.

    Args:
        event_type: 이벤트 타입 (e.g. WORK_OVERDUE, INQUIRY_CREATED)
        severity: CRITICAL/HIGH/WARNING/INFO
        title: 메시지 제목 (blocks 미지정 시 text 로 렌더 · 지정 시 fallback text)
        detail: 상세 내용 (선택, blocks 미지정 시에만 text 에 붙음)
        channel_override: 채널 강제 지정 (alert/ops/engine/inquiry/approval/free_diagnosis)
        blocks: Slack Block Kit blocks. 지정 시 payload.blocks 사용 · title 은 fallback text.
    """
    enabled = os.environ.get("SLACK_WEBHOOK_ENABLED", "true").strip().lower()
    if enabled != "true":
        logger.debug(f"Slack disabled, skip: {event_type}")
        return

    token = (os.environ.get("SLACK_BOT_TOKEN1", "") or os.environ.get("SLACK_BOT_TOKEN", "")).strip()
    if not token:
        logger.warning("SLACK_BOT_TOKEN1/SLACK_BOT_TOKEN not set, skip slack dispatch")
        return

    channel_type = channel_override or _resolve_channel(event_type, severity)
    channel_id = _get_channel_id(channel_type)
    if not channel_id:
        logger.warning(f"No channel ID for {channel_type} (event={event_type}), skip")
        return

    emoji = SEVERITY_EMOJI.get(severity, "ℹ️")
    text = f"{emoji} *[{severity}]* {title}"
    if detail and not blocks:
        text += f"\n> {detail}"

    payload = {"channel": channel_id, "text": text, "unfurl_links": False}
    if blocks:
        payload["blocks"] = blocks

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://slack.com/api/chat.postMessage",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json; charset=utf-8",
                },
                json=payload,
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
    blocks: Optional[List[dict]] = None,
):
    """동기 버전 (FastAPI 라우터에서 사용). 이벤트루프가 러닝 중이면 fire-and-forget.
    전송 완료를 반드시 기다려야 하는 호출부(예: /internal/inbox/notify)는 send_slack 을 await 하라."""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # FastAPI 내부에서 호출 시
            asyncio.ensure_future(send_slack(event_type, severity, title, detail, channel_override, blocks))
        else:
            loop.run_until_complete(send_slack(event_type, severity, title, detail, channel_override, blocks))
    except RuntimeError:
        # 이벤트 루프 없을 때
        asyncio.run(send_slack(event_type, severity, title, detail, channel_override, blocks))


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
