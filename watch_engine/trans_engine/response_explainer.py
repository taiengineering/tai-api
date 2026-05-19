"""Response Explainer — 대응 가이드 운영 언어 생성."""
from __future__ import annotations
from typing import Any

_LEVEL_DESC = {
    "critical": "즉시 대응이 권장됩니다",
    "high": "우선적으로 확인이 필요합니다",
    "medium": "확인을 권장합니다",
    "low": "관찰 수준입니다",
}

def build_guidance_summary(snapshot: dict[str, Any], playbook: dict[str, Any], level: str) -> str:
    desc = _LEVEL_DESC.get(level, "확인하세요")
    title = playbook.get("title", "대응 가이드")
    return f"{desc}. {title}: {', '.join(playbook.get('actions', [])[:2])}"

def build_why_recommended(snapshot: dict[str, Any]) -> list[str]:
    reasons = []
    dt = snapshot.get("delta_type", "")
    status = snapshot.get("status", "")
    if dt == "worsening": reasons.append("상황이 악화되고 있어 빠른 확인이 필요합니다")
    if dt == "recurring": reasons.append("이전에 해결된 문제가 재발하고 있습니다")
    if status == "escalating": reasons.append("위험이 증가하고 있습니다")
    if snapshot.get("trend") == "accelerating": reasons.append("문제 증가 속도가 빠르다")
    if not reasons: reasons.append("운영 상황 모니터링 기반 추천입니다")
    return reasons
