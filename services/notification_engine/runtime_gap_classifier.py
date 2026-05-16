"""Runtime Gap Classifier — Inconsistency 분류."""

GAP_TYPES = {
    "FEED_GAP": "Feed 불일치 — 전달 완료되었지만 Feed에 없음",
    "AUDIT_GAP": "Audit 누락 — 상태 변경이 기록되지 않음",
    "METRIC_GAP": "Metrics 불일치 — 실제 상태와 지표 불일치",
    "TIMELINE_GAP": "Timeline 누락 — 흐름 관측 불가",
    "QUEUE_GAP": "Queue 상태 충돌 — 이벤트 있는데 Queue 없음",
}


def classify_gaps(gaps: list) -> dict:
    """Gap 목록 → 유형별 분류."""
    classified = {gt: [] for gt in GAP_TYPES}
    for g in gaps:
        gt = g.get("type", "UNKNOWN")
        if gt in classified:
            classified[gt].append(g.get("detail", ""))
    return {
        "total_gaps": len(gaps),
        "by_type": {k: {"count": len(v), "items": v} for k, v in classified.items() if v},
        "severity": _assess_severity(gaps),
    }


def _assess_severity(gaps: list) -> str:
    if not gaps:
        return "CLEAN"
    types = {g.get("type") for g in gaps}
    if "QUEUE_GAP" in types or "AUDIT_GAP" in types:
        return "HIGH"
    if "FEED_GAP" in types:
        return "MEDIUM"
    return "LOW"
