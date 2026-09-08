"""WO-SAAS-OBLIGATION-IDENTITY-BRIDGE-001 STEP 4B-1 — bridge service 단위테스트.

B1 atom_id EXACT · B2 atom absent→identity 0 · B3 source_atom_ids만→합성 0 ·
B4 map_operation_presentation parity · B5 input mutation 0.
(B6 legacy writer delta / B7~B9 GET projection / B10 diagnosis delta = route/DB 레벨, Cursor projection diff와 함께.)
DB/network 불필요.
"""
from __future__ import annotations

import copy

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
