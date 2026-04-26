from __future__ import annotations

from unittest.mock import MagicMock

from services.inspection_sets_svc.errors import InspectionSetsSvcError
from services.inspection_sets_svc.law_engine import run_generate_law_engine


def test_svc_error_fields():
    e = InspectionSetsSvcError(422, "bad")
    assert e.status_code == 422
    assert e.detail == "bad"


def test_run_generate_law_engine_empty_sets():
    supabase = MagicMock()
    tbl = supabase.table.return_value
    tbl.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
    out = run_generate_law_engine("f1", supabase)
    assert out == {"total_sets": 0, "created": 0, "skipped_dup": 0, "skipped_no_condition": 0}
