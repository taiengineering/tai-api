"""WO-007 — /diagnosis/fields projects visibility_condition (null-safe)."""
from types import SimpleNamespace

from routers import diagnosis_fields as mod


class _Q:
    def __init__(self, data):
        self._data = data

    def select(self, *a, **k):
        return self

    def in_(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def order(self, *a, **k):
        return self

    def execute(self):
        return SimpleNamespace(data=self._data)


class _SB:
    def __init__(self, rows):
        self._rows = rows

    def table(self, name):
        assert name == "diagnosis_input_fields"
        return _Q(self._rows)


def test_visibility_condition_projected(monkeypatch):
    rows = [
        {
            "field_code": "has_scaffold",
            "field_name": "비계를 사용합니까?",
            "field_type": "boolean",
            "field_group": "작업·설비 확인",
            "unit": None,
            "is_required": True,
            "placeholder": None,
            "help_text": None,
            "auto_source": None,
            "input_options": None,
            "sort_order": 100,
            "tier": "FREE",
            "visibility_condition": None,
        },
        {
            "field_code": "scaffold_height_m",
            "field_name": "비계의 높이는 몇 m입니까?",
            "field_type": "number",
            "field_group": "작업·설비 확인",
            "unit": "m",
            "is_required": True,
            "placeholder": None,
            "help_text": None,
            "auto_source": None,
            "input_options": None,
            "sort_order": 101,
            "tier": "FREE",
            "visibility_condition": {"field_code": "has_scaffold", "op": "eq", "value": True},
        },
    ]
    monkeypatch.setattr(mod, "get_supabase", lambda: _SB(rows))
    monkeypatch.setattr(mod, "normalize_sector_db", lambda s: s)
    monkeypatch.setattr(mod, "sector_codes_for_query", lambda s: [s])
    monkeypatch.setattr(mod, "VALID_SECTORS", {"INDUSTRIAL", "BUILDING", "CONSTRUCTION"})

    out = mod.get_diagnosis_fields(sector="INDUSTRIAL", tier="FREE")
    fields = out["data"]["groups"][0]["fields"]
    by = {f["field_code"]: f for f in fields}
    assert by["has_scaffold"]["visibility_condition"] is None
    assert by["scaffold_height_m"]["visibility_condition"] == {
        "field_code": "has_scaffold",
        "op": "eq",
        "value": True,
    }


def test_missing_visibility_column_defaults_none(monkeypatch):
    """구 DB(컬럼 미적용)에서도 projection 이 깨지지 않게 .get → None."""
    rows = [
        {
            "field_code": "worker_count",
            "field_name": "상시 근로자 수",
            "field_type": "number",
            "field_group": "기본정보",
            "unit": "명",
            "is_required": True,
            "placeholder": None,
            "help_text": None,
            "auto_source": None,
            "input_options": None,
            "sort_order": 1,
            "tier": "FREE",
            # visibility_condition key absent
        },
    ]
    monkeypatch.setattr(mod, "get_supabase", lambda: _SB(rows))
    monkeypatch.setattr(mod, "normalize_sector_db", lambda s: s)
    monkeypatch.setattr(mod, "sector_codes_for_query", lambda s: [s])
    monkeypatch.setattr(mod, "VALID_SECTORS", {"BUILDING", "INDUSTRIAL", "CONSTRUCTION"})
    out = mod.get_diagnosis_fields(sector="BUILDING", tier="FREE")
    f = out["data"]["groups"][0]["fields"][0]
    assert f["visibility_condition"] is None
