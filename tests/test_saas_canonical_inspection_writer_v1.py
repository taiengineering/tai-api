"""WO-SAFE-ALL-OBLIGATION-MATERIALIZATION-IMPLEMENT-001
(+ prior WO-SAAS-CANONICAL-INSPECTION-WRITER-001 STEP 4B-3 REV-1).

T1~T16 all-obligation membership · W1~W15/G1~G15/W17~W24 회귀.
DB/network/LEG/LLM 불필요.
"""
from __future__ import annotations

import copy
import inspect

import pytest
from fastapi import HTTPException

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


def test_W2_non_inspect_materialize_type_preserved():
    """obligation_type 은 membership gate 아님 · 실값 보존 · INSPECT 강제 0."""
    for t in ("ACTION", "PROHIBIT", "APPOINT", "REPORT", "NOTIFY", "TRAINING", "OTHER"):
        p = build_canonical_set_payload(_raw(ob_type=t), "f1", "c1")
        assert p is not None
        assert p["obligation_type"] == t
    # 추정/정규화 0 — 원문 그대로 보존
    assert build_canonical_set_payload(_raw(ob_type="inspect"), "f1", "c1")["obligation_type"] == "inspect"
    assert build_canonical_set_payload(_raw(ob_type=None), "f1", "c1")["obligation_type"] is None


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
    # integrity fail-close (atom 없음) — type 무관
    r = _raw(ob_type="ACTION")
    r.pop("atom_id")
    out = materialize_canonical_inspection_sets(_SB(), "f1", "c1", [r])
    assert out == {"candidates": 0, "inserted": 0, "refreshed": 0, "skipped": 0}


# ── T1~T16: APPROVED TARGET membership (obligations_raw as-is) ──

def test_T1_final_inspect_yes():
    p = build_canonical_set_payload(_raw(ob_type="INSPECT"), "f1", "c1")
    assert p is not None and p["obligation_type"] == "INSPECT"


def test_T2_final_action_yes_type_preserved():
    p = build_canonical_set_payload(_raw(ob_type="ACTION", action="안전조치를 하여야 한다"), "f1", "c1")
    assert p is not None
    assert p["obligation_type"] == "ACTION"
    assert p["obligation_type"] != "INSPECT"


def test_T3_final_report_yes():
    p = build_canonical_set_payload(_raw(ob_type="REPORT", action="결과를 보고하여야 한다"), "f1", "c1")
    assert p is not None and p["obligation_type"] == "REPORT"


def test_T4_final_appoint_yes():
    p = build_canonical_set_payload(_raw(ob_type="APPOINT", action="관리자를 선임하여야 한다"), "f1", "c1")
    assert p is not None and p["obligation_type"] == "APPOINT"


def test_T5_final_notify_training_yes():
    for t, act in (("NOTIFY", "게시하여야 한다"), ("TRAINING", "교육을 실시하여야 한다")):
        p = build_canonical_set_payload(_raw(ob_type=t, action=act), "f1", "c1")
        assert p is not None and p["obligation_type"] == t


def test_T6_review_required_not_in_writer_input():
    """review_required 는 obligations_raw 가 아님 — writer 는 raw list 만 본다."""
    out = materialize_canonical_inspection_sets(_SB(), "f1", "c1", [])
    assert out["candidates"] == 0
    # raw 에 넣은 것만 대상
    out2 = materialize_canonical_inspection_sets(
        _SB(), "f1", "c1", [_raw(ob_type="ACTION", atom="a-rr")]
    )
    assert out2["candidates"] == 1 and out2["inserted"] == 1


def test_T7_atom_id_absent_fail_close():
    r = _raw(ob_type="ACTION")
    r.pop("atom_id")
    assert build_canonical_set_payload(r, "f1", "c1") is None


def test_T8_action_absent_fail_close_no_fallback():
    assert build_canonical_set_payload(_raw(ob_type="REPORT", action=None), "f1", "c1") is None


def test_T9_rediagnose_upsert_ops_preserved():
    raw_list = [_raw(atom="same", ob_type="ACTION", action="조치를 하여야 한다")]
    sb = _SB(existing=[{"id": "set-same", "legal_obligation_atom_id": "same"}])
    out = materialize_canonical_inspection_sets(sb, "f1", "c1", raw_list)
    assert out["refreshed"] == 1 and out["inserted"] == 0
    patch = sb.updates[0]
    assert patch["obligation_type"] == "ACTION"
    for forbidden in ("cycle_unit", "cycle_value", "schedule_anchor_date",
                      "next_planned_date", "assignee_user_id", "status_code", "anchor_confirmed"):
        assert forbidden not in patch


def test_T10_new_row_pending_anchor_schedule_zero():
    p = build_canonical_set_payload(_raw(ob_type="ACTION"), "f1", "c1")
    assert p["status_code"] == "PENDING_ANCHOR"
    assert p["anchor_confirmed"] is False
    assert p["assignee_user_id"] is None
    for k in _NULL_SCHED:
        assert p[k] is None, k


