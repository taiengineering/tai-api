"""tests/test_paid_result_materializer_v1.py — STEP3A T1~T18 + REV-1 T19~T22.

대상: services/paid_result_materializer.build_paid_result_materials_v1

fixture 는 반드시 "저장된 full_result shape" 기준으로 작성한다
(public.anonymous_diagnosis_results.row.full_result — LEG 저장 계약).
DB 접근 없음. 네트워크 없음. 시간 의존 없음.
"""
import copy
import json

from services.paid_result_materializer import build_paid_result_materials_v1


# ─────────────────────────────────────────────────────────────────────────────
# fixture helpers — 저장된 full_result shape 를 그대로 흉내낸다.
# ─────────────────────────────────────────────────────────────────────────────

def _obligation(
    law_name="산업안전보건기준에 관한 규칙",
    law_article="19",
    evidence="사업주는 ... 하여야 한다.",
    obligation_type="ACTION",
    content_type="OBLIGATION",
    what="안전조치를 한다",
    who="사업주",
    when=None,
    recipient=None,
    where=None,
    how=None,
    condition=None,
    triggered_by=None,
    consumer_status="applicable",
    check_result="VERIFIED",
    usable_for_evaluation=True,
    completeness="COMPLETE",
    missing_fields=None,
    inspection_cycle=None,
    atom_id="atom-1",
    source_atom_ids=None,
    applicability="APPLICABLE",
):
    detail = {}
    for key, value in (
        ("what", what), ("who", who), ("when", when), ("recipient", recipient),
        ("where", where), ("how", how), ("condition", condition),
    ):
        if value is not None:
            detail[key] = value

    enrichment = {
        "usable_for_evaluation": usable_for_evaluation,
        "completeness": completeness,
        "missing_fields": missing_fields if missing_fields is not None else [],
        "needs_numeric_condition": None,
        "consumer_status": consumer_status,
        "content_type": content_type,
        "obligation_type": obligation_type,
        "inspection_cycle": inspection_cycle,
    }

    out = {
        "atom_id": atom_id,
        "source_atom_ids": source_atom_ids if source_atom_ids is not None else [atom_id],
        "mapped_field": ",".join(triggered_by or []),
        "law_name": law_name,
        "law_article": law_article,
        "evidence": evidence,
        "applicability": applicability,
        "triggered_by": triggered_by if triggered_by is not None else [],
        "obligation_detail": detail,
        "enrichment": enrichment,
    }
    if check_result is not None:
        out["check_result"] = check_result
    return out


def _full_result(obligations=None, contract=None, engine_version="leg-runtime-v3"):
    out = {
        "engine_family": "LEG",
        "engine_version": engine_version,
        "rule_source": "leg-prod",
        "fallback_used": False,
        "leg_status": "OK",
        "leg_trace_id": "rtm-000000000000",
        "sector": "MANUFACTURING",
        "applicable_count": len(obligations or []),
        "key_obligations": [],
        "applicable_laws": [],
        "law_badges": [],
        "rules": [],
        "risk_level": None,
        "summary": None,
        "provenance": {
            "release_version": "SEMREPO-RC1-2026.07.20",
            "repository_version": "v1",
            "freeze_signature": "15cd17e871b6885d34214c84a58adf47",
            "rc_snapshot_checksum": "",
            "repository_size": 339,
        },
        "obligations_raw": obligations if obligations is not None else [],
        "facility_used": {"worker_count": 45},
    }
    if contract is not None:
        out["contract"] = contract
    return out


def _contract(active=None, missing=None, unknown=None, invalid=None):
    return {
        "valid": True,
        "active_fields": active if active is not None else [],
        "missing_fields": missing if missing is not None else [],
        "unknown_fields": unknown if unknown is not None else [],
        "invalid_fields": invalid if invalid is not None else [],
        "accepted_count": len(active or []),
    }


def _refs(rows, key="obligation_refs"):
    return [row[key] for row in rows]


# ─────────────────────────────────────────────────────────────────────────────
# T1 — obligations_raw = [] : 전체 구조 정상 / counts zero / exception 0
# ─────────────────────────────────────────────────────────────────────────────

def test_t1_empty_obligations_produces_full_structure():
    out = build_paid_result_materials_v1(_full_result([]))

    expected_keys = {
        "meta", "normalized_obligations", "overview", "law_portfolio",
        "duty_vs_prohibition", "applicability_basis", "legal_basis_bundles",
        "verification_summary", "information_gaps", "legal_actor_map", "recipient_map",
        "legal_timing_profile", "timing_character_summary", "duplicate_groups",
        "article_bundles", "compliance_profile", "coverage_summary", "execution_seed",
    }
    assert set(out) == expected_keys

    assert out["normalized_obligations"] == []
    assert out["overview"]["total_obligation_count"] == 0
    assert out["overview"]["distinct_law_count"] == 0
    assert out["overview"]["obligation_type_counts"] == {}
    assert out["law_portfolio"] == []
    assert out["duty_vs_prohibition"]["OBLIGATION"]["count"] == 0
    assert out["duty_vs_prohibition"]["PROHIBITION"]["count"] == 0
    assert out["duty_vs_prohibition"]["UNKNOWN"]["count"] == 0
    assert out["verification_summary"]["total"] == 0
    assert out["legal_timing_profile"]["with_timing_count"] == 0
    assert out["legal_timing_profile"]["without_timing_count"] == 0
    assert out["duplicate_groups"] == []
    assert out["execution_seed"] == []
    assert out["compliance_profile"]["total_obligations"] == 0
    assert out["coverage_summary"]["obligation_evaluation_coverage"]["total"] == 0


