"""
tests/test_document_link_review_write.py
WO-TAI-DOC-WP03B-IMPLEMENT-001

Contract tests: T01-T24
Write-path coverage: propose / submit-review / decision / get-link-detail
No live DB. supabase-py client is mocked.
DB writes: 0
"""

from __future__ import annotations

import os
import sys
import unittest
from typing import Any
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.document_link_review_write import (
    DocumentLinkWriteError,
    propose_link,
    transition_link,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_SAAS_UUID = "aaaaaaaa-0000-0000-0000-000000000001"
_REF_UUID  = "bbbbbbbb-0000-0000-0000-000000000002"
_LINK_ID   = "cccccccc-0000-0000-0000-000000000003"
_ACTOR_ID  = "user-001"
_APPROVAL  = "WO-TAI-DOC-WP03B-APPROVE-001"
_RETIRE    = "WO-TAI-DOC-WP03B-RETIRE-001"

_PROPOSED_ROW = {
    "id":                  _LINK_ID,
    "saas_catalog_id":     _SAAS_UUID,
    "reference_form_id":   _REF_UUID,
    "relation_type":       "SAME_DOCUMENT_CANDIDATE",
    "review_state":        "PROPOSED",
    "evidence_note":       "test evidence",
    "reviewed_by":         None,
    "reviewed_at":         None,
    "owner_approval_ref":  None,
    "version":             1,
    "created_at":          "2026-10-21T00:00:00Z",
    "updated_at":          "2026-10-21T00:00:00Z",
}


def _ok(data: dict) -> MagicMock:
    sb = MagicMock()
    sb.rpc.return_value.execute.return_value.data = {"ok": True, "data": data}
    return sb


def _err(code: str, detail: str = "") -> MagicMock:
    sb = MagicMock()
    sb.rpc.return_value.execute.return_value.data = {
        "ok": False,
        "error": code,
        "detail": detail,
    }
    return sb


def _raw(value: Any) -> MagicMock:
    sb = MagicMock()
    sb.rpc.return_value.execute.return_value.data = value
    return sb


# ---------------------------------------------------------------------------
# T01-T04: propose_link — service layer
# ---------------------------------------------------------------------------

class TestT01ProposeLinkSuccess(unittest.TestCase):
    def test_returns_row_on_ok(self):
        sb = _ok(_PROPOSED_ROW)
        row = propose_link(
            sb,
            actor_id=_ACTOR_ID,
            saas_catalog_id=_SAAS_UUID,
            reference_form_id=_REF_UUID,
            relation_type="SAME_DOCUMENT_CANDIDATE",
            evidence_note="test evidence",
        )
        self.assertEqual(row["id"], _LINK_ID)
        self.assertEqual(row["review_state"], "PROPOSED")

    def test_rpc_called_with_correct_params(self):
        sb = _ok(_PROPOSED_ROW)
        propose_link(
            sb,
            actor_id=_ACTOR_ID,
            saas_catalog_id=_SAAS_UUID,
            reference_form_id=_REF_UUID,
            relation_type="SAME_DOCUMENT_CANDIDATE",
            evidence_note="evidence",
        )
        call_args = sb.rpc.call_args
        self.assertEqual(call_args[0][0], "fn_udl_propose")
        params = call_args[0][1]
        self.assertEqual(params["p_actor_id"],          _ACTOR_ID)
        self.assertEqual(params["p_saas_catalog_id"],   _SAAS_UUID)
        self.assertEqual(params["p_reference_form_id"], _REF_UUID)
        self.assertEqual(params["p_relation_type"],     "SAME_DOCUMENT_CANDIDATE")
        self.assertEqual(params["p_evidence_note"],     "evidence")


class TestT02ProposeLinkDuplicate(unittest.TestCase):
    def test_duplicate_raises_write_error(self):
        sb = _err("DUPLICATE_ACTIVE_PAIR", "unique constraint violated")
        with self.assertRaises(DocumentLinkWriteError) as ctx:
            propose_link(
                sb,
                actor_id=_ACTOR_ID,
                saas_catalog_id=_SAAS_UUID,
                reference_form_id=_REF_UUID,
                relation_type="SAME_DOCUMENT_CANDIDATE",
                evidence_note="evidence",
            )
        self.assertEqual(ctx.exception.error_code, "DUPLICATE_ACTIVE_PAIR")


class TestT03ProposeLinkGuardRejected(unittest.TestCase):
    def test_guard_rejected_raises_write_error(self):
        sb = _err("GUARD_REJECTED", "New rows must start in PROPOSED state")
        with self.assertRaises(DocumentLinkWriteError) as ctx:
            propose_link(
                sb,
                actor_id=_ACTOR_ID,
                saas_catalog_id=_SAAS_UUID,
                reference_form_id=_REF_UUID,
                relation_type="SAME_DOCUMENT_CANDIDATE",
                evidence_note="evidence",
            )
        self.assertEqual(ctx.exception.error_code, "GUARD_REJECTED")


class TestT04ProposeLinkMalformedResponse(unittest.TestCase):
    def test_list_response_raises_malformed(self):
        sb = _raw([{"unexpected": "list"}])
        with self.assertRaises(DocumentLinkWriteError) as ctx:
            propose_link(
                sb,
                actor_id=_ACTOR_ID,
                saas_catalog_id=_SAAS_UUID,
                reference_form_id=_REF_UUID,
                relation_type="SAME_DOCUMENT_CANDIDATE",
                evidence_note="evidence",
            )
        self.assertEqual(ctx.exception.error_code, "MALFORMED_RESPONSE")


# ---------------------------------------------------------------------------
# T05-T09: transition_link — service layer
# ---------------------------------------------------------------------------

class TestT05TransitionProposedToUnderReview(unittest.TestCase):
    def test_success(self):
        under_review_row = {**_PROPOSED_ROW, "review_state": "UNDER_REVIEW",
                            "reviewed_by": _ACTOR_ID}
        sb = _ok(under_review_row)
        row = transition_link(sb, actor_id=_ACTOR_ID, link_id=_LINK_ID, new_state="UNDER_REVIEW")
        self.assertEqual(row["review_state"], "UNDER_REVIEW")

    def test_rpc_called_with_correct_params(self):
        under_review_row = {**_PROPOSED_ROW, "review_state": "UNDER_REVIEW"}
        sb = _ok(under_review_row)
        transition_link(sb, actor_id=_ACTOR_ID, link_id=_LINK_ID, new_state="UNDER_REVIEW")
        call_args = sb.rpc.call_args
        self.assertEqual(call_args[0][0], "fn_udl_transition")
        params = call_args[0][1]
        self.assertEqual(params["p_actor_id"],  _ACTOR_ID)
        self.assertEqual(params["p_link_id"],   _LINK_ID)
        self.assertEqual(params["p_new_state"], "UNDER_REVIEW")


class TestT06TransitionUnderReviewToApproved(unittest.TestCase):
    def test_success_with_owner_approval_ref(self):
        approved_row = {**_PROPOSED_ROW, "review_state": "APPROVED",
                        "owner_approval_ref": _APPROVAL}
        sb = _ok(approved_row)
        row = transition_link(
            sb, actor_id=_ACTOR_ID, link_id=_LINK_ID,
            new_state="APPROVED", owner_approval_ref=_APPROVAL,
        )
        self.assertEqual(row["review_state"], "APPROVED")
        self.assertEqual(row["owner_approval_ref"], _APPROVAL)

    def test_owner_approval_ref_passed_to_rpc(self):
        approved_row = {**_PROPOSED_ROW, "review_state": "APPROVED"}
        sb = _ok(approved_row)
        transition_link(
            sb, actor_id=_ACTOR_ID, link_id=_LINK_ID,
            new_state="APPROVED", owner_approval_ref=_APPROVAL,
        )
        params = sb.rpc.call_args[0][1]
        self.assertEqual(params["p_owner_approval_ref"], _APPROVAL)


class TestT07TransitionUnderReviewToRejected(unittest.TestCase):
    def test_success(self):
        rejected_row = {**_PROPOSED_ROW, "review_state": "REJECTED"}
        sb = _ok(rejected_row)
        row = transition_link(sb, actor_id=_ACTOR_ID, link_id=_LINK_ID, new_state="REJECTED")
        self.assertEqual(row["review_state"], "REJECTED")


class TestT08TransitionApprovedToRetired(unittest.TestCase):
    def test_success_with_new_approval_ref(self):
        retired_row = {**_PROPOSED_ROW, "review_state": "RETIRED",
                       "owner_approval_ref": _RETIRE}
        sb = _ok(retired_row)
        row = transition_link(
            sb, actor_id=_ACTOR_ID, link_id=_LINK_ID,
            new_state="RETIRED", owner_approval_ref=_RETIRE,
        )
        self.assertEqual(row["review_state"], "RETIRED")


class TestT09TransitionRejectedToRetired(unittest.TestCase):
    def test_success(self):
        retired_row = {**_PROPOSED_ROW, "review_state": "RETIRED"}
        sb = _ok(retired_row)
        row = transition_link(sb, actor_id=_ACTOR_ID, link_id=_LINK_ID, new_state="RETIRED")
        self.assertEqual(row["review_state"], "RETIRED")


# ---------------------------------------------------------------------------
# T10-T11: transition_link — domain error cases
# ---------------------------------------------------------------------------

class TestT10TransitionLinkNotFound(unittest.TestCase):
    def test_link_not_found_raises_write_error(self):
        sb = _err("LINK_NOT_FOUND", "Link cccc... not found")
        with self.assertRaises(DocumentLinkWriteError) as ctx:
            transition_link(sb, actor_id=_ACTOR_ID, link_id=_LINK_ID, new_state="UNDER_REVIEW")
        self.assertEqual(ctx.exception.error_code, "LINK_NOT_FOUND")


class TestT11TransitionInvalidTransition(unittest.TestCase):
    def test_invalid_transition_raises_write_error(self):
        sb = _err("INVALID_TRANSITION", "Cannot transition from PROPOSED to APPROVED")
        with self.assertRaises(DocumentLinkWriteError) as ctx:
            transition_link(sb, actor_id=_ACTOR_ID, link_id=_LINK_ID, new_state="APPROVED")
        self.assertEqual(ctx.exception.error_code, "INVALID_TRANSITION")


# ---------------------------------------------------------------------------
# T12: actor_id binding — taken from JWT, not from body
# ---------------------------------------------------------------------------

_CANDIDATE_ID = "SaaS-FORM-001__REF-FORM-001"


class TestT12ActorBinding(unittest.TestCase):
    def test_actor_id_from_jwt_id_injected_into_rpc(self):
        """actor_id must come from JWT 'id' field (UUID PK), not from request body."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from routers.document_link_review import router, get_current_user

        app = FastAPI()
        app.include_router(router)
        jwt_user = {"id": "jwt-uuid-actor", "role_code": "001", "is_active": True}
        app.dependency_overrides[get_current_user] = lambda: jwt_user

        captured: dict = {}

        def _mock_propose(sb, *, actor_id, **kwargs):
            captured["actor_id"] = actor_id
            return _PROPOSED_ROW

        with patch("routers.document_link_review.get_supabase"), \
             patch("routers.document_link_review.SupabaseRestClient"), \
             patch("routers.document_link_review.validate_candidate_for_propose",
                   return_value=(_SAAS_UUID, _REF_UUID)), \
             patch("routers.document_link_review.propose_link", side_effect=_mock_propose):
            client = TestClient(app, raise_server_exceptions=False)
            client.post("/api/document-link-review/links", json={
                "candidate_id":  _CANDIDATE_ID,
                "relation_type": "SAME_DOCUMENT_CANDIDATE",
                "evidence_note": "evidence",
            })

        self.assertEqual(captured.get("actor_id"), "jwt-uuid-actor")


# ---------------------------------------------------------------------------
# T13-T18: POST /links — HTTP endpoint tests
# ---------------------------------------------------------------------------

class TestT13PostLinksNoAuth(unittest.TestCase):
    def setUp(self):
        from fastapi import FastAPI
        from routers.document_link_review import router
        self.app = FastAPI()
        self.app.include_router(router)

    def test_no_auth_header_returns_401(self):
        from fastapi.testclient import TestClient
        resp = TestClient(self.app, raise_server_exceptions=False).post(
            "/api/document-link-review/links",
            json={"candidate_id": _CANDIDATE_ID,
                  "relation_type": "SAME_DOCUMENT_CANDIDATE", "evidence_note": "e"},
        )
        self.assertEqual(resp.status_code, 401)


class TestT14PostLinksNonAdmin(unittest.TestCase):
    def setUp(self):
        from fastapi import FastAPI
        from routers.document_link_review import router, get_current_user
        self.app = FastAPI()
        self.app.include_router(router)
        self.app.dependency_overrides[get_current_user] = lambda: {
            "id": "u2", "role_code": "002", "is_active": True
        }

    def tearDown(self):
        self.app.dependency_overrides.clear()

    def test_role_002_returns_403(self):
        from fastapi.testclient import TestClient
        resp = TestClient(self.app, raise_server_exceptions=False).post(
            "/api/document-link-review/links",
            json={"candidate_id": _CANDIDATE_ID,
                  "relation_type": "SAME_DOCUMENT_CANDIDATE", "evidence_note": "e"},
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["detail"]["code"], "DOCUMENT_LINK_REVIEW_FORBIDDEN")


class TestT15PostLinksSuccess(unittest.TestCase):
    def setUp(self):
        from fastapi import FastAPI
        from routers.document_link_review import router, get_current_user
        self.app = FastAPI()
        self.app.include_router(router)
        self.app.dependency_overrides[get_current_user] = lambda: {
            "id": "u1-uuid", "role_code": "001", "is_active": True
        }

    def tearDown(self):
        self.app.dependency_overrides.clear()

    def test_valid_payload_returns_201(self):
        from fastapi.testclient import TestClient
        with patch("routers.document_link_review.get_supabase"), \
             patch("routers.document_link_review.SupabaseRestClient"), \
             patch("routers.document_link_review.validate_candidate_for_propose",
                   return_value=(_SAAS_UUID, _REF_UUID)), \
             patch("routers.document_link_review.propose_link", return_value=_PROPOSED_ROW):
            resp = TestClient(self.app, raise_server_exceptions=False).post(
                "/api/document-link-review/links",
                json={
                    "candidate_id":  _CANDIDATE_ID,
                    "relation_type": "SAME_DOCUMENT_CANDIDATE",
                    "evidence_note": "test evidence",
                },
            )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["id"], _LINK_ID)
        self.assertEqual(resp.json()["review_state"], "PROPOSED")


class TestT16PostLinksMissingEvidenceNote(unittest.TestCase):
    def setUp(self):
        from fastapi import FastAPI
        from routers.document_link_review import router, get_current_user
        self.app = FastAPI()
        self.app.include_router(router)
        self.app.dependency_overrides[get_current_user] = lambda: {
            "id": "u1-uuid", "role_code": "001", "is_active": True
        }

    def tearDown(self):
        self.app.dependency_overrides.clear()

    def test_missing_evidence_note_returns_422(self):
        from fastapi.testclient import TestClient
        resp = TestClient(self.app, raise_server_exceptions=False).post(
            "/api/document-link-review/links",
            json={
                "candidate_id":  _CANDIDATE_ID,
                "relation_type": "SAME_DOCUMENT_CANDIDATE",
            },
        )
        self.assertEqual(resp.status_code, 422)

    def test_empty_evidence_note_returns_422(self):
        from fastapi.testclient import TestClient
        resp = TestClient(self.app, raise_server_exceptions=False).post(
            "/api/document-link-review/links",
            json={
                "candidate_id":  _CANDIDATE_ID,
                "relation_type": "SAME_DOCUMENT_CANDIDATE",
                "evidence_note": "",
            },
        )
        self.assertEqual(resp.status_code, 422)


class TestT17PostLinksMissingCandidateId(unittest.TestCase):
    def setUp(self):
        from fastapi import FastAPI
        from routers.document_link_review import router, get_current_user
        self.app = FastAPI()
        self.app.include_router(router)
        self.app.dependency_overrides[get_current_user] = lambda: {
            "id": "u1-uuid", "role_code": "001", "is_active": True
        }

    def tearDown(self):
        self.app.dependency_overrides.clear()

    def test_missing_candidate_id_returns_422(self):
        from fastapi.testclient import TestClient
        resp = TestClient(self.app, raise_server_exceptions=False).post(
            "/api/document-link-review/links",
            json={
                "relation_type": "SAME_DOCUMENT_CANDIDATE",
                "evidence_note": "evidence",
            },
        )
        self.assertEqual(resp.status_code, 422)


class TestT18PostLinksDuplicateConflict(unittest.TestCase):
    def setUp(self):
        from fastapi import FastAPI
        from routers.document_link_review import router, get_current_user
        self.app = FastAPI()
        self.app.include_router(router)
        self.app.dependency_overrides[get_current_user] = lambda: {
            "id": "u1-uuid", "role_code": "001", "is_active": True
        }

    def tearDown(self):
        self.app.dependency_overrides.clear()

    def test_duplicate_pair_returns_409(self):
        from fastapi.testclient import TestClient
        exc = DocumentLinkWriteError("DUPLICATE_ACTIVE_PAIR", "unique constraint")
        with patch("routers.document_link_review.get_supabase"), \
             patch("routers.document_link_review.SupabaseRestClient"), \
             patch("routers.document_link_review.validate_candidate_for_propose",
                   return_value=(_SAAS_UUID, _REF_UUID)), \
             patch("routers.document_link_review.propose_link", side_effect=exc):
            resp = TestClient(self.app, raise_server_exceptions=False).post(
                "/api/document-link-review/links",
                json={
                    "candidate_id":  _CANDIDATE_ID,
                    "relation_type": "SAME_DOCUMENT_CANDIDATE",
                    "evidence_note": "evidence",
                },
            )
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["detail"]["code"], "DUPLICATE_ACTIVE_PAIR")


# ---------------------------------------------------------------------------
# T19-T20: POST /links/{id}/submit-review
# ---------------------------------------------------------------------------

class TestT19SubmitReviewSuccess(unittest.TestCase):
    def setUp(self):
        from fastapi import FastAPI
        from routers.document_link_review import router, get_current_user
        self.app = FastAPI()
        self.app.include_router(router)
        self.app.dependency_overrides[get_current_user] = lambda: {
            "id": "u1-uuid", "role_code": "001", "is_active": True
        }

    def tearDown(self):
        self.app.dependency_overrides.clear()

    def test_submit_review_returns_200(self):
        from fastapi.testclient import TestClient
        under_review_row = {**_PROPOSED_ROW, "review_state": "UNDER_REVIEW"}
        with patch("routers.document_link_review.get_supabase"), \
             patch("routers.document_link_review.transition_link",
                   return_value=under_review_row):
            resp = TestClient(self.app, raise_server_exceptions=False).post(
                f"/api/document-link-review/links/{_LINK_ID}/submit-review"
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["review_state"], "UNDER_REVIEW")


class TestT20SubmitReviewNotFound(unittest.TestCase):
    def setUp(self):
        from fastapi import FastAPI
        from routers.document_link_review import router, get_current_user
        self.app = FastAPI()
        self.app.include_router(router)
        self.app.dependency_overrides[get_current_user] = lambda: {
            "id": "u1-uuid", "role_code": "001", "is_active": True
        }

    def tearDown(self):
        self.app.dependency_overrides.clear()

    def test_link_not_found_returns_404(self):
        from fastapi.testclient import TestClient
        exc = DocumentLinkWriteError("LINK_NOT_FOUND", "not found")
        with patch("routers.document_link_review.get_supabase"), \
             patch("routers.document_link_review.transition_link", side_effect=exc):
            resp = TestClient(self.app, raise_server_exceptions=False).post(
                f"/api/document-link-review/links/{_LINK_ID}/submit-review"
            )
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["detail"]["code"], "LINK_NOT_FOUND")


# ---------------------------------------------------------------------------
# T21-T23: POST /links/{id}/decision
# ---------------------------------------------------------------------------

class _DecisionTestBase(unittest.TestCase):
    def setUp(self):
        from fastapi import FastAPI
        from routers.document_link_review import router, get_current_user
        self.app = FastAPI()
        self.app.include_router(router)
        self.app.dependency_overrides[get_current_user] = lambda: {
            "id": "u1-uuid", "role_code": "001", "is_active": True
        }

    def tearDown(self):
        self.app.dependency_overrides.clear()

    def _client(self):
        from fastapi.testclient import TestClient
        return TestClient(self.app, raise_server_exceptions=False)


class TestT21DecisionApprove(_DecisionTestBase):
    def test_approve_returns_403_owner_gate_blocked(self):
        """APPROVE is FAIL-CLOSED: no Owner identity/approval SoT exists."""
        resp = self._client().post(
            f"/api/document-link-review/links/{_LINK_ID}/decision",
            json={"action": "APPROVE", "owner_approval_ref": _APPROVAL},
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["detail"]["code"], "OWNER_GATE_BLOCKED")

    def test_approve_without_ref_also_returns_403(self):
        """APPROVE fails immediately regardless of owner_approval_ref presence."""
        resp = self._client().post(
            f"/api/document-link-review/links/{_LINK_ID}/decision",
            json={"action": "APPROVE"},
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["detail"]["code"], "OWNER_GATE_BLOCKED")


class TestT22DecisionReject(_DecisionTestBase):
    def test_reject_returns_200_rejected(self):
        rejected_row = {**_PROPOSED_ROW, "review_state": "REJECTED"}
        with patch("routers.document_link_review.get_supabase"), \
             patch("routers.document_link_review.transition_link",
                   return_value=rejected_row):
            resp = self._client().post(
                f"/api/document-link-review/links/{_LINK_ID}/decision",
                json={"action": "REJECT"},
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["review_state"], "REJECTED")


class TestT23DecisionGuardRejected(_DecisionTestBase):
    def test_guard_rejected_returns_409(self):
        exc = DocumentLinkWriteError("GUARD_REJECTED", "state transition refused by DB guard")
        with patch("routers.document_link_review.get_supabase"), \
             patch("routers.document_link_review.transition_link", side_effect=exc):
            resp = self._client().post(
                f"/api/document-link-review/links/{_LINK_ID}/decision",
                json={"action": "REJECT"},
            )
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["detail"]["code"], "GUARD_REJECTED")


# ---------------------------------------------------------------------------
# T24: GET /links/{id}
# ---------------------------------------------------------------------------

class TestT24GetLinkDetail(unittest.TestCase):
    def setUp(self):
        from fastapi import FastAPI
        from routers.document_link_review import router, get_current_user
        self.app = FastAPI()
        self.app.include_router(router)
        self.app.dependency_overrides[get_current_user] = lambda: {
            "id": "u1-uuid", "role_code": "001", "is_active": True
        }

    def tearDown(self):
        self.app.dependency_overrides.clear()

    def _client(self):
        from fastapi.testclient import TestClient
        return TestClient(self.app, raise_server_exceptions=False)

    def test_returns_link_with_audit_history(self):
        audit_row = {
            "id": "audit-1", "link_id": _LINK_ID,
            "event_type": "PROPOSED", "actor": _ACTOR_ID,
            "from_state": None, "to_state": "PROPOSED",
            "changed_at": "2026-10-21T00:00:00Z",
            "change_note": None, "old_evidence_note": None,
            "old_value": None, "new_value": None,
        }
        with patch("routers.document_link_review.SupabaseRestClient") as MockClient:
            MockClient.return_value.select.side_effect = lambda table, **kwargs: (
                [_PROPOSED_ROW] if table == "unified_document_link" else [audit_row]
            )
            resp = self._client().get(
                f"/api/document-link-review/links/{_LINK_ID}"
            )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["id"], _LINK_ID)
        self.assertIn("audit_history", body)
        self.assertEqual(len(body["audit_history"]), 1)
        self.assertEqual(body["audit_history"][0]["event_type"], "PROPOSED")

    def test_not_found_returns_404(self):
        with patch("routers.document_link_review.SupabaseRestClient") as MockClient:
            MockClient.return_value.select.return_value = []
            resp = self._client().get(
                f"/api/document-link-review/links/{_LINK_ID}"
            )
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["detail"]["code"], "LINK_NOT_FOUND")


# ---------------------------------------------------------------------------
# CORR-001: Defect-fix regression tests
# ---------------------------------------------------------------------------

class _CorrTestBase(unittest.TestCase):
    def setUp(self):
        from fastapi import FastAPI
        from routers.document_link_review import router, get_current_user
        self.app = FastAPI()
        self.app.include_router(router)
        self.app.dependency_overrides[get_current_user] = lambda: {
            "id": "u1-uuid", "role_code": "001", "is_active": True
        }

    def tearDown(self):
        self.app.dependency_overrides.clear()

    def _client(self):
        from fastapi.testclient import TestClient
        return TestClient(self.app, raise_server_exceptions=False)


class TestCORR01ApproveIsAlwaysBlocked(_CorrTestBase):
    """CORR-A/B/D: APPROVE returns 403 OWNER_GATE_BLOCKED regardless of payload."""

    def test_approve_with_ref_blocked(self):
        resp = self._client().post(
            f"/api/document-link-review/links/{_LINK_ID}/decision",
            json={"action": "APPROVE", "owner_approval_ref": "WO-FAKE-001"},
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["detail"]["code"], "OWNER_GATE_BLOCKED")

    def test_approve_without_ref_blocked(self):
        resp = self._client().post(
            f"/api/document-link-review/links/{_LINK_ID}/decision",
            json={"action": "APPROVE"},
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["detail"]["code"], "OWNER_GATE_BLOCKED")


class TestCORR02RetireFromApprovedBlocked(_CorrTestBase):
    """CORR-E: RETIRE on an APPROVED link returns 403 OWNER_GATE_BLOCKED."""

    def test_retire_approved_link_blocked(self):
        approved_link = {**_PROPOSED_ROW, "review_state": "APPROVED"}
        with patch("routers.document_link_review.SupabaseRestClient") as MockClient:
            MockClient.return_value.select.return_value = [approved_link]
            resp = self._client().post(
                f"/api/document-link-review/links/{_LINK_ID}/decision",
                json={"action": "RETIRE"},
            )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["detail"]["code"], "OWNER_GATE_BLOCKED")


class TestCORR03RetireFromRejectedAllowed(_CorrTestBase):
    """RETIRE on a REJECTED link must still succeed (CORR-E does not affect this path)."""

    def test_retire_rejected_link_succeeds(self):
        rejected_link = {**_PROPOSED_ROW, "review_state": "REJECTED"}
        retired_row = {**_PROPOSED_ROW, "review_state": "RETIRED"}
        with patch("routers.document_link_review.SupabaseRestClient") as MockClient, \
             patch("routers.document_link_review.get_supabase"), \
             patch("routers.document_link_review.transition_link", return_value=retired_row):
            MockClient.return_value.select.return_value = [rejected_link]
            resp = self._client().post(
                f"/api/document-link-review/links/{_LINK_ID}/decision",
                json={"action": "RETIRE"},
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["review_state"], "RETIRED")


class TestCORR04InvalidCandidateId(_CorrTestBase):
    """CORR-C: candidate_id not in CSV → 404 CANDIDATE_NOT_FOUND."""

    def test_unknown_candidate_id_returns_404(self):
        from services.document_link_review_read import CandidateValidationError
        exc = CandidateValidationError("CANDIDATE_NOT_FOUND", "후보를 찾을 수 없습니다.")
        with patch("routers.document_link_review.SupabaseRestClient"), \
             patch("routers.document_link_review.validate_candidate_for_propose",
                   side_effect=exc):
            resp = self._client().post(
                "/api/document-link-review/links",
                json={
                    "candidate_id":  "NONEXISTENT__ID",
                    "relation_type": "SAME_DOCUMENT_CANDIDATE",
                    "evidence_note": "evidence",
                },
            )
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["detail"]["code"], "CANDIDATE_NOT_FOUND")


class TestCORR05StaleCandidateBlocked(_CorrTestBase):
    """CORR-C: stale candidate → 422 CANDIDATE_STALE."""

    def test_stale_candidate_returns_422(self):
        from services.document_link_review_read import CandidateValidationError
        exc = CandidateValidationError("CANDIDATE_STALE", "SaaS 문서가 비활성 상태입니다.")
        with patch("routers.document_link_review.SupabaseRestClient"), \
             patch("routers.document_link_review.validate_candidate_for_propose",
                   side_effect=exc):
            resp = self._client().post(
                "/api/document-link-review/links",
                json={
                    "candidate_id":  _CANDIDATE_ID,
                    "relation_type": "SAME_DOCUMENT_CANDIDATE",
                    "evidence_note": "evidence",
                },
            )
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["detail"]["code"], "CANDIDATE_STALE")


class TestCORR06RejectStillWorks(_CorrTestBase):
    """REJECT must still work — only APPROVE and RETIRE-from-APPROVED are blocked."""

    def test_reject_proposed_returns_200(self):
        rejected_row = {**_PROPOSED_ROW, "review_state": "REJECTED"}
        with patch("routers.document_link_review.get_supabase"), \
             patch("routers.document_link_review.transition_link", return_value=rejected_row):
            resp = self._client().post(
                f"/api/document-link-review/links/{_LINK_ID}/decision",
                json={"action": "REJECT"},
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["review_state"], "REJECTED")


class TestCORR07CandidateUuidsFromServer(_CorrTestBase):
    """CORR-C: UUIDs used for propose must come from validate_candidate_for_propose, not client."""

    def test_server_resolved_uuids_sent_to_rpc(self):
        server_saas = "ffffffff-0000-0000-0000-000000000001"
        server_ref  = "ffffffff-0000-0000-0000-000000000002"
        captured: dict = {}

        def _mock_propose(sb, *, saas_catalog_id, reference_form_id, **kwargs):
            captured["saas_catalog_id"] = saas_catalog_id
            captured["reference_form_id"] = reference_form_id
            return _PROPOSED_ROW

        with patch("routers.document_link_review.get_supabase"), \
             patch("routers.document_link_review.SupabaseRestClient"), \
             patch("routers.document_link_review.validate_candidate_for_propose",
                   return_value=(server_saas, server_ref)), \
             patch("routers.document_link_review.propose_link",
                   side_effect=_mock_propose):
            self._client().post(
                "/api/document-link-review/links",
                json={
                    "candidate_id":  _CANDIDATE_ID,
                    "relation_type": "SAME_DOCUMENT_CANDIDATE",
                    "evidence_note": "evidence",
                },
            )
        self.assertEqual(captured.get("saas_catalog_id"), server_saas)
        self.assertEqual(captured.get("reference_form_id"), server_ref)


if __name__ == "__main__":
    unittest.main()