def test_T11_human_schedule_still_needs_explicit_cycle():
    """사람 cycle 확정 전 기존 guard — canonical NULL cycle → schedule helper 진입 0."""
    p = build_canonical_set_payload(_raw(ob_type="ACTION"), "f1", "c1")
    assert has_explicit_schedule_cycle(p) is False


def test_T12_obligation_type_change_refresh_identity_stable():
    raw_list = [_raw(atom="atom-chg", ob_type="REPORT", action="보고하여야 한다")]
    sb = _SB(existing=[{"id": "set-chg", "legal_obligation_atom_id": "atom-chg"}])
    out = materialize_canonical_inspection_sets(sb, "f1", "c1", raw_list)
    assert out["refreshed"] == 1 and out["inserted"] == 0
    assert sb.updates[0]["obligation_type"] == "REPORT"


def test_T13_check_result_not_applicable_still_materialize():
    r = _raw(ob_type="ACTION", atom="atom-na")
    r["check_result"] = "NOT_APPLICABLE"
    p = build_canonical_set_payload(r, "f1", "c1")
    assert p is not None
    assert p["obligation_type"] == "ACTION"
    out = materialize_canonical_inspection_sets(_SB(), "f1", "c1", [r])
    assert out["candidates"] == 1 and out["inserted"] == 1


def test_T14_applicability_not_membership_gate():
    r = _raw(ob_type="ACTION", atom="atom-ap")
    r["applicability"] = "NOT_APPLICABLE"
    assert build_canonical_set_payload(r, "f1", "c1") is not None


def test_T15_no_inspect_hardcode_in_payload():
    p = build_canonical_set_payload(_raw(ob_type="PROHIBIT", action="사용하여서는 아니 된다"), "f1", "c1")
    assert p["obligation_type"] == "PROHIBIT"
    import services.inspection_sets_svc.canonical_writer as W
    src = inspect.getsource(W.build_canonical_set_payload)
    assert '"obligation_type": _INSPECT' not in src
    assert 'obligation_type": "INSPECT"' not in src


def test_T16_writer_has_no_check_result_or_applicability_filter():
    import services.inspection_sets_svc.canonical_writer as W
    # executable gate 부재: 필드 lookup/비교로 membership 재판정하지 않음
    body = (
        inspect.getsource(W.build_canonical_set_payload)
        + inspect.getsource(W.materialize_canonical_inspection_sets)
        + inspect.getsource(W._obligation_type)
    )
    assert 'get("check_result")' not in body
    assert '["check_result"]' not in body
    assert 'get("applicability")' not in body
    assert '["applicability"]' not in body
    assert '== "INSPECT"' not in body
    assert '!= "INSPECT"' not in body
    assert "_INSPECT" not in body
    assert '"obligation_type": "INSPECT"' not in body


# ── G1~G15: writer 회귀 (cycle_text 파싱 0 · atom exact · guard fail-close) ──

def test_G1_atom_id_exact():
    p = build_canonical_set_payload(_raw(atom="atom-G1"), "f1", "c1")
    assert p["legal_obligation_atom_id"] == "atom-G1"


def test_G2_legal_rule_id_does_not_synthesize_atom():
    r = _raw(atom="atom-A")
    r["legal_rule_id"] = "CON3-SCF-002"
    p = build_canonical_set_payload(r, "f1", "c1")
    assert p["legal_obligation_atom_id"] == "atom-A"
    assert p["legal_rule_id"] is None
    r2 = _raw()
    r2.pop("atom_id")
    r2["legal_rule_id"] = "CON3-SCF-002"
    assert build_canonical_set_payload(r2, "f1", "c1") is None


def test_G3_cycle_text_verbatim():
    p = build_canonical_set_payload(_raw(when="즉시", cycle="상시"), "f1", "c1")
    assert p["legal_operation_presentation"]["timing"] == "즉시"
    assert p["legal_operation_presentation"]["cycle"] == "상시"


def test_G4_one_year_text_not_year1():
    p = build_canonical_set_payload(_raw(when="1년", cycle="1년"), "f1", "c1")
    assert p["legal_operation_presentation"]["timing"] == "1년"
    assert p["legal_operation_presentation"]["cycle"] == "1년"
    assert p["cycle_unit"] is None and p["cycle_value"] is None


def test_G5_monthly_text_not_month1():
    p = build_canonical_set_payload(_raw(when="매월", cycle="매월"), "f1", "c1")
    assert p["legal_operation_presentation"]["cycle"] == "매월"
    assert p["cycle_unit"] is None and p["cycle_value"] is None


def test_G6_before_work_not_numeric():
    p = build_canonical_set_payload(_raw(when="작업 시작 전", cycle="작업시작전"), "f1", "c1")
    assert p["legal_operation_presentation"]["timing"] == "작업 시작 전"
    assert p["cycle_unit"] is None and p["cycle_value"] is None


