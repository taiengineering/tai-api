"""WO-SAAS-LEGAL-TIME-CONSUME-001 STEP 4B-4B — read-model helper + queries wiring.

S1~S26. helper 는 pure/additive; queries 는 supabase mock 로 projection 검증.
DB/network/LEG 불필요.
"""
from __future__ import annotations

import copy
import inspect

from services.inspection_sets_svc.legal_time_read_model import attach_legal_time_normalized
from services.legal_time_normalizer import VERSION


def _row(**over):
    r = {
        "id": "set-1",
        "factory_id": "f1",
        "source": "LEGAL_ENGINE",
        "cycle_unit": None,
        "cycle_value": None,
        "legal_obligation_atom_id": "atom-A",
        "legal_operation_presentation": {"timing": "작업 시작 전", "cycle": "1년에 1회"},
    }
    r.update(over)
    return r


# ── S1~S3 timing/cycle 독립 ──
def test_S1_timing_raw_to_normalized():
    out = attach_legal_time_normalized(_row(legal_operation_presentation={"timing": "즉시"}))
    assert out["legal_time_normalized"]["timing"]["type"] == "IMMEDIATE"
    assert "cycle" not in out["legal_time_normalized"]


def test_S2_cycle_raw_to_normalized():
    out = attach_legal_time_normalized(_row(legal_operation_presentation={"cycle": "매년"}))
    assert out["legal_time_normalized"]["cycle"]["type"] == "RECURRING"
    assert "timing" not in out["legal_time_normalized"]


def test_S3_both_independent():
    out = attach_legal_time_normalized(_row())
    n = out["legal_time_normalized"]
    assert n["version"] == VERSION
    assert n["timing"]["type"] == "EVENT_DEADLINE"
    assert n["cycle"]["type"] == "RECURRING"


# ── S4~S9 type coverage ──
def test_S4_recurring():
    out = attach_legal_time_normalized(_row(legal_operation_presentation={"cycle": "1년에 1회"}))
    c = out["legal_time_normalized"]["cycle"]
    assert (c["type"], c["value"], c["unit"], c["operator"]) == ("RECURRING", 1, "YEAR", "EVERY")


def test_S5_event_deadline_before_no_numeric():
    out = attach_legal_time_normalized(_row(legal_operation_presentation={"timing": "작업 시작 전"}))
    t = out["legal_time_normalized"]["timing"]
    assert t["type"] == "EVENT_DEADLINE" and t["operator"] == "BEFORE"
    assert "value" not in t and "unit" not in t


def test_S6_continuous_no_numeric():
    out = attach_legal_time_normalized(_row(legal_operation_presentation={"cycle": "상시"}))
    c = out["legal_time_normalized"]["cycle"]
    assert c["type"] == "CONTINUOUS"
    assert "value" not in c and "unit" not in c


def test_S7_immediate():
    out = attach_legal_time_normalized(_row(legal_operation_presentation={"timing": "즉시"}))
    assert out["legal_time_normalized"]["timing"]["type"] == "IMMEDIATE"


def test_S8_raw_only_jeonggi():
    out = attach_legal_time_normalized(_row(legal_operation_presentation={"cycle": "정기적으로"}))
    assert out["legal_time_normalized"]["cycle"]["status"] == "RAW_ONLY"


def test_S9_raw_only_twice():
    out = attach_legal_time_normalized(_row(legal_operation_presentation={"cycle": "연 2회"}))
    assert out["legal_time_normalized"]["cycle"]["status"] == "RAW_ONLY"


# ── S10 source_text EXACT (공백 보존) ──
def test_S10_source_text_exact():
    out = attach_legal_time_normalized(_row(legal_operation_presentation={"cycle": "  1년에 1회  "}))
    c = out["legal_time_normalized"]["cycle"]
    assert c["type"] == "RECURRING"
    assert c["source_text"] == "  1년에 1회  "   # 공백 EXACT


# ── S11 presentation 없음 → key 미생성 ──
def test_S11_no_presentation_no_key():
    r = _row()
    del r["legal_operation_presentation"]
    out = attach_legal_time_normalized(r)
    assert "legal_time_normalized" not in out


def test_S11b_presentation_none():
    out = attach_legal_time_normalized(_row(legal_operation_presentation=None))
    assert "legal_time_normalized" not in out


# ── S12/S26 malformed → fail-close ──
def test_S12_S26_malformed_fail_close():
    for bad in ([], "x", 123, 0, True):
        out = attach_legal_time_normalized(_row(legal_operation_presentation=bad))
        assert "legal_time_normalized" not in out
    # presentation dict 이나 timing/cycle 이 malformed → 둘 다 None → key 미생성
    out = attach_legal_time_normalized(_row(legal_operation_presentation={"timing": 123, "cycle": None}))
    assert "legal_time_normalized" not in out
    # item 자체가 dict 아님 → 그대로 반환
    for bad_item in (None, [], "x", 5):
        assert attach_legal_time_normalized(bad_item) == bad_item


# ── S13 기존 API fields delta 0 ──
def test_S13_existing_fields_delta_zero():
    r = _row(status_code="PENDING_ANCHOR", assignee_user_id=None, law_name="산안법")
    out = attach_legal_time_normalized(r)
    for k, v in r.items():
        assert out[k] == v          # 기존 key/value 그대로
    # 추가된 key 는 legal_time_normalized 하나뿐
    assert set(out.keys()) - set(r.keys()) == {"legal_time_normalized"}


