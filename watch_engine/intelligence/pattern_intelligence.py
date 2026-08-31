"""Pattern Intelligence.

\uc6b4\uc601 \ud328\ud134 \ubcc0\ud654 \uac10\uc9c0: \uc2dc\uac04\ub300, flow\ubcc4 \ucd94\uc138.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from watch_engine.intelligence.intelligence_result import IntelligenceResult
from services.time import now_kst

logger = logging.getLogger("watch_engine.intelligence.pattern")


def analyze_patterns(
    sb, hours: int = 48, now: Optional[datetime] = None,
) -> list[IntelligenceResult]:
    if now is None:
        now = now_kst()

    try:
        # \uc2dc\uac04\ub300\ubcc4 \ubd84\ud3ec \ubd84\uc11d (\ucd5c\uadfc vs \uc774\uc804)
        mid = now - timedelta(hours=hours // 2)
        since = (now - timedelta(hours=hours)).isoformat()

        events = sb.table("engine_integrity_event") \
            .select("flow_key,event_type,severity,created_at") \
            .neq("environment", "mock") \
            .not_.is_("trace_id", "null") \
            .gte("created_at", since).execute()

        # \uc804\ubc18/\ud6c4\ubc18 \ube44\uad50
        first_half = {}
        second_half = {}
        for e in (events.data or []):
            fk = e.get("flow_key", "unknown")
            created = e.get("created_at", "")
            target = second_half if created >= mid.isoformat() else first_half
            target[fk] = target.get(fk, 0) + 1

        results = []
        all_flows = set(list(first_half.keys()) + list(second_half.keys()))

        for fk in all_flows:
            before = first_half.get(fk, 0)
            after = second_half.get(fk, 0)

            if before == 0 and after == 0:
                continue

            if before == 0 and after > 0:
                trend = "NEW_ISSUE"
                risk = min(100, after * 15)
            elif after > before * 2:
                trend = "ACCELERATING"
                risk = min(100, int((after / max(before, 1)) * 20))
            elif after < before * 0.5:
                trend = "IMPROVING"
                risk = max(0, 20 - (before - after) * 5)
            else:
                trend = "STABLE"
                risk = min(50, (before + after) * 3)

            if trend in ("STABLE", "IMPROVING") and risk < 20:
                continue

            sev = "CRITICAL" if risk >= 70 else "WARNING" if risk >= 30 else "INFO"
            confidence = min(1.0, (before + after) / 15)

            results.append(IntelligenceResult(
                intelligence_type="pattern_analysis",
                severity=sev,
                risk_score=risk,
                confidence=round(confidence, 2),
                summary=f"{fk}: {trend} (\uc804\ubc18 {before} \u2192 \ud6c4\ubc18 {after}, {hours}h)",
                recommendations=_pattern_recommend(trend, fk),
                evidence=[{"flow_key": fk, "first_half": before, "second_half": after, "trend": trend}],
                details={"trend": trend},
            ))

        results.sort(key=lambda r: r.risk_score, reverse=True)
        return results

    except Exception as e:
        logger.error("analyze_patterns failed: %s", e)
        return []


def _pattern_recommend(trend: str, flow_key: str) -> list:
    if trend == "ACCELERATING":
        return [f"{flow_key} \uc774\uc288 \uac00\uc18d\ud654 \u2014 \uc989\uc2dc \uc870\uc0ac \ud544\uc694", "\uadfc\ubcf8 \uc6d0\uc778 \ud655\uc778"]
    if trend == "NEW_ISSUE":
        return [f"{flow_key} \uc2e0\uaddc \uc774\uc288 \ubc1c\uc0dd", "\ucd5c\uadfc \ubc30\ud3ec/\ubcc0\uacbd \ud655\uc778"]
    if trend == "STABLE":
        return [f"{flow_key} \uc774\uc288 \uc9c0\uc18d \u2014 \uc7a5\uae30 \ub300\uc751 \uac80\ud1a0"]
    return []
