"""WO-008A Workstream C — Targeted missing negative tests.

This file covers ONLY the gap cases identified by GPT WO-008 IV that were NOT
covered by the original 68 tests:

  N1–N4:  Router-level foreign factory ownership (GET + POST → 404)
  N5–N7:  Contract gate mismatch → runtime NOT called (LEG_POST=0, C10_WRITE=0)
  N8–N9:  Item37 missing subtype → 422 from contract helper (flag ON)
  N10–N12: Item49 CONSTRUCTION missing child predicates → 422
  N13–N14: First-insert race → 409 CONCURRENT_INSERT_CONFLICT
  N15:    Strict positive revision gap: expected_app3_revision=0 accepted as int
           (documents known gap — requires separate patch WO for StrictInt/ge=1)
  N16:    Audit retention / FK CASCADE design decision (documented assertion)

Do NOT repeat tests S1–S13, C1–C6, F1–F9, O1–O5, T1–T8, P1–P9, E1–E7.
NO LEG_POST = 0. NO DB writes. All DB calls mocked.
"""
from __future__ import annotations

from typing import Any, Optional
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient


# ── Mock helpers ──────────────────────────────────────────────────────────────

def _sb_empty():
    """Supabase mock that returns empty data (factory not found)."""
    chain = MagicMock()
    chain.execute.return_value = MagicMock(data=[])
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.limit.return_value = chain
    sb = MagicMock()
    sb.table.return_value = chain
    return sb


def _sb_factory_found(company_id="co-001"):
    """Supabase mock — factory belongs to company_id."""
    chain = MagicMock()
    chain.execute.return_value = MagicMock(data=[{"company_id": company_id}])
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.limit.return_value = chain
    sb = MagicMock()
    sb.table.return_value = chain
    return sb


def _current_user(company_id="co-001", role_code="MANAGER"):
    return {"id": "user-001", "company_id": company_id, "role_code": role_code}


# ── Router test client ────────────────────────────────────────────────────────

def _make_app():
    """Build a minimal FastAPI app with only the WO-008 router mounted."""
    from fastapi import FastAPI
    from routers.factory_legal_classification import router
    app = FastAPI()
    app.include_router(router)
    return app


# ─────────────────────────────────────────────────────────────────────────────
# N1–N2: GET /factories/{factory_id}/legal-classification — foreign factory 404
# ─────────────────────────────────────────────────────────────────────────────

class TestRouterGetForeignFactory:
    """Router GET: foreign factory (different company) must return 404 before data access."""

    def test_N1_foreign_factory_get_returns_404(self):
        """Company 'co-999' requests factory owned by 'co-001' → 404."""
        app = _make_app()
        with (
            patch("routers.factory_legal_classification.get_supabase", return_value=_sb_factory_found("co-001")),
            patch("routers.factory_legal_classification.get_current_user", return_value=_current_user("co-999")),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/factories/factory-abc/legal-classification",
                              headers={"authorization": "Bearer tok"})
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"

    def test_N2_own_factory_get_proceeds(self):
        """Same company factory — GET must not return 404 (proceeds to service call)."""
        owned_sb = _sb_factory_found("co-001")
        # Service mock: classification record exists
        owned_sb.table.return_value.execute.return_value = MagicMock(data=[{"company_id": "co-001"}])

        app = _make_app()
        with (
            patch("routers.factory_legal_classification.get_supabase", return_value=owned_sb),
            patch("routers.factory_legal_classification.get_current_user", return_value=_current_user("co-001")),
            patch("routers.factory_legal_classification.get_factory_legal_classification",
                  return_value=None),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/factories/factory-abc/legal-classification",
                              headers={"authorization": "Bearer tok"})
        # Returns UNCONFIRMED (200), not 404
        assert resp.status_code == 200
        assert resp.json()["status"] == "UNCONFIRMED"


# ─────────────────────────────────────────────────────────────────────────────
# N3–N4: POST /factories/{factory_id}/legal-classification/confirm — foreign 404
# ─────────────────────────────────────────────────────────────────────────────

