"""WO-SAAS-CANONICAL-INSPECTION-WRITER-001 STEP 4B-3 REV-1 — writer W1~W16.

W1 INSPECT+atom+action→payload · W2 non-INSPECT→0 · W3 atom absent→0 · W4 action absent→0 ·
W5 atom EXACT · W6 legal_operation_presentation==mapper · W7 law/action/type transport ·
W8 cycle NULL/next_planned NULL/default year1 0 · W9 timing "즉시" 보존·schedule 변환 0 ·
W10 cycle "상시" 보존·cycle_unit 생성 0 · W11 dup atom INSERT 0 · W12 operation state preserve(refresh) ·
W13 legacy legal_rule_id 대입 0 · W14 legacy writer delta 0 · W15 input mutation 0 · guard predicate.
(W16 diagnosis delta / W17~W24 anchor route guard = route 테스트, Cursor.)
"""
from __future__ import annotations

import copy
import inspect

from services.inspection_sets_svc.canonical_writer import (
    build_canonical_set_payload,
    materialize_canonical_inspection_sets,
    has_explicit_schedule_cycle,
)
from services.obligation_presentation_mapper import map_operation_presentation

_NULL_SCHED = (
    "cycle_unit", "cycle_value", "cycle_base_type", "cycle_base_guide",
    "schedule_anchor_date", "last_inspection_date", "next_planned_date",
)


def _raw(*, ob_type="INSPECT", atom="atom-A", action="방호장치를 점검하여야 한다",
         when="즉시", cycle="상시", law="산업안전보건법", article="38"):
    o = {
        "atom_id": atom, "source_atom_ids": [atom],
        "law_name": law, "law_article": article, "evidence": "근거문",
        "triggered_by": ["has_excavation"], "check_result": "VERIFIED", "applicability": "APPLICABLE",
        "obligation_detail": {"who": "사업주", "when": when, "how": "육안",
                              "condition": "굴착 시", "recipient": "관할관청", "where": "현장"},
        "enrichment": {},
    }
    if action is not None:
        o["obligation_detail"]["what"] = action
    if ob_type is not None:
        o["enrichment"]["obligation_type"] = ob_type
    if cycle is not None:
        o["enrichment"]["inspection_cycle"] = cycle
    return o


def test_W1_inspect_atom_action_payload():
    p = build_canonical_set_payload(_raw(), "f1", "c1")
    assert p is not None
    assert p["obligation_type"] == "INSPECT"
    assert p["source"] == "LEGAL_ENGINE"


def test_W2_non_inspect_zero():
    for t in ("ACTION", "PROHIBIT", "APPOINT", "REPORT", "NOTIFY", "TRAINING", "OTHER"):
        assert build_canonical_set_payload(_raw(ob_type=t), "f1", "c1") is None
    # 대소문자/별칭 추정 0
    assert build_canonical_set_payload(_raw(ob_type="inspect"), "f1", "c1") is None
    assert build_canonical_set_payload(_raw(ob_type=None), "f1", "c1") is None


def test_W3_atom_absent_zero():
    r = _raw(atom="A"); r.pop("atom_id")
    assert build_canonical_set_payload(r, "f1", "c1") is None
    assert build_canonical_set_payload(_raw(atom="  "), "f1", "c1") is None


def test_W4_action_absent_zero_no_fallback():
    p = build_canonical_set_payload(_raw(action=None), "f1", "c1")
    assert p is None  # obligation_summary/law/source-text fallback 0


def test_W5_atom_exact():
    p = build_canonical_set_payload(_raw(atom="atom-XYZ"), "f1", "c1")
    assert p["legal_obligation_atom_id"] == "atom-XYZ"


def test_W6_presentation_snapshot_exact():
    raw = _raw()
    p = build_canonical_set_payload(raw, "f1", "c1")
    assert p["legal_operation_presentation"] == map_operation_presentation(raw)


def test_W7_law_action_type_transport():
    raw = _raw(action="비상구를 점검하여야 한다", law="소방시설법", article="10")
    p = build_canonical_set_payload(raw, "f1", "c1")
    assert p["law_name"] == "소방시설법"
    assert p["law_article"] == "10"
    assert p["obligation_type"] == "INSPECT"
    assert p["inspection_set_name"] == "비상구를 점검하여야 한다"   # presentation.action EXACT
    assert p["obligation_summary"] == "비상구를 점검하여야 한다"
    assert p["description"] == "비상구를 점검하여야 한다"


def test_W8_cycle_null_no_default_year1():
    p = build_canonical_set_payload(_raw(), "f1", "c1")
    for k in _NULL_SCHED:
        assert p[k] is None, k
    assert p["anchor_confirmed"] is False
    assert p["assignee_user_id"] is None
    assert p["status_code"] == "PENDING_ANCHOR"
    assert p["legal_rule_id"] is None and p["legal_rule_code"] is None


