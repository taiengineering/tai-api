"""
H02-API: occupancy capacity assessments router contract tests (B5).
FastAPI TestClient — no real DB.

AUTH-01: no auth → 401
AUTH-02: wrong factory → 403
AUTH-03: own factory → reaches store
PATCH-01: DRAFT PATCH → 200, segments replaced
PATCH-02: CONFIRMED/VOID PATCH → 422
CONFIRM-01: current["id"] wired to confirmed_by_user_id
CONFIRM-02: coverage_attested=false → 422
LIFECYCLE-01: DRAFT void → 422
LIFECYCLE-02: CONFIRMED void → 200
DELETE: no DELETE route → 404/405
RULESET-01: /occupancy-assessments/ruleset-version shape
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from fractions import Fraction
from unittest.mock import MagicMock, patch

from routers.occupancy_capacity_assessments import router
from routers.auth import get_current_user
from services.occupancy_capacity.legal_registry import RULESET_VERSION, get_ruleset_sha256

_FACTORY_ID = "fac-api-test-001"
_OTHER_FACTORY_ID = "fac-other-999"
_ASSESSMENT_ID = "11111111-2222-3333-4444-555555555555"
_USER_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
_MOCK_USER = {"id": _USER_ID, "email": "user@test.com"}

_VALID_SEGMENT = {
    "scope": "UNDERGROUND",
    "row_id": "A-1-가-1",
    "seat_count": 100,
}

_DRAFT_ROW = {
    "id": _ASSESSMENT_ID,
    "factory_id": _FACTORY_ID,
    "status": "DRAFT",
    "ruleset_version": RULESET_VERSION,
    "ruleset_sha256": get_ruleset_sha256(),
    "input_segments": [],
    "coverage_attested": False,
    "result_numerator": None,
    "result_denominator": None,
    "calculation_trace": None,
}

_DRAFT_ROW_WITH_CALC = {
    **_DRAFT_ROW,
    "result_numerator": "100",
    "result_denominator": "1",
    "calculation_trace": "{}",
}

_CONFIRMED_ROW = {
    **_DRAFT_ROW_WITH_CALC,
    "status": "CONFIRMED",
    "coverage_attested": True,
    "confirmed_by_user_id": _USER_ID,
    "confirmed_at": "2026-10-06T00:00:00Z",
    "voided_at": None,
}

_VOID_ROW = {
    **_CONFIRMED_ROW,
    "status": "VOID",
    "voided_at": "2026-10-06T01:00:00Z",
}


@pytest.fixture(autouse=True, scope="module")
def _patch_supabase():
    with patch("routers.occupancy_capacity_assessments.get_supabase", return_value=MagicMock()):
        yield


@pytest.fixture(scope="module")
def authed_client():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: _MOCK_USER
    return TestClient(app, raise_server_exceptions=False)


class TestApiAuth:
    def test_no_auth_returns_401(self):
        """AUTH-01: missing auth → 401."""
        app = FastAPI()
        app.include_router(router)

        def _raise_401():
            raise HTTPException(status_code=401, detail="Not authenticated")

        app.dependency_overrides[get_current_user] = _raise_401
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            f"/factories/{_FACTORY_ID}/occupancy-assessments",
            json={"input_segments": [_VALID_SEGMENT]},
        )
        assert response.status_code == 401

    def test_wrong_factory_returns_403(self, authed_client):
        """AUTH-02: _ensure_factory_own raises HTTPException → 403."""
        with patch(
            "routers.occupancy_capacity_assessments._ensure_factory_own",
            side_effect=HTTPException(status_code=403, detail="Not your factory"),
        ):
            response = authed_client.post(
                f"/factories/{_OTHER_FACTORY_ID}/occupancy-assessments",
                json={"input_segments": [_VALID_SEGMENT]},
            )
        assert response.status_code == 403

    def test_own_factory_reaches_store(self, authed_client):
        """AUTH-03: own factory → create_draft called."""
        with patch("routers.occupancy_capacity_assessments._ensure_factory_own"), \
             patch("routers.occupancy_capacity_assessments.create_draft", return_value=_DRAFT_ROW) as mock_create, \
             patch("routers.occupancy_capacity_assessments.attach_calculation", return_value=_DRAFT_ROW_WITH_CALC):
            response = authed_client.post(
                f"/factories/{_FACTORY_ID}/occupancy-assessments",
                json={"input_segments": [_VALID_SEGMENT]},
            )
        assert response.status_code == 200
        mock_create.assert_called_once()


class TestApiPatch:
    def test_draft_patch_succeeds(self, authed_client):
        """PATCH-01: DRAFT assessment patched — update_assessment_draft called."""
        with patch("routers.occupancy_capacity_assessments._ensure_factory_own"), \
             patch("routers.occupancy_capacity_assessments.get_assessment", return_value=_DRAFT_ROW), \
             patch("routers.occupancy_capacity_assessments.update_assessment_draft", return_value=_DRAFT_ROW) as mock_update, \
             patch("routers.occupancy_capacity_assessments.attach_calculation", return_value=_DRAFT_ROW_WITH_CALC):
            response = authed_client.patch(
                f"/factories/{_FACTORY_ID}/occupancy-assessments/{_ASSESSMENT_ID}",
                json={"input_segments": [_VALID_SEGMENT]},
            )
        assert response.status_code == 200
        mock_update.assert_called_once()

    def test_confirmed_patch_returns_422(self, authed_client):
        """PATCH-02: CONFIRMED → 422."""
        with patch("routers.occupancy_capacity_assessments._ensure_factory_own"), \
             patch("routers.occupancy_capacity_assessments.get_assessment", return_value=_CONFIRMED_ROW):
            response = authed_client.patch(
                f"/factories/{_FACTORY_ID}/occupancy-assessments/{_ASSESSMENT_ID}",
                json={"input_segments": [_VALID_SEGMENT]},
            )
        assert response.status_code == 422

    def test_void_patch_returns_422(self, authed_client):
        """PATCH-02 (VOID variant): VOID → 422."""
        with patch("routers.occupancy_capacity_assessments._ensure_factory_own"), \
             patch("routers.occupancy_capacity_assessments.get_assessment", return_value=_VOID_ROW):
            response = authed_client.patch(
                f"/factories/{_FACTORY_ID}/occupancy-assessments/{_ASSESSMENT_ID}",
                json={"input_segments": [_VALID_SEGMENT]},
            )
        assert response.status_code == 422


class TestApiConfirm:
    def test_confirm_wires_user_id(self, authed_client):
        """CONFIRM-01: current["id"] is passed as confirmed_by_user_id."""
        with patch("routers.occupancy_capacity_assessments._ensure_factory_own"), \
             patch("routers.occupancy_capacity_assessments.get_assessment", return_value=_DRAFT_ROW_WITH_CALC), \
             patch("routers.occupancy_capacity_assessments.confirm_assessment", return_value=_CONFIRMED_ROW) as mock_confirm:
            response = authed_client.post(
                f"/factories/{_FACTORY_ID}/occupancy-assessments/{_ASSESSMENT_ID}/confirm",
                json={"coverage_attested": True},
            )
        assert response.status_code == 200
        call_kwargs = mock_confirm.call_args.kwargs
        assert call_kwargs["confirmed_by_user_id"] == _USER_ID

    def test_confirm_coverage_attested_false_returns_422(self, authed_client):
        """CONFIRM-02: coverage_attested=false → store raises ValueError → 422."""
        with patch("routers.occupancy_capacity_assessments._ensure_factory_own"), \
             patch("routers.occupancy_capacity_assessments.get_assessment", return_value=_DRAFT_ROW_WITH_CALC), \
             patch("routers.occupancy_capacity_assessments.confirm_assessment",
                   side_effect=ValueError("coverage_attested must be True")):
            response = authed_client.post(
                f"/factories/{_FACTORY_ID}/occupancy-assessments/{_ASSESSMENT_ID}/confirm",
                json={"coverage_attested": False},
            )
        assert response.status_code == 422


class TestApiLifecycle:
    def test_draft_void_returns_422(self, authed_client):
        """LIFECYCLE-01: DRAFT → void forbidden → 422."""
        with patch("routers.occupancy_capacity_assessments._ensure_factory_own"), \
             patch("routers.occupancy_capacity_assessments.get_assessment", return_value=_DRAFT_ROW), \
             patch("routers.occupancy_capacity_assessments.void_assessment",
                   side_effect=ValueError("Only CONFIRMED assessments can be voided")):
            response = authed_client.post(
                f"/factories/{_FACTORY_ID}/occupancy-assessments/{_ASSESSMENT_ID}/void",
            )
        assert response.status_code == 422

    def test_confirmed_void_returns_200(self, authed_client):
        """LIFECYCLE-02: CONFIRMED → void → 200."""
        with patch("routers.occupancy_capacity_assessments._ensure_factory_own"), \
             patch("routers.occupancy_capacity_assessments.get_assessment", return_value=_CONFIRMED_ROW), \
             patch("routers.occupancy_capacity_assessments.void_assessment", return_value=_VOID_ROW):
            response = authed_client.post(
                f"/factories/{_FACTORY_ID}/occupancy-assessments/{_ASSESSMENT_ID}/void",
            )
        assert response.status_code == 200
        assert response.json()["status"] == "VOID"


class TestApiDelete:
    def test_no_delete_route(self, authed_client):
        """DELETE route intentionally absent — 404 or 405."""
        response = authed_client.delete(
            f"/factories/{_FACTORY_ID}/occupancy-assessments/{_ASSESSMENT_ID}",
        )
        assert response.status_code in (404, 405)


class TestApiRulesetMeta:
    def test_ruleset_version_shape(self, authed_client):
        """RULESET-01: /occupancy-assessments/ruleset-version returns expected keys."""
        response = authed_client.get("/occupancy-assessments/ruleset-version")
        assert response.status_code == 200
        data = response.json()
        assert "ruleset_version" in data
        assert "ruleset_sha256" in data
        assert data["ruleset_version"] == RULESET_VERSION
        assert len(data["ruleset_sha256"]) == 64  # SHA-256 hex digest