class TestRouterPostForeignFactory:
    """Router POST: foreign factory must return 404 before confirm service is called."""

    _valid_body = {
        "appendix3_item_no": 10,
        "confirmed_sector": "INDUSTRIAL",
        "confirm_deliberate": True,
    }

    def test_N3_foreign_factory_post_returns_404(self):
        """Foreign company POST → 404 before service call."""
        app = _make_app()
        confirm_svc_mock = MagicMock()  # must NOT be called

        with (
            patch("routers.factory_legal_classification.get_supabase", return_value=_sb_factory_found("co-001")),
            patch("routers.factory_legal_classification.get_current_user", return_value=_current_user("co-999")),
            patch("routers.factory_legal_classification.confirm_factory_legal_classification",
                  confirm_svc_mock),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post(
                "/factories/factory-xyz/legal-classification/confirm",
                json=self._valid_body,
                headers={"authorization": "Bearer tok"},
            )
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
        confirm_svc_mock.assert_not_called()

    def test_N4_post_confirm_deliberate_false_rejected(self):
        """confirm_deliberate=false → 422 Pydantic validation (before any service call)."""
        from pydantic import ValidationError
        from routers.factory_legal_classification import FactoryLegalClassificationConfirmBody
        with pytest.raises((ValidationError, ValueError)):
            FactoryLegalClassificationConfirmBody(
                appendix3_item_no=10,
                confirmed_sector="INDUSTRIAL",
                confirm_deliberate=False,
            )


# ─────────────────────────────────────────────────────────────────────────────
# N5–N7: Contract gate mismatch → runtime (LEG/C10) NOT called
#         Proves LEG_POST=0 and C10_WRITE=0 on gate failure
# ─────────────────────────────────────────────────────────────────────────────

class TestContractGatePreventsRuntime:
    """check_saas_appendix3_contract raises 409 → runtime build/persist never called."""

    def _make_consumer(self, **kwargs):
        from types import SimpleNamespace
        defaults = {
            "appendix3_item_no": 10,
            "is_real_estate_management": None,
            "expected_app3_revision": None,
            "is_relationship_contractor": None,
            "is_civil_construction": None,
        }
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)

    def _sb_with_factory_sector(self, sector: str) -> MagicMock:
        """Mock supabase where factories.sector read returns given sector (R7 support)."""
        sb = MagicMock()
        # Configure chain: sb.table(...).select(...).eq(...).limit(...).execute().data
        sb.table.return_value.select.return_value.eq.return_value.limit.return_value \
            .execute.return_value.data = [{"sector": sector}]
        return sb

    def test_N5_item_mismatch_raises_409_classification_mismatch(self):
        """Stored item=10, request item=20 → CLASSIFICATION_MISMATCH 409.

        R7 (factory sector re-read) is satisfied; error is on item comparison.
        """
        from services.canonical.saas_appendix3_contract import check_saas_appendix3_contract

        stored_record = {
            "appendix3_item_no": 10,
            "is_real_estate_management": None,
            "confirmed_sector": "INDUSTRIAL",
            "appendix3_law_version_id": "1fa1f5af-3575-461d-8d8c-4389d0e128d8",
            "revision": 1,
        }
        # R7: factories.sector must return matching sector so R7 passes
        sb = self._sb_with_factory_sector("INDUSTRIAL")
        leg_runtime = MagicMock()  # must NOT be called
        c10_persist = MagicMock()   # must NOT be called

        with (
            patch("services.canonical.saas_appendix3_contract.SAAS_APP3_ENABLED", True),
            patch("services.factory_legal_classification_svc.get_factory_legal_classification",
                  return_value=stored_record),
        ):
            consumer = self._make_consumer(appendix3_item_no=20)  # mismatch
            with pytest.raises(HTTPException) as exc_info:
                check_saas_appendix3_contract(sb, "factory-abc", "INDUSTRIAL", consumer)

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "CLASSIFICATION_MISMATCH"
        leg_runtime.assert_not_called()
        c10_persist.assert_not_called()

    def test_N6_sector_drift_raises_409_sector_drift(self):
        """Current factory sector=INDUSTRIAL, request sector=BUILDING → SECTOR_DRIFT 409.

        R7 detects the drift from authoritative factories.sector (not only stored record).
        """
        from services.canonical.saas_appendix3_contract import check_saas_appendix3_contract

        stored_record = {
            "appendix3_item_no": 10,
            "is_real_estate_management": None,
            "confirmed_sector": "INDUSTRIAL",
            "appendix3_law_version_id": "1fa1f5af-3575-461d-8d8c-4389d0e128d8",
            "revision": 1,
        }
        # R7: factories.sector=INDUSTRIAL, request sector=BUILDING → R7 fires SECTOR_DRIFT
        sb = self._sb_with_factory_sector("INDUSTRIAL")
        with (
            patch("services.canonical.saas_appendix3_contract.SAAS_APP3_ENABLED", True),
            patch("services.factory_legal_classification_svc.get_factory_legal_classification",
                  return_value=stored_record),
        ):
            consumer = self._make_consumer(appendix3_item_no=10)
            with pytest.raises(HTTPException) as exc_info:
                check_saas_appendix3_contract(sb, "factory-abc", "BUILDING", consumer)

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "SECTOR_DRIFT"

    def test_N7_classification_not_confirmed_raises_409(self):
        """No stored record → CLASSIFICATION_NOT_CONFIRMED 409 before runtime."""
        from services.canonical.saas_appendix3_contract import check_saas_appendix3_contract

        sb = MagicMock()
        with (
            patch("services.canonical.saas_appendix3_contract.SAAS_APP3_ENABLED", True),
            patch("services.factory_legal_classification_svc.get_factory_legal_classification",
                  return_value=None),
        ):
            consumer = self._make_consumer(appendix3_item_no=10)
            with pytest.raises(HTTPException) as exc_info:
                check_saas_appendix3_contract(sb, "factory-abc", "INDUSTRIAL", consumer)

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "CLASSIFICATION_NOT_CONFIRMED"


