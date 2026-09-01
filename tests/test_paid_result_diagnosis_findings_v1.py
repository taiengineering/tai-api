"""tests/test_paid_result_diagnosis_findings_v1.py — D01 DIAGNOSIS FINDINGS v1

PAID-DIAGNOSIS-VALUE-REBUILD-01 · STEP4C-2 PKG-5A

대상: services/paid_result_materializer.py 의 D01 (`diagnosis_findings`)

D01 은 새 사실을 만들지 않는다. 기존 material 을 교차해 읽고 감사 가능한
structured fact 로 고정한다. 따라서 이 테스트의 무게는 "무엇이 나오는가" 보다
"무엇을 만들어내지 않았는가" 와 "기존 정의와 갈라지지 않았는가" 에 있다.

fixture 는 기존 materializer 테스트의 factory 를 그대로 재사용한다 —
같은 상품 안에 fixture 정의가 두 벌 생기지 않게 한다.
"""
import copy
import json

from services.paid_result_materializer import build_paid_result_materials_v1
from tests.test_paid_result_materializer_v1 import _full_result, _obligation


CATALOG = (
    ("F01", "OBLIGATION_LAW_COVERAGE", ("obligation_count", "law_count")),
    ("F02", "LAW_ARTICLE_COVERAGE", ("law_count", "article_count")),
    ("F03", "ACTOR_MAX_OBLIGATION_COUNT",
     ("obligation_count", "max_obligation_count", "actors")),
    ("F04", "LEGAL_ACTOR_DIVERSITY", ("actor_count",)),
    ("F05", "PROHIBITION_OBLIGATION_COUNT", ("prohibition_count",)),
    ("F06", "INSPECTION_OBLIGATION_COUNT", ("inspection_count",)),
    ("F07", "NOTIFICATION_OBLIGATION_COUNT", ("notification_count",)),
    ("F08", "LAW_MAX_OBLIGATION_COUNT", ("obligation_count", "laws")),
    ("F09", "ARTICLE_MAX_OBLIGATION_COUNT", ("obligation_count", "articles")),
    ("F10", "LEGAL_TIMING_COVERAGE", ("timing_obligation_count",)),
    ("F11", "CONDITION_COVERAGE", ("condition_obligation_count",)),
    ("F12", "RECIPIENT_COVERAGE", ("recipient_obligation_count",)),
    ("F13", "TRIGGER_FACT_PROFILE", ("trigger_count", "triggers")),
    ("F14", "OBLIGATION_INFORMATION_GAP_COUNT", ("obligation_gap_count",)),
)

DERIVATION_VOCABULARY = {
    "COUNT_DISTINCT_V1", "COUNT_PRESENT_V1", "COUNT_EXACT_ENUM_V1",
    "GROUP_MAX_PRESERVE_TIES_V1", "DISTINCT_VALUES_V1", "PASS_THROUGH_COUNT_V1",
}


def _d01(full_result):
    return build_paid_result_materials_v1(full_result)["diagnosis_findings"]


def _by_id(d01):
    return {f["finding_id"]: f for f in d01["findings"]}


def _fixture():
    """3의무 · 2법령 · 금지 1 · 수행주체 2종."""
    return _full_result([
        _obligation(atom_id="a1", who="사업주", when="상시",
                    triggered_by=["has_excavation"], condition="굴착하는 경우"),
        _obligation(atom_id="a2", law_name="건축법", law_article="41",
                    obligation_type="NOTIFY", who="공사시공자",
                    recipient="행정청", missing_fields=["when"]),
        _obligation(atom_id="a3", law_article="30", content_type="PROHIBITION",
                    obligation_type="PROHIBIT", who="사업주"),
    ])


# ─────────────────────────────────────────────────────────────────────────────
# 카탈로그 — 항상 14건
# ─────────────────────────────────────────────────────────────────────────────

def test_catalog_is_always_fourteen_in_fixed_order():
    for fixture in (_fixture(), _full_result([])):
        d01 = _d01(fixture)
        assert d01["version"] == 1
        assert [f["finding_id"] for f in d01["findings"]] == [c[0] for c in CATALOG]


