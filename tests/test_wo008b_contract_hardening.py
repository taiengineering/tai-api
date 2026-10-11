"""WO-008B Workstream 3 — Targeted contract hardening tests.

Covers ONLY new behavior introduced in WO-008B R1–R7 patches.
Do NOT repeat WO-008 original 68, WO-008A N1–N16, or any unchanged WO-003 tests.

R1: Strict positive StrictInt/ge=1 for revision fields (schemas + confirm router body)
R2: R6-required revision on flag-ON diagnosis (missing → 422, mismatch → 409)
R3: confirmed_at refreshed on CAS UPDATE (server UTC clock, not client)
R4: item37 subtype required at confirm service (None → 422)
R5: Canonical validator reuse in SaaS contract (no duplicate type/range logic)
R6: expected_app3_revision required on flag-ON diagnosis path
R7: Authoritative factories.sector re-read after stored record read

NO LEG_POST = 0. NO DB writes. All DB calls mocked.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException


# ── Mock helpers ──────────────────────────────────────────────────────────────

def _sb_returning(sector: str):
    """Supabase mock: factories.sector read returns given sector (R7)."""
    sb = MagicMock()
    sb.table.return_value.select.return_value.eq.return_value.limit.return_value \
        .execute.return_value.data = [{"sector": sector}]
    return sb


def _stored(item=10, subtype=None, sector="INDUSTRIAL", revision=2,
            law_version="1fa1f5af-3575-461d-8d8c-4389d0e128d8"):
    return {
        "appendix3_item_no": item,
        "is_real_estate_management": subtype,
        "confirmed_sector": sector,
        "appendix3_law_version_id": law_version,
        "revision": revision,
    }


def _consumer(item=10, subtype=None, expected_rev=None, sector_for_ns="INDUSTRIAL"):
    from types import SimpleNamespace
    return SimpleNamespace(
        appendix3_item_no=item,
        is_real_estate_management=subtype,
        expected_app3_revision=expected_rev,
        is_relationship_contractor=None,
        is_civil_construction=None,
    )


# ─────────────────────────────────────────────────────────────────────────────
# R1 — Strict positive revision fields (schemas)
# ─────────────────────────────────────────────────────────────────────────────

class TestR1StrictRevisionSchemas:
    """Three safe consumer schemas: expected_app3_revision must be StrictInt ge=1 or None."""

    @pytest.mark.parametrize("schema_path", [
        "schemas.legal_engine.SafeIndustrialConsumerInput",
        "schemas.legal_engine.SafeConstructionConsumerInput",
        "schemas.legal_engine.SafeBuildingConsumerInput",
    ])
    def test_R1a_revision_zero_rejected_all_schemas(self, schema_path: str):
        """revision=0 must be rejected by all three safe schemas."""
        from pydantic import ValidationError
        import importlib
        parts = schema_path.rsplit(".", 1)
        mod = importlib.import_module(parts[0])
        cls = getattr(mod, parts[1])
        with pytest.raises(ValidationError):
            cls(expected_app3_revision=0)

    @pytest.mark.parametrize("schema_path", [
        "schemas.legal_engine.SafeIndustrialConsumerInput",
        "schemas.legal_engine.SafeConstructionConsumerInput",
        "schemas.legal_engine.SafeBuildingConsumerInput",
    ])
    def test_R1b_revision_negative_rejected_all_schemas(self, schema_path: str):
        """revision=-1 must be rejected by all three safe schemas."""
        from pydantic import ValidationError
        import importlib
        parts = schema_path.rsplit(".", 1)
        mod = importlib.import_module(parts[0])
        cls = getattr(mod, parts[1])
        with pytest.raises(ValidationError):
            cls(expected_app3_revision=-1)

    @pytest.mark.parametrize("schema_path", [
        "schemas.legal_engine.SafeIndustrialConsumerInput",
        "schemas.legal_engine.SafeConstructionConsumerInput",
        "schemas.legal_engine.SafeBuildingConsumerInput",
    ])
    def test_R1c_revision_bool_rejected_all_schemas(self, schema_path: str):
        """revision=True (bool) must be rejected by all three safe schemas (StrictInt)."""
        from pydantic import ValidationError
        import importlib
        parts = schema_path.rsplit(".", 1)
        mod = importlib.import_module(parts[0])
        cls = getattr(mod, parts[1])
        with pytest.raises(ValidationError):
            cls(expected_app3_revision=True)

    def test_R1d_confirm_body_revision_zero_rejected(self):
        """FactoryLegalClassificationConfirmBody.expected_revision=0 must be rejected."""
        from pydantic import ValidationError
        from routers.factory_legal_classification import FactoryLegalClassificationConfirmBody
        with pytest.raises(ValidationError):
            FactoryLegalClassificationConfirmBody(
                appendix3_item_no=10,
                confirmed_sector="INDUSTRIAL",
                expected_revision=0,
                confirm_deliberate=True,
            )

    def test_R1e_confirm_body_revision_positive_accepted(self):
        """FactoryLegalClassificationConfirmBody.expected_revision=1 must be accepted."""
        from routers.factory_legal_classification import FactoryLegalClassificationConfirmBody
        b = FactoryLegalClassificationConfirmBody(
            appendix3_item_no=10,
            confirmed_sector="INDUSTRIAL",
            expected_revision=1,
            confirm_deliberate=True,
        )
        assert b.expected_revision == 1

    def test_R1f_confirm_body_revision_none_accepted(self):
        """FactoryLegalClassificationConfirmBody.expected_revision=None accepted (first insert)."""
        from routers.factory_legal_classification import FactoryLegalClassificationConfirmBody
        b = FactoryLegalClassificationConfirmBody(
            appendix3_item_no=10,
            confirmed_sector="INDUSTRIAL",
            expected_revision=None,
            confirm_deliberate=True,
        )
        assert b.expected_revision is None


# ─────────────────────────────────────────────────────────────────────────────
# R2/R6 — expected_app3_revision required on flag-ON diagnosis path
# ─────────────────────────────────────────────────────────────────────────────

class TestR2R6RevisionRequiredOnFlagOn:
    """Flag ON: expected_app3_revision is required. Missing → 422. Mismatch → 409."""

    def test_R2a_missing_revision_raises_422_when_flag_on(self):
        """Flag ON + matching record + no expected_app3_revision → 422 APPENDIX3_REVISION_REQUIRED."""
        from services.canonical.saas_appendix3_contract import check_saas_appendix3_contract
        sb = _sb_returning("INDUSTRIAL")
        with (
            patch("services.canonical.saas_appendix3_contract.SAAS_APP3_ENABLED", True),
            patch("services.factory_legal_classification_svc.get_factory_legal_classification",
                  return_value=_stored(revision=2)),
        ):
            consumer = _consumer(item=10, expected_rev=None)
            with pytest.raises(HTTPException) as exc_info:
                check_saas_appendix3_contract(sb, "fac-001", "INDUSTRIAL", consumer)

        assert exc_info.value.status_code == 422
        assert exc_info.value.detail["code"] == "APPENDIX3_REVISION_REQUIRED"

    def test_R2b_correct_revision_passes(self):
        """Flag ON + matching record + correct revision → projection returned."""
        from services.canonical.saas_appendix3_contract import check_saas_appendix3_contract
        sb = _sb_returning("INDUSTRIAL")
        with (
            patch("services.canonical.saas_appendix3_contract.SAAS_APP3_ENABLED", True),
            patch("services.factory_legal_classification_svc.get_factory_legal_classification",
                  return_value=_stored(revision=2)),
        ):
            consumer = _consumer(item=10, expected_rev=2)
            proj = check_saas_appendix3_contract(sb, "fac-001", "INDUSTRIAL", consumer)
        assert proj is not None

    def test_R2c_stale_revision_raises_409(self):
        """Flag ON + expected_rev=1 but stored=2 → 409 STALE_REVISION."""
        from services.canonical.saas_appendix3_contract import check_saas_appendix3_contract
        sb = _sb_returning("INDUSTRIAL")
        with (
            patch("services.canonical.saas_appendix3_contract.SAAS_APP3_ENABLED", True),
            patch("services.factory_legal_classification_svc.get_factory_legal_classification",
                  return_value=_stored(revision=2)),
        ):
            consumer = _consumer(item=10, expected_rev=1)  # stale
            with pytest.raises(HTTPException) as exc_info:
                check_saas_appendix3_contract(sb, "fac-001", "INDUSTRIAL", consumer)

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "STALE_REVISION"

    def test_R2d_flag_off_missing_revision_is_noop(self):
        """Flag OFF + no new fields → None (no-op). Revision not required when flag OFF."""
        from services.canonical.saas_appendix3_contract import check_saas_appendix3_contract
        sb = MagicMock()
        with patch("services.canonical.saas_appendix3_contract.SAAS_APP3_ENABLED", False):
            from types import SimpleNamespace
            consumer = SimpleNamespace(
                appendix3_item_no=None,
                is_real_estate_management=None,
                expected_app3_revision=None,
                is_relationship_contractor=None,
                is_civil_construction=None,
            )
            result = check_saas_appendix3_contract(sb, "fac-001", "INDUSTRIAL", consumer)
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# R3 — confirmed_at refreshed on CAS UPDATE
# ─────────────────────────────────────────────────────────────────────────────

class TestR3ConfirmedAtRefreshed:
    """CAS UPDATE payload must include server-generated confirmed_at (UTC)."""

    def test_R3a_update_payload_includes_confirmed_at(self):
        """UPDATE path: confirmed_at is present in the update payload."""
        from services.factory_legal_classification_svc import confirm_factory_legal_classification

        update_calls: list = []

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
            # factory_legal_classifications — existing record revision=1
            c = MagicMock()
            c.select.return_value.eq.return_value.limit.return_value.execute.return_value = \
                MagicMock(data=[{"factory_id": "f1", "appendix3_item_no": 10, "revision": 1,
                                 "confirmed_sector": "INDUSTRIAL"}])
            # Capture update payload
            def _update(payload):
                update_calls.append(payload)
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.execute.return_value = MagicMock(data=[{"factory_id": "f1", "revision": 2}])
                return chain
            c.update.side_effect = _update
            return c

        sb = MagicMock()
        sb.table.side_effect = _selective_table

        confirm_factory_legal_classification(
            sb,
            factory_id="f1",
            appendix3_item_no=10,
            is_real_estate_management=None,
            confirmed_sector="INDUSTRIAL",
            expected_revision=1,
            confirmed_by="user-001",
        )

        assert len(update_calls) == 1
        payload = update_calls[0]
        assert "confirmed_at" in payload, "confirmed_at must be in UPDATE payload"
        # Must be a valid ISO-format UTC timestamp
        confirmed_at = payload["confirmed_at"]
        dt = datetime.fromisoformat(confirmed_at.replace("Z", "+00:00"))
        assert dt.tzinfo is not None, "confirmed_at must be timezone-aware"

    def test_R3b_insert_payload_does_not_include_confirmed_at(self):
        """INSERT path (first confirm): confirmed_at is set by DB DEFAULT, not in payload."""
        from services.factory_legal_classification_svc import confirm_factory_legal_classification

        insert_calls: list = []

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
            c = MagicMock()
            c.select.return_value.eq.return_value.limit.return_value.execute.return_value = \
                MagicMock(data=[])  # no existing record

            def _insert(payload):
                insert_calls.append(payload)
                chain = MagicMock()
                chain.execute.return_value = MagicMock(data=[{"factory_id": "f2", "revision": 1}])
                return chain
            c.insert.side_effect = _insert
            return c

        sb = MagicMock()
        sb.table.side_effect = _selective_table

        confirm_factory_legal_classification(
            sb,
            factory_id="f2",
            appendix3_item_no=10,
            is_real_estate_management=None,
            confirmed_sector="INDUSTRIAL",
            expected_revision=None,
            confirmed_by="user-001",
        )

        assert len(insert_calls) == 1
        # INSERT uses DB DEFAULT now(); no client-supplied confirmed_at
        assert "confirmed_at" not in insert_calls[0], \
            "INSERT must not include confirmed_at (DB DEFAULT handles it)"


# ─────────────────────────────────────────────────────────────────────────────
# R4 — Item37 subtype required at confirm
# ─────────────────────────────────────────────────────────────────────────────

class TestR4Item37SubtypeRequiredAtConfirm:
    """Confirm service: item37 + is_real_estate_management=None must raise 422."""

    def test_R4a_item37_subtype_none_raises_422_at_confirm(self):
        """item37 + is_real_estate_management=None → 422 APPENDIX3_EXPLICIT_CLASSIFICATION_REQUIRED."""
        from services.factory_legal_classification_svc import confirm_factory_legal_classification

        def _table(name):
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
            return MagicMock()

        sb = MagicMock()
        sb.table.side_effect = _table

        with pytest.raises(HTTPException) as exc_info:
            confirm_factory_legal_classification(
                sb,
                factory_id="f1",
                appendix3_item_no=37,
                is_real_estate_management=None,  # must be rejected
                confirmed_sector="INDUSTRIAL",
                expected_revision=None,
                confirmed_by="user-001",
            )

        assert exc_info.value.status_code == 422
        detail = exc_info.value.detail
        assert "is_real_estate_management" in str(detail)

    def test_R4b_item37_subtype_true_accepted(self):
        """item37 + is_real_estate_management=True → passes confirm validation."""
        from services.factory_legal_classification_svc import confirm_factory_legal_classification

        def _table(name):
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
            c = MagicMock()
            c.select.return_value.eq.return_value.limit.return_value.execute.return_value = \
                MagicMock(data=[])  # first insert
            c.insert.return_value.execute.return_value = \
                MagicMock(data=[{"factory_id": "f1", "revision": 1}])
            return c

        sb = MagicMock()
        sb.table.side_effect = _table

        result = confirm_factory_legal_classification(
            sb,
            factory_id="f1",
            appendix3_item_no=37,
            is_real_estate_management=True,
            confirmed_sector="INDUSTRIAL",
            expected_revision=None,
            confirmed_by="user-001",
        )
        assert result is not None

    def test_R4c_item37_subtype_false_accepted(self):
        """item37 + is_real_estate_management=False → passes confirm validation."""
        from services.factory_legal_classification_svc import confirm_factory_legal_classification

        def _table(name):
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
            c = MagicMock()
            c.select.return_value.eq.return_value.limit.return_value.execute.return_value = \
                MagicMock(data=[])
            c.insert.return_value.execute.return_value = \
                MagicMock(data=[{"factory_id": "f1", "revision": 1}])
            return c

        sb = MagicMock()
        sb.table.side_effect = _table

        result = confirm_factory_legal_classification(
            sb,
            factory_id="f1",
            appendix3_item_no=37,
            is_real_estate_management=False,
            confirmed_sector="INDUSTRIAL",
            expected_revision=None,
            confirmed_by="user-001",
        )
        assert result is not None


# ─────────────────────────────────────────────────────────────────────────────
# R5 — Canonical validator reuse (no duplicate logic in SaaS gate)
# ─────────────────────────────────────────────────────────────────────────────

class TestR5CanonicalValidatorReuse:
    """SaaS gate delegates type/range/item37 checks to existing canonical validator."""

    def test_R5a_canonical_error_codes_preserved(self):
        """Type error on item_no propagates canonical APPENDIX3_ITEM_NO_TYPE error code."""
        from services.canonical.saas_appendix3_contract import check_saas_appendix3_contract
        from types import SimpleNamespace
        sb = MagicMock()
        consumer = SimpleNamespace(
            appendix3_item_no=True,  # bool — strict int rejects this
            is_real_estate_management=None,
            expected_app3_revision=None,
            is_relationship_contractor=None,
            is_civil_construction=None,
        )
        with patch("services.canonical.saas_appendix3_contract.SAAS_APP3_ENABLED", True):
            with pytest.raises(HTTPException) as exc_info:
                check_saas_appendix3_contract(sb, "fac-001", "INDUSTRIAL", consumer)
        assert exc_info.value.status_code == 422
        assert exc_info.value.detail["code"] == "APPENDIX3_ITEM_NO_TYPE"

    def test_R5b_range_error_code_preserved(self):
        """Range error on item_no=0 propagates canonical APPENDIX3_ITEM_NO_RANGE error code."""
        from services.canonical.saas_appendix3_contract import check_saas_appendix3_contract
        from types import SimpleNamespace
        sb = MagicMock()
        consumer = SimpleNamespace(
            appendix3_item_no=0,
            is_real_estate_management=None,
            expected_app3_revision=None,
            is_relationship_contractor=None,
            is_civil_construction=None,
        )
        with patch("services.canonical.saas_appendix3_contract.SAAS_APP3_ENABLED", True):
            with pytest.raises(HTTPException) as exc_info:
                check_saas_appendix3_contract(sb, "fac-001", "INDUSTRIAL", consumer)
        assert exc_info.value.status_code == 422
        assert exc_info.value.detail["code"] == "APPENDIX3_ITEM_NO_RANGE"


# ─────────────────────────────────────────────────────────────────────────────
# R7 — Authoritative factories.sector re-read
# ─────────────────────────────────────────────────────────────────────────────

class TestR7AuthoritativeSectorReread:
    """After stored record read, factories.sector is re-read and compared to request sector."""

    def test_R7a_factory_sector_matches_passes(self):
        """factories.sector=INDUSTRIAL, request INDUSTRIAL → passes R7 gate."""
        from services.canonical.saas_appendix3_contract import check_saas_appendix3_contract
        sb = _sb_returning("INDUSTRIAL")
        with (
            patch("services.canonical.saas_appendix3_contract.SAAS_APP3_ENABLED", True),
            patch("services.factory_legal_classification_svc.get_factory_legal_classification",
                  return_value=_stored(revision=1)),
        ):
            consumer = _consumer(item=10, expected_rev=1)
            proj = check_saas_appendix3_contract(sb, "fac-001", "INDUSTRIAL", consumer)
        assert proj is not None

    def test_R7b_current_sector_drift_raises_409(self):
        """factories.sector changed from INDUSTRIAL to BUILDING after classification confirmed.

        Even though stored confirmed_sector=INDUSTRIAL and request=INDUSTRIAL,
        the authoritative current factory sector=BUILDING triggers R7 SECTOR_DRIFT.
        """
        from services.canonical.saas_appendix3_contract import check_saas_appendix3_contract
        # Factory sector has changed to BUILDING (authoritative current state)
        sb = _sb_returning("BUILDING")
        with (
            patch("services.canonical.saas_appendix3_contract.SAAS_APP3_ENABLED", True),
            patch("services.factory_legal_classification_svc.get_factory_legal_classification",
                  return_value=_stored(sector="INDUSTRIAL", revision=1)),
        ):
            consumer = _consumer(item=10, expected_rev=1)
            with pytest.raises(HTTPException) as exc_info:
                # Request uses INDUSTRIAL, but factory is now BUILDING
                check_saas_appendix3_contract(sb, "fac-001", "INDUSTRIAL", consumer)

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "SECTOR_DRIFT"

    def test_R7c_factory_not_found_raises_404(self):
        """factories table returns empty data → 404 FACTORY_NOT_FOUND."""
        from services.canonical.saas_appendix3_contract import check_saas_appendix3_contract
        sb = MagicMock()
        # factories returns empty data
        sb.table.return_value.select.return_value.eq.return_value.limit.return_value \
            .execute.return_value.data = []

        with (
            patch("services.canonical.saas_appendix3_contract.SAAS_APP3_ENABLED", True),
            patch("services.factory_legal_classification_svc.get_factory_legal_classification",
                  return_value=_stored(revision=1)),
        ):
            consumer = _consumer(item=10, expected_rev=1)
            with pytest.raises(HTTPException) as exc_info:
                check_saas_appendix3_contract(sb, "fac-001", "INDUSTRIAL", consumer)

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail["code"] == "FACTORY_NOT_FOUND"
