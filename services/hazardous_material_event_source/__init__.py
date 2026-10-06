"""Hazardous material in/out operational event source.

Source contract: 초고층 및 지하연계 복합건축물 재난관리에 관한 특별법 시행규칙 제9조
Canonical TRUE only from exact CONFIRMED event + same factory.
Missing != False. DB failure is not empty source.
"""
from services.hazardous_material_event_source.store import (
    HazardousMaterialEventSourceLoadError,
    HazardousMaterialEventValidationError,
    create_event_draft,
    update_event_draft,
    confirm_event,
    void_event,
    list_factory_events,
    load_confirmed_event_context,
)
from services.hazardous_material_event_source.canonical_adapter import (
    project_hazardous_material_event_fact,
)

__all__ = [
    "HazardousMaterialEventSourceLoadError",
    "HazardousMaterialEventValidationError",
    "create_event_draft",
    "update_event_draft",
    "confirm_event",
    "void_event",
    "list_factory_events",
    "load_confirmed_event_context",
    "project_hazardous_material_event_fact",
]
