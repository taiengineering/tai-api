"""Delivery Result — Adapter 공통 반환 타입.

모든 Adapter는 send() → DeliveryResult 반환.
"""

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timezone
from services.time import now_kst, serialize_external_utc


@dataclass
class DeliveryResult:
    success: bool
    delivery_status: str  # DELIVERED / FAILED
    external_id: Optional[str] = None
    error_message: Optional[str] = None
    delivered_at: Optional[str] = None

    def __post_init__(self):
        if self.success and not self.delivered_at:
            self.delivered_at = serialize_external_utc(now_kst())
        if not self.success and not self.delivery_status:
            self.delivery_status = "FAILED"