def test_t1b_missing_obligations_raw_key_is_tolerated():
    out = build_paid_result_materials_v1({"engine_version": "leg-runtime-v3"})
    assert out["overview"]["total_obligation_count"] == 0
    out2 = build_paid_result_materials_v1(None)
    assert out2["overview"]["total_obligation_count"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# T2 — OBLIGATION + PROHIBITION + unknown 혼합 : 정확 분류, PROHIBITION→ACTION 0
# ─────────────────────────────────────────────────────────────────────────────

def test_t2_content_type_buckets_are_exact_and_prohibition_is_never_action():
    obligations = [
        _obligation(content_type="OBLIGATION", obligation_type="ACTION", atom_id="a1"),
        _obligation(content_type="PROHIBITION", obligation_type="PROHIBIT",
                    law_article="30", what="사용을 금지한다", atom_id="a2"),
        _obligation(content_type=None, obligation_type=None,
                    law_article="41", what="미상", atom_id="a3"),
    ]
    out = build_paid_result_materials_v1(_full_result(obligations))

    dvp = out["duty_vs_prohibition"]
    assert dvp["OBLIGATION"]["count"] == 1 and dvp["OBLIGATION"]["obligation_refs"] == [0]
    assert dvp["PROHIBITION"]["count"] == 1 and dvp["PROHIBITION"]["obligation_refs"] == [1]
    assert dvp["UNKNOWN"]["count"] == 1 and dvp["UNKNOWN"]["obligation_refs"] == [2]

    # PROHIBIT 가 ACTION 으로 편입되지 않는다.
    types = out["overview"]["obligation_type_counts"]
    assert types == {"ACTION": 1, "PROHIBIT": 1, "UNCLASSIFIED": 1}
    assert out["normalized_obligations"][1]["classification"]["obligation_type"] == "PROHIBIT"
    assert out["normalized_obligations"][1]["classification"]["content_type"] == "PROHIBITION"

    # 각 counts 합계 = total
    total = out["overview"]["total_obligation_count"]
    assert sum(types.values()) == total
    assert sum(out["overview"]["content_type_counts"].values()) == total
    assert sum(out["overview"]["verification_counts"].values()) == total


# ─────────────────────────────────────────────────────────────────────────────
# T3 — 같은 법령 / 다른 조문 : law_portfolio 1건, article_count 정확
# ─────────────────────────────────────────────────────────────────────────────

def test_t3_same_law_different_articles():
    obligations = [
        _obligation(law_article="19", atom_id="a1"),
        _obligation(law_article="38", atom_id="a2"),
        _obligation(law_article="338", atom_id="a3", obligation_type="INSPECT"),
    ]
    out = build_paid_result_materials_v1(_full_result(obligations))

    assert len(out["law_portfolio"]) == 1
    row = out["law_portfolio"][0]
    assert row["law_name"] == "산업안전보건기준에 관한 규칙"
    assert row["obligation_count"] == 3
    assert row["article_count"] == 3
    assert out["overview"]["distinct_law_count"] == 1
    assert len(out["article_bundles"]) == 3


def test_t3b_law_portfolio_sort_is_deterministic():
    obligations = [
        _obligation(law_name="건축법", law_article="41", atom_id="a1"),
        _obligation(law_name="산업안전보건법", law_article="1", atom_id="a2"),
        _obligation(law_name="산업안전보건법", law_article="2", atom_id="a3"),
        _obligation(law_name="가나다법", law_article="9", atom_id="a4"),
    ]
    out = build_paid_result_materials_v1(_full_result(obligations))
    names = [row["law_name"] for row in out["law_portfolio"]]
    # count DESC, 그 다음 law_name ASC
    assert names == ["산업안전보건법", "가나다법", "건축법"]


def test_t3c_missing_law_name_becomes_unspecified_bucket():
    out = build_paid_result_materials_v1(_full_result([
        _obligation(law_name=None, law_article=None, atom_id="a1"),
    ]))
    assert out["law_portfolio"][0]["law_name"] == "UNSPECIFIED"
    assert out["article_bundles"][0]["law_article"] == "UNSPECIFIED"
    assert out["normalized_obligations"][0]["legal"]["law_name"] is None
    assert out["normalized_obligations"][0]["availability"]["legal.law_name"] == "NULL"


# ─────────────────────────────────────────────────────────────────────────────
# T4 — 같은 law+article 여러 의무 : article bundle 생성, 의무 독립성 유지
# ─────────────────────────────────────────────────────────────────────────────

def test_t4_article_bundle_keeps_obligations_independent():
    obligations = [
        _obligation(law_article="221", what="인양작업 조치", atom_id="a1"),
        _obligation(law_article="221", what="작업장치 교환 조치", atom_id="a2"),
        _obligation(law_article="339", what="굴착 조치", atom_id="a3"),
    ]
    out = build_paid_result_materials_v1(_full_result(obligations))

    bundles = {(b["law_article"]): b for b in out["article_bundles"]}
    assert bundles["221"]["count"] == 2
    assert bundles["221"]["obligation_refs"] == [0, 1]
    assert bundles["339"]["count"] == 1

    # 의무는 합쳐지지 않는다 — normalized 는 여전히 3건, what 도 각각 보존.
    assert len(out["normalized_obligations"]) == 3
    whats = [o["duty"]["what"] for o in out["normalized_obligations"]]
    assert whats == ["인양작업 조치", "작업장치 교환 조치", "굴착 조치"]

    # R05 근거 묶음도 조문 단위이며 관련 의무를 연결만 한다.
    bundle_221 = [b for b in out["legal_basis_bundles"] if b["law_article"] == "221"][0]
    assert bundle_221["related_obligation_refs"] == [0, 1]


def test_t4b_legal_basis_bundle_evidence_is_exact_distinct():
    obligations = [
        _obligation(law_article="221", evidence="같은 조문 원문", atom_id="a1"),
        _obligation(law_article="221", evidence="같은 조문 원문", what="다른 행위", atom_id="a2"),
        _obligation(law_article="221", evidence="다른 조문 원문", what="또 다른 행위", atom_id="a3"),
    ]
    out = build_paid_result_materials_v1(_full_result(obligations))
    bundle = [b for b in out["legal_basis_bundles"] if b["law_article"] == "221"][0]
    assert bundle["evidence"] == ["같은 조문 원문", "다른 조문 원문"]
    assert bundle["related_obligation_refs"] == [0, 1, 2]


# ─────────────────────────────────────────────────────────────────────────────
# T5 — 완전 동일 obligation 2개 : duplicate group 1, raw/normalized 2건 유지
# ─────────────────────────────────────────────────────────────────────────────

def test_t5_exact_duplicate_group_preserves_raw():
    dup = _obligation(atom_id="a1")
    obligations = [copy.deepcopy(dup), copy.deepcopy(dup)]
    raw = _full_result(obligations)
    out = build_paid_result_materials_v1(raw)

    assert len(out["duplicate_groups"]) == 1
    group = out["duplicate_groups"][0]
    assert group["count"] == 2
    assert group["obligation_refs"] == [0, 1]

    # 원본과 normalized 모두 2건 유지 — 삭제하지 않는다.
    assert len(raw["obligations_raw"]) == 2
    assert len(out["normalized_obligations"]) == 2
    assert out["overview"]["total_obligation_count"] == 2


def test_t5b_whitespace_only_difference_is_still_exact_duplicate():
    a = _obligation(what="안전조치를 한다", atom_id="a1")
    b = _obligation(what="  안전조치를   한다  ", atom_id="a2")
    out = build_paid_result_materials_v1(_full_result([a, b]))
    assert len(out["duplicate_groups"]) == 1
    assert out["duplicate_groups"][0]["count"] == 2


# ─────────────────────────────────────────────────────────────────────────────
# T6 — 문장만 비슷하고 exact fingerprint 다름 : duplicate 아님
# ─────────────────────────────────────────────────────────────────────────────

def test_t6_similar_but_not_exact_is_not_duplicate():
    a = _obligation(what="안전조치를 하여야 한다", atom_id="a1")
    b = _obligation(what="안전 조치를 실시하여야 한다", atom_id="a2")
    out = build_paid_result_materials_v1(_full_result([a, b]))
    assert out["duplicate_groups"] == []
    assert out["overview"]["total_obligation_count"] == 2


def test_t6b_same_text_different_article_is_not_duplicate():
    a = _obligation(law_article="19", atom_id="a1")
    b = _obligation(law_article="20", atom_id="a2")
    out = build_paid_result_materials_v1(_full_result([a, b]))
    assert out["duplicate_groups"] == []


# ─────────────────────────────────────────────────────────────────────────────
# T7 — condition / triggered_by : applicability_basis 정확
# ─────────────────────────────────────────────────────────────────────────────

def test_t7_applicability_basis_preserves_raw_keys():
    obligations = [
        _obligation(condition="사업주는 굴착작업을 할 때",
                    triggered_by=["has_excavation", "worker_count"],
                    consumer_status="applicable", atom_id="a1"),
        _obligation(condition=None, triggered_by=[], consumer_status=None, atom_id="a2"),
    ]
    out = build_paid_result_materials_v1(_full_result(obligations))

    first = out["applicability_basis"][0]
    assert first["obligation_ref"] == 0
    assert first["legal_condition"] == "사업주는 굴착작업을 할 때"
    # RAW key 보존 — 한국어 라벨 변환 없음
    assert first["decision_inputs"] == ["has_excavation", "worker_count"]
    assert first["status"] == "applicable"
    assert first["availability"] == {
        "legal_condition": "AVAILABLE",
        "decision_inputs": "AVAILABLE",
        "status": "AVAILABLE",
    }

    second = out["applicability_basis"][1]
    assert second["legal_condition"] is None
    assert second["decision_inputs"] == []
    assert second["availability"]["legal_condition"] == "NULL"
    assert second["availability"]["decision_inputs"] == "NULL"


# ─────────────────────────────────────────────────────────────────────────────
# T8 — contract gaps 와 obligation missing_fields 를 분리
# ─────────────────────────────────────────────────────────────────────────────

def test_t8_information_gaps_a_and_b_are_never_merged():
    contract = _contract(
        active=["worker_count", "has_excavation"],
        missing=["total_floor_area", "building_use_type"],
        unknown=["sector"],
        invalid=[{"field": "worker_count", "reason": "음수 불가: -1"}],
    )
    obligations = [
        _obligation(missing_fields=["when", "condition"], atom_id="a1"),
        _obligation(missing_fields=["when"], law_article="38", atom_id="a2"),
        _obligation(missing_fields=[], law_article="39", atom_id="a3"),
    ]
    out = build_paid_result_materials_v1(_full_result(obligations, contract=contract))

    gaps = out["information_gaps"]
    assert set(gaps) == {"diagnosis_input_gaps", "obligation_information_gaps"}

    a = gaps["diagnosis_input_gaps"]
    assert a["source"] == "full_result.contract"
    assert a["missing_fields"] == ["building_use_type", "total_floor_area"]
    assert a["unknown_fields"] == ["sector"]
    assert a["invalid_fields"] == [{"field": "worker_count", "reason": "음수 불가: -1"}]

    b = gaps["obligation_information_gaps"]
    assert b["source"] == "obligations_raw[].enrichment.missing_fields"
    assert b["obligation_count_with_gaps"] == 2
    fields = {row["field"]: row for row in b["fields"]}
    assert fields["when"]["count"] == 2 and fields["when"]["obligation_refs"] == [0, 1]
    assert fields["condition"]["count"] == 1

    # 합산된 단일 총계가 존재하지 않는다.
    flat = json.dumps(gaps, ensure_ascii=False)
    assert "total_gap" not in flat and "combined" not in flat


def test_t8b_absent_contract_is_null_not_zero_fact():
    out = build_paid_result_materials_v1(_full_result([_obligation()]))
    assert out["information_gaps"]["diagnosis_input_gaps"]["availability"] == "NULL"
    assert out["coverage_summary"]["diagnosis_coverage"]["availability"] == "NULL"


# ─────────────────────────────────────────────────────────────────────────────
# T9 — who 여러 값 : actor map 정확
# ─────────────────────────────────────────────────────────────────────────────

def test_t9_legal_actor_map():
    obligations = [
        _obligation(who="사업주", atom_id="a1"),
        _obligation(who="사업주", law_article="38", atom_id="a2"),
        _obligation(who="공사시공자", law_article="41", atom_id="a3"),
        _obligation(who=None, law_article="42", atom_id="a4"),
    ]
    out = build_paid_result_materials_v1(_full_result(obligations))

    rows = {row["actor"]: row for row in out["legal_actor_map"]}
    assert rows["사업주"]["count"] == 2 and rows["사업주"]["obligation_refs"] == [0, 1]
    assert rows["공사시공자"]["count"] == 1
    assert rows["UNKNOWN"]["count"] == 1
    # count DESC 정렬
    assert out["legal_actor_map"][0]["actor"] == "사업주"


# ─────────────────────────────────────────────────────────────────────────────
# T10 — recipient = "근로자" : 제출기관으로 변환하지 않는다
# ─────────────────────────────────────────────────────────────────────────────

def test_t10_recipient_map_is_not_renamed_to_submit_org():
    obligations = [
        _obligation(recipient="근로자", atom_id="a1"),
        _obligation(recipient=None, law_article="38", atom_id="a2"),
    ]
    out = build_paid_result_materials_v1(_full_result(obligations))

    rows = {row["recipient"]: row for row in out["recipient_map"]}
    assert "근로자" in rows and rows["근로자"]["count"] == 1
    assert rows["UNKNOWN"]["count"] == 1
    # 라벨은 recipient 이며, 값은 RAW 그대로다.
    assert set(rows) == {"근로자", "UNKNOWN"}

    # meta.unsupported_fields 는 "제공하지 않음"을 선언하는 목록이므로 검사에서 분리한다.
    scanned = copy.deepcopy(out)
    scanned["meta"].pop("unsupported_fields")
    flat = json.dumps(scanned, ensure_ascii=False)
    assert "submit_org" not in flat
    assert "제출기관" not in flat
    # 선언 목록에는 submit_org 가 UNSUPPORTED 로 남아 있어야 한다(NULL 과 구별).
    assert "submit_org" in out["meta"]["unsupported_fields"]


# ─────────────────────────────────────────────────────────────────────────────
# T11~T13 — TIMING CHARACTER
# ─────────────────────────────────────────────────────────────────────────────

def test_t11_when_sangsi_is_continuous():
    out = build_paid_result_materials_v1(_full_result([_obligation(when="상시")]))
    ob = out["normalized_obligations"][0]
    assert ob["timing"]["raw_cycle"] == "상시"
    assert ob["timing"]["timing_character"] == "CONTINUOUS"
    assert out["timing_character_summary"]["counts"]["CONTINUOUS"] == 1


def test_t12_six_month_cycle_is_periodic():
    out = build_paid_result_materials_v1(_full_result([_obligation(when="6개월마다")]))
    ob = out["normalized_obligations"][0]
    assert ob["timing"]["timing_character"] == "PERIODIC"
    assert out["compliance_profile"]["periodic_count"] == 1


def test_t12b_other_explicit_mappings():
    cases = {
        "매월": "PERIODIC",
        "매년": "PERIODIC",
        "작업 전": "BEFORE_EVENT",
        "작업 후": "AFTER_EVENT",
    }
    for value, expected in cases.items():
        out = build_paid_result_materials_v1(_full_result([_obligation(when=value)]))
        assert out["normalized_obligations"][0]["timing"]["timing_character"] == expected, value


def test_t13_three_year_cycle_is_unknown_no_substring_heuristic():
    out = build_paid_result_materials_v1(_full_result([_obligation(when="3년마다")]))
    ob = out["normalized_obligations"][0]
    assert ob["timing"]["raw_cycle"] == "3년마다"
    assert ob["timing"]["timing_character"] == "UNKNOWN"
    assert out["compliance_profile"]["periodic_count"] == 0


def test_t13b_substring_of_mapped_token_is_not_matched():
    # "6개월마다 실시" 는 표에 없는 표현이므로 UNKNOWN. 부분일치 금지.
    out = build_paid_result_materials_v1(_full_result([_obligation(when="6개월마다 실시")]))
    assert out["normalized_obligations"][0]["timing"]["timing_character"] == "UNKNOWN"
    # 반대로 "3개월마다" 도 "3" substring 으로 분기 분류되지 않는다.
    out2 = build_paid_result_materials_v1(_full_result([_obligation(when="3개월마다")]))
    assert out2["normalized_obligations"][0]["timing"]["timing_character"] == "UNKNOWN"


# ─────────────────────────────────────────────────────────────────────────────
# T14 — when != inspection_cycle : TIMING CONFLICT
# ─────────────────────────────────────────────────────────────────────────────

def test_t14_timing_conflict_keeps_both_values():
    out = build_paid_result_materials_v1(_full_result([
        _obligation(when="상시", inspection_cycle="6개월마다"),
    ]))
    timing = out["normalized_obligations"][0]["timing"]
    assert timing["conflict"] is True
    assert timing["raw_cycle"] is None
    assert timing["when"] == "상시"
    assert timing["inspection_cycle"] == "6개월마다"
    assert timing["timing_character"] == "UNKNOWN"

    profile = out["legal_timing_profile"]
    assert profile["conflict_count"] == 1
    assert profile["conflict_obligation_refs"] == [0]
    assert profile["without_timing_count"] == 1


def test_t14b_timing_cases_a_b_c():
    # A 둘 다 없음
    a = build_paid_result_materials_v1(_full_result([_obligation()]))
    ta = a["normalized_obligations"][0]["timing"]
    assert ta["raw_cycle"] is None and ta["conflict"] is False

    # B 한쪽만 (inspection_cycle 만)
    b = build_paid_result_materials_v1(_full_result([_obligation(inspection_cycle="매년")]))
    tb = b["normalized_obligations"][0]["timing"]
    assert tb["raw_cycle"] == "매년" and tb["conflict"] is False

    # C 둘 다 동일
    c = build_paid_result_materials_v1(_full_result([
        _obligation(when="상시", inspection_cycle="상시")]))
    tc = c["normalized_obligations"][0]["timing"]
    assert tc["raw_cycle"] == "상시" and tc["conflict"] is False
    assert c["legal_timing_profile"]["with_timing_count"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# T15 — usable_for_evaluation true/false/null : coverage 정확
# ─────────────────────────────────────────────────────────────────────────────

def test_t15_evaluation_coverage():
    obligations = [
        _obligation(usable_for_evaluation=True, atom_id="a1"),
        _obligation(usable_for_evaluation=False, law_article="38", atom_id="a2"),
        _obligation(usable_for_evaluation=None, law_article="39", atom_id="a3"),
        _obligation(usable_for_evaluation="yes", law_article="40", atom_id="a4"),
    ]
    contract = _contract(active=["worker_count"], missing=["a", "b"], unknown=["c"],
                         invalid=[{"field": "x", "reason": "bad"}])
    out = build_paid_result_materials_v1(_full_result(obligations, contract=contract))

    cov = out["coverage_summary"]["obligation_evaluation_coverage"]
    assert cov["total"] == 4
    assert cov["evaluable_count"] == 1
    assert cov["not_evaluable_count"] == 1
    # bool 이 아닌 값은 추론하지 않고 unknown
    assert cov["unknown_count"] == 2

    diag = out["coverage_summary"]["diagnosis_coverage"]
    assert diag["active_count"] == 1
    assert diag["missing_count"] == 2
    assert diag["unknown_count"] == 1
    assert diag["invalid_count"] == 1

    flat = json.dumps(out["coverage_summary"], ensure_ascii=False)
    assert "%" not in flat and "score" not in flat and "percent" not in flat


# ─────────────────────────────────────────────────────────────────────────────
# T16 — 입력 mutation 없음
# ─────────────────────────────────────────────────────────────────────────────

def test_t16_input_is_not_mutated():
    raw = _full_result(
        [_obligation(when="상시", triggered_by=["has_excavation"], missing_fields=["when"])],
        contract=_contract(active=["worker_count"], missing=["total_floor_area"]),
    )
    before = copy.deepcopy(raw)
    build_paid_result_materials_v1(raw)
    assert raw == before


def test_t16b_output_mutation_does_not_reach_input():
    raw = _full_result([_obligation()])
    out = build_paid_result_materials_v1(raw)
    out["normalized_obligations"][0]["legal"]["law_name"] = "CHANGED"
    assert raw["obligations_raw"][0]["law_name"] == "산업안전보건기준에 관한 규칙"


# ─────────────────────────────────────────────────────────────────────────────
# T17 — 동일 input 두 번 : exact same output
# ─────────────────────────────────────────────────────────────────────────────

def test_t17_deterministic_output():
    raw = _full_result(
        [
            _obligation(law_name="건축법", law_article="41", who="공사시공자",
                        recipient="관할 행정청", when="매년", atom_id="a1"),
            _obligation(law_article="221", who="사업주", condition="굴착 시",
                        triggered_by=["has_excavation"], atom_id="a2"),
            _obligation(law_article="221", who="사업주", condition="굴착 시",
                        triggered_by=["has_excavation"], atom_id="a2"),
            _obligation(law_name="도시가스사업법", law_article="30",
                        content_type="PROHIBITION", obligation_type="PROHIBIT",
                        check_result="NOT_APPLICABLE", atom_id="a3"),
        ],
        contract=_contract(active=["worker_count"], missing=["total_floor_area"],
                           unknown=["sector"]),
    )
    first = build_paid_result_materials_v1(raw)
    second = build_paid_result_materials_v1(copy.deepcopy(raw))
    assert json.dumps(first, ensure_ascii=False, sort_keys=True) == \
           json.dumps(second, ensure_ascii=False, sort_keys=True)


def test_t17b_key_order_is_stable_across_input_order_of_equal_groups():
    raw = _full_result([
        _obligation(law_name="B법", law_article="1", atom_id="a1"),
        _obligation(law_name="A법", law_article="1", atom_id="a2"),
    ])
    out = build_paid_result_materials_v1(raw)
    assert [r["law_name"] for r in out["law_portfolio"]] == ["A법", "B법"]


# ─────────────────────────────────────────────────────────────────────────────
# T18 — 결과 어디에도 forbidden field/value 없음
# ─────────────────────────────────────────────────────────────────────────────

FORBIDDEN_TOKENS = (
    "risk_score", "risk_level", "risk_percentage", "risk_pct",
    "penalty", "과태료", "벌금", "penalty_summary", "max_penalty",
    "priority", "urgency", "즉시", "단기",
    "due_days", "deadline", "due_date", "next_due", "d_day", "dday",
    "qualification", "form_name", "form_url", "report_method_std",
    "online_system", "system_url", "submit_org", "retention",
    "HIGH", "MEDIUM", "LOW",
    "confidence", "accuracy", "grade",
    "generated_at", "datetime", "today",
    "위험", "심각", "높음",
)


def _rich_fixture():
    return _full_result(
        [
            _obligation(when="상시", triggered_by=["has_excavation"], atom_id="a1"),
            _obligation(law_article="30", content_type="PROHIBITION",
                        obligation_type="PROHIBIT", check_result="NOT_APPLICABLE",
                        recipient="근로자", missing_fields=["when"], atom_id="a2"),
            _obligation(law_name="건축법", law_article="41", obligation_type="NOTIFY",
                        who="공사시공자", inspection_cycle="매년", atom_id="a3"),
        ],
        contract=_contract(active=["worker_count"], missing=["total_floor_area"],
                           unknown=["sector"],
                           invalid=[{"field": "worker_count", "reason": "음수 불가: -1"}]),
    )


def test_t18_no_forbidden_field_or_value_in_output():
    out = build_paid_result_materials_v1(_rich_fixture())
    # meta.unsupported_fields 는 "제공하지 않음"을 선언하는 목록이므로 검사 대상에서 분리한다.
    unsupported = out["meta"].pop("unsupported_fields")
    assert "qualification" in unsupported  # 선언은 되어 있어야 한다

    flat = json.dumps(out, ensure_ascii=False)
    for token in FORBIDDEN_TOKENS:
        assert token not in flat, "forbidden token present in output: {}".format(token)


def test_t18b_module_source_has_no_forbidden_logic():
    import inspect

    import services.paid_result_materializer as mod

    src = inspect.getsource(mod)
    # 모듈 docstring 은 금지사항을 "선언"하는 텍스트이므로 코드 스캔에서 제외한다.
    src_body = src.replace(mod.__doc__ or "", "", 1)
    banned_calls = (
        "datetime.now", "datetime.utcnow", "time.time", "random.", "uuid4",
        "requests.", "httpx.", "open(", "os.getenv", "os.environ",
        "get_supabase", "parseWon", "difflib", "SequenceMatcher",
    )
    for token in banned_calls:
        assert token not in src_body, "forbidden implementation token: {}".format(token)

    # import 표면 자체를 고정한다 — 시간/난수/네트워크/DB/LLM 모듈 유입 차단.
    imported = set()
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith("import "):
            imported.add(stripped.split()[1].split(".")[0])
        elif stripped.startswith("from ") and " import " in stripped:
            imported.add(stripped.split()[1].split(".")[0])
    assert imported == {"__future__", "copy", "hashlib", "re", "unicodedata", "typing"}, imported


# ─────────────────────────────────────────────────────────────────────────────
# 추가 계약 검증 — provenance / meta / RAW 보존 / R06 / R14 / R16
# ─────────────────────────────────────────────────────────────────────────────

def test_provenance_present_for_every_material():
    out = build_paid_result_materials_v1(_rich_fixture())
    registry = out["meta"]["materials"]
    material_keys = set(out) - {"meta"}
    assert material_keys.issubset(set(registry))
    for key, entry in registry.items():
        assert entry["material_type"]
        assert entry["material_version"] == 1
        assert isinstance(entry["derivation_version"], int)
        assert entry["derivation_version"] >= 1
        # derivation_rule 라벨은 규칙명과 버전을 담는다 — 규칙 의미가 바뀌면 버전이 올라간다.
        assert entry["derivation_rule"].endswith("_V{}".format(entry["derivation_version"]))
        assert isinstance(entry["source_fields"], list) and entry["source_fields"]
    # STEP3A REV-1 에서 의미가 바뀐 규칙은 버전이 올라가 있어야 한다.
    assert registry["normalized_obligations"]["derivation_rule"] == "NORMALIZER_V2"
    assert registry["overview"]["derivation_rule"] == "R01_V2"
    assert registry["law_portfolio"]["derivation_rule"] == "R02_V2"
    for key in ("normalized_obligations", "applicability_basis", "execution_seed"):
        assert registry[key]["source_obligation_refs"] == [0, 1, 2]


def test_meta_has_no_time_dependency_and_carries_engine_version():
    out = build_paid_result_materials_v1(_rich_fixture())
    assert out["meta"]["material_version"] == 1
    assert out["meta"]["source_engine_version"] == "leg-runtime-v3"
    assert "generated_at" not in out["meta"]

    # engine_version 이 없으면 운반하지 않는다(만들지 않는다).
    out2 = build_paid_result_materials_v1(_full_result([], engine_version=None))
    assert "source_engine_version" not in out2["meta"]


def test_r06_verification_summary_uses_original_status_names():
    out = build_paid_result_materials_v1(_full_result([
        _obligation(check_result="VERIFIED", atom_id="a1"),
        _obligation(check_result="NOT_APPLICABLE", law_article="38", atom_id="a2"),
        _obligation(check_result=None, law_article="39", atom_id="a3"),
    ]))
    summary = out["verification_summary"]
    assert summary["total"] == 3
    assert summary["counts"] == {"NOT_APPLICABLE": 1, "UNKNOWN": 1, "VERIFIED": 1}


def test_r14_compliance_profile_is_numbers_only():
    out = build_paid_result_materials_v1(_rich_fixture())
    profile = out["compliance_profile"]
    assert set(profile) == {
        "total_obligations", "distinct_laws", "prohibition_count",
        "periodic_count", "verified_count", "unknown_verification_count",
    }
    for value in profile.values():
        assert isinstance(value, int)


def test_r16_execution_seed_excludes_user_input_fields():
    out = build_paid_result_materials_v1(_rich_fixture())
    seeds = out["execution_seed"]
    assert len(seeds) == 3
    expected = {
        "obligation_ref", "law_name", "law_article", "evidence", "content_type",
        "obligation_type", "what", "who", "recipient", "condition",
        "raw_cycle", "timing_character", "check_result",
    }
    for seed in seeds:
        assert set(seed) == expected
    flat = json.dumps(seeds, ensure_ascii=False)
    for banned in ("actual_assignee", "base_date", "next_due_date",
                   "completion_status", "completion_date", "evidence_location", "memo"):
        assert banned not in flat


def test_raw_obligation_count_equals_normalized_count():
    raw = _rich_fixture()
    out = build_paid_result_materials_v1(raw)
    assert len(out["normalized_obligations"]) == len(raw["obligations_raw"])
    assert out["overview"]["total_obligation_count"] == len(raw["obligations_raw"])


def test_non_dict_obligation_entries_are_ignored_not_invented():
    raw = _full_result([_obligation(atom_id="a1")])
    raw["obligations_raw"].extend([None, "x", 3])
    out = build_paid_result_materials_v1(raw)
    assert out["overview"]["total_obligation_count"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# STEP3A REV-1 — T19~T22
# ─────────────────────────────────────────────────────────────────────────────

def test_t19_unspecified_law_is_not_counted_as_a_law():
    obligations = [
        _obligation(law_name="산업안전보건법", law_article="17", atom_id="a1"),
        _obligation(law_name="건축법", law_article="41", atom_id="a2"),
        _obligation(law_name=None, law_article="9", atom_id="a3"),
    ]
    out = build_paid_result_materials_v1(_full_result(obligations))

    assert out["overview"]["distinct_law_count"] == 2
    assert out["overview"]["unspecified_law_obligation_count"] == 1
    # 총 의무 건수는 줄지 않는다 — 삭제가 아니라 분리 계수다.
    assert out["overview"]["total_obligation_count"] == 3

    # UNSPECIFIED 버킷 자체는 law_portfolio 에 보존된다.
    names = [row["law_name"] for row in out["law_portfolio"]]
    assert "UNSPECIFIED" in names
    assert len(out["law_portfolio"]) == 3


def test_t20_unspecified_article_is_not_counted_as_an_article():
    obligations = [
        _obligation(law_article="17", atom_id="a1"),
        _obligation(law_article="18", atom_id="a2"),
        _obligation(law_article=None, atom_id="a3"),
    ]
    out = build_paid_result_materials_v1(_full_result(obligations))

    assert len(out["law_portfolio"]) == 1
    row = out["law_portfolio"][0]
    assert row["article_count"] == 2
    assert row["unspecified_article_obligation_count"] == 1
    assert row["obligation_count"] == 3

    # R13 은 UNSPECIFIED group 을 유지한다(삭제 금지). 다만 실제 조문수로 세지 않는다.
    articles = [b["law_article"] for b in out["article_bundles"]]
    assert "UNSPECIFIED" in articles
    assert len(out["article_bundles"]) == 3


def test_t20b_unspecified_law_bucket_counts_its_own_articles_correctly():
    obligations = [
        _obligation(law_name=None, law_article="9", atom_id="a1"),
        _obligation(law_name=None, law_article=None, atom_id="a2"),
    ]
    out = build_paid_result_materials_v1(_full_result(obligations))
    row = [r for r in out["law_portfolio"] if r["law_name"] == "UNSPECIFIED"][0]
    assert row["article_count"] == 1
    assert row["unspecified_article_obligation_count"] == 1
    assert out["overview"]["distinct_law_count"] == 0
    assert out["overview"]["unspecified_law_obligation_count"] == 2


def test_t21_raw_applicability_is_preserved_losslessly():
    obligations = [
        _obligation(applicability="APPLICABLE", atom_id="a1"),
        _obligation(applicability="REQUIRED_ADDITIONAL_INPUT", law_article="38", atom_id="a2"),
        _obligation(applicability=None, law_article="39", atom_id="a3"),
    ]
    out = build_paid_result_materials_v1(_full_result(obligations))

    values = [o["applicability"]["engine_applicability"] for o in out["normalized_obligations"]]
    assert values == ["APPLICABLE", "REQUIRED_ADDITIONAL_INPUT", None]

    # 기존 applicability 필드는 삭제되지 않았다.
    first = out["normalized_obligations"][0]["applicability"]
    assert set(first) == {"engine_applicability", "condition", "triggered_by", "consumer_status"}

    # availability 도 함께 표기된다.
    assert out["normalized_obligations"][0]["availability"][
        "applicability.engine_applicability"] == "AVAILABLE"
    assert out["normalized_obligations"][2]["availability"][
        "applicability.engine_applicability"] == "NULL"


def test_t22_no_filter_implemented():
    """FILTER RULE 미확정 → 어떤 상태로도 obligation 을 제외하지 않는다.

    근거(STEP3A REV-1 / O1 조사):
      · applicability 는 현행 엔진에서 하드코딩 상수이며(rtm/api.py:92),
        비적용 원자는 응답 조립 전에 이미 제거된다(rtm/engine.py:183-191).
      · check_result=NOT_APPLICABLE 은 clause 의 actor/target 메타 부재를 뜻하며
        (check_engine/validator.py:143-154) 사업장 차원의 법적 비적용이 아니다.
    따라서 어떤 필드로도 필터링하지 않는다.
    """
    obligations = [
        _obligation(check_result="VERIFIED", consumer_status="applicable", atom_id="a1"),
        _obligation(check_result="NOT_APPLICABLE", consumer_status="applicable",
                    law_article="38", atom_id="a2"),
        _obligation(check_result="BLOCKED", consumer_status="review_required",
                    usable_for_evaluation=False, law_article="39", atom_id="a3"),
        _obligation(check_result=None, consumer_status=None, law_article="40", atom_id="a4"),
    ]
    raw = _full_result(obligations)
    out = build_paid_result_materials_v1(raw)

    # 모수 = RAW 전건. 상태로 제외하지 않는다.
    assert out["overview"]["total_obligation_count"] == 4
    assert len(out["normalized_obligations"]) == 4
    assert len(out["execution_seed"]) == 4
    assert len(out["applicability_basis"]) == 4
    assert sum(r["obligation_count"] for r in out["law_portfolio"]) == 4

    # 상태는 감추지 않고 그대로 계수한다.
    assert out["verification_summary"]["counts"] == {
        "BLOCKED": 1, "NOT_APPLICABLE": 1, "UNKNOWN": 1, "VERIFIED": 1,
    }
    assert out["verification_summary"]["total"] == 4
