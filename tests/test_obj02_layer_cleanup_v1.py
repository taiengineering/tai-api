"""tests/test_obj02_layer_cleanup_v1.py — WO-E2E-OBJ02-LAYER-CLEANUP-001.

Representation-layer regression coverage for:
    LYR-001 — triggered_by attribution stays trace-only (frozen contract).
    LYR-002 — missing_fields is canonical field-name array only (센티널 금지).
    LYR-003 — APPLICABLE / NOT_APPLICABLE / UNKNOWN terminology consistency
              & UNKNOWN 비강제 강등 방지 (missing input ≠ NOT_APPLICABLE).

원칙:
    - 이 WO 는 representation 계약만 굳힌다. obligation 발동/판정 재해석 0.
    - hard invariants (LEGAL_RESULT_DELTA / CONSUMER_STATUS_DELTA / CANONICAL_MEMBERSHIP_DELTA /
      PUBLISHED_NORM_DELTA / PSR_WRITE) 는 T9 에서 combined-fixture 재실행으로 증명.
    - DB / network / time / random 접근 0.
"""
from __future__ import annotations

import copy
import json

from services.paid_result_materializer import (
    build_paid_result_materials_v1,
    _field_name_list,
)
from services.obligation_presentation_mapper import (
    map_diagnosis_presentation,
    map_operation_presentation,
)
from schemas.obligation_result_v1 import ObligationResultV1


# ─────────────────────────────────────────────────────────────────────────────
# 공용 fixture — LEG 저장 shape 그대로 (test_paid_result_materializer_v1 과 동형)
# ─────────────────────────────────────────────────────────────────────────────