def test_finding_type_values_are_exact():
    found = _by_id(_d01(_fixture()))
    for finding_id, finding_type, _keys in CATALOG:
        assert found[finding_id]["finding_type"] == finding_type


def test_facts_keys_are_exact():
    found = _by_id(_d01(_fixture()))
    for finding_id, _type, keys in CATALOG:
        assert set(found[finding_id]["facts"]) == set(keys), finding_id


def test_ineligible_findings_are_kept_not_deleted():
    """eligible=false 라고 record 를 지우지 않는다. D01 은 감사 가능한 사실이다."""
    d01 = _d01(_full_result([]))
    assert len(d01["findings"]) == 14
    ineligible = [f for f in d01["findings"] if not f["eligible"]]
    assert len(ineligible) > 0
    for f in ineligible:
        # 사실은 남아 있어야 한다 — 빈 dict 로 비우지 않는다.
        assert isinstance(f["facts"], dict) and f["facts"] != {}
        assert f["provenance"]["source_materials"]


def test_every_finding_has_eligible_boolean():
    for f in _d01(_fixture())["findings"]:
        assert isinstance(f["eligible"], bool)


# ─────────────────────────────────────────────────────────────────────────────
# eligibility
# ─────────────────────────────────────────────────────────────────────────────

def test_eligibility_on_empty_result():
    found = _by_id(_d01(_full_result([])))
    # F10 · F11 은 언제나 eligible 이다 (0건도 사실이다).
    assert found["F10"]["eligible"] is True
    assert found["F11"]["eligible"] is True
    assert found["F10"]["facts"]["timing_obligation_count"] == 0
    assert found["F11"]["facts"]["condition_obligation_count"] == 0
    for finding_id in ("F01", "F02", "F03", "F04", "F05", "F06",
                       "F07", "F08", "F09", "F12", "F13", "F14"):
        assert found[finding_id]["eligible"] is False, finding_id


def test_eligibility_thresholds():
    found = _by_id(_d01(_fixture()))
    assert found["F01"]["eligible"] is True          # 3 >= 1
    assert found["F02"]["eligible"] is True          # 조문 3 >= 1
    assert found["F03"]["eligible"] is True          # max 2 >= 1
    assert found["F04"]["eligible"] is True          # 수행주체 2 >= 2
    assert found["F05"]["eligible"] is True          # 금지 1 >= 1
    assert found["F06"]["eligible"] is False         # 점검 0
    assert found["F07"]["eligible"] is True          # 신고 1 >= 1
    assert found["F08"]["eligible"] is True          # 법령 2 >= 2
    assert found["F12"]["eligible"] is True          # 상대방 1 >= 1
    assert found["F13"]["eligible"] is True          # trigger 1 >= 1
    assert found["F14"]["eligible"] is True          # gap 1 >= 1


def test_f08_needs_two_distinct_laws():
    """법령이 하나뿐이면 '가장 많은 법령' 은 성립하지 않는다."""
    single_law = _full_result([
        _obligation(atom_id="a1"), _obligation(atom_id="a2", law_article="30"),
    ])
    found = _by_id(_d01(single_law))
    assert found["F08"]["eligible"] is False
    # 그래도 사실은 남는다.
    assert found["F08"]["facts"]["laws"][0]["count"] == 2


def test_f09_needs_max_at_least_two():
    """조문마다 의무가 1건씩이면 '한 조문에 여러 건' 이 아니다."""
    spread = _full_result([
        _obligation(atom_id="a1", law_article="10"),
        _obligation(atom_id="a2", law_article="20"),
    ])
    found = _by_id(_d01(spread))
    assert found["F09"]["facts"]["obligation_count"] == 1
    assert found["F09"]["eligible"] is False


# ─────────────────────────────────────────────────────────────────────────────
# TIE RULE — F03 · F08 · F09
# ─────────────────────────────────────────────────────────────────────────────

