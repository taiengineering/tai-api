"""Retry Policy — Exponential Backoff + 재시도 정책.

Worker에서 사용.
"""

import math
from datetime import datetime, timezone, timedelta
from services.time import now_kst

# 기본 정책
DEFAULT_MAX_RETRIES = 3
BASE_DELAY_SECONDS = 30      # 첫 retry: 30초
MAX_DELAY_SECONDS = 300      # 최대 5분
BACKOFF_MULTIPLIER = 2.0


def calculate_next_retry_at(
    retry_count: int,
    base_delay: int = BASE_DELAY_SECONDS,
    max_delay: int = MAX_DELAY_SECONDS,
    multiplier: float = BACKOFF_MULTIPLIER,
) -> datetime:
    """Exponential backoff으로 다음 재시도 시각 계산.

    delay = min(base * multiplier^retry_count, max_delay)
    """
    delay = min(base_delay * (multiplier ** retry_count), max_delay)
    return now_kst() + timedelta(seconds=delay)


def should_retry(retry_count: int, max_retries: int = DEFAULT_MAX_RETRIES) -> bool:
    """retry_count < max_retries 이면 재시도."""
    return retry_count < max_retries


def should_deadletter(retry_count: int, max_retries: int = DEFAULT_MAX_RETRIES) -> bool:
    """max_retries 도달 시 DLQ 이동."""
    return retry_count >= max_retries
