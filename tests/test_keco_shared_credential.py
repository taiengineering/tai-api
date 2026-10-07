"""SC-01 ~ SC-14 — KECO shared data.go.kr credential contract tests.

Verifies that DATA_GO_KR_SERVICE_KEY is the canonical key and
KECO_API_SERVICE_KEY is a legacy fallback alias.

All tests use mocks — zero external API calls.
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from services.keco_chemical.contract import (
    CANONICAL_SERVICE_KEY_ENV,
    LEGACY_SERVICE_KEY_ENV,
    SERVICE_KEY_ENV,
)
from services.keco_chemical.client import _get_service_key, KecoNoServiceKeyError
from services.public_data_sync.adapters.keco_chemical import KecoChemicalAdapter
from services.public_data_sync.errors import PreflightError


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

_DB_ENV = {
    "LEG_SUPABASE_URL": "https://leg.supabase.co",
    "LEG_SUPABASE_SERVICE_ROLE_KEY": "leg_key",
    "KECO_REQUEST_BUDGET": "9000",
    "KECO_REFRESH_BATCH_SIZE": "3000",
}

from datetime import datetime, timezone
from uuid import uuid4
from services.public_data_sync.contracts import RunContext, TriggerKind


def _ctx() -> RunContext:
    return RunContext(
        run_id=str(uuid4()),
        source_id="KECO_15149420",
        trigger=TriggerKind.MANUAL,
        started_at=datetime.now(timezone.utc),
    )


# ─────────────────────────────────────────────────────────────────────────────
# SC-01 — canonical only → _get_service_key returns canonical value
# ─────────────────────────────────────────────────────────────────────────────

def test_sc_01_canonical_only():
    env = {CANONICAL_SERVICE_KEY_ENV: "CANONICAL_FAKE"}
    with patch.dict(os.environ, env, clear=True):
        assert _get_service_key() == "CANONICAL_FAKE"


# ─────────────────────────────────────────────────────────────────────────────
# SC-02 — legacy only → _get_service_key returns legacy value
# ─────────────────────────────────────────────────────────────────────────────

def test_sc_02_legacy_only():
    env = {LEGACY_SERVICE_KEY_ENV: "LEGACY_FAKE"}
    with patch.dict(os.environ, env, clear=True):
        assert _get_service_key() == "LEGACY_FAKE"


# ─────────────────────────────────────────────────────────────────────────────
# SC-03 — both present → canonical takes precedence
# ─────────────────────────────────────────────────────────────────────────────

def test_sc_03_canonical_precedence():
    env = {
        CANONICAL_SERVICE_KEY_ENV: "CANONICAL_FAKE",
        LEGACY_SERVICE_KEY_ENV: "LEGACY_FAKE",
    }
    with patch.dict(os.environ, env, clear=True):
        assert _get_service_key() == "CANONICAL_FAKE"


# ─────────────────────────────────────────────────────────────────────────────
# SC-04 — both absent → KecoNoServiceKeyError
# ─────────────────────────────────────────────────────────────────────────────

def test_sc_04_both_absent_raises():
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(KecoNoServiceKeyError):
            from services.keco_chemical.client import KecoChemicalClient
            c = KecoChemicalClient()
            c._key()


# ─────────────────────────────────────────────────────────────────────────────
# SC-05 — adapter preflight: canonical only → PASS
# ─────────────────────────────────────────────────────────────────────────────

def test_sc_05_adapter_canonical_only():
    env = {CANONICAL_SERVICE_KEY_ENV: "CANONICAL_FAKE", **_DB_ENV}
    adapter = KecoChemicalAdapter()
    with patch.dict(os.environ, env, clear=True):
        adapter.preflight(_ctx())  # must not raise


# ─────────────────────────────────────────────────────────────────────────────
# SC-06 — adapter preflight: legacy only → PASS
# ─────────────────────────────────────────────────────────────────────────────

def test_sc_06_adapter_legacy_only():
    env = {LEGACY_SERVICE_KEY_ENV: "LEGACY_FAKE", **_DB_ENV}
    adapter = KecoChemicalAdapter()
    with patch.dict(os.environ, env, clear=True):
        adapter.preflight(_ctx())  # must not raise


# ─────────────────────────────────────────────────────────────────────────────
# SC-07 — adapter preflight: both absent → PreflightError
# ─────────────────────────────────────────────────────────────────────────────

def test_sc_07_adapter_no_key():
    env = {k: v for k, v in _DB_ENV.items()}
    adapter = KecoChemicalAdapter()
    with patch.dict(os.environ, env, clear=True):
        with pytest.raises(PreflightError):
            adapter.preflight(_ctx())


# ─────────────────────────────────────────────────────────────────────────────
# SC-08 — probe: canonical only → _has_service_key() true
# ─────────────────────────────────────────────────────────────────────────────

def test_sc_08_probe_canonical_only():
    from services.keco_chemical.probe import _has_service_key
    env = {CANONICAL_SERVICE_KEY_ENV: "CANONICAL_FAKE"}
    with patch.dict(os.environ, env, clear=True):
        assert _has_service_key() is True


# ─────────────────────────────────────────────────────────────────────────────
# SC-09 — probe: legacy only → _has_service_key() true
# ─────────────────────────────────────────────────────────────────────────────

def test_sc_09_probe_legacy_only():
    from services.keco_chemical.probe import _has_service_key
    env = {LEGACY_SERVICE_KEY_ENV: "LEGACY_FAKE"}
    with patch.dict(os.environ, env, clear=True):
        assert _has_service_key() is True


# ─────────────────────────────────────────────────────────────────────────────
# SC-10 — probe: both absent → _has_service_key() false
# ─────────────────────────────────────────────────────────────────────────────

def test_sc_10_probe_missing():
    from services.keco_chemical.probe import _has_service_key
    with patch.dict(os.environ, {}, clear=True):
        assert _has_service_key() is False


# ─────────────────────────────────────────────────────────────────────────────
# SC-11 — collect: canonical only → _require_service_key() passes
# ─────────────────────────────────────────────────────────────────────────────

def test_sc_11_collect_canonical_only(monkeypatch):
    monkeypatch.setenv(CANONICAL_SERVICE_KEY_ENV, "CANONICAL_FAKE")
    monkeypatch.delenv(LEGACY_SERVICE_KEY_ENV, raising=False)

    from services.keco_chemical.collect import _require_service_key
    _require_service_key()  # must not call sys.exit


# ─────────────────────────────────────────────────────────────────────────────
# SC-12 — collect: legacy only → _require_service_key() passes
# ─────────────────────────────────────────────────────────────────────────────

def test_sc_12_collect_legacy_only(monkeypatch):
    monkeypatch.setenv(LEGACY_SERVICE_KEY_ENV, "LEGACY_FAKE")
    monkeypatch.delenv(CANONICAL_SERVICE_KEY_ENV, raising=False)

    from services.keco_chemical.collect import _require_service_key
    _require_service_key()  # must not call sys.exit


# ─────────────────────────────────────────────────────────────────────────────
# SC-13 — collect: both absent → sys.exit(1)
# ─────────────────────────────────────────────────────────────────────────────

def test_sc_13_collect_missing(monkeypatch):
    monkeypatch.delenv(CANONICAL_SERVICE_KEY_ENV, raising=False)
    monkeypatch.delenv(LEGACY_SERVICE_KEY_ENV, raising=False)

    from services.keco_chemical.collect import _require_service_key
    with pytest.raises(SystemExit) as exc_info:
        _require_service_key()
    assert exc_info.value.code == 1


# ─────────────────────────────────────────────────────────────────────────────
# SC-14 — registry: credential_pool=DATA_GO_KR, rate_limit_group=KECO
# ─────────────────────────────────────────────────────────────────────────────

def test_sc_14_registry_credential_pool():
    from services.public_data_sync.registry import registry
    spec = registry.get("KECO_15149420")
    assert spec.credential_pool == "DATA_GO_KR"
    assert spec.rate_limit_group == "KECO"