def test_f03_unique_max():
    found = _by_id(_d01(_full_result([
        _obligation(atom_id="a1", who="사업주"),
        _obligation(atom_id="a2", who="사업주", law_article="30"),
        _obligation(atom_id="a3", who="공사시공자", law_article="40"),
    ])))
    facts = found["F03"]["facts"]
    assert facts["max_obligation_count"] == 2
    assert facts["actors"] == [{"actor": "사업주", "count": 2}]
    assert found["F03"]["eligible"] is True


def test_f03_tied_max_keeps_every_winner():
    found = _by_id(_d01(_full_result([
        _obligation(atom_id="a1", who="사업주"),
        _obligation(atom_id="a2", who="공사시공자", law_article="30"),
    ])))
    facts = found["F03"]["facts"]
    assert facts["max_obligation_count"] == 1
    # 공동 1위를 둘 다 담는다 — 하나를 고르지 않는다.
    assert facts["actors"] == [
        {"actor": "공사시공자", "count": 1}, {"actor": "사업주", "count": 1},
    ]
    assert found["F03"]["eligible"] is True


def test_f08_unique_max():
    found = _by_id(_d01(_full_result([
        _obligation(atom_id="a1", law_name="산업안전보건기준에 관한 규칙"),
        _obligation(atom_id="a2", law_name="산업안전보건기준에 관한 규칙",
                    law_article="30"),
        _obligation(atom_id="a3", law_name="건축법", law_article="41"),
    ])))
    facts = found["F08"]["facts"]
    assert facts["obligation_count"] == 2
    assert facts["laws"] == [{"law_name": "산업안전보건기준에 관한 규칙", "count": 2}]


def test_f08_tied_max_keeps_every_winner():
    found = _by_id(_d01(_full_result([
        _obligation(atom_id="a1", law_name="건축법"),
        _obligation(atom_id="a2", law_name="산업안전보건법", law_article="30"),
    ])))
    facts = found["F08"]["facts"]
    assert facts["obligation_count"] == 1
    assert [r["law_name"] for r in facts["laws"]] == ["건축법", "산업안전보건법"]
    assert found["F08"]["eligible"] is True


def test_f09_unique_and_tied_max():
    unique = _by_id(_d01(_full_result([
        _obligation(atom_id="a1", law_article="221"),
        _obligation(atom_id="a2", law_article="221"),
        _obligation(atom_id="a3", law_article="30"),
    ])))["F09"]
    assert unique["facts"]["obligation_count"] == 2
    assert len(unique["facts"]["articles"]) == 1
    assert unique["eligible"] is True

    tied = _by_id(_d01(_full_result([
        _obligation(atom_id="a1", law_article="221"),
        _obligation(atom_id="a2", law_article="221"),
        _obligation(atom_id="a3", law_article="30"),
        _obligation(atom_id="a4", law_article="30"),
    ])))["F09"]
    assert tied["facts"]["obligation_count"] == 2
    assert [r["law_article"] for r in tied["facts"]["articles"]] == ["221", "30"]
    assert tied["eligible"] is True


def test_tie_over_limit_keeps_all_facts_but_is_not_eligible():
    """상한 4 는 사실 삭제 규칙이 아니라 eligibility 규칙이다."""
    obligations = [
        _obligation(atom_id="a{}".format(i), who="주체{}".format(i),
                    law_name="법령{}".format(i), law_article=str(10 + i))
        for i in range(5)
    ]
    found = _by_id(_d01(_full_result(obligations)))

    assert len(found["F03"]["facts"]["actors"]) == 5      # truncate 0
    assert found["F03"]["eligible"] is False
    assert len(found["F08"]["facts"]["laws"]) == 5        # truncate 0
    assert found["F08"]["eligible"] is False