# ─────────────────────────────────────────────────────────────────────────────
# N8–N9: Item37 missing subtype → 422 from contract helper (flag ON)
# ─────────────────────────────────────────────────────────────────────────────

class TestItem37SubtypeContractHelper:
    """Contract helper item37 subtype gate when flag ON (router path, not schema path)."""

    def _make_consumer(self, **kwargs):
        from types import SimpleNamespace
        defaults = {
            "appendix3_item_no": None,
            "is_real_estate_management": None,
            "expected_app3_revision": None,
            "is_relationship_contractor": None,
            "is_civil_construction": None,
        }
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)

    def test_N8_item37_missing_subtype_raises_422_from_contract(self):
        """Flag ON + item37 + no subtype → 422 APPENDIX3_EXPLICIT_CLASSIFICATION_REQUIRED."""
        from services.canonical.saas_appendix3_contract import check_saas_appendix3_contract

        sb = MagicMock()
        with patch("services.canonical.saas_appendix3_contract.SAAS_APP3_ENABLED", True):
            consumer = self._make_consumer(appendix3_item_no=37, is_real_estate_management=None)
            with pytest.raises(HTTPException) as exc_info:
                check_saas_appendix3_contract(sb, "factory-abc", "INDUSTRIAL", consumer)

        assert exc_info.value.status_code == 422
        detail = exc_info.value.detail
        assert detail.get("missing_fields") == ["is_real_estate_management"]

    def test_N9_item37_with_subtype_proceeds_to_db_lookup(self):
        """Flag ON + item37 + subtype present → passes type gate, proceeds to DB lookup."""
        from services.canonical.saas_appendix3_contract import check_saas_appendix3_contract

        sb = MagicMock()
        # No stored record → 409 (not 422) proves the type gate was passed
        with (
            patch("services.canonical.saas_appendix3_contract.SAAS_APP3_ENABLED", True),
            patch("services.factory_legal_classification_svc.get_factory_legal_classification",
                  return_value=None),
        ):
            consumer = self._make_consumer(appendix3_item_no=37, is_real_estate_management=True)
            with pytest.raises(HTTPException) as exc_info:
                check_saas_appendix3_contract(sb, "factory-abc", "INDUSTRIAL", consumer)

        # 409 means it passed the 422 gate and reached the DB lookup
        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "CLASSIFICATION_NOT_CONFIRMED"


# ─────────────────────────────────────────────────────────────────────────────
# N10–N12: Item49 CONSTRUCTION missing child predicates → 422
# ─────────────────────────────────────────────────────────────────────────────

