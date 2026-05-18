"""Impact Explainer — 영향 범위 언어 생성."""

from __future__ import annotations

from typing import Any


def explain_impact(events: list[dict[str, Any]]) -> str:
    """이벤트 집합으로부터 영향 범위 문장 생성.

    판단 기준:
    - CRITICAL/FATAL severity → 전체 서비스 영향
    - tenant_count > 1 → 여러 조직 영향
    - customer_facing flow → 사용자 영향
    - 그 외 → 제한적 영향
    """
    if not events:
        return "현재 영향 없음"

    severities = {e.get("severity", "INFO").upper() for e in events}
    tenant_ids = {e.get("tenant_id") for e in events if e.get("tenant_id")}
    flow_keys = {e.get("flow_key", "") for e in events}

    # FATAL / CRITICAL → 전체 영향
    if "FATAL" in severities:
        return "전체 서비스 중단 위험이 있습니다"
    if "CRITICAL" in severities and len(events) >= 5:
        return "전체 서비스 영향 가능"

    # 다수 tenant
    if len(tenant_ids) > 3:
        return "여러 조직에 걸쳐 영향 발생 가능"
    if len(tenant_ids) > 1:
        return "특정 조직들에 영향 가능"

    # 고객 대면 흐름
    customer_flows = {"payment", "subscription", "document", "diagnosis"}
    if any(fk.split("_")[0] in customer_flows for fk in flow_keys if fk):
        return "일부 사용자 영향 가능"

    if "CRITICAL" in severities:
        return "즉시 확인 필요 — 고객 경험 저하 가능"

    return "현재 영향 제한적"
