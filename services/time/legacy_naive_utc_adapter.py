from datetime import datetime, timezone
def aware_to_legacy_naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None: raise ValueError("aware required")
    return value.astimezone(timezone.utc).replace(tzinfo=None)   # .replace(tzinfo=None)은 여기서만
def legacy_naive_utc_to_aware(value: datetime) -> datetime:
    if value.tzinfo is not None: raise ValueError("expected naive UTC wall-clock")
    return value.replace(tzinfo=timezone.utc)
