"""Event Translator — 핵심 번역기.

Translation Flow:
  event dict → TranslationContext → Dictionary Lookup → HumanMessage
"""

from __future__ import annotations

from typing import Any

from .audience_profile import AudienceProfile
from .domain_dictionary import lookup, severity_to_urgency
from .human_message import HumanMessage
from .translation_context import TranslationContext


def translate_event(
    event: dict[str, Any],
    audience: str = "operator",
) -> dict[str, Any]:
    """Runtime event → Human Message dict.

    Args:
        event: Runtime event (event_type, flow_key, severity 등)
        audience: "operator" | "admin" | "developer"

    Returns:
        Human Message Contract dict
    """
    ctx = TranslationContext.from_event(event)
    profile = AudienceProfile(audience)

    # Domain 추론: 명시적 domain > flow_key prefix > event_type prefix
    domain = ctx.domain
    if not domain and ctx.flow_key:
        domain = _infer_domain(ctx.flow_key)
    if not domain:
        domain = _infer_domain(ctx.event_type)

    # Dictionary lookup
    entry, confidence = lookup(ctx.event_type, domain)

    if entry:
        msg = _from_entry(entry, ctx, profile, confidence)
    else:
        msg = _fallback(ctx, profile)

    return msg.to_dict(include_technical=profile.include_technical)


def _from_entry(
    entry: "from .domain_dictionary import DictionaryEntry",  # noqa: F821
    ctx: TranslationContext,
    profile: AudienceProfile,
    confidence: float,
) -> HumanMessage:
    """DictionaryEntry → HumanMessage."""
    if profile == AudienceProfile.OPERATOR:
        title = entry.operator_title
        summary = entry.operator_summary
    else:
        title = entry.admin_title
        summary = entry.admin_summary

    # flow_key 가 있으면 제목에 컨텍스트 추가 (admin/developer)
    if ctx.flow_key and profile.allow_domain_terms:
        flow_label = _flow_key_to_label(ctx.flow_key)
        title = f"{title} — {flow_label}"

    # window 정보가 있으면 summary 보강
    if ctx.window_minutes and ctx.count:
        time_desc = f"최근 {ctx.window_minutes}분"
        if profile == AudienceProfile.OPERATOR:
            summary = f"{time_desc} 동안 {summary}"
        else:
            summary = f"{time_desc} 동안 {ctx.count}건 — {summary}"

    urgency = severity_to_urgency(ctx.severity)

    technical = None
    if profile.include_technical:
        technical = {
            "event_type": ctx.event_type,
            "flow_key": ctx.flow_key,
            "severity": ctx.severity,
            "trace_id": ctx.trace_id,
        }
        if ctx.count:
            technical["count"] = ctx.count

    return HumanMessage(
        title=title,
        summary=summary,
        urgency=urgency,
        impact=entry.impact,
        recommended_checks=entry.recommended_checks,
        recommended_actions=entry.recommended_actions or [],
        confidence=confidence,
        technical=technical,
    )


def _fallback(
    ctx: TranslationContext,
    profile: AudienceProfile,
) -> HumanMessage:
    """사전에 없는 event → 기본 템플릿."""
    if profile == AudienceProfile.OPERATOR:
        title = "시스템에서 이벤트가 감지되었습니다"
        summary = "운영 상태에 변화가 있습니다. 상세 내용은 관리자에게 문의하세요."
    else:
        title = f"이벤트 감지: {ctx.event_type}"
        summary = f"{ctx.event_type} 이벤트가 발생했습니다."

    urgency = severity_to_urgency(ctx.severity)

    technical = None
    if profile.include_technical:
        technical = {
            "event_type": ctx.event_type,
            "flow_key": ctx.flow_key,
            "severity": ctx.severity,
            "trace_id": ctx.trace_id,
        }

    return HumanMessage(
        title=title,
        summary=summary,
        urgency=urgency,
        impact="확인 필요",
        recommended_checks=["관련 서비스 상태를 확인하세요"],
        confidence=0.50,
        technical=technical,
    )


# ──────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────

_DOMAIN_PREFIXES = {
    "payment": "payment",
    "document": "document",
    "inspection": "construction",
    "schedule": "construction",
    "compliance": "construction",
    "campaign": "marketing",
    "diagnosis": "tai",
    "subscription": "tai",
}


def _infer_domain(key: str) -> str | None:
    """flow_key 또는 event_type prefix로 domain 추론."""
    prefix = key.split(".")[0].split("_")[0].lower()
    return _DOMAIN_PREFIXES.get(prefix)


_FLOW_LABELS: dict[str, str] = {
    "payment_attempt": "결제",
    "payment_refund": "환불",
    "document_generation": "문서 생성",
    "diagnosis_run": "법령진단",
    "subscription_activate": "구독 활성화",
}


def _flow_key_to_label(flow_key: str) -> str:
    """flow_key → 사람 라벨."""
    return _FLOW_LABELS.get(flow_key, flow_key.replace("_", " "))
