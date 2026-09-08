"""WO-SAAS-OBLIGATION-IDENTITY-BRIDGE-001 STEP 4B-1 — bridge + GET projection.

B1 atom_id EXACT · B2 atom absent→identity 0 · B3 source_atom_ids만→합성 0 ·
B4 map_operation_presentation parity · B5 input mutation 0.
B6 legacy writer delta 0 · B7~B9 GET /inspection-sets projection · B10 diagnosis insert delta 0.
DB/network 불필요.
"""
from __future__ import annotations

import copy
import inspect

from services.inspection_sets_svc.canonical_bridge import (
    build_canonical_inspection_identity,
    canonical_atom_id,
)
from services.obligation_presentation_mapper import map_operation_presentation


def _raw(**over):
    base = {
        "atom_id": "atom-A",
        "source_atom_ids": ["atom-A", "atom-B"],
        "law_name": "산업안전보건법",
        "law_article": "38",
        "evidence": "근거문",
        "triggered_by": ["has_excavation"],
        "check_result": "VERIFIED",
        "applicability": "APPLICABLE",
        "obligation_detail": {
            "what": "방호장치를 점검하여야 한다", "who": "사업주",
            "when": "작업 전", "how": "육안", "condition": "굴착 시",
            "recipient": "관할관청", "where": "현장",
        },
        "enrichment": {"obligation_type": "INSPECT", "inspection_cycle": "MONTHLY"},
    }
    base.update(over)
    return base


def test_B1_atom_id_exact():
    out = build_canonical_inspection_identity(_raw(atom_id="A"))
    assert out is not None
    assert out["legal_obligation_atom_id"] == "A"
    assert canonical_atom_id(_raw(atom_id="A")) == "A"


def test_B2_atom_absent_identity_zero():
    o = _raw()
    o.pop("atom_id", None)
    assert build_canonical_inspection_identity(o) is None
    assert canonical_atom_id(o) is None
    # empty / whitespace / non-str 도 identity 0
    assert build_canonical_inspection_identity(_raw(atom_id="")) is None
    assert build_canonical_inspection_identity(_raw(atom_id="   ")) is None
    assert build_canonical_inspection_identity(_raw(atom_id=123)) is None


def test_B3_source_atom_ids_only_no_synthesis():
    o = _raw()
    o.pop("atom_id", None)
    o["source_atom_ids"] = ["s-1", "s-2"]
    # source_atom_ids 만으로 atom_id 합성 금지
    assert build_canonical_inspection_identity(o) is None


def test_B4_operation_presentation_parity():
    raw = _raw(atom_id="A")
    out = build_canonical_inspection_identity(raw)
    assert out["operation_presentation"] == map_operation_presentation(raw)
    # SaaS 운영값 생성 0 (경계)
    for k in ("assignee_user_id", "next_due_date", "status", "completed_at",
              "execution_record", "attachment"):
        assert k not in out["operation_presentation"]
    # official 값은 운반
    assert out["operation_presentation"]["action"] == "방호장치를 점검하여야 한다"
    assert out["operation_presentation"]["legal_actor"] == "사업주"
    assert out["operation_presentation"]["cycle"] == "MONTHLY"
    assert out["operation_presentation"]["identity"] == {
        "atom_id": "A", "source_atom_ids": ["atom-A", "atom-B"],
    }


def test_B5_input_mutation_zero():
    raw = _raw(atom_id="A")
    before = copy.deepcopy(raw)
    build_canonical_inspection_identity(raw)
    canonical_atom_id(raw)
    assert raw == before


def test_malformed_input():
    for bad in (None, [], "x", 123, {}):
        assert build_canonical_inspection_identity(bad) is None
        assert canonical_atom_id(bad) is None


def test_no_legal_rule_id_or_law_match_used():
    # atom_id 만 identity. legal_rule_id/law_name/article 은 identity carrier 로 쓰지 않는다.
    o = _raw(atom_id="A", legal_rule_id="CON3-SCF-002")
    out = build_canonical_inspection_identity(o)
    assert out["legal_obligation_atom_id"] == "A"
    assert out["legal_obligation_atom_id"] != "CON3-SCF-002"


# ── B6~B10: GET projection additive + legacy writer/diagnosis delta 0 ──

_EXISTING_SELECT_FIELDS = (
    "id", "company_id", "factory_id", "inspection_set_name", "inspection_set_code",
    "inspection_category", "legal_rule_id", "law_name", "law_article",
    "obligation_type", "obligation_summary", "cycle_unit", "cycle_value",
    "cycle_base_type", "cycle_base_guide", "anchor_type", "schedule_anchor_date",
    "last_inspection_date", "next_planned_date", "anchor_confirmed", "description",
    "source", "is_active", "status_code", "assignee_user_id", "created_at", "updated_at",
)

_LOOP_FILLS = (
    "penalty_summary", "form_name", "form_url", "remarks",
    "online_system", "system_url", "cycle_base_guide_rule",
)


def _set_row(**over):
    base = {
        "id": "set-1",
        "company_id": "co-1",
        "factory_id": "f1",
        "inspection_set_name": "산안법 점검",
        "inspection_set_code": "CON3-SCF-002",
        "inspection_category": "INSPECT",
        "legal_rule_id": "CON3-SCF-002",
        "law_name": "산업안전보건법",
        "law_article": "38",
        "obligation_type": "INSPECT",
        "obligation_summary": "방호장치 점검",
        "cycle_unit": "month",
        "cycle_value": 1,
        "cycle_base_type": "LAST_INSPECTION",
        "cycle_base_guide": "매월",
        "anchor_type": None,
        "schedule_anchor_date": None,
        "last_inspection_date": None,
        "next_planned_date": None,
        "anchor_confirmed": False,
        "description": "방호장치 점검",
        "source": "LEGAL_ENGINE",
        "is_active": True,
        "status_code": "PENDING_ANCHOR",
        "assignee_user_id": None,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "legal_obligation_atom_id": None,
    }
    base.update(over)
    return base


