"""WP-4B-1 HOLD resolve_open contract. Memory/Supabase parity. No production DML."""
from __future__ import annotations

from services.kosha_safety_materials.storage.hold_store import (
    HoldError,
    MemoryHoldStore,
    SupabaseHoldStore,
)


class _Resp:
    def __init__(self, data):
        self.data = data


class _HoldQuery:
    def __init__(self, client, action="select", payload=None):
        self.client = client
        self.action = action
        self.payload = payload or {}
        self.filters = {}
        self._limit = None
        self._range = None

    def select(self, cols="*"):
        return _HoldQuery(self.client, "select")

    def update(self, payload):
        return _HoldQuery(self.client, "update", payload)

    def upsert(self, body, **k):
        q = _HoldQuery(self.client, "upsert", body)
        q.upsert_kw = k
        return q

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def limit(self, n):
        self._limit = n
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def execute(self):
        matched = [
            r for r in self.client.rows
            if all(r.get(k) == v for k, v in self.filters.items())
        ]
        if self.action == "select":
            rows = matched
            if self._range:
                a, b = self._range
                rows = rows[a:b + 1]
            if self._limit is not None:
                rows = rows[: self._limit]
            return _Resp([dict(x) for x in rows])
        if self.action == "update":
            out = []
            for r in self.client.rows:
                if all(r.get(k) == v for k, v in self.filters.items()):
                    r.update(self.payload)
                    self.client.updates += 1
                    out.append(dict(r))
            return _Resp(out)
        if self.action == "upsert":
            body = dict(self.payload)
            key = (body.get("snapshot_id"), body.get("asset_id"), body.get("reason"))
            for r in self.client.rows:
                if (r.get("snapshot_id"), r.get("asset_id"), r.get("reason")) == key:
                    return _Resp([])
            body["id"] = self.client.next_id
            self.client.next_id += 1
            self.client.rows.append(body)
            return _Resp([dict(body)])
        return _Resp([])


class FakeHoldSB:
    def __init__(self, rows=None):
        self.rows = [dict(r) for r in (rows or [])]
        self.next_id = 1 + max((r.get("id") or 0) for r in self.rows) if self.rows else 1
        self.updates = 0

    def table(self, name):
        assert name == "kosha_safety_material_storage_holds"
        return _HoldQuery(self)


def _open_row(**k):
    row = {
        "id": 1,
        "snapshot_id": "snap-1",
        "asset_id": 6484,
        "material_id": "m1",
        "source_med_seq": "1",
        "reason": "SOURCE_ASSET_MULTI_MATCH",
        "expected_file_name": "a.pdf",
        "observed_files": [],
        "status": "OPEN",
        "resolution_note": None,
        "resolved_at": None,
    }
    row.update(k)
    return row


def _memory_with(row):
    h = MemoryHoldStore()
    h.record_open(
        snapshot_id=row["snapshot_id"],
        asset_id=row["asset_id"],
        material_id=row["material_id"],
        source_med_seq=row.get("source_med_seq"),
        reason=row["reason"],
        expected_file_name=row.get("expected_file_name"),
        observed_files=row.get("observed_files") or [],
    )
    return h


def _supabase_with(row, monkeypatch):
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "svc")
    sb = FakeHoldSB([row])
    return SupabaseHoldStore(sb=sb), sb


def _stores(monkeypatch, row=None):
    row = row or _open_row()
    mem = _memory_with(row)
    sb_store, sb = _supabase_with(row, monkeypatch)
    return [("memory", mem, None), ("supabase", sb_store, sb)]


def test_open_resolves_with_note_and_kst(monkeypatch):
    for name, store, sb in _stores(monkeypatch):
        out = store.resolve_open(
            snapshot_id="snap-1",
            asset_id=6484,
            reason="SOURCE_ASSET_MULTI_MATCH",
            resolution_note="STORED_AFTER_STABLE_IDENTITY_DEDUPE",
        )
        assert out["status"] == "RESOLVED", name
        row = out["row"]
        assert row["status"] == "RESOLVED", name
        assert row["resolution_note"] == "STORED_AFTER_STABLE_IDENTITY_DEDUPE", name
        assert row["resolved_at"].endswith("+09:00"), name
        assert "+00:00" not in row["resolved_at"][-6:], name
        assert store.open_rows("snap-1") == [], name
        if sb is not None:
            assert sb.updates == 1, name


