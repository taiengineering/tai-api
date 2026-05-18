"""Situation Builder — 여러 이벤트 → 운영 상황 요약.

조합:
  priority_ranker + trend_narrator + impact_explainer
  + storyline_builder + event_translator
"""

from __future__ import annotations

from typing import Any

from .event_translator import translate_event
from .impact_explainer import explain_impact
from .priority_ranker import rank_priority
from .storyline_builder import build_storyline
from .trend_narrator import describe_trend, infer_trend


def build_operational_situation(
    events: list[dict[str, Any]],
    audience: str = "operator",
) -> dict[str, Any]:
    """여러 Runtime Event → Operational Situation.

    Returns:
        {
          situation_title, situation_summary,
          urgency, impact, trend, trend_description,
          recommended_focus, storyline, priority,
          messages, confidence
        }
    """
    if not events:
        return {
            "situation_title": "현재 특이사항 없음",
            "situation_summary": "운영 상황에 특이사항이 없습니다.",
            "urgency": "정보 수준",
            "impact": "현재 영향 없음",
            "trend": "stable",
            "trend_description": "현재 상태가 유지되고 있습니다.",
            "recommended_focus": [],
            "storyline": [],
            "priority": {"score": 0, "level": "P4", "label": "정보 수준"},
            "messages": [],
            "confidence": 1.0,
        }

    # 각 모듈 실행
    priority = rank_priority(events)
    trend = infer_trend(events)
    trend_desc = describe_trend(trend)
    impact = explain_impact(events)
    storyline = build_storyline(events, audience)
    messages = [translate_event(e, audience) for e in events]

    # Situation title 생성
    situation_title = _build_title(events, priority.label)
    situation_summary = _build_summary(events, trend_desc, impact)

    # recommended_focus: 개별 메시지의 recommended_checks 합산 (top 5, 중복 제거)
    seen: set[str] = set()
    focus: list[str] = []
    for m in messages:
        for c in m.get("recommended_checks", []):
            if c not in seen:
                seen.add(c)
                focus.append(c)
            if len(focus) >= 5:
                break
        if len(focus) >= 5:
            break

    # confidence: 개별 메시지 confidence 평균
    confs = [m.get("confidence", 0.5) for m in messages]
    avg_conf = sum(confs) / len(confs) if confs else 0.5

    return {
        "situation_title": situation_title,
        "situation_summary": situation_summary,
        "urgency": priority.label,
        "impact": impact,
        "trend": trend,
        "trend_description": trend_desc,
        "recommended_focus": focus,
        "storyline": storyline,
        "priority": priority.to_dict(),
        "messages": messages,
        "confidence": round(avg_conf, 3),
    }


def _build_title(
    events: list[dict[str, Any]],
    urgency_label: str,
) -> str:
    """이벤트 집합에서 상황 제목 생성."""
    flow_keys = [e.get("flow_key", "") for e in events if e.get("flow_key")]
    types = {e.get("event_type", "") for e in events}

    # 도메인 힌트
    domain = ""
    if flow_keys:
        first = flow_keys[0].split("_")[0]
        domain_map = {
            "payment": "결제 흐름",
            "document": "문서 생성",
            "diagnosis": "법령진단",
            "subscription": "구독",
            "campaign": "캠페인",
        }
        domain = domain_map.get(first, first.replace("_", " "))

    # 상황 유형
    if "escalation" in types:
        situation = "위험 증가"
    elif "degradation" in types or "runtime.degraded" in types:
        situation = "안정성 저하"
    elif "repeated_failure" in types:
        situation = "반복 실패"
    elif any(t.endswith(".failed") for t in types):
        situation = "실패 발생"
    else:
        situation = "이상 감지"

    if domain:
        return f"{domain} {situation}"
    return f"시스템 {situation}"


def _build_summary(
    events: list[dict[str, Any]],
    trend_desc: str,
    impact: str,
) -> str:
    """상황 요약 문장 생성."""
    count = len(events)
    return f"최근 {count}건의 이벤트가 감지되었습니다. {trend_desc} {impact}."
