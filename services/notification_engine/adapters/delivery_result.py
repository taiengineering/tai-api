"""Delivery Result — Adapter 공통 반환 타입.

모든 Adapter는 send() → DeliveryResult 반환.
"""

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timezone


@dataclass
class DeliveryResult:
    success: bool
    delivery_status: str  # DELIVERED / FAILED
    external_id: Optional[str] = None
    error_message: Optional[str] = None
    delivered_at: Optional[str] = None

    def __post_init__(self):
        if self.success and not self.delivered_at:
            self.delivered_at = datetime.now(timezone.utc).isoformat()
        if not self.success and not self.delivery_status:
            self.delivery_status = "FAILED"
