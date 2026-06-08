"""Tests for anonymous_factory_service (Phase 2 compiler consumer path)."""

from unittest.mock import MagicMock, patch

import pytest

from schemas.legal_engine import DiagnoseStep1Body
from services.anonymous_factory_service import (
    _compiler_result_to_step1_format,
    cleanup_temp_factory,
    create_temp_factory,
    run_anonymous_diagnosis,
)


class _FakeResponse:
    def __init__(self, data):
        self.data = data


def test_compiler_result_to_step1_format_shape():
    compiler = {
        "compiler_version": "v3.0-deterministic",
        "warning": "All results are CANDIDATES.",
        "applicability_candidates": [{"id": "a1", "applicability_status": "MATCH_CANDIDATE", "draft_id": "d1"}],
        "task_candidates": [
            {
                "id": "t1",
                "task_type": "APPOINTMENT",
                "source_action_family": "APPOINT_FAMILY",
                "obligation_family": "산업안전보건법",
                "status": "CANDIDATE",
            }
        ],
        "schedule_candidates": [],
    }
    out = _compiler_result_to_step1_format(
        compiler,
        sector_raw="BUILDING",
        facility_ctx={"worker_count": 10, "total_floor_area": 500},
        evaluated_at="2026-06-08T00:00:00+00:00",
    )
    assert out["risk_level"] in ("LOW", "MEDIUM", "HIGH")
    assert out["rules_table"]
    assert out["rules"] == out["rules_table"]
    assert out["key_obligations"]
    assert out["law_badges"]
    assert out["applicable_count"] >= 1
    assert out["summary"]["total"] >= 1
    assert out["compiler_core"]["task_count"] == 1
    assert out["engine_version"] == "v3.0-compiler-core-anonymous"


def test_create_temp_factory_maps_building_fields():
    sb = MagicMock()
    sb.table.return_value.insert.return_value.execute.return_value = _FakeResponse(
        [{"id": "fac-uuid-1"}]
    )
    body = DiagnoseStep1Body(
        sector="BUILDING",
        floor_area=1200.0,
        total_floor_area=1200.0,
        worker_count=25,
        employee_count=25,
        building_use_type="사무실",
    )
    fid = create_temp_factory(sb, body)
    assert fid == "fac-uuid-1"
    insert_call = sb.table.return_value.insert.call_args[0][0]
    assert insert_call["is_active"] is False
    assert insert_call["name"].startswith("[ANON]BUILDING")
    assert insert_call["employee_count"] == 25
    assert insert_call["building_area"] == 1200.0


def test_cleanup_temp_factory_deletes_rows():
    sb = MagicMock()
    cleanup_temp_factory(sb, "fac-1")
    assert sb.table.call_args_list[0][0][0] == "facility_applicability"
    assert sb.table.call_args_list[1][0][0] == "factories"


@patch("services.anonymous_factory_service.cleanup_temp_factory")
@patch("services.anonymous_factory_service.fetch_compiler_candidates")
@patch("services.anonymous_factory_service.evaluate_single_factory")
@patch("services.anonymous_factory_service.create_temp_factory")
def test_run_anonymous_diagnosis_orchestration(
    mock_create, mock_eval, mock_fetch, mock_cleanup
):
    mock_create.return_value = "temp-fac"
    mock_eval.return_value = {"applicability_inserted": 2}
    mock_fetch.return_value = {
        "compiler_version": "v3.0-deterministic",
        "warning": "candidate only",
        "applicability_candidates": [],
        "task_candidates": [
            {
                "id": "t1",
                "task_type": "REPORT",
                "source_action_family": "REPORT_FAMILY",
                "obligation_family": "화재예방법",
            }
        ],
        "schedule_candidates": [],
    }
    body = DiagnoseStep1Body(sector="MANUFACTURING", worker_count=30, employee_count=30)
    out = run_anonymous_diagnosis(MagicMock(), body, frozenset({"MANUFACTURING", "BUILDING", "CONSTRUCTION", "SPECIAL_FACILITY", "SPECIAL"}))
    assert out["rules_table"]
    assert out["sector"] == "MANUFACTURING"
    mock_create.assert_called_once()
    mock_eval.assert_called_once()
    mock_fetch.assert_called_once()
    mock_cleanup.assert_called_once()


def test_run_anonymous_diagnosis_invalid_sector():
    body = DiagnoseStep1Body(sector="INVALID")
    with pytest.raises(ValueError):
        run_anonymous_diagnosis(MagicMock(), body, frozenset({"BUILDING"}))
