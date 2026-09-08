"""WO-FREE-OBLIGATION-PRESENTATION-V1-001 STEP 3 — backend B1~B10.

_leg_rule_row / rules_table: presentation = map_diagnosis_presentation(raw) additive.
free_obligations 3키 값 불변 · presentation pass-through · rules_out 5건 · paid materializer δ0.
"""
from __future__ import annotations

import copy

import routers.diagnosis_result_web as rw
from services.obligation_presentation_mapper import map_diagnosis_presentation
from services.paid_result_materializer import build_paid_result_materials_v1
from tests.test_paid_obligation_presentation_v1 import _raw_full
from tests.test_paid_result_delivery_wiring_v1 import (
    install,
    leg_obligation,
    source_item,
    stored_rec,
)


FREE_KEYS = ("obligation_type", "obligation_summary", "law_name")


def _raw_ob(*, what="점검해야 한다", who="사업주", when="즉시",
            cycle="ANNUAL", condition="굴착 시", recipient="관할관청",
            where="현장", how="서면", evidence="근거문",
            law="산업안전보건법", article="38", atom="a0"):
    return {
        "atom_id": atom,
        "law_name": law,
        "law_article": article,
        "evidence": evidence,
        "applicability": "APPLICABLE",
        "check_result": "VERIFIED",
        "triggered_by": ["has_excavation"],
        "obligation_detail": {
            "what": what,
            "who": who,
            "when": when,
            "how": how,
            "condition": condition,
            "recipient": recipient,
            "where": where,
        },
        "enrichment": {
            "obligation_type": "INSPECT",
            "content_type": "OBLIGATION",
            "inspection_cycle": cycle,
        },
    }


def test_B1_what_to_presentation_action_exact_on_leg_rule_row():
    o = _raw_ob(what="경보설비 설치")
    row = rw._leg_rule_row(o)
    assert row["presentation"]["action"] == "경보설비 설치"
    assert row["presentation"]["action"] == o["obligation_detail"]["what"]
    assert row["presentation"] == map_diagnosis_presentation(o)
    rows = rw._leg_rules_from_obligations_raw([o])
    assert rows[0]["presentation"]["action"] == "경보설비 설치"


def test_B2_who_to_actor_exact():
    o = _raw_ob(who="관리감독자")
    assert rw._leg_rule_row(o)["presentation"]["actor"] == "관리감독자"


def test_B3_when_cycle_condition_exact():
    o = _raw_ob(when="작업 전", cycle="MONTHLY", condition="굴착작업 시")
    p = rw._leg_rule_row(o)["presentation"]
    assert p["timing"] == "작업 전"
    assert p["cycle"] == "MONTHLY"
    assert p["condition"] == "굴착작업 시"


def test_B4_where_how_recipient_preserved():
    o = _raw_ob(where="옥상", how="서면통지", recipient="소방서")
    p = rw._leg_rule_row(o)["presentation"]
    assert p["where"] == "옥상"
    assert p["how"] == "서면통지"
    assert p["recipient"] == "소방서"


def test_B5_absent_source_key_not_created_in_presentation():
    o = {
        "atom_id": "a1",
        "law_name": "건축법",
        "law_article": "41",
        "applicability": "APPLICABLE",
        "obligation_detail": {"what": "게시하여야 한다", "who": "공사시공자"},
        "enrichment": {"obligation_type": "NOTIFY"},
    }
    p = rw._leg_rule_row(o)["presentation"]
    for k in ("how", "timing", "cycle", "condition", "where", "recipient",
              "reason", "evidence", "status"):
        assert k not in p
    assert "action" in p
    assert "actor" in p


def test_B6_source_index_one_to_one():
    raw = [_raw_ob(atom="a0", what="A"), _raw_ob(atom="a1", what="B", law="건축법")]
    rows = rw._leg_rules_from_obligations_raw(raw)
    assert [r[rw._INTERNAL_SOURCE_INDEX] for r in rows] == [0, 1]
    for i, r in enumerate(rows):
        assert r["presentation"] == map_diagnosis_presentation(raw[i])
        assert r["presentation"]["action"] == raw[i]["obligation_detail"]["what"]