def test_G7_always_on_not_numeric():
    p = build_canonical_set_payload(_raw(when="상시", cycle="상시"), "f1", "c1")
    assert p["legal_operation_presentation"]["cycle"] == "상시"
    assert p["cycle_unit"] is None and p["cycle_value"] is None


def test_G8_next_planned_null():
    p = build_canonical_set_payload(_raw(), "f1", "c1")
    assert p["next_planned_date"] is None
    assert p["schedule_anchor_date"] is None
    assert p["anchor_confirmed"] is False
    assert p["status_code"] == "PENDING_ANCHOR"


def test_G9_cycle_unit_value_null():
    p = build_canonical_set_payload(_raw(), "f1", "c1")
    assert p["cycle_unit"] is None
    assert p["cycle_value"] is None


def test_G10_legacy_writer_delta_zero():
    from routers.inspection_set_auto import auto_create_inspection_sets_from_diagnosis
    src = inspect.getsource(auto_create_inspection_sets_from_diagnosis)
    assert "canonical_writer" not in src
    assert "has_explicit_schedule_cycle" not in src


def test_G11_guard_false_on_canonical_payload():
    p = build_canonical_set_payload(_raw(), "f1", "c1")
    assert has_explicit_schedule_cycle(p) is False


def test_G12_mapper_input_mutation_zero():
    raw = _raw()
    before = copy.deepcopy(raw)
    build_canonical_set_payload(raw, "f1", "c1")
    map_operation_presentation(raw)
    assert raw == before


def test_G13_leg_call_zero():
    import services.inspection_sets_svc.canonical_writer as W
    src = inspect.getsource(W)
    for banned in ("rtm_engine", "fetch_clause", "/rtm/", "leg-runtime"):
        assert banned not in src


def test_G14_llm_fuzzy_regex_parse_zero():
    import services.inspection_sets_svc.canonical_writer as W
    import services.inspection_sets_svc.anchors as A
    import services.inspection_sets_svc.schedules as S
    blob = (
        inspect.getsource(W)
        + inspect.getsource(A.set_anchor_bulk)
        + inspect.getsource(A.bulk_update_anchors)
        + inspect.getsource(A.patch_set)
        + inspect.getsource(A.update_anchor)
        + inspect.getsource(S.generate_schedules_for_factory)
    )
    for banned in ("openai", "anthropic", "ChatCompletion", "fuzzy", "difflib", "re.search", "re.match"):
        assert banned not in blob


def test_G15_legal_text_without_structured_schedule_is_absent():
    p = build_canonical_set_payload(_raw(when="즉시", cycle="상시"), "f1", "c1")
    assert p["legal_operation_presentation"]["timing"] == "즉시"
    assert p["legal_operation_presentation"]["cycle"] == "상시"
    assert p["cycle_unit"] is None and p["cycle_value"] is None
    assert has_explicit_schedule_cycle(p) is False
    from services.inspection_sets_helpers import _build_next_schedule_row
    src = inspect.getsource(_build_next_schedule_row)
    assert 'or "year"' in src and "or 1" in src


# ── W17~W24: 5 write 경계 guard (canonical NULL-cycle → helper 진입 0) ──

_SKIP = "주기가 설정되지 않았습니다."
_NEED_CYCLE = "점검 주기를 먼저 설정해주세요."


def _canonical_row(**over):
    row = {
        "id": "set-c",
        "factory_id": "f1",
        "company_id": "c1",
        "inspection_set_name": "방호장치를 점검하여야 한다",
        "inspection_category": "INSPECT",
        "source": "LEGAL_ENGINE",
        "status_code": "PENDING_ANCHOR",
        "is_active": True,
        "cycle_unit": None,
        "cycle_value": None,
        "schedule_anchor_date": None,
        "next_planned_date": None,
        "anchor_confirmed": False,
        "legal_obligation_atom_id": "atom-A",
    }
    row.update(over)
    return row


def _legacy_row(**over):
    row = {
        "id": "set-l",
        "factory_id": "f1",
        "company_id": "c1",
        "inspection_set_name": "산안법 점검",
        "inspection_category": "INSPECT",
        "source": "LEGAL_ENGINE",
        "status_code": "PENDING_ANCHOR",
        "is_active": True,
        "cycle_unit": "month",
        "cycle_value": 1,
        "schedule_anchor_date": None,
        "next_planned_date": None,
        "anchor_confirmed": False,
        "legal_rule_id": "CON3-SCF-002",
        # LEGAL_ENGINE schedule readiness: cycle + anchor + assignee
        "assignee_user_id": "user-ready",
    }
    row.update(over)
    return row


