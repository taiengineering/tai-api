"""Route contract — additional_information paid isolation (BE-T12 / BE-T13).

get_supabase mock + fake rec. 기존 paid-result 회귀로 대체하지 않는다.
"""
from __future__ import annotations

import routers.diagnosis_result_web as rw


def _rec(*, tier: str):
    return {
        "id": "row-1",
        "public_token": "tok-1",
        "tier_code": tier,
        "status": "ACTIVE",
        "expires_at": None,
        "created_at": "2026-09-08T00:00:00+00:00",
        "input_data": {"company_name": "샘플", "sector": "BUILDING"},
        "full_result": {
            "sector": "BUILDING",
            "contract": {"missing_fields": ["a"], "unknown_fields": [], "invalid_fields": []},
            "obligations_raw": [
                {"enrichment": {"missing_fields": ["f1"], "usable_for_evaluation": True}},
            ],
        },
    }


class _FakeQuery:
    def __init__(self, rec):
        self._rec = rec

    def select(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def in_(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def execute(self):
        class R:
            data = [self._rec]
        return R()


class _FakeSupabase:
    def __init__(self, rec):
        self._rec = rec

    def table(self, *a, **k):
        return _FakeQuery(self._rec)


def _install(monkeypatch, rec):
    monkeypatch.setattr(rw, "get_supabase", lambda: _FakeSupabase(rec))
    monkeypatch.setattr(rw, "build_paid_result_product_v1", lambda row: {
        "contract_version": 1,
        "diagnosis": {},
        "diagnosis_profile": {},
        "paid_result_materials_v1": {},
        "paid_result_evidence_v1": {},
        rw.SOURCE_TEXT_KEY: {"version": 1, "source_mode": "LIVE_LEG_SOURCE", "items": [], "unresolved": []},
    })


def test_BE_T12_free_payload_additional_information_present(monkeypatch):
    _install(monkeypatch, _rec(tier="BUILDING_FREE"))
    data = rw._build_result_payload("tok-1", free_preview_limit=5)["data"]
    assert data["is_free"] is True
    assert "additional_information" in data
    ai = data["additional_information"]
    assert set(ai.keys()) == {"input_gaps", "obligation_gaps", "coverage"}
    assert ai["input_gaps"]["missing_count"] == 1


def test_BE_T13_paid_payload_additional_information_absent(monkeypatch):
    _install(monkeypatch, _rec(tier="BUILDING_V2"))
    data = rw._build_result_payload(
        "tok-1", free_preview_limit=None, include_paid_product=True,
    )["data"]
    assert data["is_free"] is False
    assert "additional_information" not in data
