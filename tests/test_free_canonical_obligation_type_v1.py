"""WO-FREE-OBLIGATION-TYPE-FIRST-UX-001 REV-1 STEP 1 — backend B1~B8.

canonical_obligation_type = enrichment.obligation_type EXACT (additive).
기존 obligation_type collapse(PROHIBIT/TRAINING→ACTION) 무변경.
"""
from __future__ import annotations

import copy

import pytest

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
ALLOWED = set(FREE_KEYS) | {"presentation", "canonical_obligation_type"}
COLLAPSED_KEEP = {
    "INSPECT": "INSPECT",
    "APPOINT": "APPOINT",
    "REPORT": "REPORT",
    "NOTIFY": "NOTIFY",
    "ACTION": "ACTION",
}


def _raw(*, ob_type="INSPECT", atom="a0", what="점검해야 한다", law="산업안전보건법"):
    o = {
        "atom_id": atom,
        "law_name": law,
        "law_article": "38",
        "applicability": "APPLICABLE",
        "obligation_detail": {"what": what},
        "enrichment": {},
    }
    if ob_type is not None:
        o["enrichment"]["obligation_type"] = ob_type
    return o


def test_B1_prohibit_canonical_exact_and_collapsed_action_preserved():
    o = _raw(ob_type="PROHIBIT", what="해서는 아니 된다")
    before = copy.deepcopy(o)
    row = rw._leg_rule_row(o)
    assert o == before
    assert row["canonical_obligation_type"] == "PROHIBIT"
    assert row["obligation_type"] == "ACTION"
    assert row["canonical_obligation_type"] != row["obligation_type"]


def test_B2_training_canonical_exact_collapsed_unchanged():
    o = _raw(ob_type="TRAINING", what="교육을 실시하여야 한다")
    row = rw._leg_rule_row(o)
    assert row["canonical_obligation_type"] == "TRAINING"
    assert row["obligation_type"] == "ACTION"


@pytest.mark.parametrize("ob_type", ["INSPECT", "APPOINT", "REPORT", "NOTIFY", "ACTION"])
def test_B3_passthrough_types_canonical_exact(ob_type):
    row = rw._leg_rule_row(_raw(ob_type=ob_type))
    assert row["canonical_obligation_type"] == ob_type
    assert row["obligation_type"] == COLLAPSED_KEEP[ob_type]


def test_B4_absent_enrichment_type_does_not_create_canonical_key():
    o = _raw(ob_type=None)
    assert "obligation_type" not in o["enrichment"]
    row = rw._leg_rule_row(o)
    assert "canonical_obligation_type" not in row
    assert row["obligation_type"] == "ACTION"  # collapse default 유지


def test_B5_free_obligations_additive_only_via_get_diagnosis_result_web(monkeypatch):
    rec = stored_rec(
        [
            _raw(ob_type="PROHIBIT", atom="a0", what="금지", law="법0"),
            _raw(ob_type="INSPECT", atom="a1", what="점검", law="법1"),
        ],
        tier="BUILDING_FREE",
    )
    install(monkeypatch, rec)
    data = rw.get_diagnosis_result_web("tok-1")["data"]
    fo = data["free_obligations"]
    raws = rec["full_result"]["obligations_raw"]
    assert len(fo) == 2
    assert set(fo[0].keys()) <= ALLOWED
    assert set(FREE_KEYS) <= set(fo[0].keys())
    assert fo[0]["canonical_obligation_type"] == "PROHIBIT"
    assert fo[0]["obligation_type"] == "ACTION"
    assert fo[0]["obligation_summary"] == "금지"
    assert fo[0]["law_name"] == "법0"
    assert fo[0]["presentation"] == map_diagnosis_presentation(raws[0])
    assert fo[1]["canonical_obligation_type"] == "INSPECT"
    assert fo[1]["obligation_type"] == "INSPECT"
    assert fo[1]["presentation"] == map_diagnosis_presentation(raws[1])
    assert "content_type" not in fo[0]
    assert "content_type" not in fo[1]


def test_B6_presentation_parity_unchanged():
    o = _raw(ob_type="PROHIBIT", what="해서는 아니 된다")
    row = rw._leg_rule_row(o)
    assert row["presentation"] == map_diagnosis_presentation(o)


def test_B7_paid_materializer_not_called_on_free_and_premium_delta_zero(monkeypatch):
    rec = stored_rec([leg_obligation("a0", "점검")], tier="BUILDING_FREE")
    _, calls = install(monkeypatch, rec, product_items=[source_item(0, "a0", "원문A")])
    data = rw.get_diagnosis_result_web("tok-1")["data"]
    assert calls["n"] == 0
    assert "premium_result_v1" not in data

    raw = _raw_full()
    before = copy.deepcopy(raw)
    mats = build_paid_result_materials_v1(raw)
    assert raw == before
    for i, raw_ob in enumerate(raw["obligations_raw"]):
        assert mats["normalized_obligations"][i]["presentation"] == \
            map_diagnosis_presentation(raw_ob)
        ident = mats["normalized_obligations"][i]
        assert "canonical_obligation_type" not in ident


def test_B8_input_mutation_zero():
    o = _raw(ob_type="PROHIBIT")
    before = copy.deepcopy(o)
    rw._leg_rule_row(o)
    rw._leg_rules_from_obligations_raw([o])
    assert o == before