def _manual_row(**over):
    row = {
        "id": "set-m",
        "factory_id": "f1",
        "company_id": "c1",
        "inspection_set_name": "수동 점검",
        "inspection_category": "GENERAL",
        "source": "MANUAL",
        "status_code": "PENDING_ANCHOR",
        "is_active": True,
        "cycle_unit": "month",
        "cycle_value": 1,
        "schedule_anchor_date": None,
        "next_planned_date": None,
        "anchor_confirmed": False,
        "assignee_user_id": None,
    }
    row.update(over)
    return row


class _Resp:
    def __init__(self, data=None):
        self.data = data if data is not None else []


class _WQ:
    def __init__(self, sb, name):
        self.sb = sb
        self.name = name
        self._op = "select"
        self._eq = {}
        self._payload = None

    def select(self, *a, **k):
        self._op = "select"
        return self

    def eq(self, col, val):
        self._eq[col] = val
        return self

    def limit(self, n):
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def insert(self, row):
        self._op = "insert"
        self._payload = row
        return self

    def delete(self):
        self._op = "delete"
        return self

    def execute(self):
        self.sb.calls.append({
            "name": self.name, "op": self._op,
            "eq": dict(self._eq), "payload": self._payload,
        })
        if self.name == "inspection_sets":
            if self._op == "select":
                rows = [copy.deepcopy(r) for r in self.sb.sets]
                for col, val in self._eq.items():
                    rows = [r for r in rows if r.get(col) == val]
                return _Resp(rows)
            if self._op == "update":
                sid = self._eq.get("id")
                updated = []
                for r in self.sb.sets:
                    if r.get("id") == sid:
                        r.update(self._payload)
                        updated.append(copy.deepcopy(r))
                self.sb.set_updates.append({"id": sid, "payload": dict(self._payload)})
                return _Resp(updated)
        if self.name == "work_schedules":
            if self._op == "insert":
                rows = self._payload if isinstance(self._payload, list) else [self._payload]
                self.sb.schedule_inserts.extend(rows)
                return _Resp(list(rows))
            if self._op == "delete":
                self.sb.schedule_deletes.append(dict(self._eq))
                return _Resp([])
            if self._op == "select":
                sid = self._eq.get("inspection_set_id")
                found = [s for s in self.sb.existing_schedules if s.get("inspection_set_id") == sid]
                return _Resp(found)
        return _Resp([])


class _WriteSB:
    def __init__(self, sets, existing_schedules=None):
        self.sets = [copy.deepcopy(s) for s in sets]
        self.existing_schedules = existing_schedules or []
        self.calls = []
        self.set_updates = []
        self.schedule_inserts = []
        self.schedule_deletes = []

    def table(self, name):
        return _WQ(self, name)


def _install_anchors(monkeypatch, sb):
    import services.inspection_sets_svc.anchors as A
    monkeypatch.setattr(A, "get_supabase", lambda: sb)
    seen = []
    real = A._build_next_schedule_row

    def spy(iset, anchor):
        seen.append(copy.deepcopy(iset))
        assert has_explicit_schedule_cycle(iset)
        return real(iset, anchor)

    monkeypatch.setattr(A, "_build_next_schedule_row", spy)
    return A, seen


def _install_schedules(monkeypatch, sb):
    import services.inspection_sets_svc.schedules as S
    monkeypatch.setattr(S, "get_supabase", lambda: sb)
    seen = []
    real = S._build_next_schedule_row

    def spy(iset, anchor):
        seen.append(copy.deepcopy(iset))
        assert has_explicit_schedule_cycle(iset)
        return real(iset, anchor)

    monkeypatch.setattr(S, "_build_next_schedule_row", spy)
    return S, seen


def test_W17_set_anchor_bulk_skips_canonical_null_cycle(monkeypatch):
    from schemas.inspection_sets import BulkAnchorBody
    sb = _WriteSB([_canonical_row(), _legacy_row()])
    A, seen = _install_anchors(monkeypatch, sb)
    out = A.set_anchor_bulk(BulkAnchorBody(factory_id="f1", anchor_date="2026-01-15"))
    skip = [r for r in out["data"]["results"] if r.get("status") == "skipped"]
    ok = [r for r in out["data"]["results"] if r.get("id") == "set-l"]
    assert len(skip) == 1 and skip[0]["id"] == "set-c"
    assert skip[0]["reason"] == _SKIP
    assert len(ok) == 1 and "error" not in ok[0]
    assert [s["id"] for s in seen] == ["set-l"]
    assert all(u["id"] != "set-c" for u in sb.set_updates)
    assert all((ins.get("inspection_set_id") != "set-c") for ins in sb.schedule_inserts)
    canon = next(r for r in sb.sets if r["id"] == "set-c")
    assert canon["status_code"] == "PENDING_ANCHOR"
    assert canon["anchor_confirmed"] is False
    assert canon["next_planned_date"] is None
    legacy = next(r for r in sb.sets if r["id"] == "set-l")
    assert legacy["status_code"] == "ACTIVE"
    assert legacy["anchor_confirmed"] is True


