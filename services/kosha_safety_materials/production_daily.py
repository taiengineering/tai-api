"""Production assembly helpers for KOSHA Safety Material Control Plane adapter.

Extracted from scripts/kosha_safety_material_daily_sync.py so the adapter can
call the production pipeline without importing a scripts/ file.
"""
from __future__ import annotations

import socket


async def run_production_daily() -> tuple[dict, int]:
    """Assemble all production stores and run the full daily pipeline."""
    from routers.kosha_collect import _fetch_safety_materials_page
    from services.kosha_safety_material_sync import SupabaseSnapshotStore, sync_safety_materials
    from services.kosha_safety_material_storage import _r2
    from services.kosha_safety_materials.daily_sync import (
        network_preflight,
        production_consistency,
        run_daily,
        wrap_detail_batch,
    )
    from services.kosha_safety_materials.display import SupabaseDisplayStore
    from services.kosha_safety_materials.storage.hold_store import SupabaseHoldStore
    from services.kosha_safety_materials.storage.runner import BATCH_SIZE as STORAGE_BATCH
    from services.kosha_safety_materials.storage.runner import StorageQuery, apply_bulk
    from services.kosha_safety_materials.storage.version_service import (
        SupabaseVersionStore,
        assert_production_versions,
    )
    from services.kosha_safety_materials.writer import SupabaseStore

    snapshot_store = SupabaseSnapshotStore()

    async def sync_fn(*, dry_run: bool, start_page: int):
        return await sync_safety_materials(
            fetch_page=_fetch_safety_materials_page,
            store=snapshot_store,
            dry_run=dry_run,
            start_page=start_page,
        )

    enrich_store = SupabaseStore()
    display_store = SupabaseDisplayStore()

    store = SupabaseStore()
    holds = SupabaseHoldStore(store.sb)
    query = StorageQuery(store.sb)
    r2 = _r2()
    versions = SupabaseVersionStore()
    assert_production_versions(versions)

    def storage_fn(*, snapshot_id: str):
        out = apply_bulk(store, query, r2, versions, holds=holds, batch_size=STORAGE_BATCH)
        out["r2_overwrite"] = int(getattr(r2, "overwrites", 0) or 0)
        out["r2_delete"] = int(getattr(r2, "deletes", 0) or getattr(r2, "delete_count", 0) or 0)
        out["existing_open_holds"] = out.get("held")
        return out

    return await run_daily(
        preflight_fn=network_preflight,
        sync_fn=sync_fn,
        latest_completed_fn=snapshot_store.latest_completed,
        detail_batch_fn=wrap_detail_batch(enrich_store),
        storage_fn=storage_fn,
        consistency_fn=production_consistency(
            snapshot_store=enrich_store,
            display_store=display_store,
        ),
        host=socket.gethostname(),
    )


async def run_production_dry_run() -> dict:
    """Run sync_safety_materials with dry_run=True using production stores."""
    from routers.kosha_collect import _fetch_safety_materials_page
    from services.kosha_safety_material_sync import SupabaseSnapshotStore, sync_safety_materials

    store = SupabaseSnapshotStore()
    return await sync_safety_materials(
        fetch_page=_fetch_safety_materials_page,
        store=store,
        dry_run=True,
        start_page=1,
    )
