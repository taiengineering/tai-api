"""tests/test_saas_diagnosis_snapshot_svc.py

WO-DIAGNOSIS-RESULT-SNAPSHOT-INVENTORY-SEPARATION-001.

Unit tests for saas_diagnosis_snapshot_svc.get_saas_diagnosis_snapshot().
"""
import pytest
from unittest.mock import MagicMock
from services.saas_diagnosis_snapshot_svc import (
    get_saas_diagnosis_snapshot,
    SnapshotNotFound,
    SnapshotContractError,
)

VALID_FULL_RESULT = {
    "obligations_raw": [{"id": "O1", "law_name": "산업안전보건법"}],
    "applicable_count": 1,
    "sector": "MANUFACTURING",
    "engine_version": "5.8.0",
}


def _sb(data):
    """Build a minimal supabase stub that returns data on execute()."""
    stub = MagicMock()
    chain = MagicMock()
    chain.execute.return_value = MagicMock(data=data)
    stub.table.return_value.select.return_value.eq.return_value.limit.return_value = chain
    return stub


class TestGetSaasDiagnosisSnapshotHappyPath:
    def test_returns_expected_keys(self):
        row = {
            "id": "diag-uuid-1",
            "input_data": {"factory_id": "f-1", "company_id": "c-1", "sector": "MANUFACTURING"},
            "full_result": VALID_FULL_RESULT,
            "engine_version": "5.8.0",
            "created_at": "2026-09-29T10:00:00+09:00",
            "source_type": "saas",
        }
        result = get_saas_diagnosis_snapshot(_sb([row]), diagnosis_id="diag-uuid-1")

        assert result["diagnosis_id"] == "diag-uuid-1"
        assert result["factory_id"] == "f-1"
        assert result["sector"] == "MANUFACTURING"
        assert result["engine_version"] == "5.8.0"
        assert result["created_at"] == "2026-09-29T10:00:00+09:00"
        assert result["full_result"] == VALID_FULL_RESULT
        assert result["_stored_company_id"] == "c-1"

    def test_sector_fallback_to_full_result(self):
        """input_data sector absent → full_result.sector used."""
        row = {
            "id": "diag-uuid-2",
            "input_data": {"factory_id": "f-1", "company_id": "c-1"},
            "full_result": VALID_FULL_RESULT,
            "engine_version": "5.8.0",
            "created_at": None,
            "source_type": "saas",
        }
        result = get_saas_diagnosis_snapshot(_sb([row]), diagnosis_id="diag-uuid-2")
        assert result["sector"] == "MANUFACTURING"

    def test_company_id_not_in_return_keys(self):
        row = {
            "id": "diag-uuid-3",
            "input_data": {"factory_id": "f-1", "company_id": "c-1"},
            "full_result": VALID_FULL_RESULT,
            "engine_version": None,
            "created_at": None,
            "source_type": "saas",
        }
        result = get_saas_diagnosis_snapshot(_sb([row]), diagnosis_id="diag-uuid-3")
        public_keys = {k for k in result if not k.startswith("_")}
        assert "company_id" not in public_keys
        assert "public_token" not in public_keys


class TestGetSaasDiagnosisSnapshotFailClosed:
    def test_not_found_when_no_row(self):
        with pytest.raises(SnapshotNotFound):
            get_saas_diagnosis_snapshot(_sb([]), diagnosis_id="missing")

    def test_not_found_when_source_type_not_saas(self):
        row = {
            "id": "diag-uuid-4",
            "input_data": {"factory_id": "f-1", "company_id": "c-1"},
            "full_result": VALID_FULL_RESULT,
            "engine_version": None,
            "created_at": None,
            "source_type": "paid",
        }
        with pytest.raises(SnapshotNotFound):
            get_saas_diagnosis_snapshot(_sb([row]), diagnosis_id="diag-uuid-4")

    def test_contract_error_when_company_id_absent(self):
        row = {
            "id": "diag-uuid-5",
            "input_data": {"factory_id": "f-1"},  # no company_id
            "full_result": VALID_FULL_RESULT,
            "engine_version": None,
            "created_at": None,
            "source_type": "saas",
        }
        with pytest.raises(SnapshotContractError):
            get_saas_diagnosis_snapshot(_sb([row]), diagnosis_id="diag-uuid-5")

    def test_contract_error_when_input_data_none(self):
        row = {
            "id": "diag-uuid-6",
            "input_data": None,
            "full_result": VALID_FULL_RESULT,
            "engine_version": None,
            "created_at": None,
            "source_type": "saas",
        }
        with pytest.raises(SnapshotContractError):
            get_saas_diagnosis_snapshot(_sb([row]), diagnosis_id="diag-uuid-6")
