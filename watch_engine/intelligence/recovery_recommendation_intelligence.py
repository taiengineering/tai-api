"""Recovery Recommendation Intelligence.

\uacfc\uac70 action \ud6a8\uacfc\uc131 \uae30\ubc18 \ubcf5\uad6c \ucd94\ucc9c.
"""

import logging
from watch_engine.intelligence.intelligence_result import IntelligenceResult

logger = logging.getLogger("watch_engine.intelligence.recovery")


def recommend_recovery(sb, event_type: str = None, flow_key: str = None) -> list[IntelligenceResult]:
    try:
        # 1. \uacfc\uac70 action \ud6a8\uacfc\uc131
        q = sb.table("incident_action_log") \
            .select("action_type,outcome_status,action_note,incident_id")
        if event_type:
            # incident_id\ub85c \uc5f0\uacb0\ub41c integrity_event\uc758 event_type \ud655\uc778 \ubd88\uac00
            # \ub300\uc2e0 action_note\uc5d0\uc11c \ud78c\ud2b8
            pass
        actions = q.execute()

        # action_type\ubcc4 \uc131\uacf5\ub960
        stats = {}
        for a in (actions.data or []):
            at = a.get("action_type", "UNKNOWN")
            if at not in stats:
                stats[at] = {"total": 0, "resolved": 0, "unresolved": 0}
            stats[at]["total"] += 1
            if a.get("outcome_status") == "resolved":
                stats[at]["resolved"] += 1
            elif a.get("outcome_status") == "unresolved":
                stats[at]["unresolved"] += 1

        # 2. recovery_registry \ub9e4\ud551
        recovery = sb.table("workflow_recovery_registry") \
            .select("event_type,recovery_action,recovery_description,auto_executable,priority") \
            .eq("enabled", True).execute()

        recovery_map = {}
        for r in (recovery.data or []):
            et = r.get("event_type", "")
            if et not in recovery_map:
                recovery_map[et] = []
            recovery_map[et].append(r)

        results = []

        # 3. \ucd94\ucc9c \uc0dd\uc131
        for at, s in sorted(stats.items(), key=lambda x: x[1]["total"], reverse=True):
            rate = round(s["resolved"] / s["total"] * 100, 1) if s["total"] > 0 else 0
            confidence = min(1.0, s["total"] / 5)

            results.append(IntelligenceResult(
                intelligence_type="recovery_recommendation",
                severity="INFO",
                risk_score=100 - int(rate),  # \ub0ae\uc744\uc218\ub85d \uc704\ud5d8
                confidence=round(confidence, 2),
                summary=f"{at}: \uc131\uacf5\ub960 {rate}% ({s['resolved']}/{s['total']})",
                recommendations=[f"\uc131\uacf5\ub960 {rate}%" + (" \u2014 \ud6a8\uacfc\uc801" if rate >= 70 else " \u2014 \ub300\uc548 \uac80\ud1a0 \ud544\uc694" if rate < 40 else "")],
                evidence=[{"action_type": at, **s, "success_rate": rate}],
            ))

        # \ubbf8\ub4f1\ub85d event_type\uc5d0 \ub300\ud55c recovery \ucd94\ucc9c
        if event_type and event_type in recovery_map:
            for r in recovery_map[event_type]:
                results.append(IntelligenceResult(
                    intelligence_type="recovery_recommendation",
                    severity="INFO",
                    risk_score=30,
                    confidence=0.7,
                    summary=f"{event_type} \u2192 {r['recovery_action']}",
                    recommendations=[r.get("recovery_description", r["recovery_action"])],
                    evidence=[{"event_type": event_type, "recovery_action": r["recovery_action"],
                               "auto": r.get("auto_executable"), "priority": r.get("priority")}],
                ))

        return results

    except Exception as e:
        logger.error("recommend_recovery failed: %s", e)
        return []
