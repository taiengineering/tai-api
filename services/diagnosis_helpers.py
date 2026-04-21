import hashlib
from datetime import datetime, timezone
from typing import Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _auto_tier(
    sector: str,
    floor_area: float = 0.0,
    contract_amount_eok: float = 0.0,
    user_tier: Optional[str] = None,
) -> str:
    if sector == "BUILDING":
        return "BUILDING_LARGE_V2" if (floor_area or 0) >= 5000 else "BUILDING_V2"
    if sector == "CONSTRUCTION":
        return "CONSTRUCTION_PREMIUM" if (contract_amount_eok or 0) >= 50 else "CONSTRUCTION"
    return user_tier or "INDUSTRY_V2"


def _build_partial(full: dict) -> dict:
    return {
        "risk_level": full.get("risk_level"),
        "summary": full.get("summary"),
        "applicable_count": full.get("applicable_count"),
        "sector": full.get("sector"),
        "key_obligations": (full.get("key_obligations") or [])[:6],
        "law_badges": (full.get("law_badges") or [])[:18],
    }