class _Resp:
    def __init__(self, data, count):
        self.data = data
        self.count = count


class _ListQ:
    def __init__(self, client):
        self.client = client

    def select(self, cols, count=None):
        self.client.last_select = cols
        self.client.last_count = count
        return self

    def eq(self, *a, **k):
        return self

    def order(self, *a, **k):
        return self

    def range(self, *a, **k):
        return self

    def execute(self):
        return _Resp(copy.deepcopy(self.client.rows), len(self.client.rows))


class _ListSB:
    def __init__(self, rows):
        self.rows = rows
        self.last_select = None
        self.last_count = None

    def table(self, name):
        assert name == "inspection_sets"
        return _ListQ(self)


def _call_list_route(monkeypatch, rows):
    import routers.inspection_sets as R
    from services.inspection_sets_svc import queries as Q

    sb = _ListSB(rows)
    monkeypatch.setattr(R, "get_supabase", lambda: sb)
    monkeypatch.setattr(R, "_ensure_factory_own", lambda *a, **k: None)
    monkeypatch.setattr(Q, "get_supabase", lambda: sb)
    out = R.get_inspection_sets(
        factory_id="f1",
        source=None,
        anchor_confirmed=None,
        page=1,
        size=20,
        current={"id": "u"},
    )
    return out, sb


def test_B6_legacy_writer_delta_zero():
    from routers.inspection_set_auto import auto_create_inspection_sets_from_diagnosis

    src = inspect.getsource(auto_create_inspection_sets_from_diagnosis)
    assert "legal_obligation_atom_id" not in src
    assert "canonical_atom_id" not in src
    assert "build_canonical_inspection_identity" not in src


def test_B7_get_inspection_sets_official_linked(monkeypatch):
    row = _set_row(legal_obligation_atom_id="atom-A")
    out, sb = _call_list_route(monkeypatch, [row])
    assert sb.last_count == "exact"
    select = sb.last_select
    for field in _EXISTING_SELECT_FIELDS:
        assert field in select, field
    assert "legal_obligation_atom_id" in select
    assert select.rstrip().endswith("legal_obligation_atom_id")
    assert "created_at, updated_at, " in select

    item = out["data"]["items"][0]
    assert item["legal_obligation_atom_id"] == "atom-A"
    assert item["legal_rule_id"] == "CON3-SCF-002"
    assert item["legal_obligation_atom_id"] != item["legal_rule_id"]
    for field in _EXISTING_SELECT_FIELDS:
        assert item[field] == row[field]
    for field in _LOOP_FILLS:
        assert field in item


def test_B8_get_inspection_sets_legacy_null(monkeypatch):
    row = _set_row(legal_obligation_atom_id=None)
    out, _sb = _call_list_route(monkeypatch, [row])
    item = out["data"]["items"][0]
    assert "legal_obligation_atom_id" in item
    assert item["legal_obligation_atom_id"] is None
    assert item["legal_rule_id"] == "CON3-SCF-002"
    assert item["law_name"] == "산업안전보건법"
    assert item["obligation_type"] == "INSPECT"


def test_B9_legal_rule_id_not_used_as_identity(monkeypatch):
    row = _set_row(legal_rule_id="CON3-SCF-002", legal_obligation_atom_id=None)
    out, _sb = _call_list_route(monkeypatch, [row])
    item = out["data"]["items"][0]
    assert item["legal_obligation_atom_id"] is None
    assert item["legal_rule_id"] == "CON3-SCF-002"
    from services.inspection_sets_svc import queries as Q
    src = inspect.getsource(Q.get_sets_list)
    assert "legal_obligation_atom_id" in src
    assert 'item["legal_obligation_atom_id"]' not in src
    assert "legal_rule_id" not in src.split("legal_obligation_atom_id", 1)[1]


def test_B10_diagnosis_auto_create_insert_delta_zero():
    from routers.inspection_set_auto import auto_create_inspection_sets_from_diagnosis

    class _AutoQ:
        def __init__(self, sb):
            self.sb = sb
            self._op = "select"
            self._payload = None

        def select(self, *a, **k):
            self._op = "select"
            return self

        def eq(self, *a, **k):
            return self

        def insert(self, rows):
            self._op = "insert"
            self._payload = rows
            self.sb.inserts.append(rows)
            return self

        def execute(self):
            if self._op == "insert":
                class R:
                    data = list(self._payload)
                return R()

            class R:
                data = []
            return R()

    class _AutoSB:
        def __init__(self):
            self.inserts = []

        def table(self, name):
            assert name == "inspection_sets"
            return _AutoQ(self)

    sb = _AutoSB()
    n = auto_create_inspection_sets_from_diagnosis(
        sb, "f1", "c1",
        [{
            "rule_id": "CON3-SCF-002",
            "inspection_required": True,
            "obligation_type": "INSPECT",
            "law_name": "산안법",
            "atom_id": "atom-A",
        }],
    )
    assert n == 1
    inserted = sb.inserts[0][0]
    assert "legal_obligation_atom_id" not in inserted
    assert inserted["legal_rule_id"] == "CON3-SCF-002"
    assert inserted["source"] == "LEGAL_ENGINE"