def test_W18_set_anchor_bulk_legacy_regression(monkeypatch):
    from schemas.inspection_sets import BulkAnchorBody
    sb = _WriteSB([_legacy_row()])
    A, seen = _install_anchors(monkeypatch, sb)
    out = A.set_anchor_bulk(BulkAnchorBody(factory_id="f1", anchor_date="2026-01-15"))
    assert out["data"]["total_created"] >= 1
    assert seen and seen[0]["id"] == "set-l"
    assert sb.schedule_inserts
    assert sb.sets[0]["status_code"] == "ACTIVE"


def test_W19_bulk_update_anchors_skips_canonical(monkeypatch):
    from schemas.inspection_sets import AnchorBulkItem, AnchorBulkPatchBody
    sb = _WriteSB([_canonical_row()])
    A, seen = _install_anchors(monkeypatch, sb)
    out = A.bulk_update_anchors(AnchorBulkPatchBody(items=[
        AnchorBulkItem(id="set-c", schedule_anchor_date="2026-01-15"),
    ]))
    assert out["data"]["updated"] == 0
    assert out["data"]["errors"] == [{"id": "set-c", "reason": _SKIP}]
    assert seen == []
    assert sb.set_updates == []
    assert sb.schedule_inserts == []


def test_W20_bulk_update_anchors_legacy_regression(monkeypatch):
    from schemas.inspection_sets import AnchorBulkItem, AnchorBulkPatchBody
    sb = _WriteSB([_legacy_row()])
    A, seen = _install_anchors(monkeypatch, sb)
    out = A.bulk_update_anchors(AnchorBulkPatchBody(items=[
        AnchorBulkItem(id="set-l", schedule_anchor_date="2026-01-15"),
    ]))
    assert out["data"]["updated"] == 1
    assert out["data"]["failed"] == 0
    assert seen and seen[0]["id"] == "set-l"
    assert sb.sets[0]["status_code"] == "ACTIVE"
    assert sb.schedule_inserts


def test_W21_patch_set_canonical_anchor_422(monkeypatch):
    from schemas.inspection_sets import InspectionSetPatchBody
    sb = _WriteSB([_canonical_row()])
    A, seen = _install_anchors(monkeypatch, sb)
    import routers.inspection_sets as R
    monkeypatch.setattr(R, "get_supabase", lambda: sb)
    monkeypatch.setattr(R, "_ensure_set_own", lambda *a, **k: None)
    with pytest.raises(HTTPException) as ei:
        R.patch_inspection_set(
            "set-c",
            InspectionSetPatchBody(schedule_anchor_date="2026-01-15"),
            current={"id": "u"},
        )
    assert ei.value.status_code == 422
    assert ei.value.detail == _NEED_CYCLE
    assert seen == []
    assert sb.set_updates == []
    assert sb.schedule_inserts == []
    # non-anchor patch on canonical still allowed
    out = A.patch_set("set-c", InspectionSetPatchBody(description="메모"))
    assert out["status"] == "success"
    assert sb.sets[0]["description"] == "메모"
    assert sb.sets[0]["status_code"] == "PENDING_ANCHOR"
    assert sb.sets[0]["next_planned_date"] is None


def test_W22_patch_set_legacy_anchor_regression(monkeypatch):
    from schemas.inspection_sets import InspectionSetPatchBody
    sb = _WriteSB([_legacy_row()])
    A, seen = _install_anchors(monkeypatch, sb)
    out = A.patch_set("set-l", InspectionSetPatchBody(schedule_anchor_date="2026-01-15"))
    assert out["status"] == "success"
    assert seen and seen[0]["id"] == "set-l"
    assert sb.sets[0]["status_code"] == "ACTIVE"
    assert sb.sets[0]["anchor_confirmed"] is True
    assert sb.schedule_inserts


def test_W23_update_anchor_canonical_422_legacy_ok(monkeypatch):
    from schemas.inspection_sets import AnchorBody
    sb = _WriteSB([_canonical_row()])
    A, seen = _install_anchors(monkeypatch, sb)
    import routers.inspection_sets as R
    monkeypatch.setattr(R, "get_supabase", lambda: sb)
    monkeypatch.setattr(R, "_ensure_set_own", lambda *a, **k: None)
    with pytest.raises(HTTPException) as ei:
        R.update_inspection_anchor(
            "set-c", AnchorBody(anchor_date="2026-01-15"), current={"id": "u"},
        )
    assert ei.value.status_code == 422
    assert ei.value.detail == _NEED_CYCLE
    assert seen == []
    assert sb.schedule_inserts == []

    sb2 = _WriteSB([_legacy_row()])
    A2, seen2 = _install_anchors(monkeypatch, sb2)
    out = A2.update_anchor("set-l", AnchorBody(anchor_date="2026-01-15"))
    assert out["status"] == "success"
    assert seen2 and seen2[0]["id"] == "set-l"
    assert sb2.sets[0]["status_code"] == "ACTIVE"


