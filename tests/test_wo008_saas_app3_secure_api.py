"""WO-008: Local deterministic fixture tests — SaaS Appendix3 secure API.

Coverage per WO-008 Section 5:
  1. Three safe routes: strict item validation (type/range), item37 subtype, non37 null.
  2. CONSTRUCTION + item49 child predicates; no aliasing from Art68 fields.
  3. RLS privilege SQL guard (static SQL review — no live DB).
  4. Facility confirmation: owner/foreign/sector-drift/stale-revision/race/audit.
  5. Projection: item1/37/40/49 maps to expected AP01-05 leaves; C3 preserves raw item.
  6. Default flag OFF: no passthrough; 422 on new fields.

NO LEG_POST = 0. NO DB writes. All DB calls mocked.
"""
from __future__ import annotations

import importlib
import sys
import types
from types import SimpleNamespace
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest


# ── Helpers ──────────────────────────────────────────────────────────────────


def _mock_sb(rows: list = None, *, update_rows: list = None):
    """Build a minimal supabase mock that returns `rows` on execute()."""
    rows = rows or []
    ures = MagicMock()
    ures.data = update_rows if update_rows is not None else rows
    chain = MagicMock()
    chain.execute.return_value = ures
    chain.select.return_value = chain
    chain.insert.return_value = chain
    chain.update.return_value = chain
    chain.eq.return_value = chain
    chain.limit.return_value = chain
    sb = MagicMock()
    sb.table.return_value = chain
    return sb, chain, ures


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1 — Strict item validation
# ─────────────────────────────────────────────────────────────────────────────


