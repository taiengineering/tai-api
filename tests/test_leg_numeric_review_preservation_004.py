"""WO-NUMERIC-UNKNOWN-PRESERVATION-004 T11 — tai-api consumer channel 보존 (재판정 0).

LEG /rtm/evaluate 의 review_required 를 full_result 에 원본 보존하고
기존 consumer shape(unconfirmed) 로만 변환한다.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from clients import leg_runtime_client as leg_client
from services.leg_diagnosis_svc import run_leg_diagnosis


LEG_REVIEW = {
    "atom_id": "aaaaaaaa-0000-0000-0000-000000000001",
    "source_atom_ids": ["aaaaaaaa-0000-0000-0000-000000000001"],
    "law_name": "산업안전보건기준에 관한 규칙",
    "law_article": "제42조",
    "applicability": "REVIEW_REQUIRED",
    "reason_code": "MISSING_NUMERIC_INPUT",
    "missing_fields": ["work_height_m"],
    "condition_desc": "work_height_m>=2.0",
}

LEG_OBLIGATION = {
    "atom_id": "bbbbbbbb-0000-0000-0000-000000000002",
    "source_atom_ids": ["bbbbbbbb-0000-0000-0000-000000000002"],
    "law_name": "산업안전보건기준에 관한 규칙",
    "law_article": "제10조",
    "applicability": "APPLICABLE",
    "triggered_by": ["has_crane"],
    "evidence": "크레인을 사용하는 작업",
}


class _Body:
    def __init__(self, sector="INDUSTRY", input=None):
        self.sector = sector
        self.input = input or {}


def test_T11_leg_review_required_preserved_into_consumer_unconfirmed(monkeypatch):
    captured = {}

    def fake_eval(facility, *, timeout=None):
        captured["facility"] = facility
        return {
            "status": "OK",
            "obligations": [dict(LEG_OBLIGATION)],
            "obligation_count": 1,
            "trace_id": "wo-004-t11",
            "provenance": {"release_version": "t"},
            "contract": {"valid": True},
            "review_required": [dict(LEG_REVIEW)],
            "review_required_count": 1,
        }

    monkeypatch.setattr(leg_client, "evaluate_rtm", fake_eval)
    full = run_leg_diagnosis(_Body(input={"has_crane": True}))

    # raw LEG channel 보존 (재판정 금지: 엔진이 준 객체 그대로)
    assert full["review_required"] == [LEG_REVIEW]
    assert full["review_required_count"] == 1
    # 기존 consumer shape
    assert full["unconfirmed_count"] == 1
    u = full["unconfirmed"][0]
    assert u["atom_id"] == LEG_REVIEW["atom_id"]
    assert u["missing_fields"] == ["work_height_m"]
    assert u["reason_code"] == "MISSING_NUMERIC_INPUT"
    assert u["title"] == "산업안전보건기준에 관한 규칙 제42조"
    assert u["reason"] == "추가 수치 정보가 필요하여 적용 여부를 확정하지 못했습니다."
    # 기존 obligations/key_obligations 불변
    assert full["applicable_count"] == 1
    assert full["obligations_raw"] == [LEG_OBLIGATION]
    assert full["key_obligations"][0]["atom_id"] == LEG_OBLIGATION["atom_id"]
    assert full["key_obligations"][0]["applicability"] == "APPLICABLE"
    # 소비자 입력으로 재판정하지 않음
    assert "work_height_m" not in (captured.get("facility") or {})
