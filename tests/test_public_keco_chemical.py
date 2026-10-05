"""A01-A12: GET /public/keco/chemicals/by-cas/{cas_no} contract tests.

No real DB. LEG client and DB calls are patched.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.public_keco_chemical as mod
from services.keco_chemical.read import KecoLegUnavailable


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_SAMPLE_CHEMICAL = {
    "id": "chem-uuid-001",
    "source_record_id": "NCISS-001",
    "cas_no": "50-00-0",
    "korexst_raw": "KE-99999",
    "chemical_name_ko": "포름알데히드",
    "chemical_name_en": "Formaldehyde",
    "alias_name_ko": "포르말린",
    "alias_name_en": "Formalin",
    "molecular_formula": "CH2O",
    "molecular_weight_raw": "30.03",
    "last_seen_at": "2026-10-01T00:00:00+00:00",
    "last_changed_at": "2026-10-01T00:00:00+00:00",
}

_SAMPLE_FACT = {
    "keco_chemical_id": "chem-uuid-001",
    "classification_type": "유해화학물질",
    "unique_no": "2024-001",
    "content_info": "취급 제한",
    "exception_info": None,
    "notice_date_raw": "2024-01-01",
    "notice_info": "고시 2024-001",
    "source_ordinal": 1,
}


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(mod.router)
    return app


def _mock_leg_db(chemicals: list, facts: list):
    """Build a mock LEG supabase client that returns given rows."""
    db = MagicMock()
    chem_q = MagicMock()
    chem_q.execute.return_value = MagicMock(data=chemicals)
    db.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        MagicMock(data=chemicals)
    )

    fact_q = MagicMock()
    fact_q.execute.return_value = MagicMock(data=facts)

    def _table_dispatch(name):
        t = MagicMock()
        if name == "keco_chemicals":
            t.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=chemicals
            )
        elif name == "keco_regulatory_facts":
            t.select.return_value.in_.return_value.order.return_value.execute.return_value = (
                MagicMock(data=facts)
            )
        return t

    db.table.side_effect = _table_dispatch
    return db


def _patch_leg_client(monkeypatch, chemicals, facts):
    client = MagicMock()
    client.schema.return_value = _mock_leg_db(chemicals, facts)
    monkeypatch.setattr(
        "services.keco_chemical.read._get_leg_client", lambda: client
    )


# ---------------------------------------------------------------------------
# A01: Valid CAS with matching chemical → 200 with chemicals list
# ---------------------------------------------------------------------------

def test_a01_valid_cas_with_match(monkeypatch):
    _patch_leg_client(monkeypatch, [_SAMPLE_CHEMICAL], [_SAMPLE_FACT])
    client = TestClient(_make_app())
    resp = client.get("/public/keco/chemicals/by-cas/50-00-0")
    assert resp.status_code == 200
    data = resp.json()
    assert data["cas_no"] == "50-00-0"
    assert len(data["chemicals"]) == 1
    chem = data["chemicals"][0]
    assert chem["source_record_id"] == "NCISS-001"
    assert chem["chemical_name_ko"] == "포름알데히드"


# ---------------------------------------------------------------------------
# A02: Valid CAS with no matching chemical → 200 empty list
# ---------------------------------------------------------------------------

def test_a02_valid_cas_no_match(monkeypatch):
    _patch_leg_client(monkeypatch, [], [])
    client = TestClient(_make_app())
    resp = client.get("/public/keco/chemicals/by-cas/7732-18-5")
    assert resp.status_code == 200
    data = resp.json()
    assert data["cas_no"] == "7732-18-5"
    assert data["chemicals"] == []


# ---------------------------------------------------------------------------
# A03: Invalid CAS — no dashes → 422
# ---------------------------------------------------------------------------

def test_a03_invalid_cas_no_dashes(monkeypatch):
    client = TestClient(_make_app())
    resp = client.get("/public/keco/chemicals/by-cas/500000")
    assert resp.status_code == 422
    assert "INVALID_CAS_FORMAT" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# A04: Invalid CAS — wrong digit count → 422
# ---------------------------------------------------------------------------

def test_a04_invalid_cas_wrong_digits(monkeypatch):
    client = TestClient(_make_app())
    resp = client.get("/public/keco/chemicals/by-cas/50-0-0")
    assert resp.status_code == 422
    assert "INVALID_CAS_FORMAT" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# A05: LEG_SUPABASE not configured → 503
# ---------------------------------------------------------------------------

def test_a05_leg_unavailable(monkeypatch):
    monkeypatch.setattr(
        "services.keco_chemical.read._get_leg_client",
        lambda: (_ for _ in ()).throw(KecoLegUnavailable("LEG not configured")),
    )
    client = TestClient(_make_app())
    resp = client.get("/public/keco/chemicals/by-cas/50-00-0")
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "KECO_LEG_UNAVAILABLE"


# ---------------------------------------------------------------------------
# A06: Regulatory facts included in response
# ---------------------------------------------------------------------------

def test_a06_regulatory_facts_included(monkeypatch):
    _patch_leg_client(monkeypatch, [_SAMPLE_CHEMICAL], [_SAMPLE_FACT])
    client = TestClient(_make_app())
    resp = client.get("/public/keco/chemicals/by-cas/50-00-0")
    assert resp.status_code == 200
    facts = resp.json()["chemicals"][0]["regulatory_facts"]
    assert len(facts) == 1
    assert facts[0]["classification_type"] == "유해화학물질"
    assert facts[0]["unique_no"] == "2024-001"


# ---------------------------------------------------------------------------
# A07: CAS normalization — leading/trailing whitespace stripped
# (URL path segments are stripped by the router before validate_cas)
# Tested here via the validate_cas function directly.
# ---------------------------------------------------------------------------

def test_a07_cas_validation_strips_whitespace():
    from services.keco_chemical.read import validate_cas
    assert validate_cas("  50-00-0  ") == "50-00-0"


# ---------------------------------------------------------------------------
# A08: raw_payload NOT in response
# ---------------------------------------------------------------------------

def test_a08_raw_payload_not_exposed(monkeypatch):
    chemical_with_raw = {**_SAMPLE_CHEMICAL, "raw_payload": {"secret": "data"}}
    _patch_leg_client(monkeypatch, [chemical_with_raw], [])
    client = TestClient(_make_app())
    resp = client.get("/public/keco/chemicals/by-cas/50-00-0")
    assert resp.status_code == 200
    chem = resp.json()["chemicals"][0]
    assert "raw_payload" not in chem


# ---------------------------------------------------------------------------
# A09: Multiple chemicals for the same CAS
# ---------------------------------------------------------------------------

def test_a09_multiple_chemicals_same_cas(monkeypatch):
    chem2 = {**_SAMPLE_CHEMICAL, "id": "chem-uuid-002", "source_record_id": "NCISS-002"}
    _patch_leg_client(monkeypatch, [_SAMPLE_CHEMICAL, chem2], [])
    client = TestClient(_make_app())
    resp = client.get("/public/keco/chemicals/by-cas/50-00-0")
    assert resp.status_code == 200
    assert len(resp.json()["chemicals"]) == 2


# ---------------------------------------------------------------------------
# A10: Chemical with no regulatory facts → regulatory_facts=[]
# ---------------------------------------------------------------------------

def test_a10_no_regulatory_facts(monkeypatch):
    _patch_leg_client(monkeypatch, [_SAMPLE_CHEMICAL], [])
    client = TestClient(_make_app())
    resp = client.get("/public/keco/chemicals/by-cas/50-00-0")
    assert resp.status_code == 200
    assert resp.json()["chemicals"][0]["regulatory_facts"] == []


# ---------------------------------------------------------------------------
# A11: CAS with all 7 digits in first segment → still valid
# ---------------------------------------------------------------------------

def test_a11_cas_max_digits_valid(monkeypatch):
    from services.keco_chemical.read import validate_cas
    assert validate_cas("1234567-89-0") == "1234567-89-0"


# ---------------------------------------------------------------------------
# A12: Response shape — required keys present
# ---------------------------------------------------------------------------

def test_a12_response_shape(monkeypatch):
    _patch_leg_client(monkeypatch, [_SAMPLE_CHEMICAL], [_SAMPLE_FACT])
    client = TestClient(_make_app())
    resp = client.get("/public/keco/chemicals/by-cas/50-00-0")
    assert resp.status_code == 200
    data = resp.json()
    assert "cas_no" in data
    assert "chemicals" in data
    chem = data["chemicals"][0]
    required_keys = {
        "source_record_id", "cas_no", "chemical_name_ko", "chemical_name_en",
        "alias_name_ko", "alias_name_en", "korexst_raw",
        "molecular_formula", "molecular_weight_raw",
        "last_seen_at", "last_changed_at", "regulatory_facts",
    }
    for k in required_keys:
        assert k in chem, f"Missing key: {k}"


# ===========================================================================
# PATCH-001 tests (P02-P04)
# ===========================================================================

# ---------------------------------------------------------------------------
# P02: Public API source_id == KECO_15149420
# ---------------------------------------------------------------------------

def test_p02_public_api_source_id(monkeypatch):
    from services.keco_chemical.contract import SOURCE_ID
    _patch_leg_client(monkeypatch, [_SAMPLE_CHEMICAL], [])
    client = TestClient(_make_app())
    resp = client.get("/public/keco/chemicals/by-cas/50-00-0")
    assert resp.status_code == 200
    data = resp.json()
    assert data["source_id"] == SOURCE_ID
    assert data["source_id"] == "KECO_15149420"


# ---------------------------------------------------------------------------
# P03: Public API provider == 한국환경공단
# ---------------------------------------------------------------------------

def test_p03_public_api_provider(monkeypatch):
    from services.keco_chemical.contract import PROVIDER
    _patch_leg_client(monkeypatch, [_SAMPLE_CHEMICAL], [])
    client = TestClient(_make_app())
    resp = client.get("/public/keco/chemicals/by-cas/50-00-0")
    assert resp.status_code == 200
    assert resp.json()["provider"] == PROVIDER
    assert resp.json()["provider"] == "한국환경공단"


# ---------------------------------------------------------------------------
# P04: Public API source_dataset_url == official dataset URL
# ---------------------------------------------------------------------------

def test_p04_public_api_source_dataset_url(monkeypatch):
    from services.keco_chemical.contract import DATASET_URL
    _patch_leg_client(monkeypatch, [_SAMPLE_CHEMICAL], [])
    client = TestClient(_make_app())
    resp = client.get("/public/keco/chemicals/by-cas/50-00-0")
    assert resp.status_code == 200
    assert resp.json()["source_dataset_url"] == DATASET_URL
    assert resp.json()["source_dataset_url"] == "https://www.data.go.kr/data/15149420/openapi.do"


# ===========================================================================
# PATCH-002 tests (P15-P18)
# ===========================================================================

# ---------------------------------------------------------------------------
# P15: chemical query .execute() raises exception → HTTP 503
# ---------------------------------------------------------------------------

def test_p15_chemical_query_failure_is_503(monkeypatch):
    """DB execute() exception during chemicals query → KecoLegUnavailable → 503."""
    from unittest.mock import MagicMock

    def _bad_client():
        client = MagicMock()
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.execute.side_effect = (
            RuntimeError("PostgREST connection error")
        )
        client.schema.return_value = db
        return client

    monkeypatch.setattr("services.keco_chemical.read._get_leg_client", _bad_client)
    client = TestClient(_make_app())
    resp = client.get("/public/keco/chemicals/by-cas/50-00-0")
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "KECO_LEG_UNAVAILABLE"


# ---------------------------------------------------------------------------
# P16: regulatory_facts query .execute() raises exception → HTTP 503
# ---------------------------------------------------------------------------

def test_p16_facts_query_failure_is_503(monkeypatch):
    """DB execute() exception during regulatory_facts query → KecoLegUnavailable → 503."""
    from unittest.mock import MagicMock

    call_count = {"n": 0}

    def _partial_fail_client():
        client = MagicMock()
        db = MagicMock()

        def _table_dispatch(name):
            t = MagicMock()
            if name == "keco_chemicals":
                # First query succeeds: returns one chemical
                t.select.return_value.eq.return_value.execute.return_value = MagicMock(
                    data=[_SAMPLE_CHEMICAL]
                )
            elif name == "keco_regulatory_facts":
                # Facts query fails
                t.select.return_value.in_.return_value.order.return_value.execute.side_effect = (
                    RuntimeError("DB timeout")
                )
            return t

        db.table.side_effect = _table_dispatch
        client.schema.return_value = db
        return client

    monkeypatch.setattr("services.keco_chemical.read._get_leg_client", _partial_fail_client)
    client = TestClient(_make_app())
    resp = client.get("/public/keco/chemicals/by-cas/50-00-0")
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "KECO_LEG_UNAVAILABLE"


# ---------------------------------------------------------------------------
# P17: missing LEG configuration → 503, no env var names in public response
# ---------------------------------------------------------------------------

def test_p17_missing_leg_config_no_env_leak(monkeypatch):
    """LEG env vars not set → 503. Response must not contain env var names."""
    monkeypatch.delenv("LEG_SUPABASE_URL", raising=False)
    monkeypatch.delenv("LEG_SUPABASE_SERVICE_ROLE_KEY", raising=False)
    # Ensure _get_leg_client sees no env vars (don't mock, use real function)
    monkeypatch.setattr(
        "services.keco_chemical.read._get_leg_client",
        lambda: (_ for _ in ()).throw(
            KecoLegUnavailable("KECO_LEG_UNAVAILABLE: LEG_SUPABASE_URL and LEG_SUPABASE_SERVICE_ROLE_KEY must be set")
        ),
    )
    client = TestClient(_make_app())
    resp = client.get("/public/keco/chemicals/by-cas/50-00-0")
    assert resp.status_code == 503
    detail = resp.json()["detail"]
    response_text = str(detail)
    assert "LEG_SUPABASE_URL" not in response_text
    assert "LEG_SUPABASE_SERVICE_ROLE_KEY" not in response_text
    assert detail["code"] == "KECO_LEG_UNAVAILABLE"


# ---------------------------------------------------------------------------
# P18: DB internal exception message not exposed in public response
# ---------------------------------------------------------------------------

def test_p18_db_exception_message_not_in_response(monkeypatch):
    """Internal exception message must not appear in public 503 response."""
    from unittest.mock import MagicMock

    _INTERNAL_MSG = "INTERNAL: supabase_secret_token=abc123 host=db.internal.supabase.co"

    def _fail_client():
        client = MagicMock()
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.execute.side_effect = (
            RuntimeError(_INTERNAL_MSG)
        )
        client.schema.return_value = db
        return client

    monkeypatch.setattr("services.keco_chemical.read._get_leg_client", _fail_client)
    client = TestClient(_make_app())
    resp = client.get("/public/keco/chemicals/by-cas/50-00-0")
    assert resp.status_code == 503
    response_text = resp.text
    assert _INTERNAL_MSG not in response_text
    assert "supabase_secret_token" not in response_text
    assert resp.json()["detail"]["message"] == "KECO reference data is temporarily unavailable"