def test_already_resolved_is_idempotent(monkeypatch):
    for name, store, sb in _stores(monkeypatch):
        first = store.resolve_open(
            snapshot_id="snap-1",
            asset_id=6484,
            reason="SOURCE_ASSET_MULTI_MATCH",
            resolution_note="STORED_AFTER_STABLE_IDENTITY_DEDUPE",
        )
        resolved_at = first["row"]["resolved_at"]
        second = store.resolve_open(
            snapshot_id="snap-1",
            asset_id=6484,
            reason="SOURCE_ASSET_MULTI_MATCH",
            resolution_note="STORED_AFTER_BINARY_RETRY",
        )
        assert second["status"] == "ALREADY_RESOLVED", name
        assert second["row"]["status"] == "RESOLVED", name
        assert second["row"]["resolved_at"] == resolved_at, name
        assert second["row"]["resolution_note"] == "STORED_AFTER_STABLE_IDENTITY_DEDUPE", name
        if name == "memory":
            assert len(store.rows) == 1
        else:
            assert len(sb.rows) == 1
            assert sb.updates == 1


def test_wrong_snapshot_rejected(monkeypatch):
    for name, store, sb in _stores(monkeypatch):
        try:
            store.resolve_open(
                snapshot_id="other",
                asset_id=6484,
                reason="SOURCE_ASSET_MULTI_MATCH",
                resolution_note="STORED_AFTER_STABLE_IDENTITY_DEDUPE",
            )
            assert False, name
        except HoldError as e:
            assert e.code == "HOLD_NOT_FOUND", name
        assert store.open_rows("snap-1")[0]["status"] == "OPEN", name
        if sb is not None:
            assert sb.updates == 0, name


def test_wrong_asset_rejected(monkeypatch):
    for name, store, _sb in _stores(monkeypatch):
        try:
            store.resolve_open(
                snapshot_id="snap-1",
                asset_id=9999,
                reason="SOURCE_ASSET_MULTI_MATCH",
                resolution_note="STORED_AFTER_STABLE_IDENTITY_DEDUPE",
            )
            assert False, name
        except HoldError as e:
            assert e.code == "HOLD_NOT_FOUND", name
        assert store.open_rows("snap-1")[0]["status"] == "OPEN", name


def test_wrong_reason_rejected(monkeypatch):
    for name, store, _sb in _stores(monkeypatch):
        try:
            store.resolve_open(
                snapshot_id="snap-1",
                asset_id=6484,
                reason="SOURCE_BINARY_UNAVAILABLE",
                resolution_note="STORED_AFTER_BINARY_RETRY",
            )
            assert False, name
        except HoldError as e:
            assert e.code == "HOLD_NOT_FOUND", name
        assert store.open_rows("snap-1")[0]["status"] == "OPEN", name


def test_missing_hold_rejected(monkeypatch):
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "svc")
    mem = MemoryHoldStore()
    sb = SupabaseHoldStore(sb=FakeHoldSB())
    for name, store in [("memory", mem), ("supabase", sb)]:
        try:
            store.resolve_open(
                snapshot_id="snap-1",
                asset_id=1,
                reason="SOURCE_ASSET_MULTI_MATCH",
                resolution_note="STORED_AFTER_STABLE_IDENTITY_DEDUPE",
            )
            assert False, name
        except HoldError as e:
            assert e.code == "HOLD_NOT_FOUND", name


def test_empty_note_rejected(monkeypatch):
    for name, store, _sb in _stores(monkeypatch):
        try:
            store.resolve_open(
                snapshot_id="snap-1",
                asset_id=6484,
                reason="SOURCE_ASSET_MULTI_MATCH",
                resolution_note="  ",
            )
            assert False, name
        except HoldError as e:
            assert e.code == "RESOLUTION_NOTE_REQUIRED", name
        assert store.open_rows("snap-1")[0]["status"] == "OPEN", name


def test_memory_supabase_contract_parity(monkeypatch):
    cases = [
        ("ok", dict(snapshot_id="snap-1", asset_id=6484, reason="SOURCE_ASSET_MULTI_MATCH",
                    resolution_note="STORED_AFTER_STABLE_IDENTITY_DEDUPE"), "RESOLVED"),
        ("miss", dict(snapshot_id="nope", asset_id=6484, reason="SOURCE_ASSET_MULTI_MATCH",
                      resolution_note="STORED_AFTER_STABLE_IDENTITY_DEDUPE"), "HOLD_NOT_FOUND"),
    ]
    for label, kwargs, expect in cases:
        mem = _memory_with(_open_row())
        sb_store, _sb = _supabase_with(_open_row(), monkeypatch)
        mem_status = _status(mem, kwargs)
        sb_status = _status(sb_store, kwargs)
        assert mem_status == sb_status == expect, label


def _status(store, kwargs):
    try:
        return store.resolve_open(**kwargs)["status"]
    except HoldError as e:
        return e.code
