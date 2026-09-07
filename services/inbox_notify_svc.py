"""
Inbox 알림 빌더 (formatter-only).

Doc: docs/inbox-system/PHASE3_NOTIFY_ENDPOINT.md
WO-SLACK-EVENT-HUB-001 PR-①: 이 모듈은 inquiries row → Block Kit 변환만 담당하며,
실제 발송은 services.slack_dispatcher 경유로 라우터가 수행한다. 이 파일에는
외부 API URL / 봇 토큰 env / 채널 env 를 직접 참조하는 코드가 없어야 한다.
"""
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

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


def resolve_event_type(record: Dict[str, Any]) -> str:
    """inquiries row → WO 이벤트명. inquiry_type 기준(category/source 로 추론 금지).

    - inquiry_type == 'FEEDBACK' → TAI_WISH_CREATED
    - else                        → INQUIRY_CREATED
    """
    return "TAI_WISH_CREATED" if record.get("inquiry_type") == "FEEDBACK" else "INQUIRY_CREATED"


def fallback_title(record: Dict[str, Any]) -> str:
    """Slack blocks 미표시 클라이언트/알림용 fallback text."""
    is_fb = record.get("inquiry_type") == "FEEDBACK"
    label = "TAI에 바란다" if is_fb else "도입 문의"
    who = record.get("name") or "익명"
    return f"{label} · {who}"
