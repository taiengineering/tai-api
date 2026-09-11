"""WP-1C-5B Gate-1 SupabaseVersionStore RPC adapter tests. No live R2."""
from __future__ import annotations

import os

import pytest

from services.kosha_safety_materials.storage.version_service import (
    ALLOWED_PROMOTION,
    RPC_FUNCTION,
    RPC_PARAM_NAMES,
    MemoryVersionStore,
    SupabaseVersionStore,
    VersionError,
    assert_production_versions,
    parse_promotion_result,
    payload_to_rpc,
)


class _Resp:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return self


class FakeSB:
    def __init__(self, data=None, exc=None):
        self.data = data if data is not None else {"status": "NEW_VERSION", "id": 3, "dml": 1}
        self.exc = exc
        self.calls = []

    def rpc(self, name, params):
        self.calls.append((name, params))
        if self.exc:
            raise self.exc

        class _Q:
            def __init__(self, outer):
                self.outer = outer

            def execute(self):
                return _Resp(self.outer.data)

        return _Q(self)


def _payload():
    return {
        "asset_id": 1,
        "material_id": "m1",
        "source_asset_key": "a" * 64,
        "content_checksum": "b" * 64,
        "storage_provider": "R2",
        "storage_bucket": "tai-kosha-originals",
        "storage_key": "kosha/x",
        "source_file_name": "a.pdf",
        "source_content_type": "application/pdf",
        "source_file_size": 10,
        "source_fetched_at": "2026-09-11T00:00:00+00:00",
        "is_derivative": False,
        "license_observed_at": "2026-09-11T00:00:00+00:00",
        "license_observed_type": "1",
        "license_name": None,
        "license_source_url": None,
        "storage_basis": "KOGL",
        "source_med_seq": "1",
        "source_url": "https://portal.kosha.or.kr/x",
        "med_gonggongnuri_raw": "01",
        "med_gonggongnuri_nm_raw": None,
    }


def test_rpc_function_and_param_names():
    assert RPC_FUNCTION == "promote_kosha_safety_material_asset_version"
    params = payload_to_rpc(_payload())
    assert set(params) == set(RPC_PARAM_NAMES)
    assert params["p_is_derivative"] is False
    assert params["p_material_id"] == "m1"


def test_parse_allowed_statuses():
    for st in ("NO_CHANGE", "NEW_VERSION", "PROMOTED_EXISTING_VERSION"):
        p = parse_promotion_result({"status": st, "id": 1, "dml": 0})
        assert p["status"] == st
        assert st in ALLOWED_PROMOTION
    try:
        parse_promotion_result({"status": "WEIRD"})
        assert False
    except VersionError as e:
        assert e.code == "UNKNOWN_PROMOTION_RESULT"


def test_rpc_promote_and_exception(monkeypatch):
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "svc")
    sb = FakeSB({"status": "NO_CHANGE", "id": 1, "dml": 0})
    st = SupabaseVersionStore(sb=sb)
    r = st.promote(_payload())
    assert r["status"] == "NO_CHANGE"
    assert sb.calls[0][0] == RPC_FUNCTION
    assert set(sb.calls[0][1]) == set(RPC_PARAM_NAMES)

    sb2 = FakeSB(exc=RuntimeError("boom"))
    st2 = SupabaseVersionStore(sb=sb2)
    try:
        st2.promote(_payload())
        assert False
    except VersionError as e:
        assert e.code == "DB_PROMOTION_FAILED"


def test_memory_store_forbidden_in_production():
    try:
        assert_production_versions(MemoryVersionStore())
        assert False
    except VersionError as e:
        assert e.code == "MEMORY_STORE_FORBIDDEN"
    monkeypatch_ok = type("Prod", (), {})()
    assert_production_versions(monkeypatch_ok)
