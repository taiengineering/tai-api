"""WO-PAID-OBLIGATION-PRESENTATION-V1-001 — backend B1~B10.

materializer: map_diagnosis_presentation(raw) @ source_index 1:1
public projection: materials.obligations[].presentation ADDITIVE
"""
from __future__ import annotations

import copy

import routers.diagnosis_result_web as rw
from services.obligation_presentation_mapper import map_diagnosis_presentation
from services.paid_result_materializer import build_paid_result_materials_v1
from services.paid_result_public_projection_svc import build_public_premium_result_v1
from tests.test_paid_result_delivery_wiring_v1 import (
    install,
    leg_obligation,
    source_item,
    stored_rec,
)
from tests.test_paid_result_public_projection_v1 import _sample_product


def _raw_full(*, what="점검해야 한다", who="사업주", how="서면", when="즉시",
              cycle="ANNUAL", condition="굴착 시", recipient="관할관청",
              where="현장"):
    return {
        "sector": "BUILDING",
        "obligations_raw": [
            {
                "atom_id": "a0",
                "law_name": "산업안전보건법",
                "law_article": "38",
                "evidence": "근거문",
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
            },
            {
                "atom_id": "a1",
                "law_name": "건축법",
                "law_article": "41",
                "obligation_detail": {"what": "게시하여야 한다", "who": "공사시공자"},
                "enrichment": {"obligation_type": "NOTIFY"},
            },
        ],
    }


def test_B1_what_to_presentation_action_exact():
    mats = build_paid_result_materials_v1(_raw_full(what="경보설비 설치"))
    assert mats["normalized_obligations"][0]["presentation"]["action"] == "경보설비 설치"
    assert mats["normalized_obligations"][1]["presentation"]["action"] == "게시하여야 한다"


def test_B2_who_to_actor_exact():
    mats = build_paid_result_materials_v1(_raw_full(who="관리감독자"))
    assert mats["normalized_obligations"][0]["presentation"]["actor"] == "관리감독자"


def test_B3_how_present_exact():
    mats = build_paid_result_materials_v1(_raw_full(how="서면통지"))
    assert mats["normalized_obligations"][0]["presentation"]["how"] == "서면통지"


def test_B4_absent_how_key_not_created():
    mats = build_paid_result_materials_v1(_raw_full())
    # second obligation has no how in obligation_detail
    assert "how" not in mats["normalized_obligations"][1]["presentation"]


def test_B5_timing_cycle_condition_exact():
    mats = build_paid_result_materials_v1(
        _raw_full(when="작업 전", cycle="MONTHLY", condition="굴착작업 시")
    )
    p = mats["normalized_obligations"][0]["presentation"]
    assert p["timing"] == "작업 전"
    assert p["cycle"] == "MONTHLY"
    assert p["condition"] == "굴착작업 시"


def test_B6_source_index_ref_one_to_one():
    mats = build_paid_result_materials_v1(_raw_full())
    for i, ob in enumerate(mats["normalized_obligations"]):
        assert ob["identity"]["source_index"] == i
    product = {
        "contract_version": 1,
        "diagnosis": {},
        "diagnosis_profile": {},
        "paid_result_materials_v1": mats,
        "paid_result_evidence_v1": {"articles": []},
        "paid_result_source_text_v1": {"items": [], "unresolved": []},
    }
    pub = build_public_premium_result_v1(product)
    refs = [o["ref"] for o in pub["materials"]["obligations"]]
    assert refs == [0, 1]
    for i, o in enumerate(pub["materials"]["obligations"]):
        assert o["presentation"] == mats["normalized_obligations"][i]["presentation"]


def test_B7_fuzzy_join_zero_identity_is_enumerate_only():
    """law/article 이 같아도 source_index 는 enumerate 순서 그대로다."""
    raw = _raw_full()
    raw["obligations_raw"].append(copy.deepcopy(raw["obligations_raw"][0]))
    raw["obligations_raw"][2]["atom_id"] = "a2"
    mats = build_paid_result_materials_v1(raw)
    idxs = [o["identity"]["source_index"] for o in mats["normalized_obligations"]]
    assert idxs == [0, 1, 2]
    # presentation comes from the same raw element — not from law+article match
    assert mats["normalized_obligations"][0]["presentation"]["action"] == \
        mats["normalized_obligations"][2]["presentation"]["action"]
    assert mats["normalized_obligations"][0]["presentation"] is not \
        mats["normalized_obligations"][2]["presentation"]


def test_B8_input_mutation_zero():
    raw = _raw_full()
    before = copy.deepcopy(raw)
    build_paid_result_materials_v1(raw)
    assert raw == before


def test_B9_existing_premium_obligation_fields_delta_zero():
    """기존 public obligation 키 집합은 presentation 1키 ADDITIVE 만."""
    product = _sample_product()
    # inject presentation like materializer would
    product["paid_result_materials_v1"]["normalized_obligations"][0]["presentation"] = {
        "action": "점검을 해야 한다",
        "actor": "사업주",
    }
    ob = build_public_premium_result_v1(product)["materials"]["obligations"][0]
    assert set(ob) == {
        "ref", "legal", "classification", "duty", "applicability",
        "verification", "timing", "decision_input_count", "presentation",
    }
    assert set(ob["duty"]) == {"who", "recipient", "where", "how"}
    assert "what" not in ob["duty"]
    assert ob["presentation"]["action"] == "점검을 해야 한다"


def test_B10_free_route_premium_materializer_zero(monkeypatch):
    rec = stored_rec([leg_obligation("a0", "점검")], tier="BUILDING_FREE")
    _, calls = install(monkeypatch, rec, product_items=[source_item(0, "a0", "원문A")])
    data = rw.get_paid_result_web("tok-1")["data"]
    assert "premium_result_v1" not in data
    assert calls["n"] == 0
    free = data.get("free_obligations") or []
    assert free
    # STEP 3: free_obligations.presentation 은 _leg_rule_row mapper (materializer 0).
    assert free[0]["presentation"] == map_diagnosis_presentation(
        rec["full_result"]["obligations_raw"][0]
    )


def test_mapper_parity_with_materializer_presentation():
    raw = _raw_full()
    mats = build_paid_result_materials_v1(raw)
    for i, raw_ob in enumerate(raw["obligations_raw"]):
        assert mats["normalized_obligations"][i]["presentation"] == \
            map_diagnosis_presentation(raw_ob)
