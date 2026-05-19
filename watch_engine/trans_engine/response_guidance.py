"""Response Guidance — 통합 엔트리포인트."""
from __future__ import annotations
from typing import Any
from .guidance_builder import build_response_guidance

def enrich_snapshot_guidance(snapshot: dict[str, Any]) -> dict[str, Any]:
    """snapshot에 guidance 정보 추가."""
    g = build_response_guidance(snapshot)
    snapshot["guidance_level"] = g["guidance_level"]
    snapshot["recommended_actions"] = g["recommended_actions"]
    snapshot["recommended_checks"] = g["recommended_checks"]
    snapshot["recommended_order"] = g["recommended_order"]
    snapshot["guidance_summary"] = g["guidance_summary"]
    return snapshot
