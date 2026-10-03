"""tests/test_paid_result_pdf_visual_v1.py — PV01~PV28
WO-MAIN-PAID-PDF-VISUAL-04 + PATCH-1

Visual builder 단위 테스트 + template render 계약 테스트.
INPUT = premium_result_v1 with materials.duty_vs_prohibition +
        materials.timing_character_summary.
실 LEG/DB 0.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import pytest

from services.paid_result_pdf_view_v1 import (
    _build_v1_band,
    _build_v2_bars,
    _build_v3_data,
    _build_v4_grid,
    build_paid_result_pdf_view_v1,
)

_TMPL_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")


# ── 픽스처 헬퍼 ──────────────────────────────────────────────────────────────

def _dvp(obligation: int = 0, prohibition: int = 0, unknown: int = 0) -> Dict[str, Any]:
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
                "distinct_law_count": len(law_portfolio) if law_portfolio else 0,
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


def _render(
    legal_actor_map: Optional[List] = None,
    article_bundles: Optional[List] = None,
    distinct_law_count: int = 1,
    total_obligation_count: int = 10,
    v1_band: Optional[List] = None,
    v2_bars: Optional[List] = None,
    v3_data: Optional[Dict] = None,
    v4_grid: Optional[List] = None,
) -> str:
    """Render the PDF template for contract/regression tests."""
    from jinja2 import Environment, FileSystemLoader, select_autoescape
    env = Environment(
        loader=FileSystemLoader(_TMPL_DIR),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("diagnosis_report_paid_v2.html")
    return template.render(
        report_date="2026년 10월 03일",
        diagnosed_at=None,
        profile={
            "company_name": "테스트", "sector": None, "workers": None,
            "floor_area": None, "contract_amount_eok": None, "construction_type": None,
            "building_use_type": None, "address": None, "has_excavation": None,
            "has_hazardous_material": None,
        },
        total_obligation_count=total_obligation_count,
        distinct_law_count=distinct_law_count,
        obligation_type_counts={},
        obligations=[],
        law_portfolio=[],
        article_bundles=article_bundles or [],
        legal_actor_map=legal_actor_map or [],
        evidence=[],
        v1_band=v1_band,
        v2_bars=v2_bars,
        v3_data=v3_data,
        v4_grid=v4_grid,
    )


# ── PV01: v1_band — duty_vs_prohibition 없으면 None ──────────────────────────

def test_pv01_v1_band_none_when_absent():
    assert _build_v1_band(None) is None


# ── PV02: v1_band — 정상 데이터 → 세그먼트 반환 ─────────────────────────────

def test_pv02_v1_band_segments_present():
    result = _build_v1_band(_dvp(obligation=8, prohibition=2, unknown=0))
    assert result is not None
    assert all("key" in s and "label" in s and "count" in s and "share" in s and "color" in s
               for s in result)


# ── PV03: v1_band — UNKNOWN count=0이면 제외 ─────────────────────────────────

def test_pv03_v1_band_unknown_excluded_when_zero():
    result = _build_v1_band(_dvp(obligation=7, prohibition=3, unknown=0))
    assert result is not None
    assert "UNKNOWN" not in {s["key"] for s in result}


# ── PV04: v1_band — total=0 → None ───────────────────────────────────────────

def test_pv04_v1_band_none_when_all_zero():
    assert _build_v1_band(_dvp()) is None


# ── PV05: v1_band — share 합 ~100% ───────────────────────────────────────────

def test_pv05_v1_band_shares_sum_to_100():
    result = _build_v1_band(_dvp(obligation=6, prohibition=3, unknown=1))
    assert result is not None
    assert abs(sum(s["share"] for s in result) - 100.0) < 1.0


# ── PV06: v2_bars — 빈 dict → None ───────────────────────────────────────────

def test_pv06_v2_bars_none_when_empty():
    assert _build_v2_bars({}) is None


# ── PV07: v2_bars — 데이터 있어도 None (canonical label source 없음) ──────────

def test_pv07_v2_bars_none_regardless_of_input():
    """V2 omitted: no approved canonical label source exists in repo."""
    assert _build_v2_bars(_otc(INSPECTION=5, REPORTING=2, TRAINING=8)) is None


# ── PV08: v2_bars — canonical enum 입력에도 None ──────────────────────────────

def test_pv08_v2_bars_none_with_canonical_enums():
    """Canonical PAID enum values must not be exposed raw to customers."""
    assert _build_v2_bars({"ACTION": 5, "PROHIBIT": 3, "NOTIFY": 1}) is None


# ── PV09: v3_data — law_portfolio 비어있으면 None ────────────────────────────

def test_pv09_v3_data_none_when_empty():
    assert _build_v3_data([]) is None


# ── PV10: v3_data — 4개 법령 → mode=ring + ring_gradient ─────────────────────

def test_pv10_v3_data_ring_mode_4laws():
    result = _build_v3_data([_lp(f"법령{i}", 3) for i in range(4)])
    assert result is not None
    assert result["mode"] == "ring"
    assert result["ring_gradient"].startswith("conic-gradient")


# ── PV11: v3_data — 7개 법령 → mode=bars + ring_gradient 없음 ───────────────

def test_pv11_v3_data_bars_mode_7laws():
    result = _build_v3_data([_lp(f"법령{i}", 2) for i in range(7)])
    assert result is not None
    assert result["mode"] == "bars"
    assert "ring_gradient" not in result


# ── PV12: v3_data — share 합 ~100% ───────────────────────────────────────────

def test_pv12_v3_data_shares_sum_to_100():
    result = _build_v3_data([_lp("법A", 5), _lp("법B", 3), _lp("법C", 2)])
    assert result is not None
    assert abs(sum(s["share"] for s in result["segments"]) - 100.0) < 1.0


# ── PV13: v4_grid — non-zero 카테고리 1개 이하 → None ─────────────────────

def test_pv13_v4_grid_none_when_one_category():
    assert _build_v4_grid(_timing(continuous=10)) is None


def test_pv13b_v4_grid_none_when_zero_all():
    assert _build_v4_grid(_timing()) is None


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


# ── PV16: view model — visual 키 존재 + v2_bars는 None (regression gate) ────

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
    assert view["v2_bars"] is None   # canonical label source absent → None by design
    assert view["v3_data"] is not None
    assert view["v4_grid"] is not None


# ── PV17: V1 단일 카테고리 → None (eligibility) ─────────────────────────────

def test_pv17_v1_band_single_category_none():
    assert _build_v1_band(_dvp(obligation=10, prohibition=0, unknown=0)) is None
    assert _build_v1_band(_dvp(obligation=0, prohibition=5, unknown=0)) is None


# ── PV18: V2 canonical 추출 enum → None (raw enum 안전) ──────────────────────

def test_pv18_v2_canonical_raw_enum_none():
    """PAID canonical 7종 enum 입력 → None; 고객 PDF에 raw enum 노출 0."""
    canonical_enums = {"ACTION": 5, "PROHIBIT": 3, "NOTIFY": 2,
                       "INSPECT": 4, "APPOINT": 1, "TRAINING": 2, "REPORT": 3}
    assert _build_v2_bars(canonical_enums) is None


# ── PV19: V2 — 독립 비승인 사전 없음 ────────────────────────────────────────

def test_pv19_v2_no_independent_dict():
    """V2는 항상 None — PDF 독자 의미사전 생성 금지 원칙 준수."""
    for otc in [{"INSPECTION": 5}, {"any_key": 1}, {"X": 100, "Y": 200}]:
        assert _build_v2_bars(otc) is None


# ── PV20: V2 — None 입력도 None ──────────────────────────────────────────────

def test_pv20_v2_none_input_also_none():
    assert _build_v2_bars(None) is None
    assert _build_v2_bars({}) is None


# ── PV21: V3 — 1개 법령 → None ───────────────────────────────────────────────

def test_pv21_v3_one_law_none():
    assert _build_v3_data([_lp("산업안전보건법", 10)]) is None
    assert _build_v3_data([]) is None


# ── PV22: V3 — 5개 법령 → ring ───────────────────────────────────────────────

def test_pv22_v3_five_laws_ring():
    result = _build_v3_data([_lp(f"법령{i}", 3) for i in range(5)])
    assert result is not None
    assert result["mode"] == "ring"
    assert "ring_gradient" in result


# ── PV23: V3 — 6개 법령 → bars (off-by-one 수정 확인) ───────────────────────

def test_pv23_v3_six_laws_bars():
    result = _build_v3_data([_lp(f"법령{i}", 2) for i in range(6)])
    assert result is not None
    assert result["mode"] == "bars"
    assert "ring_gradient" not in result


# ── PV24: V5 — [:8] 절단 없음 — 10개 전부 렌더 ───────────────────────────────

def test_pv24_v5_no_truncation_all_actors_in_html():
    actors = [{"actor": f"주체{i:02d}", "count": i + 1} for i in range(10)]
    html = _render(legal_actor_map=actors)
    for i in range(10):
        assert f"주체{i:02d}" in html, f"주체{i:02d} 누락"


# ── PV25: V5 — 모든 actor count 렌더 ─────────────────────────────────────────

def test_pv25_v5_all_actor_counts_rendered():
    actors = [{"actor": f"주체{i:02d}", "count": i + 1} for i in range(10)]
    html = _render(legal_actor_map=actors)
    rendered = sum(1 for i in range(10) if f"주체{i:02d}" in html)
    assert rendered == 10


# ── PV26: V5 — card grid 구조 확인 ───────────────────────────────────────────

def test_pv26_v5_card_grid_structure():
    actors = [{"actor": "사업주", "count": 7}, {"actor": "관리감독자", "count": 3}]
    html = _render(legal_actor_map=actors)
    assert "grid-template-columns" in html
    assert "사업주" in html
    assert "관리감독자" in html


# ── PV27: V6 — 복수 법령 시 law_name 표시 ────────────────────────────────────

def test_pv27_v6_multi_law_shows_law_name():
    bundles = [
        {"law_name": "유니크법령A", "law_article": "제15조", "count": 5},
        {"law_name": "유니크법령B", "law_article": "제9조", "count": 3},
    ]
    html = _render(article_bundles=bundles, distinct_law_count=2)
    assert "유니크법령A" in html
    assert "유니크법령B" in html


def test_pv27b_v6_single_law_articles_present():
    bundles = [
        {"law_name": "산업안전보건법", "law_article": "제15조", "count": 5},
        {"law_name": "산업안전보건법", "law_article": "제29조", "count": 3},
    ]
    html = _render(article_bundles=bundles, distinct_law_count=1)
    assert "제15조" in html
    assert "제29조" in html


# ── PV28: V6 — 전체 article bundles 렌더 (절단 없음) ─────────────────────────

def test_pv28_v6_all_article_bundles_rendered():
    bundles = [
        {"law_name": "산업안전보건법", "law_article": f"제{i}조", "count": i}
        for i in range(1, 9)
    ]
    html = _render(article_bundles=bundles, distinct_law_count=1, total_obligation_count=36)
    for i in range(1, 9):
        assert f"제{i}조" in html, f"제{i}조 누락"
