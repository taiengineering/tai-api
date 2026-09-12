from __future__ import annotations

from unittest.mock import MagicMock

from services.inspection_sets_svc.errors import InspectionSetsSvcError
from services.inspection_sets_svc.law_engine import run_generate_law_engine


def test_svc_error_fields():
    e = InspectionSetsSvcError(422, "bad")
    assert e.status_code == 422
    assert e.detail == "bad"


def test_run_generate_law_engine_empty_sets():
    """Compatibility wrapper returns empty counters when no LEGAL_ENGINE sets."""
    supabase = MagicMock()

    class _Chain:
        def __init__(self):
            self.data = []

        def select(self, *a, **k):
            return self

        def eq(self, *a, **k):
            return self

        def execute(self):
            return self

    supabase.table.return_value = _Chain()
    out = run_generate_law_engine("f1", supabase)
    assert out["total_sets"] == 0
    assert out["created"] == 0
    assert out["skipped_dup"] == 0
    assert out["skipped_no_condition"] == 0
