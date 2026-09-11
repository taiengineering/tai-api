"""WP-1C-5B production runner — MemoryVersionStore apply forbidden."""
from services.kosha_safety_materials.detail_client import StopRun
from services.kosha_safety_materials.storage.binary_fetch import BinaryFetchError
from services.kosha_safety_materials.storage.hold_store import MemoryHoldStore
from services.kosha_safety_materials.storage.runner import apply_assets, apply_bulk, map_fetch_stop
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


class _ProdHolds:
    def open_asset_ids(self, snapshot_id):
        return set()

    def record_open(self, **k):
        raise AssertionError("no hold")


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


def test_apply_bulk_stops_when_pending_does_not_decrease(monkeypatch):
    item = {"asset_id": 1, "material_id": "m1", "kogl_type": "1"}

    def collect(store, query, **k):
        return {"pending": [item], "pending_count": 1, "held": 0}

    monkeypatch.setattr("services.kosha_safety_materials.storage.runner.collect_eligible", collect)
    monkeypatch.setattr(
        "services.kosha_safety_materials.storage.runner.apply_assets",
        lambda *a, **k: {"attempted": 1, "stored": 0, "NO_CHANGE": 1, "NEW_VERSION": 0, "PROMOTED_EXISTING_VERSION": 0, "HOLD": 0, "last": None},
    )
    try:
        apply_bulk(_FakeStore(), query=None, r2=None, versions=_Prod(), holds=_ProdHolds(), batch_size=20)
        assert False
    except StopRun as e:
        assert e.reason == "PENDING_NO_PROGRESS"


def test_transient_upstream_is_not_integrity():
    try:
        map_fetch_stop(BinaryFetchError("TRANSIENT_UPSTREAM_FAILURE"))
        assert False
    except StopRun as e:
        assert e.reason == "TRANSIENT_UPSTREAM_FAILURE"


def test_apply_bulk_rejects_memory_holds():
    try:
        apply_bulk(_FakeStore(), query=None, r2=None, versions=_Prod(), holds=MemoryHoldStore())
        assert False
    except StopRun as e:
        assert e.reason == "MEMORY_HOLD_STORE_FORBIDDEN"


def test_apply_bulk_storage_sweep_complete_when_only_holds_remain(monkeypatch):
    calls = {"n": 0}

    def collect(store, query, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"pending": [{"asset_id": 4523, "material_id": "m1"}], "pending_count": 1, "held": 0}
        return {"pending": [], "pending_count": 0, "held": 1}

    monkeypatch.setattr("services.kosha_safety_materials.storage.runner.collect_eligible", collect)
    monkeypatch.setattr(
        "services.kosha_safety_materials.storage.runner.apply_assets",
        lambda *a, **k: {"attempted": 1, "stored": 0, "NO_CHANGE": 0, "NEW_VERSION": 0, "PROMOTED_EXISTING_VERSION": 0, "HOLD": 1, "last": {"status": "HOLD"}},
    )
    out = apply_bulk(_FakeStore(), query=None, r2=None, versions=_Prod(), holds=_ProdHolds(), batch_size=20)
    assert out["status"] == "STORAGE_SWEEP_COMPLETE_WITH_HOLDS"
    assert out["HOLD"] == 1
    assert out["remaining"] == 0
    assert out["held"] == 1