def test_B7_fuzzy_join_zero_same_law_article_keeps_own_action():
    a = _raw_ob(atom="a0", what="첫번째 의무")
    b = copy.deepcopy(a)
    b["atom_id"] = "a1"
    b["obligation_detail"]["what"] = "두번째 의무"
    rows = rw._leg_rules_from_obligations_raw([a, b])
    assert rows[0]["presentation"]["action"] == "첫번째 의무"
    assert rows[1]["presentation"]["action"] == "두번째 의무"
    assert rows[0]["presentation"] is not rows[1]["presentation"]


def test_B8_input_mutation_zero():
    o = _raw_ob()
    before = copy.deepcopy(o)
    rw._leg_rule_row(o)
    rw._leg_rules_from_obligations_raw([o])
    assert o == before


def test_B9_free_response_field_delta_zero_presentation_additive_only(monkeypatch):
    rec = stored_rec(
        [_raw_ob(atom=f"a{i}", what=f"의무{i}", law=f"법{i % 3}") for i in range(8)],
        tier="BUILDING_FREE",
    )
    install(monkeypatch, rec)
    data = rw.get_diagnosis_result_web("tok-1")["data"]

    rules_out = data["rules_table"]
    assert len(rules_out) == 5
    for r in rules_out:
        assert "presentation" in r
        assert r["presentation"] == map_diagnosis_presentation(
            next(o for o in rec["full_result"]["obligations_raw"]
                 if o["atom_id"] == r["atom_id"])
        )

    fo = data["free_obligations"]
    raws = rec["full_result"]["obligations_raw"]
    assert len(fo) == 8
    assert data["free_obligation_count"] == 8
    for i, item in enumerate(fo):
        assert set(FREE_KEYS) <= set(item.keys())
        assert set(item.keys()) <= set(FREE_KEYS) | {"presentation"}
        assert item["presentation"] == map_diagnosis_presentation(raws[i])
        if i < 5:
            src_row = rules_out[i]
            assert item["obligation_type"] == src_row["obligation_type"]
            assert item["obligation_summary"] == src_row["obligation_summary"]
            assert item["law_name"] == src_row["law_name"]
            assert item["presentation"] == src_row["presentation"]
        assert "atom_id" not in item
        assert "law_article" not in item
        assert "executor_type_label" not in item

    assert "summary" in data
    assert "law_badges" in data
    assert "total" in data["summary"]


def test_B10_paid_materializer_delta_zero_and_diagnosis_result_regression(monkeypatch):
    raw = _raw_full()
    before = copy.deepcopy(raw)
    mats = build_paid_result_materials_v1(raw)
    assert raw == before
    for i, raw_ob in enumerate(raw["obligations_raw"]):
        assert mats["normalized_obligations"][i]["presentation"] == \
            map_diagnosis_presentation(raw_ob)

    rec = stored_rec([leg_obligation("a0", "점검")], tier="BUILDING_V2")
    _, calls = install(monkeypatch, rec, product_items=[source_item(0, "a0", "원문A")])
    paid = rw.get_paid_result_web("tok-1")["data"]
    assert calls["n"] == 1
    assert "premium_result_v1" in paid

    rec_free = stored_rec([leg_obligation("a0", "점검")], tier="BUILDING_FREE")
    _, calls_free = install(monkeypatch, rec_free, product_items=[source_item(0, "a0", "원문A")])
    free_paid_route = rw.get_paid_result_web("tok-1")["data"]
    assert calls_free["n"] == 0
    assert "premium_result_v1" not in free_paid_route
    free_preview = rw.get_diagnosis_result_web("tok-1")["data"]
    assert len(free_preview["rules_table"]) == 1
    assert "presentation" in free_preview["rules_table"][0]
