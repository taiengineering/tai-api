"""tests/test_paid_result_source_text_v1.py — WO-DQ-WHAT-05C

C01~C09  clients/leg_runtime_client.fetch_source_texts   (HTTP 계약, fake httpx)
S01~S16  services/paid_result_source_text_svc            (obligation sidecar, fake loader)

실 HTTP / 실 LEG Runtime 은 호출하지 않는다(§24 LIVE DEFERRED).
"""
from __future__ import annotations

import copy
import inspect

import pytest

import clients.leg_runtime_client as leg
from clients.leg_runtime_client import LegRuntimeError, fetch_source_texts
from services.paid_result_source_text_svc import (
    PaidResultSourceTextError,
    build_paid_result_source_text_v1,
)


# ─────────────────────────────────────────────────────────────────────────────
# fake httpx response
# ─────────────────────────────────────────────────────────────────────────────
class FakeResp:
    def __init__(self, status_code=200, payload=None, text="", raise_json=False):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text
        self._raise_json = raise_json

    def json(self):
        if self._raise_json:
            raise ValueError("no json")
        return self._payload


def install_post(monkeypatch, resp=None, exc=None, url_is="http://leg.test"):
    calls = {"n": 0, "url": None, "json": None, "timeout": None}

    def fake_post(url, json=None, timeout=None):
        calls["n"] += 1
        calls["url"] = url
        calls["json"] = json
        calls["timeout"] = timeout
        if exc is not None:
            raise exc
        return resp

    monkeypatch.setattr(leg, "LEG_RUNTIME_URL", url_is)
    monkeypatch.setattr(leg.httpx, "post", fake_post)
    return calls


# ── C01 ──────────────────────────────────────────────────────────────────────
def test_C01_missing_url_raises(monkeypatch):
    monkeypatch.setattr(leg, "LEG_RUNTIME_URL", "")
    with pytest.raises(LegRuntimeError):
        fetch_source_texts(["a"])


def test_C02_exact_post_path(monkeypatch):
    calls = install_post(monkeypatch, FakeResp(200, {"ok": 1}))
    fetch_source_texts(["a"])
    assert calls["url"] == "http://leg.test/rtm/source-texts"


def test_C03_exact_payload(monkeypatch):
    calls = install_post(monkeypatch, FakeResp(200, {"ok": 1}))
    fetch_source_texts(["a", "b"])
    assert calls["json"] == {"atom_ids": ["a", "b"]}


def test_C04_http_200_json_pass(monkeypatch):
    payload = {"version": 1, "source_mode": "LIVE_LEG_SOURCE", "items": [], "unresolved": []}
    install_post(monkeypatch, FakeResp(200, payload))
    assert fetch_source_texts(["a"]) == payload


def test_C05_network_exception(monkeypatch):
    install_post(monkeypatch, exc=RuntimeError("conn reset"))
    with pytest.raises(LegRuntimeError):
        fetch_source_texts(["a"])


def test_C06_non200_raises_without_body_leak(monkeypatch):
    install_post(monkeypatch, FakeResp(500, text="SECRET-REPO-DETAIL-leak"))
    with pytest.raises(LegRuntimeError) as ei:
        fetch_source_texts(["a"])
    assert "SECRET-REPO-DETAIL-leak" not in str(ei.value)
    assert "500" in str(ei.value)


def test_C07_invalid_json(monkeypatch):
    install_post(monkeypatch, FakeResp(200, raise_json=True))
    with pytest.raises(LegRuntimeError):
        fetch_source_texts(["a"])


def test_C08_retry_zero(monkeypatch):
    calls = install_post(monkeypatch, FakeResp(500))
    with pytest.raises(LegRuntimeError):
        fetch_source_texts(["a"])
    assert calls["n"] == 1  # retry 0


def _leg_code_only():
    """모듈 docstring 과 # 주석을 걷어낸 실행부. 금지어를 '적었다'는 이유로 위반되지 않게 한다."""
    src = inspect.getsource(leg)
    i = src.find('"""')
    j = src.find('"""', i + 3)
    body = src[j + 3:] if (i != -1 and j != -1) else src
    return "\n".join(l for l in body.splitlines() if not l.lstrip().startswith("#"))


def test_C09_no_direct_db_access():
    body = _leg_code_only()
    for banned in ["DATABASE_URL", "psycopg", "supabase", "SUPABASE_DB_URL", ".table("]:
        assert banned not in body, "LEG client must not touch DB directly: %s" % banned


# ─────────────────────────────────────────────────────────────────────────────
# source-service fixtures
# ─────────────────────────────────────────────────────────────────────────────
def ob(source_index, atom_id=None, source_atom_ids=None):
    return {"identity": {
        "source_index": source_index,
        "atom_id": atom_id,
        "source_atom_ids": list(source_atom_ids or []),
    }}


