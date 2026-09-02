"""tests/test_paid_result_delivery_wiring_v1.py — WO-DQ-WHAT-05D-A

routers/diagnosis_result_web.py : paid-result 6-key Product canonical caller 연결 +
source-text EXACT 안전 투영(canonical_source_text). T01~T18.

실 Supabase/LEG Runtime 미호출 — get_supabase / build_paid_result_product_v1 monkeypatch.
"""
from __future__ import annotations

import copy
import json

import pytest

import routers.diagnosis_result_web as rw
from routers.diagnosis_result_web import (
    _INTERNAL_SOURCE_INDEX,
    _attach_canonical_source_text,
    _leg_rules_from_obligations_raw,
    _source_text_exact_items_by_ref,
    _strip_internal_source_index,
)

SOURCE_TEXT_KEY = rw.SOURCE_TEXT_KEY
CANON = "canonical_source_text"


# ─────────────────────────────────────────────────────────────
# fixtures
# ─────────────────────────────────────────────────────────────
def leg_obligation(atom, what, *, law="산업안전보건기준에 관한 규칙", art="1", appl="APPLICABLE"):
    return {
        "atom_id": atom, "law_name": law, "law_article": art,
        "applicability": appl,
        "obligation_detail": {"what": what},
        "enrichment": {"obligation_type": "INSPECT"},
    }


def full_result_leg(obligations):
    return {"sector": "BUILDING", "obligations_raw": obligations}


def stored_rec(obligations, *, tier="BUILDING_V2", status="ACTIVE", rules_table=None):
    fr = full_result_leg(obligations)
    if rules_table is not None:
        fr["rules_table"] = rules_table
    return {
        "id": "row-1", "public_token": "tok-1", "tier_code": tier,
        "status": status, "expires_at": None, "created_at": "2026-08-11T01:25:02+00:00",
        "input_data": {"company_name": "샘플", "sector": "BUILDING", "workers": 10},
        "full_result": fr,
    }


def source_item(ref, atom, text, *, status="EXACT", spid="sp", scid="sc",
                law="산업안전보건기준에 관한 규칙", art="1", sha="h"):
    return {
        "obligation_ref": ref, "atom_id": atom, "source_atom_ids": [atom],
        "semantic_clause_id": scid, "source_part_id": spid,
        "law_name": law, "law_article": art, "text": text, "source_sha256": sha,
        "resolution_status": status,
    }


def fake_product(items, unresolved=None):
    return {
        "contract_version": 1, "diagnosis": {}, "diagnosis_profile": {},
        "paid_result_materials_v1": {}, "paid_result_evidence_v1": {},
        SOURCE_TEXT_KEY: {"version": 1, "source_mode": "LIVE_LEG_SOURCE",
                          "items": list(items), "unresolved": list(unresolved or [])},
    }