def _obligation(
    *,
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
    for k, v in (
        ("what", what), ("who", who), ("when", when), ("recipient", recipient),
        ("where", where), ("how", how), ("condition", condition),
    ):
        if v is not None:
            detail[k] = v
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
    ob = {
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
        ob["check_result"] = check_result
    return ob


def _contract(*, active=None, missing=None, unknown=None, invalid=None):
    return {
        "valid": True,
        "active_fields": active if active is not None else [],
        "missing_fields": missing if missing is not None else [],
        "unknown_fields": unknown if unknown is not None else [],
        "invalid_fields": invalid if invalid is not None else [],
        "accepted_count": len(active or []),
    }


def _full_result(obligations=None, contract=None):
    out = {
        "engine_family": "LEG",
        "engine_version": "leg-runtime-v3",
        "rule_source": "leg-prod",
        "fallback_used": False,
        "leg_status": "OK",
        "leg_trace_id": "rtm-obj02-layer-cleanup",
        "sector": "MANUFACTURING",
        "applicable_count": len(obligations or []),
        "key_obligations": [],
        "applicable_laws": [],
        "law_badges": [],
        "rules": [],
        "risk_level": None,
        "summary": None,
        "provenance": {
            "release_version": "OBJ02-RC1",
            "repository_version": "v1",
            "freeze_signature": "obj02-layer-cleanup",
            "rc_snapshot_checksum": "",
            "repository_size": 1,
        },
        "obligations_raw": obligations if obligations is not None else [],
        "facility_used": {"worker_count": 45},
    }
    if contract is not None:
        out["contract"] = contract
    return out


def _applicable_identity_set(materials):
    """LEGAL_RESULT_DELTA 판정용 결정적 identity 집합.

    (atom_id, law_name, law_article, check_result) — representation-layer 변경으로
    이 집합이 바뀌면 semantic defect 이므로 STOP.
    """
    ids = []
    for ob in materials["normalized_obligations"]:
        ids.append((
            ob["identity"]["atom_id"],
            ob["legal"]["law_name"],
            ob["legal"]["law_article"],
            ob["verification"]["check_result"],
        ))
    return sorted(ids)


# ─────────────────────────────────────────────────────────────────────────────
# T1 — LYR-001: triggered_by 는 trace 필드이며 decision_inputs 로 운반된다.
# ─────────────────────────────────────────────────────────────────────────────

def test_t1_lyr001_triggered_by_positive_attribution():
    """triggered_by 는 decision_inputs (판정에 사용된 입력 필드) 로만 운반한다.

    materializer 는 _r04_applicability_basis 에서 이를 `decision_inputs` 로 라벨한다.
    법적 충분조건(legal_condition) 과 절대 병합하지 않는다.
    """
    raw = _full_result([
        _obligation(
            atom_id="a1", triggered_by=["has_scaffold", "worker_count"],
            condition="상시근로자 50명 이상",
        ),
    ])
    out = build_paid_result_materials_v1(raw)
    r04 = out["applicability_basis"]
    assert len(r04) == 1
    row = r04[0]
    # decision_inputs = triggered_by verbatim (재정렬/의역 없음)
    assert row["decision_inputs"] == ["has_scaffold", "worker_count"]
    # legal_condition 은 별도 축이며 triggered_by 와 병합되지 않는다.
    assert row["legal_condition"] == "상시근로자 50명 이상"
    # obligation view 자체에도 원본 triggered_by 는 applicability.triggered_by 로 보존.
    ob = out["normalized_obligations"][0]
    assert ob["applicability"]["triggered_by"] == ["has_scaffold", "worker_count"]


# ─────────────────────────────────────────────────────────────────────────────
# T2 — LYR-001: representation 변경이 obligation identity 집합을 바꾸지 않는다.
# ─────────────────────────────────────────────────────────────────────────────

def test_t2_lyr001_no_legal_result_delta():
    raw = _full_result([
        _obligation(atom_id="a1", triggered_by=["has_scaffold"]),
        _obligation(atom_id="a2", law_article="221",
                    condition="굴착 시", triggered_by=["has_excavation"]),
        _obligation(atom_id="a3", law_name="도시가스사업법", law_article="30",
                    content_type="PROHIBITION", obligation_type="PROHIBIT",
                    check_result="NOT_APPLICABLE"),
    ])
    out = build_paid_result_materials_v1(copy.deepcopy(raw))
    identities = _applicable_identity_set(out)
    # deterministic — 두 번 돌려도 동일해야 하고, 원본 obligation 3건 그대로 보존.
    out2 = build_paid_result_materials_v1(copy.deepcopy(raw))
    assert _applicable_identity_set(out2) == identities
    assert len(identities) == 3
    # check_result 상태 3-set 이 그대로 보존 (VERIFIED / VERIFIED / NOT_APPLICABLE)
    states = sorted(t[3] for t in identities)
    assert states == ["NOT_APPLICABLE", "VERIFIED", "VERIFIED"]


# ─────────────────────────────────────────────────────────────────────────────
# T3 — LYR-002: 실제 missing field → canonical field 이름만 담긴다.
# ─────────────────────────────────────────────────────────────────────────────

def test_t3_lyr002_real_missing_field_canonical_names():
    raw = _full_result([
        _obligation(atom_id="a1", missing_fields=["when", "condition_code"]),
        _obligation(atom_id="a2", law_article="20", missing_fields=[]),
    ], contract=_contract(missing=["total_floor_area", "worker_count"]))
    out = build_paid_result_materials_v1(raw)
    # per-obligation
    assert out["normalized_obligations"][0]["verification"]["missing_fields"] == \
        ["when", "condition_code"]
    assert out["normalized_obligations"][1]["verification"]["missing_fields"] == []
    # contract 축
    gaps = out["information_gaps"]["diagnosis_input_gaps"]
    assert gaps["missing_fields"] == ["total_floor_area", "worker_count"]


# ─────────────────────────────────────────────────────────────────────────────
# T4 — LYR-002: missing 없음 → [] (센티널 배열 금지)
# ─────────────────────────────────────────────────────────────────────────────

def test_t4_lyr002_no_missing_field_empty_array():
    raw = _full_result([
        _obligation(atom_id="a1", missing_fields=[]),
    ], contract=_contract(missing=[], unknown=[]))
    out = build_paid_result_materials_v1(raw)
    assert out["normalized_obligations"][0]["verification"]["missing_fields"] == []
    gaps = out["information_gaps"]["diagnosis_input_gaps"]
    assert gaps["missing_fields"] == []
    assert gaps["unknown_fields"] == []
    # coverage 카운트도 0
    cov = out["coverage_summary"]["diagnosis_coverage"]
    assert cov["missing_count"] == 0
    assert cov["unknown_count"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# T5 — LYR-002: blank / whitespace / null sentinel 유입 → drop.
#      real canonical field name 은 함께 있으면 살리고, 센티널만 제거.
# ─────────────────────────────────────────────────────────────────────────────

def test_t5_lyr002_blank_sentinel_regression_prohibited():
    # per-obligation enrichment.missing_fields 에 sentinel 이 섞여 들어와도 drop.
    raw = _full_result([
        _obligation(atom_id="a1", missing_fields=["when", "", " ", None, "condition_code"]),
        _obligation(atom_id="a2", law_article="20", missing_fields=[""]),
        _obligation(atom_id="a3", law_article="21", missing_fields=[" ", "   "]),
    ], contract=_contract(
        missing=["total_floor_area", "", " ", None, "worker_count"],
        unknown=["", "sector", "  "],
    ))
    out = build_paid_result_materials_v1(raw)
    v0 = out["normalized_obligations"][0]["verification"]["missing_fields"]
    v1 = out["normalized_obligations"][1]["verification"]["missing_fields"]
    v2 = out["normalized_obligations"][2]["verification"]["missing_fields"]
    # 센티널 (blank/whitespace/null) 은 통과 못한다.
    assert "" not in v0 and " " not in v0 and None not in v0
    assert v0 == ["when", "condition_code"]
    assert v1 == []   # 전부 센티널
    assert v2 == []
    # contract 축도 동일 계약.
    gaps = out["information_gaps"]["diagnosis_input_gaps"]
    assert gaps["missing_fields"] == ["total_floor_area", "worker_count"]
    assert gaps["unknown_fields"] == ["sector"]
    # information_gaps.obligation_information_gaps.fields 는 empty-key 버킷 없음.
    obl_fields = out["information_gaps"]["obligation_information_gaps"]["fields"]
    for row in obl_fields:
        assert isinstance(row["field"], str)
        assert row["field"].strip() != ""
    # coverage 카운트도 센티널 반영 안 함.
    cov = out["coverage_summary"]["diagnosis_coverage"]
    assert cov["missing_count"] == 2
    assert cov["unknown_count"] == 1


def test_t5b_field_name_list_helper_pure():
    """_field_name_list 자체가 순수 & 결정적."""
    assert _field_name_list(None) == []
    assert _field_name_list([]) == []
    assert _field_name_list(["a", "", " ", None, "b"]) == ["a", "b"]
    assert _field_name_list(["  worker_count  "]) == ["worker_count"]
    # 문자열이 아닌 원소는 조용히 drop (센티널 취급)
    assert _field_name_list(["a", 1, {"k": "v"}, "b"]) == ["a", "b"]
    # 입력 mutation 없음
    src = ["a", "", "b"]
    _field_name_list(src)
    assert src == ["a", "", "b"]


# ─────────────────────────────────────────────────────────────────────────────
# T6 — LYR-003: APPLICABLE 용어 일관 (per-obligation applicability).
# ─────────────────────────────────────────────────────────────────────────────

def test_t6_lyr003_applicable_terminology():
    raw = _full_result([
        _obligation(atom_id="a1", applicability="APPLICABLE", check_result="VERIFIED"),
    ])
    out = build_paid_result_materials_v1(raw)
    ob = out["normalized_obligations"][0]
    # LEG 저장 계약 필드는 그대로 engine_applicability 로 운반.
    assert ob["applicability"]["engine_applicability"] == "APPLICABLE"
    # check_result 도 VERIFIED 로 보존.
    assert ob["verification"]["check_result"] == "VERIFIED"
    # obligation_result contract 모델도 동일 문자열을 그대로 담는다.
    m = ObligationResultV1.from_raw(raw["obligations_raw"][0])
    assert m.applicability == "APPLICABLE"
    assert m.check_result == "VERIFIED"


# ─────────────────────────────────────────────────────────────────────────────
# T7 — LYR-003: NOT_APPLICABLE 용어 일관 (check_result 축).
# ─────────────────────────────────────────────────────────────────────────────

def test_t7_lyr003_not_applicable_terminology():
    raw = _full_result([
        _obligation(atom_id="a1", check_result="NOT_APPLICABLE"),
    ])
    out = build_paid_result_materials_v1(raw)
    ob = out["normalized_obligations"][0]
    assert ob["verification"]["check_result"] == "NOT_APPLICABLE"
    # r06_verification_summary 도 원본 상태명을 그대로 카운트한다.
    summary = out["verification_summary"]
    assert summary["counts"].get("NOT_APPLICABLE") == 1


# ─────────────────────────────────────────────────────────────────────────────
# T8 — LYR-003: missing / UNKNOWN 의미 보존.
#      obligation.check_result 가 None 이면 UNKNOWN 으로 카운트하되,
#      절대 NOT_APPLICABLE 로 강등하거나 False 로 사영하지 않는다.
# ─────────────────────────────────────────────────────────────────────────────

def test_t8_lyr003_unknown_not_coerced():
    raw = _full_result([
        _obligation(atom_id="a1", check_result=None),  # 없음 = UNKNOWN
        _obligation(atom_id="a2", check_result="NOT_APPLICABLE"),
        _obligation(atom_id="a3", check_result="VERIFIED"),
    ])
    out = build_paid_result_materials_v1(raw)
    counts = out["verification_summary"]["counts"]
    # 3 개 상태가 각기 다른 버킷으로 남는다 — UNKNOWN 이 NOT_APPLICABLE 로 접히지 않음.
    assert counts.get("UNKNOWN") == 1
    assert counts.get("NOT_APPLICABLE") == 1
    assert counts.get("VERIFIED") == 1
    # per-obligation check_result 도 원본대로 (None 이면 None 그대로 보존).
    obs = out["normalized_obligations"]
    assert obs[0]["verification"]["check_result"] is None
    assert obs[1]["verification"]["check_result"] == "NOT_APPLICABLE"
    assert obs[2]["verification"]["check_result"] == "VERIFIED"


# ─────────────────────────────────────────────────────────────────────────────
# T9 — 결합 response-contract regression + full-result-delta guard.
#      동일 fixture 를 fix-전 (raw 재구성) 과 fix-후 를 비교하지 않고,
#      대신 (a) obligation identity 집합이 그대로이고 (b) 응답 shape 이 결정적임을 증명.
# ─────────────────────────────────────────────────────────────────────────────

def test_t9_combined_contract_regression_and_delta_guard():
    raw = _full_result([
        _obligation(
            atom_id="a1", triggered_by=["has_scaffold"],
            missing_fields=["when", "", " ", None],  # 센티널 섞임
        ),
        _obligation(
            atom_id="a2", law_article="221", condition="굴착 시",
            triggered_by=["has_excavation"],
            check_result="NOT_APPLICABLE",
            missing_fields=[],
        ),
        _obligation(
            atom_id="a3", law_name="도시가스사업법", law_article="30",
            content_type="PROHIBITION", obligation_type="PROHIBIT",
            check_result=None,  # UNKNOWN
            missing_fields=["", " "],
        ),
    ], contract=_contract(
        active=["worker_count"],
        missing=["total_floor_area", "", None],
        unknown=[""],
    ))
    raw_snapshot = copy.deepcopy(raw)

    out1 = build_paid_result_materials_v1(copy.deepcopy(raw))
    out2 = build_paid_result_materials_v1(copy.deepcopy(raw))

    # 입력 mutation 0
    assert raw == raw_snapshot

    # deterministic
    assert json.dumps(out1, ensure_ascii=False, sort_keys=True) == \
        json.dumps(out2, ensure_ascii=False, sort_keys=True)

    # LEGAL_RESULT_DELTA = 0 — 원본 3 개 obligation 이 그대로 identity 를 지킨다.
    ids = _applicable_identity_set(out1)
    assert len(ids) == 3
    assert ("a1", "산업안전보건기준에 관한 규칙", "19", "VERIFIED") in ids
    assert ("a2", "산업안전보건기준에 관한 규칙", "221", "NOT_APPLICABLE") in ids
    assert ("a3", "도시가스사업법", "30", None) in ids

    # CONSUMER_STATUS_DELTA = 0 — 각 obligation 의 consumer_status 원본 보존.
    for ob in out1["normalized_obligations"]:
        assert ob["applicability"]["consumer_status"] == "applicable"

    # LYR-002 계약 — 어디에도 blank sentinel 이 흘러들지 않는다.
    def _walk_missing_fields(node, hits):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "missing_fields" and isinstance(v, list):
                    hits.append(v)
                _walk_missing_fields(v, hits)
        elif isinstance(node, list):
            for item in node:
                _walk_missing_fields(item, hits)

    hits = []
    _walk_missing_fields(out1, hits)
    assert hits, "expected at least one missing_fields array in output"
    for arr in hits:
        for item in arr:
            # canonical field-name 축은 non-empty str 만 통과한다.
            assert isinstance(item, str), f"non-str element in missing_fields: {item!r}"
            assert item.strip() != "", "blank sentinel leaked into missing_fields"


# ─────────────────────────────────────────────────────────────────────────────
# LYR-001 supplementary — presentation mapper 는 frozen alias 계약을 유지.
# WO 는 이 alias 를 확장·재설계하지 않는다 (STOP — frozen consumer contract).
# ─────────────────────────────────────────────────────────────────────────────

def test_lyr001_presentation_reason_alias_is_frozen():
    """map_diagnosis_presentation 의 `reason` alias 는 frozen 계약이므로 재이름 없음."""
    ob = {
        "obligation_detail": {"what": "설치", "who": "사업주"},
        "triggered_by": ["has_scaffold"],
    }
    d = map_diagnosis_presentation(ob)
    # frozen alias — trace field 를 표시용 "reason" 으로 라벨한다.
    assert d.get("reason") == ["has_scaffold"]
    op = map_operation_presentation(ob)
    assert op.get("reason") == ["has_scaffold"]


def test_lyr001_triggered_by_absence_no_key():
    """triggered_by 없음 → presentation.reason key 자체 미생성 (ABSENT ≠ NULL)."""
    ob = {"obligation_detail": {"what": "x"}}
    d = map_diagnosis_presentation(ob)
    assert "reason" not in d
    op = map_operation_presentation(ob)
    assert "reason" not in op
