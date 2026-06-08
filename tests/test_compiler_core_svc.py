"""Tests for compiler_core_svc fetch shape (mocked Supabase)."""


class _FakeResponse:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, table: str, store: dict):
        self._table = table
        self._store = store
        self._filters = []

    def select(self, *_cols, **_kw):
        return self

    def eq(self, col, val):
        self._filters.append((col, val))
        return self

    def in_(self, col, vals):
        self._filters.append((col, "in", vals))
        return self

    def limit(self, _n):
        return self

    def execute(self):
        rows = list(self._store.get(self._table, []))
        for f in self._filters:
            if len(f) == 2:
                col, val = f
                rows = [r for r in rows if r.get(col) == val]
            else:
                col, _, vals = f
                rows = [r for r in rows if r.get(col) in vals]
        return _FakeResponse(rows)


class _FakeSB:
    def __init__(self, store: dict):
        self._store = store

    def table(self, name: str):
        return _FakeQuery(name, self._store)


def test_fetch_compiler_candidates_shape():
    from services.compiler_core_svc import fetch_compiler_candidates

    sb = _FakeSB(
        {
            "facility_applicability": [
                {
                    "id": "a1",
                    "factory_id": "fac-1",
                    "draft_id": "d1",
                    "applicability_status": "MATCH_CANDIDATE",
                    "part_id": "p1",
                }
            ],
            "task_candidate": [
                {"id": "t1", "factory_id": "fac-1", "task_type": "REPORT", "status": "CANDIDATE"}
            ],
            "schedule_candidate": [],
            "penalty_obligation_relation": [],
            "compliance_review_queue": [],
            "compliance_package": [],
        }
    )
    out = fetch_compiler_candidates(sb, "fac-1")
    assert out["factory_id"] == "fac-1"
    assert len(out["applicability_candidates"]) == 1
    assert out["compiler_version"] == "v3.0-deterministic"
    assert out["warning"]