class FakeQuery:
    def __init__(self, store):
        self._store = store

    def select(self, sel):
        self._store["select"] = sel
        return self

    def eq(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def execute(self):
        class R:
            data = self._store["data"]
        return R()


class FakeSupabase:
    def __init__(self, rec):
        self.store = {"data": [rec] if rec is not None else [], "select": None}

    def table(self, *a, **k):
        return FakeQuery(self.store)


def install(monkeypatch, rec, product_items=None, product_exc=None):
    fake_sb = FakeSupabase(rec)
    monkeypatch.setattr(rw, "get_supabase", lambda: fake_sb)
    calls = {"n": 0, "rec": None}

    def spy(row):
        calls["n"] += 1
        calls["rec"] = row
        if product_exc is not None:
            raise product_exc
        return fake_product(product_items or [])

    monkeypatch.setattr(rw, "build_paid_result_product_v1", spy)
    return fake_sb, calls


# ─────────────────────────────────────────────────────────────
# T01~T04 — route boundary / product call gating / row read
# ─────────────────────────────────────────────────────────────
def test_T01_free_route_no_product_call(monkeypatch):
    rec = stored_rec([leg_obligation("a0", "점검을 해야 한다")], tier="BUILDING_V2")  # genuine paid tier
    _, calls = install(monkeypatch, rec, product_items=[source_item(0, "a0", "원문A")])
    rw.get_diagnosis_result_web("tok-1")          # FREE ROUTE
    assert calls["n"] == 0                          # route(=free)로 gate, tier 무관


def test_T02_paid_route_free_tier_no_product_call(monkeypatch):
    rec = stored_rec([leg_obligation("a0", "점검")], tier="BUILDING_FREE")  # free tier
    _, calls = install(monkeypatch, rec, product_items=[source_item(0, "a0", "원문A")])
    rw.get_paid_result_web("tok-1")                # PAID ROUTE + FREE TIER
    assert calls["n"] == 0


def test_T03_genuine_paid_product_call_exactly_once(monkeypatch):
    rec = stored_rec([leg_obligation("a0", "점검")], tier="BUILDING_V2")
    _, calls = install(monkeypatch, rec, product_items=[source_item(0, "a0", "원문A")])
    rw.get_paid_result_web("tok-1")
    assert calls["n"] == 1


def test_T04_select_includes_created_at(monkeypatch):
    rec = stored_rec([leg_obligation("a0", "점검")], tier="BUILDING_V2")
    fake_sb, _ = install(monkeypatch, rec, product_items=[source_item(0, "a0", "원문A")])
    rw.get_paid_result_web("tok-1")
    assert "created_at" in fake_sb.store["select"]


# ─────────────────────────────────────────────────────────────
# T05~T10, T13 — pure attach rule (STEP 6)
# ─────────────────────────────────────────────────────────────
def _rows(*specs):
    # specs: (source_index, atom_id) -> minimal LEG-like row
    out = []
    for si, atom in specs:
        out.append({"law_name": "L", "law_article": "1", "obligation_summary": "w",
                    "description": "w", "atom_id": atom, _INTERNAL_SOURCE_INDEX: si})
    return out


def test_T05_exact_attach():
    rows = _rows((0, "a0"))
    _attach_canonical_source_text(rows, _source_text_exact_items_by_ref(
        fake_product([source_item(0, "a0", "원문A")])))
    assert rows[0][CANON] == "원문A"


def test_T06_source_mismatch_absent():
    rows = _rows((0, "a0"))
    _attach_canonical_source_text(rows, _source_text_exact_items_by_ref(
        fake_product([source_item(0, "a0", None, status="SOURCE_MISMATCH")])))
    assert CANON not in rows[0]


def test_T07_unresolved_absent():
    rows = _rows((0, "a0"))
    prod = fake_product([], unresolved=[{"obligation_ref": 0, "atom_id": "a0",
                                         "resolution_status": "UNRESOLVED", "reason": "X"}])
    _attach_canonical_source_text(rows, _source_text_exact_items_by_ref(prod))
    assert CANON not in rows[0]


def test_T08_missing_item_absent():
    rows = _rows((0, "a0"))
    _attach_canonical_source_text(rows, _source_text_exact_items_by_ref(
        fake_product([source_item(5, "a5", "원문X")])))  # ref 5 != row si 0
    assert CANON not in rows[0]


def test_T09_source_index_mismatch_no_attach():
    rows = _rows((2, "a2"))
    _attach_canonical_source_text(rows, _source_text_exact_items_by_ref(
        fake_product([source_item(0, "a2", "원문")])))  # same atom, wrong ref
    assert CANON not in rows[0]


def test_T10_atom_id_mismatch_no_attach():
    rows = _rows((0, "a0"))
    _attach_canonical_source_text(rows, _source_text_exact_items_by_ref(
        fake_product([source_item(0, "DIFFERENT", "원문")])))
    assert CANON not in rows[0]


def test_T13_article375_two_rows_no_collapse():
    A = "29800eea-2fc1-58c2-9598-1fd46297c409"
    B = "50f40032-855f-52eb-ae90-ebf8a319582a"
    SP = "e9164e6b-b962-4364-bd89-d6a091a6a798"
    rows = _rows((0, A), (1, B))
    prod = fake_product([source_item(0, A, "유도.", spid=SP, art="375"),
                         source_item(1, B, "유도.", spid=SP, art="375")])
    _attach_canonical_source_text(rows, _source_text_exact_items_by_ref(prod))
    assert len(rows) == 2
    assert rows[0][CANON] == rows[1][CANON] == "유도."


# ─────────────────────────────────────────────────────────────
# T11, T12, T14~T18 — end-to-end via _build_result_payload
# ─────────────────────────────────────────────────────────────
def test_T11_existing_display_unchanged(monkeypatch):
    rec = stored_rec([leg_obligation("a0", "점검을 해야 한다")], tier="BUILDING_V2")
    install(monkeypatch, rec, product_items=[source_item(0, "a0", "제1조 원문 전문…")])
    d = rw.get_paid_result_web("tok-1")["data"]
    row = d["rules_table"][0]
    assert row["obligation_summary"] == "점검을 해야 한다"   # duty.what 유지
    assert row["description"] == "점검을 해야 한다"
    assert row[CANON] == "제1조 원문 전문…"                   # additive only


def test_T12_legacy_raw_rules_no_product_no_canonical(monkeypatch):
    # WO-05D-A REV-1 / DECISION-C: T12 책임(legacy raw_rules→Product 미호출/canonical 미부착)
    #   외의 legacy enrichment DB transport 를 격리. gate(not raw_rules)는 실제 route 로 평가.
    monkeypatch.setattr(rw, "enrich_rules_with_candidate_slots", lambda *args, **kwargs: None)
    rules_table = [{"law_name": "L", "law_article": "1", "obligation_type": "INSPECT",
                    "obligation_summary": "레거시", "description": "레거시", "rule_id": "r1"}]
    rec = stored_rec([leg_obligation("a0", "무시")], tier="BUILDING_V2", rules_table=rules_table)
    _, calls = install(monkeypatch, rec, product_items=[source_item(0, "a0", "원문")])
    d = rw.get_paid_result_web("tok-1")["data"]
    assert calls["n"] == 0                                   # legacy path → product 미호출
    assert all(CANON not in r for r in d["rules_table"])     # 추측 부착 0


def test_T14_no_internal_source_index_exposed(monkeypatch):
    rec = stored_rec([leg_obligation("a0", "점검")], tier="BUILDING_V2")
    install(monkeypatch, rec, product_items=[source_item(0, "a0", "원문A")])
    d = rw.get_paid_result_web("tok-1")["data"]
    blob = repr(d)
    assert _INTERNAL_SOURCE_INDEX not in blob
    for r in d["rules_table"]:
        assert _INTERNAL_SOURCE_INDEX not in r


def test_T15_no_internal_product_exposure(monkeypatch):
    rec = stored_rec([leg_obligation("a0", "점검")], tier="BUILDING_V2")
    install(monkeypatch, rec, product_items=[source_item(0, "a0", "원문A")])
    d = rw.get_paid_result_web("tok-1")["data"]
    blob = repr(d)
    for banned in ["source_atom_ids", "semantic_clause_id", "source_part_id",
                   "source_sha256", "paid_result_materials_v1", "paid_result_evidence_v1",
                   "paid_result_source_text_v1"]:
        assert banned not in blob, banned


def test_T16_product_exception_503_not_silent(monkeypatch):
    from fastapi import HTTPException
    rec = stored_rec([leg_obligation("a0", "점검")], tier="BUILDING_V2")
    install(monkeypatch, rec, product_exc=RuntimeError("leg down"))
    with pytest.raises(HTTPException) as ei:
        rw.get_paid_result_web("tok-1")
    assert ei.value.status_code == 503
    assert "leg down" not in str(ei.value.detail)             # 내부 detail 누출 0


def test_T17_free_payload_regression(monkeypatch):
    obs = [leg_obligation("a%d" % i, "점검 %d" % i, art=str(i)) for i in range(8)]
    rec = stored_rec(obs, tier="BUILDING_FREE")   # free tier → is_free True → preview 절단 적용
    install(monkeypatch, rec, product_items=[source_item(i, "a%d" % i, "원문%d" % i) for i in range(8)])
    d = rw.get_diagnosis_result_web("tok-1")["data"]
    assert d["is_free"] is True
    assert len(d["rules_table"]) == 5                          # free preview limit(=5)
    assert all(CANON not in r for r in d["rules_table"])       # free route: no canonical


def test_T18_paid_payload_additive_only_where_exact(monkeypatch):
    obs = [leg_obligation("a0", "점검0"), leg_obligation("a1", "점검1", art="2")]
    rec = stored_rec(obs, tier="BUILDING_V2")
    # only ref0 EXACT; ref1 SOURCE_MISMATCH → only row0 canonical
    install(monkeypatch, rec, product_items=[
        source_item(0, "a0", "원문0"),
        source_item(1, "a1", None, status="SOURCE_MISMATCH")])
    d = rw.get_paid_result_web("tok-1")["data"]
    rows = d["rules_table"]
    assert len(rows) == 2
    assert rows[0][CANON] == "원문0"
    assert CANON not in rows[1]
    # 기존 필드 보존
    assert rows[0]["obligation_summary"] == "점검0"
    assert rows[1]["obligation_summary"] == "점검1"


# source_index tracking sanity (STEP 5)
def test_source_index_enumerate_alignment():
    obs = [leg_obligation("a0", "w0"), leg_obligation("a1", "w1"), leg_obligation("a2", "w2")]
    rows = _leg_rules_from_obligations_raw(obs)
    assert [r[_INTERNAL_SOURCE_INDEX] for r in rows] == [0, 1, 2]


# ─────────────────────────────────────────────────────────────
# WO-DQ-WHAT-05D-A REV-1 — security hygiene: public_token must NOT reach logger
#   T16(generic 503/detail 미노출)과 목적이 다름: 이 테스트는 우리 코드가
#   public_token 을 log.exception 인자로 넘기지 않는 계약을 고정한다.
# ─────────────────────────────────────────────────────────────
def test_T19_product_exception_log_excludes_public_token(monkeypatch):
    from fastapi import HTTPException

    captured = {"calls": []}

    def fake_exception(msg, *args, **kwargs):
        captured["calls"].append((msg, args))

    monkeypatch.setattr(rw.log, "exception", fake_exception)

    rec = stored_rec([leg_obligation("a0", "점검")], tier="BUILDING_V2")  # public_token="tok-1"
    install(monkeypatch, rec, product_exc=RuntimeError("leg down"))

    with pytest.raises(HTTPException) as ei:
        rw.get_paid_result_web("tok-1")
    assert ei.value.status_code == 503

    # 정확히 1회 로깅, 메시지는 토큰 없는 고정 문자열, positional args 비어있음.
    assert len(captured["calls"]) == 1
    msg, args = captured["calls"][0]
    assert msg == "paid_result_product build failed"
    assert args == ()
    # public_token("tok-1")이 message/args 어디에도 없어야 함.
    assert "tok-1" not in msg
    assert all("tok-1" not in str(a) for a in args)
    assert "public_token" not in msg


# ─────────────────────────────────────────────────────────────
# WO-DQ-WHAT-05D-A-PUBLIC-KEY-OBLIGATION-SANITIZE-001
#   full_result.key_obligations → public payload allowlist projection.
#   내부 provenance(source_atom_ids 등) 차단, denylist 아닌 allowlist fail-closed.
# ─────────────────────────────────────────────────────────────
def _rec_with_key_obligations(key_obs, *, tier="BUILDING_V2"):
    rec = stored_rec([leg_obligation("a0", "점검")], tier=tier)
    rec["full_result"]["key_obligations"] = key_obs
    return rec


def _paid_key_obligations(monkeypatch, key_obs):
    rec = _rec_with_key_obligations(key_obs)
    install(monkeypatch, rec, product_items=[source_item(0, "a0", "원문A")])
    return rw.get_paid_result_web("tok-1")["data"]["key_obligations"]


def test_K1_allowlist_preservation(monkeypatch):
    row = {
        "type": "APPOINT", "obligation_type": "APPOINT",
        "obligation_summary": "요약", "description": "설명", "remarks": "비고",
        "rule_name": "룰명", "law": "법", "law_name": "산업안전보건법",
        "law_article": "38", "penalty": "벌칙", "penalty_summary": "과태료",
    }
    out = _paid_key_obligations(monkeypatch, [row])
    assert len(out) == 1
    for k, v in row.items():
        assert out[0][k] == v          # allowlist 값 EXACT 보존


def test_K2_known_internal_raw_strip(monkeypatch):
    row = {
        "obligation_summary": "요약", "law_name": "산업안전보건법",  # 보존
        # 차단 대상(이번 raw key + provenance)
        "applicability": "APPLICABLE", "atom_id": "a-1", "evidence": "근거원문",
        "source": "LEG", "source_atom_ids": ["a-1"], "title": "제목", "triggered_by": ["x"],
        "semantic_clause_id": "sc-1", "source_part_id": "sp-1", "source_sha256": "h",
    }
    out = _paid_key_obligations(monkeypatch, [row])[0]
    for banned in ("applicability", "atom_id", "evidence", "source", "source_atom_ids",
                   "title", "triggered_by", "semantic_clause_id", "source_part_id", "source_sha256"):
        assert banned not in out, banned
    assert out["obligation_summary"] == "요약"      # 보존은 유지
    assert out["law_name"] == "산업안전보건법"


def test_K3_unknown_future_field_fail_closed(monkeypatch):
    row = {"obligation_summary": "요약", "_future_internal_field": "SECRET"}
    out = _paid_key_obligations(monkeypatch, [row])[0]
    assert "_future_internal_field" not in out       # allowlist라 미승인 신규 필드 자동 차단
    assert "SECRET" not in json.dumps(out, ensure_ascii=False)
    assert out["obligation_summary"] == "요약"


def test_K4_order_and_count_preserved(monkeypatch):
    obs = [
        {"obligation_summary": "s0", "source_atom_ids": ["a0"]},
        {"obligation_summary": "s1", "source_atom_ids": ["a1"]},
        {"obligation_summary": "s2", "source_atom_ids": ["a2"]},
    ]
    out = _paid_key_obligations(monkeypatch, obs)
    assert len(out) == 3
    assert [r["obligation_summary"] for r in out] == ["s0", "s1", "s2"]
    assert all("source_atom_ids" not in r for r in out)


def test_K5_source_atom_ids_absent_end_to_end(monkeypatch):
    # 전체 응답 재귀 스캔: 내부 provenance key 노출 0
    rec = _rec_with_key_obligations([{"obligation_summary": "요약", "source_atom_ids": ["a0"],
                                      "atom_id": "a0", "law_name": "산업안전보건법"}])
    install(monkeypatch, rec, product_items=[source_item(0, "a0", "원문A")])
    d = rw.get_paid_result_web("tok-1")["data"]
    blob = json.dumps(d, ensure_ascii=False)
    for banned in ("source_atom_ids", "semantic_clause_id", "source_part_id", "source_sha256",
                   "__source_index", "paid_result_materials_v1", "paid_result_evidence_v1",
                   "paid_result_source_text_v1"):
        assert '"%s"' % banned not in blob, banned