def test_W9_legal_timing_preserved_no_schedule_conversion():
    raw = _raw(when="즉시")
    p = build_canonical_set_payload(raw, "f1", "c1")
    assert p["legal_operation_presentation"]["timing"] == "즉시"
    assert p["cycle_unit"] is None and p["cycle_value"] is None  # schedule 변환 0


def test_W10_legal_cycle_preserved_no_cycle_unit():
    raw = _raw(cycle="상시")
    p = build_canonical_set_payload(raw, "f1", "c1")
    assert p["legal_operation_presentation"]["cycle"] == "상시"
    assert p["cycle_unit"] is None


def test_W13_legacy_rule_id_not_assigned():
    p = build_canonical_set_payload(_raw(atom="atom-A"), "f1", "c1")
    assert p["legal_rule_id"] is None
    assert p["legal_rule_id"] != p["legal_obligation_atom_id"]
    assert p["legal_rule_code"] is None


def test_W15_input_mutation_zero():
    raw = _raw()
    before = copy.deepcopy(raw)
    build_canonical_set_payload(raw, "f1", "c1")
    assert raw == before


def test_guard_has_explicit_schedule_cycle():
    assert has_explicit_schedule_cycle({"cycle_unit": "month", "cycle_value": 1}) is True
    assert has_explicit_schedule_cycle({"cycle_unit": None, "cycle_value": None}) is False
    assert has_explicit_schedule_cycle({"cycle_unit": "month", "cycle_value": None}) is False
    assert has_explicit_schedule_cycle({"cycle_unit": "", "cycle_value": 1}) is False
    assert has_explicit_schedule_cycle({}) is False


# ── materialize: INSERT / refresh / dup (supabase mock) ──

class _Q:
    def __init__(self, sb):
        self.sb = sb; self._op = None; self._payload = None; self._eq = {}

    def select(self, *a, **k): self._op = "select"; return self
    def eq(self, col, val): self._eq[col] = val; return self
    def in_(self, col, vals): self._eq[col] = list(vals); return self
    def update(self, patch): self._op = "update"; self._payload = patch; self.sb.updates.append(patch); return self
    def insert(self, rows): self._op = "insert"; self._payload = rows; self.sb.inserts.append(rows); return self

    def execute(self):
        class R: pass
        r = R()
        r.data = list(self.sb.existing) if self._op == "select" else (self._payload if isinstance(self._payload, list) else [self._payload])
        return r


class _SB:
    def __init__(self, existing=None):
        self.existing = existing or []; self.inserts = []; self.updates = []
    def table(self, name):
        assert name == "inspection_sets"; return _Q(self)


def test_W11_W12_insert_refresh_operation_preserve():
    raw_list = [_raw(atom="a0", action="A0"), _raw(atom="a1", action="A1")]
    # a0 already exists → refresh only; a1 new → insert
    sb = _SB(existing=[{"id": "set-a0", "legal_obligation_atom_id": "a0"}])
    out = materialize_canonical_inspection_sets(sb, "f1", "c1", raw_list)
    assert out["candidates"] == 2
    assert out["inserted"] == 1 and out["refreshed"] == 1
    # insert = a1 only
    assert len(sb.inserts) == 1 and len(sb.inserts[0]) == 1
    assert sb.inserts[0][0]["legal_obligation_atom_id"] == "a1"
    # refresh patch = LEGAL fields only, 운영값 미포함
    patch = sb.updates[0]
    assert set(patch.keys()) == {"law_name", "law_article", "obligation_type",
                                 "obligation_summary", "description", "legal_operation_presentation"}
    for forbidden in ("cycle_unit", "cycle_value", "schedule_anchor_date",
                      "next_planned_date", "assignee_user_id", "status_code", "anchor_confirmed"):
        assert forbidden not in patch


def test_W11_dup_atom_single_insert():
    raw_list = [_raw(atom="dup", action="X"), _raw(atom="dup", action="X")]
    sb = _SB(existing=[])
    out = materialize_canonical_inspection_sets(sb, "f1", "c1", raw_list)
    assert out["candidates"] == 1  # 동일 atom 1건만
    assert out["inserted"] == 1
    assert len(sb.inserts[0]) == 1


def test_W14_legacy_writer_delta_zero():
    from routers.inspection_set_auto import auto_create_inspection_sets_from_diagnosis
    src = inspect.getsource(auto_create_inspection_sets_from_diagnosis)
    assert "canonical_writer" not in src
    assert "materialize_canonical_inspection_sets" not in src
    assert "legal_operation_presentation" not in src


def test_no_candidates_returns_zero():
    out = materialize_canonical_inspection_sets(_SB(), "f1", "c1", [_raw(ob_type="ACTION")])
    assert out == {"candidates": 0, "inserted": 0, "refreshed": 0, "skipped": 0}
