"""
슬랙 인터랙티브 메시지 — 지식인 초안 검토용 [승인][수정][삭제] 버튼.
"""

from __future__ import annotations

import json
from typing import Any


def build_kin_review_blocks(
    *,
    log_id: str,
    question_title: str,
    question_link: str,
    draft_preview: str,
) -> list[dict[str, Any]]:
    """chat.postMessage 의 attachments 또는 blocks 필드용."""
    preview = (draft_preview or "").strip().replace("\n", " ")
    if len(preview) > 280:
        preview = preview[:277] + "…"

    value_payload = json.dumps(
        {"log_id": log_id},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    if len(value_payload) > 2000:
        value_payload = json.dumps({"log_id": log_id})[:2000]

    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*🔔 지식인 답변 초안 검토*\n"
                    f"*제목:* {question_title}\n"
                    f"*링크:* {question_link}\n"
                    f"*미리보기:* {preview or '—'}"
                ),
            },
        },
        {
            "type": "actions",
            "block_id": f"kin_actions_{log_id[:8]}",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "승인"},
                    "style": "primary",
                    "action_id": "kin_approve",
                    "value": value_payload,
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "수정"},
                    "action_id": "kin_edit",
                    "value": value_payload,
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "삭제"},
                    "style": "danger",
                    "action_id": "kin_delete",
                    "value": value_payload,
                },
            ],
        },
    ]
