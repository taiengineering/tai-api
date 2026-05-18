"""Summary Builder — 다건 이벤트 상황 요약."""

from __future__ import annotations

from typing import Any

from .event_translator import translate_event


def build_summary(
    events: list[dict[str, Any]],
    audience: str = "operator",
) -> dict[str, Any]:
    """여러 이벤트를 상황 요약으로 변환.

    Returns:
        {
            "total": int,
            "urgency_counts": {"즉시 확인 필요": n, "주의 필요": n, "참고": n},
            "messages": [HumanMessage dict, ...],
            "overall_urgency": str,
            "overall_summary": str,
        }
    """
    if not events:
        return {
            "total": 0,
            "urgency_counts": {},
            "messages": [],
            "overall_urgency": "참고",
            "overall_summary": "현재 특이사항이 없습니다.",
        }

    messages = [translate_event(e, audience) for e in events]

    urgency_order = ["즉시 확인 필요", "주의 필요", "참고"]
    urgency_counts: dict[str, int] = {}
    for m in messages:
        u = m.get("urgency", "참고")
        urgency_counts[u] = urgency_counts.get(u, 0) + 1

    # 최고 긴급도
    overall_urgency = "참고"
    for u in urgency_order:
        if urgency_counts.get(u, 0) > 0:
            overall_urgency = u
            break

    # 요약 문장 생성
    parts = []
    for u in urgency_order:
        cnt = urgency_counts.get(u, 0)
        if cnt > 0:
            parts.append(f"{u} {cnt}건")
    overall_summary = f"총 {len(events)}건의 이벤트 — " + ", ".join(parts)

    return {
        "total": len(events),
        "urgency_counts": urgency_counts,
        "messages": messages,
        "overall_urgency": overall_urgency,
        "overall_summary": overall_summary,
    }
