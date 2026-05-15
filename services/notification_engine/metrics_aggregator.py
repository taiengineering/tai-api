"""Metrics Aggregator — Runtime 상태 집계 + Health Score 계산.

주기 실행 가능 구조. cron 또는 수동 호출.
runtime_notification_metrics 테이블에 기록.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger("notification_engine.metrics")


def collect_and_record(window_minutes: int = 10) -> dict:
    """현재 Runtime 상태 집계 → metrics 테이블 INSERT.

    Returns: 집계된 metrics dict.
    """
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()
        now = datetime.now(timezone.utc)
        since = (now - timedelta(minutes=window_minutes)).isoformat()

        # 1. Queue 상태별 건수
        counts = _count_queue_statuses(sb)

        # 2. Delivery latency (최근 window 내 DELIVERED)
        latency = _calc_delivery_latency(sb, since)

        # 3. Throughput (최근 window)
        throughput = _calc_throughput(sb, since)

        # 4. DLQ
        dlq_total = _count_dlq(sb)
        dlq_delta = _count_dlq_delta(sb, since)

        # 5. Retry 평균
        avg_retry = _calc_avg_retry(sb, since)

        # 6. Health Score
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
        logger.info("Metrics recorded: health=%s throughput=%d latency=%sms",
                    health, throughput.get("total", 0), latency.get("avg_ms"))
        return row

    except Exception as e:
        logger.error("Metrics collection failed: %s", e)
        return {"error": str(e)}


def get_runtime_summary() -> dict:
    """현재 시점 Runtime 요약 (저장 없이 실시간 계산)."""
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()
        now = datetime.now(timezone.utc)
        since_10m = (now - timedelta(minutes=10)).isoformat()

        counts = _count_queue_statuses(sb)
        latency = _calc_delivery_latency(sb, since_10m)
        throughput = _calc_throughput(sb, since_10m)
        dlq_total = _count_dlq(sb)
        dlq_delta = _count_dlq_delta(sb, since_10m)
        avg_retry = _calc_avg_retry(sb, since_10m)
        health = _calc_health_score(counts, latency, dlq_delta, avg_retry)

        return {
            "timestamp": now.isoformat(),
            "queue": counts,
            "latency": latency,
            "throughput": throughput,
            "dlq": {"total": dlq_total, "delta_10m": dlq_delta},
            "avg_retry_count": avg_retry,
            "health": health,
        }
    except Exception as e:
        logger.error("Runtime summary failed: %s", e)
        return {"error": str(e)}


# ===== Internal helpers =====

def _count_queue_statuses(sb) -> dict:
    statuses = ["QUEUED", "PROCESSING", "DELIVERED", "FAILED",
                "RETRY_PENDING", "DEADLETTER", "ACKNOWLEDGED", "RESOLVED"]
    result = {}
    for s in statuses:
        try:
            resp = sb.table("runtime_notification_queue") \
                .select("id", count="exact").eq("delivery_status", s).execute()
            result[s] = resp.count or 0
        except Exception:
            result[s] = 0
    return result


def _calc_delivery_latency(sb, since: str) -> dict:
    """DELIVERED 항목의 delivered_at - created_at 평균/최대."""
    try:
        resp = sb.table("runtime_notification_queue") \
            .select("created_at, delivered_at") \
            .eq("delivery_status", "DELIVERED") \
            .gte("delivered_at", since) \
            .not_.is_("delivered_at", "null") \
            .limit(200).execute()

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

        return {
            "avg_ms": int(sum(latencies) / len(latencies)),
            "max_ms": max(latencies),
            "sample_count": len(latencies),
        }
    except Exception:
        return {"avg_ms": None, "max_ms": None, "sample_count": 0}


def _calc_throughput(sb, since: str) -> dict:
    """최근 window 내 처리량."""
    try:
        total = sb.table("runtime_notification_queue") \
            .select("id", count="exact") \
            .gte("created_at", since).execute()
        success = sb.table("runtime_notification_queue") \
            .select("id", count="exact") \
            .eq("delivery_status", "DELIVERED") \
            .gte("delivered_at", since).execute()
        fail = sb.table("runtime_notification_queue") \
            .select("id", count="exact") \
            .in_("delivery_status", ["FAILED", "DEADLETTER"]) \
            .gte("created_at", since).execute()
        return {
            "total": total.count or 0,
            "success": success.count or 0,
            "fail": fail.count or 0,
        }
    except Exception:
        return {"total": 0, "success": 0, "fail": 0}


def _count_dlq(sb) -> int:
    try:
        resp = sb.table("runtime_notification_deadletter") \
            .select("id", count="exact").execute()
        return resp.count or 0
    except Exception:
        return 0


def _count_dlq_delta(sb, since: str) -> int:
    try:
        resp = sb.table("runtime_notification_deadletter") \
            .select("id", count="exact").gte("created_at", since).execute()
        return resp.count or 0
    except Exception:
        return 0


def _calc_avg_retry(sb, since: str) -> Optional[float]:
    try:
        resp = sb.table("runtime_notification_queue") \
            .select("retry_count") \
            .gt("retry_count", 0) \
            .gte("created_at", since) \
            .limit(200).execute()
        if not resp.data:
            return 0.0
        total = sum(r.get("retry_count", 0) for r in resp.data)
        return round(total / len(resp.data), 2)
    except Exception:
        return None


def _calc_health_score(counts: dict, latency: dict, dlq_delta: int, avg_retry) -> str:
    """Runtime Health Score 계산.

    HEALTHY / WARNING / DEGRADED / CRITICAL
    """
    score = 0  # 0=HEALTHY, 1=WARNING, 2=DEGRADED, 3=CRITICAL

    # Queue backlog
    backlog = counts.get("QUEUED", 0) + counts.get("PROCESSING", 0) + counts.get("RETRY_PENDING", 0)
    if backlog > 100:
        score = max(score, 3)
    elif backlog > 50:
        score = max(score, 2)
    elif backlog > 20:
        score = max(score, 1)

    # DLQ 급증
    if dlq_delta > 10:
        score = max(score, 3)
    elif dlq_delta > 5:
        score = max(score, 2)
    elif dlq_delta > 0:
        score = max(score, 1)

    # Latency
    avg_ms = latency.get("avg_ms")
    if avg_ms is not None:
        if avg_ms > 30000:
            score = max(score, 3)
        elif avg_ms > 10000:
            score = max(score, 2)
        elif avg_ms > 5000:
            score = max(score, 1)

    # Retry ratio
    if avg_retry is not None and avg_retry > 2.0:
        score = max(score, 2)
    elif avg_retry is not None and avg_retry > 1.0:
        score = max(score, 1)

    # Failed count
    if counts.get("FAILED", 0) > 10:
        score = max(score, 2)

    return ["HEALTHY", "WARNING", "DEGRADED", "CRITICAL"][min(score, 3)]
