"""
Inbox Slack 알림 빌더 + 발송

Doc: docs/inbox-system/PHASE3_NOTIFY_ENDPOINT.md
"""
import json
import logging
import os
from typing import Any, Dict, List

import httpx

logger = logging.getLogger(__name__)

SLACK_API = "https://slack.com/api/chat.postMessage"
ADMIN_BASE_URL = (
    "https://admin.taieng.co.kr/html/horizontal-menu-template/inquiry-list.html"
)

# 소스 라벨
SOURCE_LABEL = {
    "direct": "어드민 직접 입력",
    "marketing": "마케팅 사이트",
    "safe": "SaaS (safe.taieng.co.kr)",
}

# 카테고리 라벨
CATEGORY_LABEL = {
    # INQUIRY
    "consult": "법적진단 컨설팅",
    "safety": "안전관리자 선임대행",
    "electric": "전기설비 점검",
    "risk": "위험성평가",
    "csia": "중대재해처벌법",
    "saas": "SaaS 서비스",
    "repair": "수선중개",
    "edu": "안전보건교육",
    "partner": "파트너/협력 제안",
    "other": "기타",
    # FEEDBACK
    "fb_feature": "기능 제안",
    "fb_bug": "버그/오류",
    "fb_ux": "사용성 불편",
    "fb_idea": "아이디어",
    "fb_praise": "응원·칭찬",
}


def build_blocks(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    """inquiries row → Slack Block Kit"""
    is_feedback = record.get("inquiry_type") == "FEEDBACK"
    emoji = "💬" if is_feedback else "📨"
    type_label = "TAI에 바란다" if is_feedback else "도입 문의"

    source_lbl = SOURCE_LABEL.get(record.get("source", ""), record.get("source", "-"))
    category_lbl = CATEGORY_LABEL.get(
        record.get("category", ""), record.get("category", "-")
    )

    body = (record.get("content") or "").strip()
    if len(body) > 600:
        body = body[:600] + "…"
    body_quoted = "\n".join(">" + line for line in body.split("\n"))

    name = record.get("name") or "익명"
    email = record.get("email") or "-"
    phone = record.get("phone") or "-"
    contact_line = f"보낸이: *{name}* · {email} · {phone}"

    return [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"{emoji} {type_label}"},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*인입경로*\n{source_lbl}"},
                {"type": "mrkdwn", "text": f"*분류*\n{category_lbl}"},
            ],
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": body_quoted or "_(내용 없음)_"},
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": contact_line}],
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "어드민에서 보기"},
                    "url": ADMIN_BASE_URL,
                }
            ],
        },
    ]


async def send_inbox_notification(record: Dict[str, Any]) -> bool:
    """슬랙 알림 발송. 실패 시 로그만 남기고 False 반환."""
    token = os.environ.get("SLACK_BOT_TOKEN")
    channel = os.environ.get("SLACK_CHANNEL_ID_INBOX")

    if not token or not channel:
        logger.warning(
            "[inbox_notify] missing slack env vars (token=%s, channel=%s)",
            bool(token),
            bool(channel),
        )
        return False

    blocks = build_blocks(record)
    payload = {
        "channel": channel,
        "blocks": blocks,
        "text": "새 인박스 메시지",  # fallback
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                SLACK_API,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json; charset=utf-8",
                },
                json=payload,
            )
        data = resp.json()
        if not data.get("ok"):
            logger.warning(
                "[inbox_notify] slack error: %s — %s",
                data.get("error"),
                json.dumps(data)[:500],
            )
            return False
        return True
    except Exception as e:
        logger.warning("[inbox_notify] exception: %s", e)
        return False