def materials(obligations):
    return {"normalized_obligations": obligations}


def leg_item(atom_id, *, status="EXACT", text="원문.", sha="deadbeef",
             scid="sc-1", spid="sp-1", law="법", art="1"):
    return {
        "atom_id": atom_id, "semantic_clause_id": scid, "source_part_id": spid,
        "law_name": law, "law_article": art, "text": text, "source_sha256": sha,
        "resolution_status": status,
    }


def leg_resp(items=None, unresolved=None):
    return {
        "version": 1, "source_mode": "LIVE_LEG_SOURCE",
        "items": list(items or []), "unresolved": list(unresolved or []),
    }


def recording_loader(resp):
    calls = {"n": 0, "atom_ids": None}

    def _loader(atom_ids):
        calls["n"] += 1
        calls["atom_ids"] = list(atom_ids)
        return resp

    return _loader, calls


# ── S01 ──────────────────────────────────────────────────────────────────────
def test_S01_empty_obligations_no_http():
    loader, calls = recording_loader(leg_resp())
    out = build_paid_result_source_text_v1(materials([]), loader=loader)
    assert calls["n"] == 0
    assert out == {"version": 1, "source_mode": "LIVE_LEG_SOURCE", "items": [], "unresolved": []}


def test_S02_primary_identity_atom_id():
    loader, calls = recording_loader(leg_resp(items=[leg_item("atom-1")]))
    out = build_paid_result_source_text_v1(materials([ob(0, atom_id="atom-1")]), loader=loader)
    assert calls["atom_ids"] == ["atom-1"]
    assert len(out["items"]) == 1
    it = out["items"][0]
    assert it["atom_id"] == "atom-1" and it["resolution_status"] == "EXACT"
    assert it["obligation_ref"] == 0


def test_S03_source_atom_ids_exact1_fallback():
    loader, calls = recording_loader(leg_resp(items=[leg_item("x")]))
    out = build_paid_result_source_text_v1(
        materials([ob(0, atom_id=None, source_atom_ids=["x"])]), loader=loader)
    assert calls["atom_ids"] == ["x"]
    assert out["items"][0]["atom_id"] == "x"


def test_S04_source_atom_ids_ambiguous_unresolved():
    loader, calls = recording_loader(leg_resp())
    out = build_paid_result_source_text_v1(
        materials([ob(0, atom_id=None, source_atom_ids=["x", "y"])]), loader=loader)
    assert calls["n"] == 0  # no resolvable atom
    assert out["items"] == []
    assert out["unresolved"][0]["reason"] == "ATOM_ID_AMBIGUOUS"
    assert out["unresolved"][0]["obligation_ref"] == 0


def test_S04b_source_atom_ids_missing_unresolved():
    loader, calls = recording_loader(leg_resp())
    out = build_paid_result_source_text_v1(
        materials([ob(0, atom_id=None, source_atom_ids=[])]), loader=loader)
    assert calls["n"] == 0
    assert out["unresolved"][0]["reason"] == "ATOM_ID_MISSING"


def test_S05_unique_batch_loader_exactly_once():
    loader, calls = recording_loader(leg_resp(items=[leg_item("a"), leg_item("b")]))
    build_paid_result_source_text_v1(
        materials([ob(0, atom_id="a"), ob(1, atom_id="b")]), loader=loader)
    assert calls["n"] == 1
    assert calls["atom_ids"] == ["a", "b"]


def test_S06_duplicate_query_atom_dedup():
    loader, calls = recording_loader(leg_resp(items=[leg_item("a")]))
    out = build_paid_result_source_text_v1(
        materials([ob(0, atom_id="a"), ob(1, atom_id="a")]), loader=loader)
    assert calls["atom_ids"] == ["a"]          # HTTP query dedup
    assert len(out["items"]) == 2              # obligation rows NOT collapsed
    assert [i["obligation_ref"] for i in out["items"]] == [0, 1]


def test_S07_output_count_and_order_preserved():
    loader, _ = recording_loader(leg_resp(items=[leg_item("a"), leg_item("c")]))
    obs = [ob(0, atom_id="a"), ob(1, atom_id=None, source_atom_ids=[]), ob(2, atom_id="c")]
    out = build_paid_result_source_text_v1(materials(obs), loader=loader)
    total = len(out["items"]) + len(out["unresolved"])
    assert total == 3
    assert [i["obligation_ref"] for i in out["items"]] == [0, 2]
    assert [u["obligation_ref"] for u in out["unresolved"]] == [1]