# ── S14 cycle_unit/value mutation 0 / S15/S16/S17 write 0 ──
def test_S14_cycle_fields_unchanged():
    r = _row(cycle_unit=None, cycle_value=None)
    out = attach_legal_time_normalized(r)
    assert out["cycle_unit"] is None and out["cycle_value"] is None
    assert "next_planned_date" not in out or out.get("next_planned_date") == r.get("next_planned_date")


# ── S20 legacy presentation NULL → absent ──
def test_S20_legacy_null_absent():
    legacy = {"id": "set-l", "source": "LEGAL_ENGINE", "cycle_unit": "month", "cycle_value": 1,
              "legal_operation_presentation": None}
    out = attach_legal_time_normalized(legacy)
    assert "legal_time_normalized" not in out
    assert out["cycle_unit"] == "month" and out["cycle_value"] == 1


# ── S24 input mutation 0 (원본 deepcopy equality) ──
def test_S24_input_mutation_zero():
    r = _row()
    before = copy.deepcopy(r)
    out = attach_legal_time_normalized(r)
    assert r == before                                  # 원본 무변경
    assert out is not r                                 # 새 dict
    assert out["legal_operation_presentation"] is r["legal_operation_presentation"]  # snapshot 원문 무변경(동일 참조)
    assert "legal_time_normalized" not in r


# ── S23 deterministic ──
def test_S23_deterministic():
    r = _row()
    first = attach_legal_time_normalized(copy.deepcopy(r))
    for _ in range(50):
        assert attach_legal_time_normalized(copy.deepcopy(r)) == first


# ── S25 VERSION source ──
def test_S25_version_from_normalizer():
    out = attach_legal_time_normalized(_row())
    assert out["legal_time_normalized"]["version"] == VERSION
    import services.inspection_sets_svc.legal_time_read_model as H
    src = inspect.getsource(H)
    assert '"v1"' not in src and "'v1'" not in src   # VERSION 하드코딩 금지


# ── S7(static boundary) helper 순수성 ──
def test_static_boundary_helper():
    import services.inspection_sets_svc.legal_time_read_model as H
    src = inspect.getsource(H)
    for banned in ("supabase", "get_supabase", "CYCLE_CODE_MAP", "law_engine",
                   "rtm_engine", "openai", "anthropic", "canonical_writer"):
        assert banned not in src


# ── queries wiring (supabase mock) ──
class _Q:
    def __init__(self, sb):
        self.sb = sb; self._eq = {}

    def select(self, cols, count=None):
        self.sb.last_select = cols; return self
    def eq(self, c, v): self._eq[c] = v; return self
    def order(self, *a, **k): return self
    def range(self, *a, **k): return self
    def single(self): self.sb.single = True; return self
    def execute(self):
        class R: pass
        r = R()
        if getattr(self.sb, "single", False):
            r.data = copy.deepcopy(self.sb.rows[0]) if self.sb.rows else None
        else:
            r.data = [copy.deepcopy(x) for x in self.sb.rows]; r.count = len(self.sb.rows)
        return r


class _SB:
    def __init__(self, rows):
        self.rows = rows; self.last_select = None; self.single = False
    def table(self, n):
        assert n == "inspection_sets"; return _Q(self)


def test_get_sets_list_projection(monkeypatch):
    from services.inspection_sets_svc import queries as Q
    sb = _SB([_row(id="c1"), {"id": "l1", "source": "MANUAL", "cycle_unit": "month",
                              "cycle_value": 1, "legal_operation_presentation": None}])
    monkeypatch.setattr(Q, "get_supabase", lambda: sb)
    out = Q.get_sets_list("f1", None, None, 1, 20)
    assert "legal_operation_presentation" in sb.last_select   # select additive
    items = out["data"]["items"]
    # canonical row → normalized 부착
    c = next(i for i in items if i["id"] == "c1")
    assert c["legal_time_normalized"]["cycle"]["type"] == "RECURRING"
    assert c["legal_operation_presentation"] == {"timing": "작업 시작 전", "cycle": "1년에 1회"}  # 원문 무변경
    # legacy(presentation None) → 미부착 + 기존 fill 유지
    l = next(i for i in items if i["id"] == "l1")
    assert "legal_time_normalized" not in l
    assert l["obligation_type"] == "OTHER" and l["cycle_base_guide_rule"] == ""


def test_get_set_by_id_projection(monkeypatch):
    from services.inspection_sets_svc import queries as Q
    sb = _SB([_row(id="d1")])
    monkeypatch.setattr(Q, "get_supabase", lambda: sb)
    out = Q.get_set_by_id("d1")
    assert sb.last_select == "*"                             # select("*") 보존
    assert out["data"]["legal_time_normalized"]["timing"]["type"] == "EVENT_DEADLINE"


def test_get_set_by_id_legacy(monkeypatch):
    from services.inspection_sets_svc import queries as Q
    sb = _SB([{"id": "d2", "legal_operation_presentation": None, "cycle_unit": "year", "cycle_value": 1}])
    monkeypatch.setattr(Q, "get_supabase", lambda: sb)
    out = Q.get_set_by_id("d2")
    assert "legal_time_normalized" not in out["data"]
    assert out["data"]["cycle_unit"] == "year"


def test_canonical_writer_and_normalizer_delta_zero():
    # 이 WP 는 canonical_writer / legal_time_normalizer semantic 을 건드리지 않는다.
    import services.inspection_sets_svc.canonical_writer as W
    assert "legal_time_read_model" not in inspect.getsource(W)
    assert "legal_time_normalized" not in inspect.getsource(W)