def test_tie_order_never_picks_a_winner():
    """입력 순서를 뒤집어도 공동 1위 집합과 개수가 같다."""
    rows = [
        _obligation(atom_id="a1", who="사업주"),
        _obligation(atom_id="a2", who="공사시공자", law_article="30"),
        _obligation(atom_id="a3", who="관리감독자", law_article="40"),
    ]
    forward = _by_id(_d01(_full_result(list(rows))))["F03"]["facts"]["actors"]
    backward = _by_id(_d01(_full_result(list(reversed(rows)))))["F03"]["facts"]["actors"]
    assert forward == backward
    assert len(forward) == 3


# ─────────────────────────────────────────────────────────────────────────────
# CANONICAL REUSE — 같은 개념의 정의가 두 개 생기지 않는다
# ─────────────────────────────────────────────────────────────────────────────

def test_f10_reuses_r10_and_does_not_recount_duty_when():
    """F10 은 legal_timing_profile.with_timing_count 를 그대로 쓴다."""
    out = build_paid_result_materials_v1(_fixture())
    found = _by_id(out["diagnosis_findings"])
    assert (found["F10"]["facts"]["timing_obligation_count"]
            == out["legal_timing_profile"]["with_timing_count"])
    assert found["F10"]["provenance"]["source_materials"] == ["legal_timing_profile"]


def test_f14_counts_obligations_not_missing_field_items():
    """F14 는 gap 이 있는 '의무 수' 다. missing field 항목 총수가 아니다."""
    out = build_paid_result_materials_v1(_full_result([
        _obligation(atom_id="a1", missing_fields=["when", "condition", "recipient"]),
    ]))
    found = _by_id(out["diagnosis_findings"])
    assert found["F14"]["facts"]["obligation_gap_count"] == 1
    assert (found["F14"]["facts"]["obligation_gap_count"]
            == out["information_gaps"]["obligation_information_gaps"]
                  ["obligation_count_with_gaps"])


def test_counts_agree_with_canonical_materials():
    out = build_paid_result_materials_v1(_fixture())
    found = _by_id(out["diagnosis_findings"])
    assert found["F01"]["facts"]["obligation_count"] == out["overview"]["total_obligation_count"]
    assert found["F01"]["facts"]["law_count"] == out["overview"]["distinct_law_count"]
    assert found["F02"]["facts"]["law_count"] == out["overview"]["distinct_law_count"]
    assert (found["F05"]["facts"]["prohibition_count"]
            == out["duty_vs_prohibition"]["PROHIBITION"]["count"])


def test_unspecified_bucket_is_not_counted_as_a_law_or_article():
    """R01 v2 / R02 v2 와 같은 경계를 쓴다. 법령 수가 두 개가 되면 안 된다."""
    out = build_paid_result_materials_v1(_full_result([
        _obligation(atom_id="a1", law_name=None, law_article=None),
        _obligation(atom_id="a2", law_name="건축법", law_article="41"),
    ]))
    found = _by_id(out["diagnosis_findings"])
    assert found["F01"]["facts"]["law_count"] == 1
    assert found["F02"]["facts"]["article_count"] == 1
    assert [r["law_name"] for r in found["F08"]["facts"]["laws"]] == ["건축법"]
    assert all(r["law_name"] != "UNSPECIFIED"
               for r in found["F09"]["facts"]["articles"])


def test_unknown_actor_is_not_a_legal_actor():
    """UNKNOWN 은 수행주체의 이름이 아니라 값이 없다는 뜻이다."""
    found = _by_id(_d01(_full_result([
        _obligation(atom_id="a1", who=None),
        _obligation(atom_id="a2", who="사업주", law_article="30"),
    ])))
    assert found["F04"]["facts"]["actor_count"] == 1
    assert [r["actor"] for r in found["F03"]["facts"]["actors"]] == ["사업주"]


# ─────────────────────────────────────────────────────────────────────────────
# F13 — raw trigger 보존
# ─────────────────────────────────────────────────────────────────────────────