def test_W24_generate_schedules_anchor_mode_skips_null_cycle(monkeypatch):
    canon = _canonical_row(
        status_code="ACTIVE",
        anchor_confirmed=True,
        schedule_anchor_date="2026-01-15",
    )
    legacy = _legacy_row(
        status_code="ACTIVE",
        anchor_confirmed=True,
        schedule_anchor_date="2026-01-15",
    )
    sb = _WriteSB([canon, legacy])
    S, seen = _install_schedules(monkeypatch, sb)
    out = S.generate_schedules_for_factory("f1", "anchor", False)
    skip = [r for r in out["data"]["results"] if r.get("status") == "skipped"]
    created = [r for r in out["data"]["results"] if r.get("status") == "created"]
    assert skip == [{"id": "set-c", "name": canon["inspection_set_name"],
                     "status": "skipped", "reason": _SKIP}]
    assert len(created) == 1 and created[0]["id"] == "set-l"
    assert [s["id"] for s in seen] == ["set-l"]
    assert all(ins.get("inspection_set_id") != "set-c" for ins in sb.schedule_inserts)
    assert any(ins.get("inspection_set_id") == "set-l" for ins in sb.schedule_inserts)
    assert sb.schedule_inserts[0]["assigned_user_id"] == "user-ready"


# ── WO-SAFE-SCHEDULE-READINESS-ASSIGNEE-001 (T1~T14) ──

_ASSIGNEE_SKIP = "담당자가 지정되지 않았습니다."
_NEED_ASSIGNEE = "담당자를 먼저 지정해주세요."


def test_T1_legal_engine_anchor_no_assignee_422(monkeypatch):
    """patch_set single: cycle OK, anchor request, assignee missing → 422, mutation 0."""
    from schemas.inspection_sets import InspectionSetPatchBody
    row = _legacy_row(assignee_user_id=None)
    sb = _WriteSB([row])
    A, seen = _install_anchors(monkeypatch, sb)
    with pytest.raises(Exception) as ei:
        A.patch_set("set-l", InspectionSetPatchBody(schedule_anchor_date="2026-01-15"))
    from services.inspection_sets_svc.errors import InspectionSetsSvcError
    assert isinstance(ei.value, InspectionSetsSvcError)
    assert ei.value.status_code == 422
    assert ei.value.detail == _NEED_ASSIGNEE
    assert seen == []
    assert sb.set_updates == []
    assert sb.schedule_inserts == []
    assert sb.sets[0]["status_code"] == "PENDING_ANCHOR"
    assert sb.sets[0]["schedule_anchor_date"] is None
    assert sb.sets[0]["anchor_confirmed"] is False


def test_T2_legal_engine_stored_assignee_anchor_ok(monkeypatch):
    from schemas.inspection_sets import InspectionSetPatchBody
    sb = _WriteSB([_legacy_row(assignee_user_id="USER-STORED")])
    A, seen = _install_anchors(monkeypatch, sb)
    out = A.patch_set("set-l", InspectionSetPatchBody(schedule_anchor_date="2026-01-15"))
    assert out["status"] == "success"
    assert seen and seen[0]["id"] == "set-l"
    assert len(sb.schedule_inserts) == 1
    assert sb.schedule_inserts[0]["assigned_user_id"] == "USER-STORED"


def test_T3_patch_set_same_request_assignee_and_anchor(monkeypatch):
    from schemas.inspection_sets import InspectionSetPatchBody
    sb = _WriteSB([_legacy_row(assignee_user_id=None)])
    A, seen = _install_anchors(monkeypatch, sb)
    out = A.patch_set(
        "set-l",
        InspectionSetPatchBody(assignee_user_id="USER-REQ", schedule_anchor_date="2026-01-15"),
    )
    assert out["status"] == "success"
    assert sb.sets[0]["assignee_user_id"] == "USER-REQ"
    assert len(sb.schedule_inserts) == 1
    assert sb.schedule_inserts[0]["assigned_user_id"] == "USER-REQ"
    assert seen[0]["assignee_user_id"] == "USER-REQ"


def test_T4_update_anchor_no_assignee_422(monkeypatch):
    from schemas.inspection_sets import AnchorBody
    sb = _WriteSB([_legacy_row(assignee_user_id=None)])
    A, seen = _install_anchors(monkeypatch, sb)
    from services.inspection_sets_svc.errors import InspectionSetsSvcError
    with pytest.raises(InspectionSetsSvcError) as ei:
        A.update_anchor("set-l", AnchorBody(anchor_date="2026-01-15"))
    assert ei.value.status_code == 422
    assert ei.value.detail == _NEED_ASSIGNEE
    assert seen == []
    assert sb.schedule_inserts == []
    assert sb.set_updates == []


