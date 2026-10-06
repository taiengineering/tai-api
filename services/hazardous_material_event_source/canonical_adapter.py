"""Canonical fact projection for hazardous material in/out events.

Exactly one canonical boolean:
  has_hazardous_material_in_out_event = True

Only emitted for exact CONFIRMED event context with matching factory.
Missing != False. {} returned for all non-qualifying inputs.
False synthesis is prohibited.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


def project_hazardous_material_event_fact(
    event: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Project CONFIRMED event → canonical fact dict.

    Returns {"has_hazardous_material_in_out_event": True} for a valid
    CONFIRMED event row. Returns {} for None or non-CONFIRMED rows.
    Never returns {"has_hazardous_material_in_out_event": False}.
    """
    if not isinstance(event, dict):
        return {}
    if event.get("status") != "CONFIRMED":
        return {}
    if not event.get("id") or not event.get("factory_id"):
        return {}
    return {"has_hazardous_material_in_out_event": True}