def test_S08_endpoint_unresolved_mapping():
    loader, _ = recording_loader(leg_resp(
        unresolved=[{"atom_id": "a", "resolution_status": "UNRESOLVED", "reason": "ATOM_NOT_FOUND"}]))
    out = build_paid_result_source_text_v1(materials([ob(0, atom_id="a")]), loader=loader)
    assert out["items"] == []
    assert out["unresolved"][0]["reason"] == "ATOM_NOT_FOUND"
    assert out["unresolved"][0]["obligation_ref"] == 0


def test_S09_source_mismatch_text_sha_null():
    loader, _ = recording_loader(leg_resp(
        items=[leg_item("a", status="SOURCE_MISMATCH", text="원문.", sha="abc")]))
    out = build_paid_result_source_text_v1(materials([ob(0, atom_id="a")]), loader=loader)
    it = out["items"][0]
    assert it["resolution_status"] == "SOURCE_MISMATCH"
    assert it["text"] is None and it["source_sha256"] is None
    assert it["source_part_id"] == "sp-1"  # provenance 유지


def test_S10_missing_resolver_row_unresolved():
    loader, _ = recording_loader(leg_resp())  # atom 'a' 요청했지만 응답에 없음
    out = build_paid_result_source_text_v1(materials([ob(0, atom_id="a")]), loader=loader)
    assert out["items"] == []
    assert out["unresolved"][0]["reason"] == "RESOLVER_RESULT_MISSING"


def test_S11_malformed_response_fail_closed():
    for bad in [None, [], {"version": 2, "source_mode": "LIVE_LEG_SOURCE", "items": [], "unresolved": []},
                {"version": 1, "source_mode": "X", "items": [], "unresolved": []},
                {"version": 1, "source_mode": "LIVE_LEG_SOURCE", "items": None, "unresolved": []},
                {"version": 1, "source_mode": "LIVE_LEG_SOURCE", "items": [], "unresolved": None}]:
        loader = lambda a, _b=bad: _b
        with pytest.raises(PaidResultSourceTextError):
            build_paid_result_source_text_v1(materials([ob(0, atom_id="a")]), loader=loader)


def test_S12_materials_not_mutated():
    m = materials([ob(0, atom_id="a"), ob(1, atom_id=None, source_atom_ids=["x", "y"])])
    before = copy.deepcopy(m)
    loader, _ = recording_loader(leg_resp(items=[leg_item("a")]))
    build_paid_result_source_text_v1(m, loader=loader)
    assert m == before


def test_S13_normalized_obligation_not_mutated():
    o = ob(0, atom_id="a", source_atom_ids=["a"])
    before = copy.deepcopy(o)
    loader, _ = recording_loader(leg_resp(items=[leg_item("a")]))
    out = build_paid_result_source_text_v1(materials([o]), loader=loader)
    assert o == before
    # 출력 source_atom_ids 는 별도 리스트(입력 aliasing 아님)
    out["items"][0]["source_atom_ids"].append("MUT")
    assert o["identity"]["source_atom_ids"] == ["a"]


def test_S14_source_index_to_obligation_ref_exact():
    loader, _ = recording_loader(leg_resp(items=[leg_item("a")]))
    out = build_paid_result_source_text_v1(materials([ob(7, atom_id="a")]), loader=loader)
    assert out["items"][0]["obligation_ref"] == 7


def test_S15_same_source_part_two_atoms_two_items():
    loader, _ = recording_loader(leg_resp(items=[
        leg_item("a", spid="SAME", sha="H"), leg_item("b", spid="SAME", sha="H")]))
    out = build_paid_result_source_text_v1(
        materials([ob(0, atom_id="a"), ob(1, atom_id="b")]), loader=loader)
    assert len(out["items"]) == 2
    assert out["items"][0]["source_part_id"] == out["items"][1]["source_part_id"] == "SAME"


def test_S16_article375_pair_no_grouping():
    A = "29800eea-2fc1-58c2-9598-1fd46297c409"
    B = "50f40032-855f-52eb-ae90-ebf8a319582a"
    SP = "e9164e6b-b962-4364-bd89-d6a091a6a798"
    SHA = "60e24bed009a11eca141db05dfc8bfa4ddbeadbf58fdfe07783f24de4732375f"
    loader, calls = recording_loader(leg_resp(items=[
        leg_item(A, spid=SP, sha=SHA, text="유도.", art="375"),
        leg_item(B, spid=SP, sha=SHA, text="유도.", art="375")]))
    out = build_paid_result_source_text_v1(
        materials([ob(0, atom_id=A), ob(1, atom_id=B)]), loader=loader)
    assert len(out["items"]) == 2                       # GROUPING = 0
    a, b = out["items"]
    assert a["source_part_id"] == b["source_part_id"] == SP
    assert a["source_sha256"] == b["source_sha256"] == SHA
    assert (a["obligation_ref"], b["obligation_ref"]) == (0, 1)