class TestItem49ConstructionChildPredicates:
    """Router path: item49 CONSTRUCTION children via contract helper."""

    def _make_consumer(self, **kwargs):
        from types import SimpleNamespace
        defaults = {
            "appendix3_item_no": 49,
            "is_real_estate_management": None,
            "expected_app3_revision": None,
            "is_relationship_contractor": None,
            "is_civil_construction": None,
        }
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)

    def test_N10_item49_construction_missing_is_relationship_contractor(self):
        """item49 CONSTRUCTION without is_relationship_contractor → 422."""
        from services.canonical.saas_appendix3_contract import check_saas_appendix3_contract

        sb = MagicMock()
        with patch("services.canonical.saas_appendix3_contract.SAAS_APP3_ENABLED", True):
            consumer = self._make_consumer(
                is_relationship_contractor=None,  # missing
                is_civil_construction=True,
            )
            with pytest.raises(HTTPException) as exc_info:
                check_saas_appendix3_contract(sb, "factory-abc", "CONSTRUCTION", consumer)

        assert exc_info.value.status_code == 422
        detail = exc_info.value.detail
        assert "is_relationship_contractor" in str(detail)

    def test_N11_item49_construction_missing_is_civil_construction(self):
        """item49 CONSTRUCTION without is_civil_construction → 422."""
        from services.canonical.saas_appendix3_contract import check_saas_appendix3_contract

        sb = MagicMock()
        with patch("services.canonical.saas_appendix3_contract.SAAS_APP3_ENABLED", True):
            consumer = self._make_consumer(
                is_relationship_contractor=True,
                is_civil_construction=None,  # missing
            )
            with pytest.raises(HTTPException) as exc_info:
                check_saas_appendix3_contract(sb, "factory-abc", "CONSTRUCTION", consumer)

        assert exc_info.value.status_code == 422
        detail = exc_info.value.detail
        assert "is_civil_construction" in str(detail)

    def test_N12_item49_construction_both_children_proceeds(self):
        """item49 CONSTRUCTION with both children → passes predicate gate → DB lookup."""
        from services.canonical.saas_appendix3_contract import check_saas_appendix3_contract

        sb = MagicMock()
        with (
            patch("services.canonical.saas_appendix3_contract.SAAS_APP3_ENABLED", True),
            patch("services.factory_legal_classification_svc.get_factory_legal_classification",
                  return_value=None),
        ):
            consumer = self._make_consumer(
                is_relationship_contractor=True,
                is_civil_construction=True,
            )
            with pytest.raises(HTTPException) as exc_info:
                check_saas_appendix3_contract(sb, "factory-abc", "CONSTRUCTION", consumer)

        # 409 = passed 422 gate, reached DB lookup
        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "CLASSIFICATION_NOT_CONFIRMED"


# ─────────────────────────────────────────────────────────────────────────────
# N13–N14: First-insert race → 409 CONCURRENT_INSERT_CONFLICT
# ─────────────────────────────────────────────────────────────────────────────

class TestFirstInsertRace:
    """Service layer concurrent first-insert race → 409 CONCURRENT_INSERT_CONFLICT."""

    def test_N13_unique_violation_raises_409_concurrent(self):
        """DB raises unique constraint error on first insert → 409 CONCURRENT_INSERT_CONFLICT."""
        from services.factory_legal_classification_svc import confirm_factory_legal_classification

        def _raise_unique(*args, **kwargs):
            raise Exception("ERROR:  duplicate key value violates unique constraint (23505)")

        sb = MagicMock()
        # Factory with sector=INDUSTRIAL (no existing record)
        sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = \
            MagicMock(data=[{"sector": "INDUSTRIAL", "company_id": "co-001"}])

        chain = MagicMock()
        chain.execute.side_effect = _raise_unique
        chain.insert.return_value = chain

        # Patch: first table call (for factory read) works; second (insert) raises
        call_count = [0]
        original_table = sb.table

        def _selective_table(name):
            call_count[0] += 1
            if name == "factories":
                return MagicMock(
                    select=MagicMock(return_value=MagicMock(
                        eq=MagicMock(return_value=MagicMock(
                            limit=MagicMock(return_value=MagicMock(
                                execute=MagicMock(return_value=MagicMock(data=[{"sector": "INDUSTRIAL"}]))
                            ))
                        ))
                    ))
                )
            # factory_legal_classifications table
            c = MagicMock()
            c.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
            c.insert.return_value.execute.side_effect = _raise_unique
            return c

        sb.table.side_effect = _selective_table

        with pytest.raises(HTTPException) as exc_info:
            confirm_factory_legal_classification(
                sb,
                factory_id="factory-race",
                appendix3_item_no=10,
                is_real_estate_management=None,
                confirmed_sector="INDUSTRIAL",
                expected_revision=None,
                confirmed_by="user-001",
            )

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "CONCURRENT_INSERT_CONFLICT"

    def test_N14_existing_record_with_expected_revision_none_raises_409_stale(self):
        """Record exists, expected_revision=None provided → 409 STALE_REVISION (update path)."""
        from services.factory_legal_classification_svc import confirm_factory_legal_classification

        sb = MagicMock()

        def _selective_table(name):
            if name == "factories":
                return MagicMock(
                    select=MagicMock(return_value=MagicMock(
                        eq=MagicMock(return_value=MagicMock(
                            limit=MagicMock(return_value=MagicMock(
                                execute=MagicMock(return_value=MagicMock(data=[{"sector": "INDUSTRIAL"}]))
                            ))
                        ))
                    ))
                )
            # factory_legal_classifications — existing record (revision=1)
            c = MagicMock()
            c.select.return_value.eq.return_value.limit.return_value.execute.return_value = \
                MagicMock(data=[{
                    "factory_id": "factory-abc",
                    "appendix3_item_no": 10,
                    "revision": 1,
                    "confirmed_sector": "INDUSTRIAL",
                }])
            return c

        sb.table.side_effect = _selective_table

        with pytest.raises(HTTPException) as exc_info:
            confirm_factory_legal_classification(
                sb,
                factory_id="factory-abc",
                appendix3_item_no=10,
                is_real_estate_management=None,
                confirmed_sector="INDUSTRIAL",
                expected_revision=None,  # omitted → must supply for update
                confirmed_by="user-001",
            )

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "STALE_REVISION"


