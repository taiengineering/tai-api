"""Metrics Aggregator v2.0 — Quiet Hour Delayed 지표 추가."""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from services.time import now_kst

logger = logging.getLogger("notification_engine.metrics")


def collect_and_record(window_minutes: int = 10) -> dict:
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()
        now = now_kst()
        since = (now - timedelta(minutes=window_minutes)).isoformat()

        counts = _count_queue_statuses(sb)
        latency = _calc_delivery_latency(sb, since)
        throughput = _calc_throughput(sb, since)
        dlq_total = _count_dlq(sb)
        dlq_delta = _count_dlq_delta(sb, since)
        avg_retry = _calc_avg_retry(sb, since)
        qh_stats = _calc_quiet_hour_stats(sb, since)
        health = _calc_health_score(counts, latency, dlq_delta, avg_retry)

        row = {
            "metric_time": now.isoformat(),
            "queue_count": counts.get("QUEUED", 0),
            "processing_count": counts.get("PROCESSING", 0),
            "delivered_count": counts.get("DELIVERED", 0),
            "failed_count": counts.get("FAILED", 0),
            "retry_pending_count": counts.get("RETRY_PENDING", 0),
            "deadletter_count": counts.get("DEADLETTER", 0),
            "acknowledged_count": counts.get("ACKNOWLEDGED", 0),
            "avg_delivery_latency_ms": latency.get("avg_ms"),
            "max_delivery_latency_ms": latency.get("max_ms"),
            "avg_retry_count": avg_retry,
            "queue_throughput": throughput.get("total", 0),
            "success_throughput": throughput.get("success", 0),
            "fail_throughput": throughput.get("fail", 0),
            "dlq_total": dlq_total,
            "dlq_delta": dlq_delta,
            "health_score": health,
        }

        sb.table("runtime_notification_metrics").insert(row).execute()
        logger.info("Metrics: health=%s qh_delayed=%d qh_resumed=%d",
                    health, qh_stats.get("delayed", 0), qh_stats.get("resumed", 0))

        row["quiet_hour"] = qh_stats
        return row
    except Exception as e:
        logger.error("Metrics collection failed: %s", e)
        return {"error": str(e)}


def get_runtime_summary() -> dict:
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()
        now = now_kst()
        since = (now - timedelta(minutes=10)).isoformat()

        counts = _count_queue_statuses(sb)
        latency = _calc_delivery_latency(sb, since)
        throughput = _calc_throughput(sb, since)
        dlq_total = _count_dlq(sb)
        dlq_delta = _count_dlq_delta(sb, since)
        avg_retry = _calc_avg_retry(sb, since)
        qh_stats = _calc_quiet_hour_stats(sb, since)
        health = _calc_health_score(counts, latency, dlq_delta, avg_retry)

        return {
            "timestamp": now.isoformat(),
            "queue": counts,
            "latency": latency,
            "throughput": throughput,
            "dlq": {"total": dlq_total, "delta_10m": dlq_delta},
            "quiet_hour": qh_stats,
            "avg_retry_count": avg_retry,
            "health": health,
        }
    except Exception as e:
        return {"error": str(e)}


def _count_queue_statuses(sb) -> dict:
    statuses = ["QUEUED", "PROCESSING", "DELIVERED", "FAILED",
                "RETRY_PENDING", "DEADLETTER", "ACKNOWLEDGED",
                "RESOLVED", "QUIET_HOUR_DELAYED"]
    result = {}
    for s in statuses:
        try:
            resp = sb.table("runtime_notification_queue") \
                .select("id", count="exact").eq("delivery_status", s).execute()
            result[s] = resp.count or 0
        except Exception:
            result[s] = 0
    return result


