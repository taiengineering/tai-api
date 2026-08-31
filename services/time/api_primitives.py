"""Pure API datetime primitives. No FastAPI / Pydantic global patch."""
from datetime import datetime

from services.time.tai_time import parse_business_datetime, serialize_business_datetime


def validate_business_datetime(value: str) -> datetime:
    """Reject naive strings. Return Asia/Seoul-aware datetime."""
    return parse_business_datetime(value)


def serialize_api_datetime(value: datetime) -> str:
    """Serialize as +09:00 ISO-8601. Naive values raise."""
    return serialize_business_datetime(value)