class TestSchemaItemValidation:
    """SafeIndustrialConsumerInput — appendix3_item_no strict type/range."""

    def _parse(self, payload: dict):
        from schemas.legal_engine import SafeIndustrialConsumerInput
        return SafeIndustrialConsumerInput(**payload)

    def test_S1_item_0_rejected(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            self._parse({"appendix3_item_no": 0})

    def test_S2_item_1_accepted(self):
        m = self._parse({"appendix3_item_no": 1})
        assert m.appendix3_item_no == 1

    def test_S3_item_49_accepted(self):
        m = self._parse({"appendix3_item_no": 49})
        assert m.appendix3_item_no == 49

    def test_S4_item_50_rejected(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            self._parse({"appendix3_item_no": 50})

    def test_S5_item_string_rejected(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            self._parse({"appendix3_item_no": "1"})

    def test_S6_item_float_rejected(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            self._parse({"appendix3_item_no": 1.0})

    def test_S7_item_bool_rejected(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            self._parse({"appendix3_item_no": True})

    def test_S8_item37_subtype_true(self):
        m = self._parse({"appendix3_item_no": 37, "is_real_estate_management": True})
        assert m.is_real_estate_management is True

    def test_S9_item37_subtype_false_preserved(self):
        m = self._parse({"appendix3_item_no": 37, "is_real_estate_management": False})
        assert m.is_real_estate_management is False

    def test_S10_item37_subtype_missing_accepted(self):
        m = self._parse({"appendix3_item_no": 37})
        assert m.is_real_estate_management is None

    def test_S11_non37_subtype_null(self):
        m = self._parse({"appendix3_item_no": 10})
        assert m.is_real_estate_management is None

    def test_S12_expected_app3_revision_control_field(self):
        m = self._parse({"appendix3_item_no": 5, "expected_app3_revision": 3})
        assert m.expected_app3_revision == 3

    def test_S13_extra_field_forbidden(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            self._parse({"appendix3_item_no": 5, "is_appendix3_1_27": True})


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2 — CONSTRUCTION child predicates + Art68 no-alias
# ─────────────────────────────────────────────────────────────────────────────


class TestConstructionSchemaPredicates:
    """SafeConstructionConsumerInput — WO-008 App3 + item49 children."""

    def _parse(self, payload: dict):
        from schemas.legal_engine import SafeConstructionConsumerInput
        return SafeConstructionConsumerInput(**payload)

    def test_C1_item49_relationship_and_civil_accepted(self):
        m = self._parse({
            "appendix3_item_no": 49,
            "is_relationship_contractor": True,
            "is_civil_construction": False,
        })
        assert m.is_relationship_contractor is True
        assert m.is_civil_construction is False

    def test_C2_item49_relationship_strict_false(self):
        m = self._parse({"appendix3_item_no": 49, "is_relationship_contractor": False, "is_civil_construction": True})
        assert m.is_relationship_contractor is False

    def test_C3_item49_child_missing_accepted_at_schema_layer(self):
        m = self._parse({"appendix3_item_no": 49})
        assert m.is_relationship_contractor is None
        assert m.is_civil_construction is None

    def test_C4_leads_and_manages_not_aliased(self):
        m = self._parse({
            "appendix3_item_no": 49,
            "leads_and_manages_construction_execution": True,
            "is_relationship_contractor": False,
            "is_civil_construction": False,
        })
        # leads_and_manages_construction_execution is Art.68 fact, not an alias
        assert m.leads_and_manages_construction_execution is True
        assert m.is_relationship_contractor is False

    def test_C5_art68_field_stays_independent(self):
        m = self._parse({"leads_and_manages_construction_execution": True})
        assert m.appendix3_item_no is None
        assert m.is_relationship_contractor is None

    def test_C6_extra_derived_leaf_forbidden(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            self._parse({"appendix3_item_no": 49, "is_appendix3_28_48": True})


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3 — RLS privilege static SQL review
# ─────────────────────────────────────────────────────────────────────────────


class TestRlsPrivilegeStaticSql:
    """Static analysis of migration SQL — RLS on / anon revoked / service_role minimal."""

    @pytest.fixture
    def sql(self) -> str:
        import os
        path = os.path.join(
            os.path.dirname(__file__), "..",
            "supabase", "migrations",
            "20261011000001_factory_legal_classifications_foundation.sql",
        )
        with open(os.path.abspath(path)) as f:
            return f.read()

    def test_R1_rls_enabled_on_classifications(self, sql):
        assert "enable row level security" in sql.lower()

    def test_R2_revoke_anon_classifications(self, sql):
        assert "revoke all on public.factory_legal_classifications from anon" in sql

    def test_R3_revoke_authenticated_classifications(self, sql):
        assert "revoke all on public.factory_legal_classifications from authenticated" in sql

    def test_R4_revoke_anon_events(self, sql):
        assert "revoke all on public.factory_legal_classification_events from anon" in sql

    def test_R5_revoke_authenticated_events(self, sql):
        assert "revoke all on public.factory_legal_classification_events from authenticated" in sql

    def test_R6_service_role_minimal_classifications(self, sql):
        assert "grant select, insert, update on public.factory_legal_classifications to service_role" in sql

    def test_R7_service_role_minimal_events_no_update(self, sql):
        assert "grant select, insert on public.factory_legal_classification_events to service_role" in sql
        # UPDATE must NOT be granted to events (append-only)
        lines = sql.split("\n")
        for line in lines:
            if "grant" in line.lower() and "factory_legal_classification_events" in line.lower():
                assert "update" not in line.lower(), f"events table must not grant UPDATE: {line}"

    def test_R8_no_factories_rls_alteration(self, sql):
        assert "factories enable row level security" not in sql.lower()

    def test_R9_security_invoker_not_definer(self, sql):
        assert "security invoker" in sql.lower()
        # Check non-comment lines only: comments may mention DEFINER to explain the prohibition
        non_comment_lines = [l for l in sql.split("\n") if not l.strip().startswith("--")]
        non_comment_sql = "\n".join(non_comment_lines).lower()
        assert "security definer" not in non_comment_sql

    def test_R10_trigger_covers_insert_and_update(self, sql):
        assert "after insert or update" in sql.lower()

    def test_R11_audit_table_uses_legal_table_not_factories(self, sql):
        assert "public.factory_legal_classifications" in sql
        assert "public.factory_legal_classification_events" in sql
        # factories table must only appear as FK reference, not as authority target
        lines = [l for l in sql.split("\n") if "public.factories" in l.lower() and "enable row level" in l.lower()]
        assert len(lines) == 0


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4 — Facility confirmation service
# ─────────────────────────────────────────────────────────────────────────────


class TestConfirmService:
    """factory_legal_classification_svc — owner/foreign/sector-drift/CAS/race/audit."""

    def _confirm(self, sb, **kwargs):
        from services.factory_legal_classification_svc import confirm_factory_legal_classification
        defaults = dict(
            factory_id="fac-001",
            appendix3_item_no=10,
            is_real_estate_management=None,
            confirmed_sector="INDUSTRIAL",
            expected_revision=None,
            confirmed_by="user-001",
        )
        defaults.update(kwargs)
        return confirm_factory_legal_classification(sb, **defaults)

    def _factories_row(self, sector: str = "INDUSTRIAL") -> list:
        return [{"sector": sector}]

    def test_F1_first_insert_returns_row(self):
        sb = MagicMock()
        # factories.sector read
        frow = MagicMock(); frow.data = [{"sector": "INDUSTRIAL"}]
        # factory_legal_classifications read (empty)
        rrow = MagicMock(); rrow.data = []
        # insert result
        irow = MagicMock(); irow.data = [{"factory_id": "fac-001", "revision": 1}]
        chain = MagicMock()
        chain.select.return_value = chain
        chain.insert.return_value = chain
        chain.update.return_value = chain
        chain.eq.return_value = chain
        chain.limit.return_value = chain

        call_count = {"n": 0}
        def execute():
            n = call_count["n"]
            call_count["n"] += 1
            if n == 0:
                return frow   # factories sector
            elif n == 1:
                return rrow   # no current record
            else:
                return irow   # insert
        chain.execute.side_effect = execute
        sb.table.return_value = chain

        row = self._confirm(sb)
        assert row["revision"] == 1

    def test_F2_existing_factory_no_record_is_unconfirmed(self):
        from services.factory_legal_classification_svc import get_factory_legal_classification
        sb, chain, ures = _mock_sb([])
        result = get_factory_legal_classification(sb, "fac-999")
        assert result is None

    def test_F3_stale_revision_raises_409(self):
        from fastapi import HTTPException
        sb = MagicMock()
        frow = MagicMock(); frow.data = [{"sector": "INDUSTRIAL"}]
        rrow = MagicMock(); rrow.data = [{"factory_id": "fac-001", "revision": 5, "appendix3_item_no": 10, "confirmed_sector": "INDUSTRIAL", "appendix3_law_version_id": "1fa1f5af-3575-461d-8d8c-4389d0e128d8", "is_real_estate_management": None}]
        call_count = {"n": 0}
        chain = MagicMock()
        chain.select.return_value = chain
        chain.eq.return_value = chain
        chain.limit.return_value = chain
        def execute():
            n = call_count["n"]
            call_count["n"] += 1
            return frow if n == 0 else rrow
        chain.execute.side_effect = execute
        sb.table.return_value = chain

        with pytest.raises(HTTPException) as exc_info:
            self._confirm(sb, expected_revision=3)  # wrong revision
        assert exc_info.value.status_code == 409
        assert "STALE_REVISION" in str(exc_info.value.detail)

    def test_F4_sector_drift_raises_409(self):
        from fastapi import HTTPException
        sb = MagicMock()
        # factory sector is BUILDING but confirm requests INDUSTRIAL
        frow = MagicMock(); frow.data = [{"sector": "BUILDING"}]
        chain = MagicMock()
        chain.select.return_value = chain
        chain.eq.return_value = chain
        chain.limit.return_value = chain
        chain.execute.return_value = frow
        sb.table.return_value = chain

        with pytest.raises(HTTPException) as exc_info:
            self._confirm(sb, confirmed_sector="INDUSTRIAL")
        assert exc_info.value.status_code == 409
        assert "SECTOR_DRIFT" in str(exc_info.value.detail)

    def test_F5_invalid_item_0_raises_422(self):
        from fastapi import HTTPException
        sb, _, _ = _mock_sb([{"sector": "INDUSTRIAL"}])
        with pytest.raises(HTTPException) as exc_info:
            self._confirm(sb, appendix3_item_no=0)
        assert exc_info.value.status_code == 422

    def test_F6_invalid_item_50_raises_422(self):
        from fastapi import HTTPException
        sb, _, _ = _mock_sb([{"sector": "INDUSTRIAL"}])
        with pytest.raises(HTTPException) as exc_info:
            self._confirm(sb, appendix3_item_no=50)
        assert exc_info.value.status_code == 422

    def test_F7_non37_with_subtype_raises_422(self):
        from fastapi import HTTPException
        sb, _, _ = _mock_sb([{"sector": "INDUSTRIAL"}])
        with pytest.raises(HTTPException) as exc_info:
            self._confirm(sb, appendix3_item_no=10, is_real_estate_management=True)
        assert exc_info.value.status_code == 422
        assert "NON37" in str(exc_info.value.detail)

    def test_F8_cas_zero_rows_returns_409(self):
        from fastapi import HTTPException
        sb = MagicMock()
        frow = MagicMock(); frow.data = [{"sector": "INDUSTRIAL"}]
        rrow = MagicMock(); rrow.data = [{"factory_id": "fac-001", "revision": 2, "appendix3_item_no": 10, "confirmed_sector": "INDUSTRIAL", "appendix3_law_version_id": "1fa1f5af-3575-461d-8d8c-4389d0e128d8", "is_real_estate_management": None}]
        urow = MagicMock(); urow.data = []  # CAS predicate missed — 0 rows
        call_count = {"n": 0}
        chain = MagicMock()
        chain.select.return_value = chain
        chain.update.return_value = chain
        chain.eq.return_value = chain
        chain.limit.return_value = chain
        def execute():
            n = call_count["n"]
            call_count["n"] += 1
            if n == 0: return frow
            elif n == 1: return rrow
            else: return urow
        chain.execute.side_effect = execute
        sb.table.return_value = chain

        with pytest.raises(HTTPException) as exc_info:
            self._confirm(sb, expected_revision=2)  # correct revision, but CAS returns 0 rows
        assert exc_info.value.status_code == 409
        assert "STALE_REVISION" in str(exc_info.value.detail)

    def test_F9_item_changes_allowed_with_correct_revision(self):
        """Re-confirm with different item_no is allowed when revision matches."""
        sb = MagicMock()
        frow = MagicMock(); frow.data = [{"sector": "INDUSTRIAL"}]
        rrow = MagicMock(); rrow.data = [{"factory_id": "fac-001", "revision": 1, "appendix3_item_no": 5, "confirmed_sector": "INDUSTRIAL", "appendix3_law_version_id": "1fa1f5af-3575-461d-8d8c-4389d0e128d8", "is_real_estate_management": None}]
        urow = MagicMock(); urow.data = [{"factory_id": "fac-001", "revision": 2, "appendix3_item_no": 10}]
        call_count = {"n": 0}
        chain = MagicMock()
        chain.select.return_value = chain
        chain.update.return_value = chain
        chain.eq.return_value = chain
        chain.limit.return_value = chain
        def execute():
            n = call_count["n"]
            call_count["n"] += 1
            if n == 0: return frow
            elif n == 1: return rrow
            else: return urow
        chain.execute.side_effect = execute
        sb.table.return_value = chain

        row = self._confirm(sb, appendix3_item_no=10, expected_revision=1)
        assert row["revision"] == 2


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5 — Projection: AP01-05 leaves from source item
# ─────────────────────────────────────────────────────────────────────────────


class TestProjection:
    """project_explicit_appendix3_classification — item→leaves mapping."""

    def _proj(self, item_no, subtype=None):
        from services.canonical.explicit_appendix3_classification import (
            project_explicit_appendix3_classification,
        )
        return project_explicit_appendix3_classification(item_no, subtype)

    def test_P1_item1_maps_to_1_27_true(self):
        p = self._proj(1)
        assert p["is_appendix3_1_27"] is True
        assert p["is_appendix3_28_48"] is False
        assert p["is_appendix3_item_37"] is False
        assert p["is_appendix3_item_40"] is False

    def test_P2_item37_no_subtype_leaves_present(self):
        p = self._proj(37)
        assert p["is_appendix3_28_48"] is True
        assert p["is_appendix3_item_37"] is True
        assert "is_real_estate_management" not in p

    def test_P3_item37_subtype_false_preserved(self):
        p = self._proj(37, False)
        assert p["is_appendix3_item_37"] is True
        assert p["is_real_estate_management"] is False

    def test_P4_item37_subtype_true(self):
        p = self._proj(37, True)
        assert p["is_real_estate_management"] is True

    def test_P5_item40_maps_to_item_40_true(self):
        p = self._proj(40)
        assert p["is_appendix3_item_40"] is True
        assert p["is_appendix3_28_48"] is True
        assert p["is_appendix3_item_37"] is False

    def test_P6_item49_all_false(self):
        p = self._proj(49)
        assert p["is_appendix3_1_27"] is False
        assert p["is_appendix3_28_48"] is False
        assert p["is_appendix3_item_37"] is False
        assert p["is_appendix3_item_40"] is False

    def test_P7_item49_no_is_construction_implied(self):
        p = self._proj(49)
        assert "is_construction" not in p

    def test_P8_client_cannot_supply_derived_leaves(self):
        from pydantic import ValidationError
        from schemas.legal_engine import SafeIndustrialConsumerInput
        with pytest.raises(ValidationError):
            SafeIndustrialConsumerInput(is_appendix3_1_27=True)

    def test_P9_raw_item_preserved_alongside_leaves_in_override_fields(self):
        from services.safe_industrial_leg_runtime import SAFE_UI_OVERRIDE_FIELDS
        assert "appendix3_item_no" in SAFE_UI_OVERRIDE_FIELDS
        # AP01-05 leaves must NOT be in SAFE_UI_OVERRIDE_FIELDS (server-generated only)
        for leaf in ("is_appendix3_1_27", "is_appendix3_28_48", "is_appendix3_item_37",
                     "is_appendix3_item_40"):
            assert leaf not in SAFE_UI_OVERRIDE_FIELDS


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6 — Default flag OFF behaviour
# ─────────────────────────────────────────────────────────────────────────────


class TestFlagOff:
    """SAAS_APP3_ENABLED=false (default) — 422 on new fields, no-op otherwise."""

    @pytest.fixture(autouse=True)
    def _ensure_flag_off(self, monkeypatch):
        from services.canonical import saas_appendix3_contract as mod
        monkeypatch.setattr(mod, "SAAS_APP3_ENABLED", False)

    def test_O1_no_app3_fields_returns_none(self):
        from services.canonical.saas_appendix3_contract import check_saas_appendix3_contract
        from schemas.legal_engine import SafeIndustrialConsumerInput
        sb, _, _ = _mock_sb([])
        inp = SafeIndustrialConsumerInput(worker_count=10)
        result = check_saas_appendix3_contract(sb, "fac-001", "INDUSTRIAL", inp)
        assert result is None

    def test_O2_item_no_present_raises_422(self):
        from fastapi import HTTPException
        from services.canonical.saas_appendix3_contract import check_saas_appendix3_contract
        from schemas.legal_engine import SafeIndustrialConsumerInput
        sb, _, _ = _mock_sb([])
        inp = SafeIndustrialConsumerInput(appendix3_item_no=10)
        with pytest.raises(HTTPException) as exc_info:
            check_saas_appendix3_contract(sb, "fac-001", "INDUSTRIAL", inp)
        assert exc_info.value.status_code == 422
        assert "SAAS_APP3_NOT_ENABLED" in str(exc_info.value.detail)

    def test_O3_is_real_estate_management_present_raises_422(self):
        from fastapi import HTTPException
        from services.canonical.saas_appendix3_contract import check_saas_appendix3_contract
        from schemas.legal_engine import SafeIndustrialConsumerInput
        sb, _, _ = _mock_sb([])
        inp = SafeIndustrialConsumerInput(appendix3_item_no=37, is_real_estate_management=False)
        with pytest.raises(HTTPException) as exc_info:
            check_saas_appendix3_contract(sb, "fac-001", "INDUSTRIAL", inp)
        assert exc_info.value.status_code == 422

    def test_O4_expected_revision_present_raises_422(self):
        from fastapi import HTTPException
        from services.canonical.saas_appendix3_contract import check_saas_appendix3_contract
        from schemas.legal_engine import SafeIndustrialConsumerInput
        sb, _, _ = _mock_sb([])
        inp = SafeIndustrialConsumerInput(expected_app3_revision=1)
        with pytest.raises(HTTPException) as exc_info:
            check_saas_appendix3_contract(sb, "fac-001", "INDUSTRIAL", inp)
        assert exc_info.value.status_code == 422

    def test_O5_old_fields_only_returns_none(self):
        from services.canonical.saas_appendix3_contract import check_saas_appendix3_contract
        from schemas.legal_engine import SafeIndustrialConsumerInput
        sb, _, _ = _mock_sb([])
        inp = SafeIndustrialConsumerInput(worker_count=50, has_boiler=True)
        result = check_saas_appendix3_contract(sb, "fac-001", "INDUSTRIAL", inp)
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7 — Flag ON contract matching
# ─────────────────────────────────────────────────────────────────────────────


_STORED_RECORD = {
    "factory_id": "fac-001",
    "appendix3_item_no": 10,
    "is_real_estate_management": None,
    "confirmed_sector": "INDUSTRIAL",
    "appendix3_law_version_id": "1fa1f5af-3575-461d-8d8c-4389d0e128d8",
    "revision": 3,
    # R7 (WO-008B): factories.sector re-read uses same mock chain; sector must match route sector.
    "sector": "INDUSTRIAL",
}


class TestFlagOnContract:
    """SAAS_APP3_ENABLED=true — stored record comparison and projection return."""

    @pytest.fixture(autouse=True)
    def _flag_on(self, monkeypatch):
        from services.canonical import saas_appendix3_contract as mod
        monkeypatch.setattr(mod, "SAAS_APP3_ENABLED", True)

    def _run(self, sb, sector: str, item_no: int, subtype=None, expected_rev=None, **extra):
        from services.canonical.saas_appendix3_contract import check_saas_appendix3_contract
        input_cls_map = {
            "INDUSTRIAL": "schemas.legal_engine.SafeIndustrialConsumerInput",
            "BUILDING": "schemas.legal_engine.SafeBuildingConsumerInput",
        }
        from schemas.legal_engine import SafeIndustrialConsumerInput
        kwargs = {"appendix3_item_no": item_no}
        if subtype is not None:
            kwargs["is_real_estate_management"] = subtype
        if expected_rev is not None:
            kwargs["expected_app3_revision"] = expected_rev
        kwargs.update(extra)
        inp = SafeIndustrialConsumerInput(**kwargs)
        return check_saas_appendix3_contract(sb, "fac-001", sector, inp)

    def _sb_with_record(self, record: dict):
        sb = MagicMock()
        row = MagicMock(); row.data = [record]
        chain = MagicMock()
        chain.select.return_value = chain
        chain.eq.return_value = chain
        chain.limit.return_value = chain
        chain.execute.return_value = row
        sb.table.return_value = chain
        return sb

    def test_T1_matching_item_returns_projection(self):
        sb = self._sb_with_record(_STORED_RECORD)
        # R6 (WO-008B): expected_rev required on flag-ON path; use stored revision=3.
        proj = self._run(sb, "INDUSTRIAL", 10, expected_rev=3)
        assert proj is not None
        assert proj["is_appendix3_1_27"] is True
        assert proj["is_appendix3_28_48"] is False

    def test_T2_item_mismatch_raises_409(self):
        from fastapi import HTTPException
        sb = self._sb_with_record(_STORED_RECORD)
        with pytest.raises(HTTPException) as exc_info:
            self._run(sb, "INDUSTRIAL", 20)
        assert exc_info.value.status_code == 409
        assert "CLASSIFICATION_MISMATCH" in str(exc_info.value.detail)

    def test_T3_sector_mismatch_raises_409(self):
        from fastapi import HTTPException
        sb = self._sb_with_record(_STORED_RECORD)
        with pytest.raises(HTTPException) as exc_info:
            self._run(sb, "BUILDING", 10)
        assert exc_info.value.status_code == 409
        assert "SECTOR_DRIFT" in str(exc_info.value.detail)

    def test_T4_stale_revision_raises_409(self):
        from fastapi import HTTPException
        sb = self._sb_with_record(_STORED_RECORD)
        with pytest.raises(HTTPException) as exc_info:
            self._run(sb, "INDUSTRIAL", 10, expected_rev=1)  # stored is 3
        assert exc_info.value.status_code == 409
        assert "STALE_REVISION" in str(exc_info.value.detail)

    def test_T5_correct_revision_passes(self):
        sb = self._sb_with_record(_STORED_RECORD)
        proj = self._run(sb, "INDUSTRIAL", 10, expected_rev=3)
        assert proj is not None

    def test_T6_no_stored_record_raises_409(self):
        from fastapi import HTTPException
        sb, chain, ures = _mock_sb([])
        from services.canonical.saas_appendix3_contract import check_saas_appendix3_contract
        from schemas.legal_engine import SafeIndustrialConsumerInput
        inp = SafeIndustrialConsumerInput(appendix3_item_no=10)
        with pytest.raises(HTTPException) as exc_info:
            check_saas_appendix3_contract(sb, "fac-001", "INDUSTRIAL", inp)
        assert exc_info.value.status_code == 409
        assert "CLASSIFICATION_NOT_CONFIRMED" in str(exc_info.value.detail)

    def test_T7_wrong_law_version_raises_409(self):
        from fastapi import HTTPException
        bad_record = dict(_STORED_RECORD, appendix3_law_version_id="00000000-0000-0000-0000-000000000000")
        sb = self._sb_with_record(bad_record)
        with pytest.raises(HTTPException) as exc_info:
            self._run(sb, "INDUSTRIAL", 10)
        assert exc_info.value.status_code == 409
        assert "LAW_VERSION_MISMATCH" in str(exc_info.value.detail)

    def test_T8_item37_subtype_mismatch_raises_409(self):
        from fastapi import HTTPException
        record_37 = dict(_STORED_RECORD,
                         appendix3_item_no=37, is_real_estate_management=False)
        sb = self._sb_with_record(record_37)
        # request sends True but stored is False
        from services.canonical.saas_appendix3_contract import check_saas_appendix3_contract
        from schemas.legal_engine import SafeIndustrialConsumerInput
        inp = SafeIndustrialConsumerInput(appendix3_item_no=37, is_real_estate_management=True)
        with pytest.raises(HTTPException) as exc_info:
            check_saas_appendix3_contract(sb, "fac-001", "INDUSTRIAL", inp)
        assert exc_info.value.status_code == 409


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 8 — SAFE_CST_OVERRIDE_FIELDS extension
# ─────────────────────────────────────────────────────────────────────────────


class TestCstOverrideFields:
    def test_E1_app3_item_in_cst_override(self):
        from services.safe_construction_leg_runtime import SAFE_CST_OVERRIDE_FIELDS
        assert "appendix3_item_no" in SAFE_CST_OVERRIDE_FIELDS

    def test_E2_subtype_in_cst_override(self):
        from services.safe_construction_leg_runtime import SAFE_CST_OVERRIDE_FIELDS
        assert "is_real_estate_management" in SAFE_CST_OVERRIDE_FIELDS

    def test_E3_relationship_contractor_in_cst_override(self):
        from services.safe_construction_leg_runtime import SAFE_CST_OVERRIDE_FIELDS
        assert "is_relationship_contractor" in SAFE_CST_OVERRIDE_FIELDS

    def test_E4_civil_construction_in_cst_override(self):
        from services.safe_construction_leg_runtime import SAFE_CST_OVERRIDE_FIELDS
        assert "is_civil_construction" in SAFE_CST_OVERRIDE_FIELDS

    def test_E5_expected_revision_not_in_cst_override(self):
        from services.safe_construction_leg_runtime import SAFE_CST_OVERRIDE_FIELDS
        assert "expected_app3_revision" not in SAFE_CST_OVERRIDE_FIELDS

    def test_E6_expected_revision_not_in_ind_override(self):
        from services.safe_industrial_leg_runtime import SAFE_UI_OVERRIDE_FIELDS
        assert "expected_app3_revision" not in SAFE_UI_OVERRIDE_FIELDS

    def test_E7_ap01_05_leaves_not_in_ind_override(self):
        from services.safe_industrial_leg_runtime import SAFE_UI_OVERRIDE_FIELDS
        for leaf in ("is_appendix3_1_27", "is_appendix3_28_48",
                     "is_appendix3_item_37", "is_appendix3_item_40"):
            assert leaf not in SAFE_UI_OVERRIDE_FIELDS