def test_T5_set_anchor_bulk_mixed_assignee(monkeypatch):
    from schemas.inspection_sets import BulkAnchorBody
    a = _legacy_row(id="set-a", assignee_user_id="USER-A")
    b = _legacy_row(id="set-b", assignee_user_id=None, inspection_set_name="B")
    sb = _WriteSB([a, b])
    A, seen = _install_anchors(monkeypatch, sb)
    out = A.set_anchor_bulk(BulkAnchorBody(factory_id="f1", anchor_date="2026-01-15"))
    skip = [r for r in out["data"]["results"] if r.get("status") == "skipped"]
    ok = [r for r in out["data"]["results"] if r.get("id") == "set-a" and "error" not in r]
    assert len(ok) == 1
    assert skip == [{"id": "set-b", "name": "B", "status": "skipped", "reason": _ASSIGNEE_SKIP}]
    assert [s["id"] for s in seen] == ["set-a"]
    assert all(u["id"] != "set-b" for u in sb.set_updates)
    assert all(ins.get("inspection_set_id") != "set-b" for ins in sb.schedule_inserts)
    assert sb.schedule_inserts[0]["assigned_user_id"] == "USER-A"
    b_row = next(r for r in sb.sets if r["id"] == "set-b")
    assert b_row["status_code"] == "PENDING_ANCHOR"
    assert b_row["anchor_confirmed"] is False


def test_T6_bulk_update_anchors_mixed_assignee(monkeypatch):
    from schemas.inspection_sets import AnchorBulkItem, AnchorBulkPatchBody
    a = _legacy_row(id="set-a", assignee_user_id="USER-A")
    b = _legacy_row(id="set-b", assignee_user_id=None)
    sb = _WriteSB([a, b])
    A, seen = _install_anchors(monkeypatch, sb)
    out = A.bulk_update_anchors(AnchorBulkPatchBody(items=[
        AnchorBulkItem(id="set-a", schedule_anchor_date="2026-01-15"),
        AnchorBulkItem(id="set-b", schedule_anchor_date="2026-01-15"),
    ]))
    assert out["data"]["updated"] == 1
    assert out["data"]["failed"] == 1
    assert out["data"]["errors"] == [{"id": "set-b", "reason": _ASSIGNEE_SKIP}]
    assert [s["id"] for s in seen] == ["set-a"]
    assert all(ins.get("inspection_set_id") != "set-b" for ins in sb.schedule_inserts)


def test_T7_generate_anchor_mode_no_assignee_skip(monkeypatch):
    row = _legacy_row(
        assignee_user_id=None,
        status_code="ACTIVE",
        anchor_confirmed=True,
        schedule_anchor_date="2026-01-15",
    )
    sb = _WriteSB([row], existing_schedules=[{"id": "ws-old", "inspection_set_id": "set-l"}])
    S, seen = _install_schedules(monkeypatch, sb)
    out = S.generate_schedules_for_factory("f1", "anchor", False)
    assert out["data"]["created"] == 0
    assert out["data"]["results"] == [{
        "id": "set-l",
        "name": row["inspection_set_name"],
        "status": "skipped",
        "reason": _ASSIGNEE_SKIP,
    }]
    assert seen == []
    assert sb.schedule_inserts == []
    assert sb.schedule_deletes == []


def test_T8_generate_anchor_mode_with_assignee_create(monkeypatch):
    row = _legacy_row(
        assignee_user_id="USER-OK",
        status_code="ACTIVE",
        anchor_confirmed=True,
        schedule_anchor_date="2026-01-15",
    )
    sb = _WriteSB([row])
    S, seen = _install_schedules(monkeypatch, sb)
    out = S.generate_schedules_for_factory("f1", "anchor", False)
    assert out["data"]["created"] >= 1
    assert seen and seen[0]["assignee_user_id"] == "USER-OK"
    assert sb.schedule_inserts[0]["assigned_user_id"] == "USER-OK"


def test_T9_force_true_no_assignee_no_delete(monkeypatch):
    row = _legacy_row(
        assignee_user_id=None,
        status_code="ACTIVE",
        anchor_confirmed=True,
        schedule_anchor_date="2026-01-15",
    )
    sb = _WriteSB([row], existing_schedules=[{"id": "ws-old", "inspection_set_id": "set-l", "status_code": "SCHEDULED"}])
    S, seen = _install_schedules(monkeypatch, sb)
    out = S.generate_schedules_for_factory("f1", "anchor", True)
    assert out["data"]["created"] == 0
    assert out["data"]["results"][0]["reason"] == _ASSIGNEE_SKIP
    assert seen == []
    assert sb.schedule_deletes == []
    assert sb.schedule_inserts == []


