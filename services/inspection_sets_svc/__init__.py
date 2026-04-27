from db.supabase_client import get_supabase as _health_get_supabase
from services.health_registry import register_probe
from .anchors import bulk_update_anchors, patch_set, set_anchor_bulk, update_anchor
from .errors import InspectionSetsSvcError
from .queries import (
    create_manual_set,
    generate_all_items,
    generate_items_for_set,
    get_company_sets,
    get_factory_sets,
    get_preview_schedule,
    get_set_by_id,
    get_sets_list,
)
from .schedules import generate_schedules_all, generate_schedules_for_factory

__all__ = [
    "InspectionSetsSvcError",
    "get_sets_list",
    "create_manual_set",
    "get_preview_schedule",
    "set_anchor_bulk",
    "bulk_update_anchors",
    "generate_all_items",
    "generate_schedules_all",
    "generate_schedules_for_factory",
    "patch_set",
    "update_anchor",
    "generate_items_for_set",
    "get_company_sets",
    "get_factory_sets",
    "get_set_by_id",
]


async def _probe_inspection():
    sb = _health_get_supabase()
    r = sb.table("inspection_sets").select("id", count="exact").limit(1).execute()
    return {"sets_count": r.count or 0}


register_probe("inspection", _probe_inspection, critical=False, desc_ko="점검 관리")