def _calc_quiet_hour_stats(sb, since: str) -> dict:
    try:
        delayed = sb.table("runtime_notification_queue") \
            .select("id", count="exact") \
            .eq("delivery_status", "QUIET_HOUR_DELAYED").execute()
        resumed = sb.table("runtime_notification_policy_audit") \
            .select("id", count="exact") \
            .eq("policy_type", "QUIET_HOUR_RESUME") \
            .gte("created_at", since).execute()
        return {
            "delayed": delayed.count or 0,
            "resumed_10m": resumed.count or 0,
        }
    except Exception:
        return {"delayed": 0, "resumed_10m": 0}


def _calc_delivery_latency(sb, since):
    try:
        resp = sb.table("runtime_notification_queue") \
            .select("created_at, delivered_at") \
            .eq("delivery_status", "DELIVERED").gte("delivered_at", since) \
            .not_.is_("delivered_at", "null").limit(200).execute()
        if not resp.data:
            return {"avg_ms": None, "max_ms": None, "sample_count": 0}
        latencies = []
        for r in resp.data:
            try:
                c = datetime.fromisoformat(str(r["created_at"]).replace("Z", "+00:00"))
                d = datetime.fromisoformat(str(r["delivered_at"]).replace("Z", "+00:00"))
                ms = int((d - c).total_seconds() * 1000)
                if ms >= 0:
                    latencies.append(ms)
            except Exception:
                continue
        if not latencies:
            return {"avg_ms": None, "max_ms": None, "sample_count": 0}
        return {"avg_ms": int(sum(latencies) / len(latencies)),
                "max_ms": max(latencies), "sample_count": len(latencies)}
    except Exception:
        return {"avg_ms": None, "max_ms": None, "sample_count": 0}


def _calc_throughput(sb, since):
    try:
        t = sb.table("runtime_notification_queue").select("id", count="exact").gte("created_at", since).execute()
        s = sb.table("runtime_notification_queue").select("id", count="exact").eq("delivery_status", "DELIVERED").gte("delivered_at", since).execute()
        f = sb.table("runtime_notification_queue").select("id", count="exact").in_("delivery_status", ["FAILED", "DEADLETTER"]).gte("created_at", since).execute()
        return {"total": t.count or 0, "success": s.count or 0, "fail": f.count or 0}
    except Exception:
        return {"total": 0, "success": 0, "fail": 0}


def _count_dlq(sb):
    try:
        return sb.table("runtime_notification_deadletter").select("id", count="exact").execute().count or 0
    except Exception:
        return 0


def _count_dlq_delta(sb, since):
    try:
        return sb.table("runtime_notification_deadletter").select("id", count="exact").gte("created_at", since).execute().count or 0
    except Exception:
        return 0


def _calc_avg_retry(sb, since):
    try:
        resp = sb.table("runtime_notification_queue").select("retry_count").gt("retry_count", 0).gte("created_at", since).limit(200).execute()
        if not resp.data:
            return 0.0
        return round(sum(r.get("retry_count", 0) for r in resp.data) / len(resp.data), 2)
    except Exception:
        return None


def _calc_health_score(counts, latency, dlq_delta, avg_retry):
    score = 0
    backlog = counts.get("QUEUED", 0) + counts.get("PROCESSING", 0) + counts.get("RETRY_PENDING", 0)
    if backlog > 100: score = max(score, 3)
    elif backlog > 50: score = max(score, 2)
    elif backlog > 20: score = max(score, 1)
    if dlq_delta > 10: score = max(score, 3)
    elif dlq_delta > 5: score = max(score, 2)
    elif dlq_delta > 0: score = max(score, 1)
    avg_ms = latency.get("avg_ms")
    if avg_ms is not None:
        if avg_ms > 30000: score = max(score, 3)
        elif avg_ms > 10000: score = max(score, 2)
        elif avg_ms > 5000: score = max(score, 1)
    if avg_retry is not None and avg_retry > 2.0: score = max(score, 2)
    elif avg_retry is not None and avg_retry > 1.0: score = max(score, 1)
    if counts.get("FAILED", 0) > 10: score = max(score, 2)
    return ["HEALTHY", "WARNING", "DEGRADED", "CRITICAL"][min(score, 3)]