def test_T10_cycle_missing_still_422_even_with_assignee(monkeypatch):
    from schemas.inspection_sets import InspectionSetPatchBody
    sb = _WriteSB([_canonical_row(assignee_user_id="USER-X")])
    A, seen = _install_anchors(monkeypatch, sb)
    from services.inspection_sets_svc.errors import InspectionSetsSvcError
    with pytest.raises(InspectionSetsSvcError) as ei:
        A.patch_set("set-c", InspectionSetPatchBody(schedule_anchor_date="2026-01-15"))
    assert ei.value.status_code == 422
    assert ei.value.detail == _NEED_CYCLE
    assert seen == []
    assert sb.schedule_inserts == []


def test_T11_law_engine_mode_unchanged_delegation(monkeypatch):
    """mode=law_engine delegates to official OTR materializer (compat mode name retained)."""
    import services.inspection_sets_svc.schedules as S
    called = {}

    def fake_run(fid, sb):
        called["fid"] = fid
        return {"total_sets": 2, "created": 1, "skipped_dup": 0, "skipped_no_condition": 1}

    monkeypatch.setattr(S, "get_supabase", lambda: object())
    monkeypatch.setattr(S, "run_generate_operation_schedules", fake_run)
    out = S.generate_schedules_for_factory("f1", "law_engine", False)
    assert called["fid"] == "f1"
    assert out["data"]["mode"] == "law_engine"
    assert out["data"]["created"] == 1
    assert out["data"]["skipped_no_condition"] == 1


def test_T12_operation_cycle_no_schedule_gate(monkeypatch):
    """operation_cycle remains cycle-only; assignee presence irrelevant; schedule 0."""
    import inspect as ins
    import services.inspection_sets_svc.operation_cycle as OC
    # Code body (exclude module docstring): no assignee gate / schedule builder.
    body = ins.getsource(OC.set_operation_cycle)
    assert "assignee_user_id" not in body
    assert "_build_next_schedule_row" not in body
    assert "generate_schedules" not in body
    assert "table(\"work_schedules\")" not in body
    assert "table('work_schedules')" not in body


def test_T13_manual_row_without_assignee_still_schedules(monkeypatch):
    """MANUAL semantics: assignee readiness not forced."""
    from schemas.inspection_sets import InspectionSetPatchBody, BulkAnchorBody, AnchorBody
    sb = _WriteSB([_manual_row()])
    A, seen = _install_anchors(monkeypatch, sb)
    out = A.patch_set("set-m", InspectionSetPatchBody(schedule_anchor_date="2026-01-15"))
    assert out["status"] == "success"
    assert sb.schedule_inserts
    assert sb.schedule_inserts[0]["assigned_user_id"] is None
    assert sb.sets[0]["status_code"] == "ACTIVE"

    sb2 = _WriteSB([_manual_row(id="set-m2")])
    A2, _ = _install_anchors(monkeypatch, sb2)
    out2 = A2.set_anchor_bulk(BulkAnchorBody(factory_id="f1", anchor_date="2026-01-15"))
    assert out2["data"]["total_created"] >= 1
    assert all(r.get("status") != "skipped" for r in out2["data"]["results"])

    sb3 = _WriteSB([_manual_row(id="set-m3")])
    A3, _ = _install_anchors(monkeypatch, sb3)
    out3 = A3.update_anchor("set-m3", AnchorBody(anchor_date="2026-01-15"))
    assert out3["status"] == "success"
    assert sb3.schedule_inserts


def test_T13b_manual_with_assignee_keeps_schedule_assigned_none(monkeypatch):
    """PATCH-1: MANUAL + assignee on set must NOT leak into work_schedules.assigned_user_id."""
    from schemas.inspection_sets import InspectionSetPatchBody
    sb = _WriteSB([_manual_row(assignee_user_id="USER-MANUAL")])
    A, _ = _install_anchors(monkeypatch, sb)
    out = A.patch_set("set-m", InspectionSetPatchBody(schedule_anchor_date="2026-01-15"))
    assert out["status"] == "success"
    assert sb.sets[0]["assignee_user_id"] == "USER-MANUAL"
    assert len(sb.schedule_inserts) == 1
    assert sb.schedule_inserts[0]["assigned_user_id"] is None


def test_T14_legal_actor_not_used_as_assignee(monkeypatch):
    from schemas.inspection_sets import InspectionSetPatchBody
    row = _legacy_row(assignee_user_id=None)
    row["legal_actor"] = "사업주"
    sb = _WriteSB([row])
    A, seen = _install_anchors(monkeypatch, sb)
    from services.inspection_sets_svc.errors import InspectionSetsSvcError
    with pytest.raises(InspectionSetsSvcError) as ei:
        A.patch_set("set-l", InspectionSetPatchBody(schedule_anchor_date="2026-01-15"))
    assert ei.value.detail == _NEED_ASSIGNEE
    assert seen == []
    assert sb.schedule_inserts == []
    import services.inspection_sets_svc.anchors as Anch
    blob = inspect.getsource(Anch)
    assert "legal_actor" not in blob