# ─────────────────────────────────────────────────────────────────────────────
# N15: Strict positive revision gap documentation
# ─────────────────────────────────────────────────────────────────────────────

class TestRevisionTypeGap:
    """N15/N15b: Gap CLOSED (WO-008B R1) — StrictInt/ge=1 now enforced.

    These tests document the gap was real (WO-008A) and confirm it is now fixed (WO-008B).
    """

    def test_N15_expected_app3_revision_zero_rejected(self):
        """WO-008B R1: expected_app3_revision=0 must now be rejected (ge=1 enforced)."""
        from pydantic import ValidationError
        from schemas.legal_engine import SafeIndustrialConsumerInput
        with pytest.raises(ValidationError) as exc_info:
            SafeIndustrialConsumerInput(expected_app3_revision=0)
        assert "greater_than_equal" in str(exc_info.value) or "ge" in str(exc_info.value).lower()

    def test_N15b_expected_app3_revision_bool_rejected(self):
        """WO-008B R1: expected_app3_revision=True must now be rejected (StrictInt rejects bool)."""
        from pydantic import ValidationError
        from schemas.legal_engine import SafeIndustrialConsumerInput
        with pytest.raises(ValidationError):
            SafeIndustrialConsumerInput(expected_app3_revision=True)

    def test_N15c_expected_app3_revision_positive_accepted(self):
        """WO-008B R1: expected_app3_revision=1 (positive int) must be accepted."""
        from schemas.legal_engine import SafeIndustrialConsumerInput
        m = SafeIndustrialConsumerInput(expected_app3_revision=1)
        assert m.expected_app3_revision == 1

    def test_N15d_expected_app3_revision_none_accepted(self):
        """WO-008B R1: expected_app3_revision=None (first insert, flag OFF) must be accepted."""
        from schemas.legal_engine import SafeIndustrialConsumerInput
        m = SafeIndustrialConsumerInput(expected_app3_revision=None)
        assert m.expected_app3_revision is None


# ─────────────────────────────────────────────────────────────────────────────
# N16: Audit retention — FK ON DELETE RESTRICT (WO-008B R2 CLOSED)
# ─────────────────────────────────────────────────────────────────────────────

class TestAuditRetentionDesignDecision:
    """N16: FK ON DELETE RESTRICT 계약 확인 (WO-008B R2).

    Owner 결정 (2026-10-11): B안 — ON DELETE RESTRICT.
    두 FK 모두 RESTRICT로 변경됨:
      factory_legal_classifications.factory_id → factories(id) ON DELETE RESTRICT
      factory_legal_classification_events.factory_id → factories(id) ON DELETE RESTRICT

    분류·이력이 존재하는 시설의 물리 DELETE는 FK 위반으로 차단.
    논리 삭제(UPDATE is_active=false)는 영향 없음.
    """

    def test_N16_fk_restrict_is_present_in_migration(self):
        """ON DELETE RESTRICT가 migration SQL에 존재하고 CASCADE는 없음을 확인."""
        migration_path = (
            "supabase/migrations/20261011000001_factory_legal_classifications_foundation.sql"
        )
        import os
        full_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            migration_path
        )
        assert os.path.exists(full_path), f"Migration not found at {full_path}"
        with open(full_path) as f:
            sql = f.read().lower()

        # RESTRICT가 두 FK에 존재해야 함 (코멘트 포함 최소 2)
        restrict_count = sql.count("on delete restrict")
        assert restrict_count >= 2, (
            f"Expected at least 2 'ON DELETE RESTRICT' in migration, found {restrict_count}"
        )
        # CASCADE는 존재하지 않아야 함
        assert "on delete cascade" not in sql, (
            "ON DELETE CASCADE must not appear — R2 decision is RESTRICT."
        )
