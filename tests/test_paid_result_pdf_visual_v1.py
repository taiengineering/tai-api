"""tests/test_paid_result_pdf_visual_v1.py — PV01~PV15
WO-MAIN-PAID-PDF-VISUAL-04

Visual builder 단위 테스트.
INPUT = premium_result_v1 with materials.duty_vs_prohibition +
        materials.timing_character_summary.
실 LEG/DB 0.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from services.paid_result_pdf_view_v1 import (
    _build_v1_band,
    _build_v2_bars,
    _build_v3_data,
    _build_v4_grid,
    build_paid_result_pdf_view_v1,
)


# ── 픽스처 헬퍼 ──────────────────────────────────────────────────────────────

def _dvp(obligation: int = 0, prohibition: int = 0, unknown: int = 0) -> Dict[str, Any]:
    """duty_vs_prohibition 픽스처."""
    return {
        "OBLIGATION":  {"count": obligation},
        "PROHIBITION": {"count": prohibition},
        "UNKNOWN":     {"count": unknown},
    }


def _timing(
    continuous: int = 0,
    periodic: int = 0,
    before_event: int = 0,
    after_event: int = 0,
) -> Dict[str, Any]:
    """timing_character_summary 픽스처."""
    return {
        "counts": {
            "CONTINUOUS":   continuous,
            "PERIODIC":     periodic,
            "BEFORE_EVENT": before_event,
            "AFTER_EVENT":  after_event,
        }
    }


def _lp(law_name: str, obligation_count: int) -> Dict[str, Any]:
    return {"law_name": law_name, "obligation_count": obligation_count, "article_count": 1}


def _otc(**kwargs: int) -> Dict[str, int]:
    return dict(kwargs)


def _premium_visual(
    dvp: Optional[Dict] = None,
    timing_summary: Optional[Dict] = None,
    obligation_type_counts: Optional[Dict] = None,
    law_portfolio: Optional[List] = None,
) -> Dict[str, Any]:
    """premium_result_v1 with visual fields."""
    n = 10
    return {
        "version": 1,
        "contract_version": 1,
        "diagnosis": {"diagnosed_at": "2026-10-01T00:00:00+00:00"},
        "profile": {
            "company_name": "시각화 테스트 사업장",
            "sector": "CONSTRUCTION",
            "workers": 50,
            "floor_area": None,
            "contract_amount_eok": None,
            "construction_type": None,
            "building_use_type": None,
            "address": None,
            "has_excavation": False,
            "has_hazardous_material": False,
        },
        "materials": {
            "overview": {
                "total_obligation_count": n,
                "distinct_law_count": 2,
                "obligation_type_counts": obligation_type_counts or {},
            },
            "obligations": [],
            "law_portfolio": law_portfolio or [],
            "article_bundles": [],
            "legal_actor_map": [],
            "duty_vs_prohibition": dvp,
            "timing_character_summary": timing_summary,
        },
        "canonical_sources": [],
        "evidence": {"articles": []},
    }


# ── PV01: v1_band — duty_vs_prohibition 없으면 None ──────────────────────────

def test_pv01_v1_band_none_when_absent():
    result = _build_v1_band(None)
    assert result is None


# ── PV02: v1_band — 정상 데이터 → 세그먼트 반환 ─────────────────────────────

def test_pv02_v1_band_segments_present():
    result = _build_v1_band(_dvp(obligation=8, prohibition=2, unknown=0))
    assert result is not None
    keys_present = all("key" in s and "label" in s and "count" in s and "share" in s and "color" in s for s in result)
    assert keys_present


# ── PV03: v1_band — UNKNOWN count=0이면 세그먼트에서 제외 ─────────────────────

def test_pv03_v1_band_unknown_excluded_when_zero():
    result = _build_v1_band(_dvp(obligation=7, prohibition=3, unknown=0))
    assert result is not None
    keys_in_result = {s["key"] for s in result}
    assert "UNKNOWN" not in keys_in_result


# ── PV04: v1_band — 전체 total=0 → None ─────────────────────────────────────

def test_pv04_v1_band_none_when_all_zero():
    result = _build_v1_band(_dvp(obligation=0, prohibition=0, unknown=0))
    assert result is None


# ── PV05: v1_band — share 합이 ~100% (부동소수점 허용 오차 1%) ───────────────

def test_pv05_v1_band_shares_sum_to_100():
    result = _build_v1_band(_dvp(obligation=6, prohibition=3, unknown=1))
    assert result is not None
    total_share = sum(s["share"] for s in result)
    assert abs(total_share - 100.0) < 1.0


# ── PV06: v2_bars — obligation_type_counts 없으면 None ───────────────────────

def test_pv06_v2_bars_none_when_empty():
    result = _build_v2_bars({})
    assert result is None


# ── PV07: v2_bars — 내림차순 정렬 확인 ─────────────────────────────────────

def test_pv07_v2_bars_sorted_descending():
    result = _build_v2_bars(_otc(INSPECTION=5, REPORTING=2, TRAINING=8))
    assert result is not None
    counts = [r["count"] for r in result]
    assert counts == sorted(counts, reverse=True)


# ── PV08: v2_bars — count=0 항목 제외 ───────────────────────────────────────

def test_pv08_v2_bars_zero_excluded():
    result = _build_v2_bars(_otc(INSPECTION=5, REPORTING=0))
    assert result is not None
    assert all(r["count"] > 0 for r in result)


# ── PV09: v3_data — law_portfolio 비어있으면 None ────────────────────────────

def test_pv09_v3_data_none_when_empty():
    result = _build_v3_data([])
    assert result is None


# ── PV10: v3_data — ≤5 법령 → mode=ring + ring_gradient 존재 ────────────────

def test_pv10_v3_data_ring_mode_le5():
    portfolio = [_lp(f"법령{i}", 3) for i in range(4)]
    result = _build_v3_data(portfolio)
    assert result is not None
    assert result["mode"] == "ring"
    assert "ring_gradient" in result
    assert result["ring_gradient"].startswith("conic-gradient")


# ── PV11: v3_data — ≥6 법령 → mode=bars + ring_gradient 없음 ────────────────

def test_pv11_v3_data_bars_mode_ge6():
    portfolio = [_lp(f"법령{i}", 2) for i in range(7)]
    result = _build_v3_data(portfolio)
    assert result is not None
    assert result["mode"] == "bars"
    assert "ring_gradient" not in result


# ── PV12: v3_data — 세그먼트 share 합이 ~100% ────────────────────────────────

def test_pv12_v3_data_shares_sum_to_100():
    portfolio = [_lp("법A", 5), _lp("법B", 3), _lp("법C", 2)]
    result = _build_v3_data(portfolio)
    assert result is not None
    total = sum(s["share"] for s in result["segments"])
    assert abs(total - 100.0) < 1.0


# ── PV13: v4_grid — non-zero 카테고리 1개 이하 → None ─────────────────────

def test_pv13_v4_grid_none_when_one_category():
    result = _build_v4_grid(_timing(continuous=10))
    assert result is None


def test_pv13b_v4_grid_none_when_zero_all():
    result = _build_v4_grid(_timing())
    assert result is None


# ── PV14: v4_grid — ≥2 non-zero → 목록 반환 ────────────────────────────────

def test_pv14_v4_grid_returned_ge2():
    result = _build_v4_grid(_timing(continuous=5, periodic=3))
    assert result is not None
    assert len(result) == 2
    assert all("label" in r and "count" in r for r in result)


# ── PV15: v4_grid — zero 카테고리 제외 ──────────────────────────────────────

def test_pv15_v4_grid_zero_excluded():
    result = _build_v4_grid(_timing(continuous=5, periodic=0, before_event=3, after_event=0))
    assert result is not None
    assert all(r["count"] > 0 for r in result)
    assert len(result) == 2


# ── PV16: build_paid_result_pdf_view_v1 — visual 키 존재 (regression gate) ──

def test_pv16_view_model_visual_keys_present():
    premium = _premium_visual(
        dvp=_dvp(obligation=8, prohibition=2),
        timing_summary=_timing(continuous=5, periodic=3),
        obligation_type_counts=_otc(INSPECTION=5, REPORTING=5),
        law_portfolio=[_lp("산업안전보건법", 8), _lp("소방시설법", 2)],
    )
    view = build_paid_result_pdf_view_v1(premium)
    for key in ("v1_band", "v2_bars", "v3_data", "v4_grid"):
        assert key in view, f"키 없음: {key}"
    assert view["v1_band"] is not None
    assert view["v2_bars"] is not None
    assert view["v3_data"] is not None
    assert view["v4_grid"] is not None