def test_f13_preserves_unknown_triggers_raw():
    """사전에 없는 trigger 도 버리지 않는다. 고객 노출 판단은 presentation 몫이다."""
    found = _by_id(_d01(_full_result([
        _obligation(atom_id="a1", triggered_by=["has_excavation", "has_unmapped_thing"]),
    ])))
    facts = found["F13"]["facts"]
    assert facts["triggers"] == ["has_excavation", "has_unmapped_thing"]
    assert facts["trigger_count"] == 2


# ─────────────────────────────────────────────────────────────────────────────
# provenance
# ─────────────────────────────────────────────────────────────────────────────

def test_provenance_present_and_sorted_for_every_finding():
    for f in _d01(_fixture())["findings"]:
        prov = f["provenance"]
        assert set(prov) == {"source_materials", "source_fields", "derivation_rule"}
        assert prov["source_materials"] == sorted(prov["source_materials"])
        assert prov["source_fields"] == sorted(prov["source_fields"])
        assert prov["source_materials"] and prov["source_fields"]
        assert prov["derivation_rule"] in DERIVATION_VOCABULARY, f["finding_id"]


def test_material_registry_declares_d01():
    meta = build_paid_result_materials_v1(_fixture())["meta"]
    entry = meta["materials"]["diagnosis_findings"]
    assert entry["material_type"] == "DIAGNOSIS_FINDINGS"
    assert entry["derivation_rule"] == "D01_V1"
    assert entry["derivation_version"] == 1
    assert entry["source_fields"]


# ─────────────────────────────────────────────────────────────────────────────
# 만들지 않은 것
# ─────────────────────────────────────────────────────────────────────────────

def test_no_customer_text_anywhere():
    """D01 은 문장을 만들지 않는다."""
    d01 = _d01(_fixture())
    blob = json.dumps(d01, ensure_ascii=False)
    for banned in ("customer_text", "sentence", "summary_text", "message",
                   "label", "description", "headline"):
        assert banned not in blob, banned
    # 조사·연결어가 붙은 한국어 문장이 fact 로 들어오지 않는다.
    for f in d01["findings"]:
        for value in f["facts"].values():
            if isinstance(value, str):
                assert "습니다" not in value and "입니다" not in value


def test_no_score_priority_or_judgement_vocabulary():
    blob = json.dumps(_d01(_fixture()), ensure_ascii=False)
    for banned in ("risk", "score", "priority", "urgency", "grade", "rank",
                   "severity", "위험", "시급", "중요", "우선", "즉시",
                   "due", "deadline", "d_day"):
        assert banned not in blob, banned


# ─────────────────────────────────────────────────────────────────────────────
# 순수성
# ─────────────────────────────────────────────────────────────────────────────

def test_deterministic_across_repeated_runs():
    fixture = _fixture()
    first = json.dumps(_d01(copy.deepcopy(fixture)), ensure_ascii=False, sort_keys=True)
    second = json.dumps(_d01(copy.deepcopy(fixture)), ensure_ascii=False, sort_keys=True)
    assert first == second


def test_input_is_not_mutated():
    fixture = _fixture()
    before = json.dumps(fixture, ensure_ascii=False, sort_keys=True)
    build_paid_result_materials_v1(fixture)
    assert json.dumps(fixture, ensure_ascii=False, sort_keys=True) == before


def test_d01_does_not_change_r01_to_r16():
    """D01 추가가 기존 material 출력을 바꾸지 않는다."""
    out = build_paid_result_materials_v1(_fixture())
    existing = {k: v for k, v in out.items()
                if k not in ("diagnosis_findings", "meta")}
    assert set(existing) == {
        "normalized_obligations", "overview", "law_portfolio", "duty_vs_prohibition",
        "applicability_basis", "legal_basis_bundles", "verification_summary",
        "information_gaps", "legal_actor_map", "recipient_map", "legal_timing_profile",
        "timing_character_summary", "duplicate_groups", "article_bundles",
        "compliance_profile", "coverage_summary", "execution_seed",
    }
    # D01 은 읽기만 한다 — 소비한 material 을 건드리지 않는다.
    assert out["overview"]["total_obligation_count"] == 3
    assert out["legal_timing_profile"]["with_timing_count"] == 1
