"""WP-1C-5B production runner — MemoryVersionStore apply forbidden."""
from services.kosha_safety_materials.detail_client import StopRun
from services.kosha_safety_materials.storage.runner import apply_assets
from services.kosha_safety_materials.storage.store import StorageError
from services.kosha_safety_materials.storage.version_service import MemoryVersionStore, VersionError


def test_apply_rejects_memory_store():
    try:
        apply_assets([], store=None, query=None, r2=None, versions=MemoryVersionStore())
        assert False
    except VersionError as e:
        assert e.code == "MEMORY_STORE_FORBIDDEN"


class _FakeStore:
    def latest_completed(self):
        return {"id": "s", "snapshot_hash": "h", "status": "COMPLETED", "unique_count": 1}

    def membership(self, snapshot_id):
        return [{"material_id": "m1"}]


class _Prod:
    pass


def test_apply_fail_closed_on_storage_error(monkeypatch):
    def boom(*a, **k):
        raise StorageError("BINARY_INTEGRITY_BLOCKED")

    monkeypatch.setattr("services.kosha_safety_materials.storage.runner._store_one", boom)
    try:
        apply_assets(
            [{"asset_id": 1, "material_id": "m1"}],
            store=_FakeStore(), query=None, r2=None, versions=_Prod(),
        )
        assert False
    except StopRun as e:
        assert e.reason == "BINARY_INTEGRITY_BLOCKED"
