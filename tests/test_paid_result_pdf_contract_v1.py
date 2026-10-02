"""tests/test_paid_result_pdf_contract_v1.py — PDF01~PDF20
WO-WP04-PDF-PREMIUM-CONTRACT-REPOINT-001

INPUT = premium_result_v1 (build_public_premium_result_v1 출력 형태).
실 LEG/DB 0. router 접근 게이트 단위 테스트 포함.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import pytest

from services.paid_result_pdf_view_v1 import build_paid_result_pdf_view_v1

# ── 테스트 픽스처 헬퍼 ───────────────────────────────────────────────────────


def _ob(
    ref: int,
    *,
    law: str = "산업안전보건법",
    article: str = "제1조",
    otype: str = "ACTION",
    action: str = "기본 조치",
    actor: str = "사업주",
    timing: Optional[str] = "매월 1회",
    cycle: Optional[str] = None,
    condition: Optional[str] = None,
    how: Optional[str] = None,
    where: Optional[str] = None,
    ltn: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    ob: Dict[str, Any] = {
        "ref": ref,
        "legal": {"law_name": law, "law_article": article},
        "classification": {"obligation_type": otype},
        "presentation": {
            "action": action,
            "actor": actor,
            "timing": timing,
            "cycle": cycle,
            "condition": condition,
            "how": how,
            "where": where,
        },
    }
    if ltn is not None:
        ob["legal_time_normalized"] = ltn
    return ob


def _ltn(timing_src: Optional[str] = None, cycle_src: Optional[str] = None) -> Dict[str, Any]:
    d: Dict[str, Any] = {"version": "v1"}
    if timing_src is not None:
        d["timing"] = {"source_text": timing_src, "status": "OK", "type": "PERIODIC"}
    if cycle_src is not None:
        d["cycle"] = {"source_text": cycle_src, "status": "OK", "type": "PERIODIC"}
    return d


def _source(ref: int, text: str) -> Dict[str, Any]:
    return {"ref": ref, "text": text}


def _premium(
    obligations=None,
    evidence_articles=None,
    canonical_sources=None,
    overview_override=None,
    law_portfolio=None,
    article_bundles=None,
    legal_actor_map=None,
    company_name: str = "테스트 사업장",
    sector: str = "CONSTRUCTION",
    workers: int = 50,
) -> Dict[str, Any]:
    obs = obligations or [_ob(1), _ob(2)]
    n = len(obs)
    laws = {o["legal"]["law_name"] for o in obs if o["legal"].get("law_name")}
    overview = overview_override or {
        "total_obligation_count": n,
        "distinct_law_count": len(laws),
        "obligation_type_counts": {"ACTION": n},
    }
    return {
        "version": 1,
        "contract_version": 1,
        "diagnosis": {"diagnosed_at": "2026-10-01T00:00:00+00:00"},
        "profile": {
            "company_name": company_name,
            "sector": sector,
            "workers": workers,
            "floor_area": None,
            "contract_amount_eok": None,
            "construction_type": None,
            "building_use_type": None,
            "address": "서울시 강남구",
            "has_excavation": False,
            "has_hazardous_material": False,
        },
        "materials": {
            "overview": overview,
            "obligations": obs,
            "law_portfolio": law_portfolio or [],
            "article_bundles": article_bundles or [],
            "legal_actor_map": legal_actor_map or [],
        },
        "canonical_sources": canonical_sources or [],
        "evidence": {
            "articles": evidence_articles or [],
        },
    }


# ── PDF01: premium entry path — 출력 키 완전성 ─────────────────────────────

def test_pdf01_output_keys_complete():
    view = build_paid_result_pdf_view_v1(_premium())
    expected = {
        "pdf_view_version",
        "diagnosed_at",
        "profile",
        "total_obligation_count",
        "distinct_law_count",
        "obligation_type_counts",
        "obligations",
        "law_portfolio",
        "article_bundles",
        "legal_actor_map",
        "evidence",
    }
    assert expected.issubset(view.keys())


# ── PDF02: 레거시 법령 소스 없음 ─────────────────────────────────────────────

def test_pdf02_no_legacy_legal_source():
    view = build_paid_result_pdf_view_v1(_premium())
    forbidden = {
        "rules_table", "applicable_rules", "appointment_required",
        "inspection_required", "penalty_summary", "submit_org_label",
        "qualification_required",
    }
    assert not forbidden.intersection(view.keys())
    for ob_row in view["obligations"]:
        assert not forbidden.intersection(ob_row.keys())


# ── PDF03: overview parity — 재계산 없음 ────────────────────────────────────

def test_pdf03_overview_parity_exact():
    # overview 에 넣은 숫자가 그대로 반환되어야 한다 — 의무 리스트 건수와 달라도.
    obs = [_ob(1), _ob(2), _ob(3)]
    override = {"total_obligation_count": 99, "distinct_law_count": 7}
    view = build_paid_result_pdf_view_v1(_premium(obligations=obs, overview_override=override))
    assert view["total_obligation_count"] == 99
    assert view["distinct_law_count"] == 7


# ── PDF04: obligation cardinality ─────────────────────────────────────────────

def test_pdf04_obligation_cardinality():
    obs = [_ob(i) for i in range(5)]
    view = build_paid_result_pdf_view_v1(_premium(obligations=obs))
    assert len(view["obligations"]) == 5


# ── PDF05: action → title ─────────────────────────────────────────────────────

def test_pdf05_title_from_presentation_action():
    obs = [_ob(1, action="안전관리자 선임")]
    view = build_paid_result_pdf_view_v1(_premium(obligations=obs))
    assert view["obligations"][0]["title"] == "안전관리자 선임"


# ── PDF06: actor field ─────────────────────────────────────────────────────────

def test_pdf06_actor_from_presentation():
    obs = [_ob(1, actor="안전관리자")]
    view = build_paid_result_pdf_view_v1(_premium(obligations=obs))
    assert view["obligations"][0]["actor"] == "안전관리자"


# ── PDF07: Legal Time WP-03 timing — ltn.source_text EXACT 우선 ───────────

def test_pdf07_timing_ltn_source_text_exact():
    raw_timing = "  매분기 1회 이상  "
    ltn = _ltn(timing_src=raw_timing)
    obs = [_ob(1, timing="presentation_timing", ltn=ltn)]
    view = build_paid_result_pdf_view_v1(_premium(obligations=obs))
    assert view["obligations"][0]["timing"] == raw_timing


def test_pdf07b_timing_falls_back_to_presentation_when_ltn_absent():
    obs = [_ob(1, timing="프레젠테이션 타이밍")]
    view = build_paid_result_pdf_view_v1(_premium(obligations=obs))
    assert view["obligations"][0]["timing"] == "프레젠테이션 타이밍"


# ── PDF08: Legal Time WP-03 cycle — ltn.source_text EXACT 우선 ────────────

def test_pdf08_cycle_ltn_source_text_exact():
    raw_cycle = "  6개월마다  "
    ltn = _ltn(cycle_src=raw_cycle)
    obs = [_ob(1, cycle="ignored_cycle", ltn=ltn)]
    view = build_paid_result_pdf_view_v1(_premium(obligations=obs))
    assert view["obligations"][0]["cycle"] == raw_cycle


def test_pdf08b_cycle_falls_back_to_presentation_when_ltn_absent():
    obs = [_ob(1, cycle="연 1회")]
    view = build_paid_result_pdf_view_v1(_premium(obligations=obs))
    assert view["obligations"][0]["cycle"] == "연 1회"


# ── PDF09: canonical source EXACT ────────────────────────────────────────────

def test_pdf09_canonical_source_text_exact():
    canonical_text = "제375조(화물취급) 사업주는 화물 취급 작업을..."
    sources = [_source(ref=1, text=canonical_text)]
    obs = [_ob(1)]
    view = build_paid_result_pdf_view_v1(_premium(obligations=obs, canonical_sources=sources))
    assert view["obligations"][0]["source_text"] == canonical_text


def test_pdf09b_source_text_absent_when_ref_not_in_canonical():
    obs = [_ob(1), _ob(2)]
    sources = [_source(ref=1, text="ref1 원문")]
    view = build_paid_result_pdf_view_v1(_premium(obligations=obs, canonical_sources=sources))
    assert view["obligations"][0]["source_text"] == "ref1 원문"
    assert view["obligations"][1]["source_text"] is None


# ── PDF10: evidence rows ──────────────────────────────────────────────────────

def test_pdf10_evidence_rows_from_articles():
    articles = [
        {
            "law_name": "산업안전보건법",
            "article_no": 15,
            "article_sub_no": None,
            "article_title": "안전보건관리책임자",
            "article_text": "제15조 원문",
            "related_refs": [1],
        }
    ]
    view = build_paid_result_pdf_view_v1(_premium(evidence_articles=articles))
    assert len(view["evidence"]) == 1
    ev = view["evidence"][0]
    assert ev["law_name"] == "산업안전보건법"
    assert ev["article_no"] == 15
    assert ev["article_text"] == "제15조 원문"


def test_pdf10b_evidence_skipped_when_article_text_none():
    articles = [
        {
            "law_name": "산업안전보건법",
            "article_no": 15,
            "article_sub_no": None,
            "article_title": None,
            "article_text": None,  # 누락
            "related_refs": [],
        }
    ]
    view = build_paid_result_pdf_view_v1(_premium(evidence_articles=articles))
    assert len(view["evidence"]) == 0


def test_pdf10c_evidence_skipped_when_law_name_none():
    articles = [
        {
            "law_name": None,
            "article_no": 15,
            "article_sub_no": None,
            "article_title": None,
            "article_text": "원문",
            "related_refs": [],
        }
    ]
    view = build_paid_result_pdf_view_v1(_premium(evidence_articles=articles))
    assert len(view["evidence"]) == 0


# ── PDF11: forbidden field absent in obligations ──────────────────────────────

def test_pdf11_forbidden_fields_not_in_obligation_rows():
    forbidden = {
        "penalty_summary", "submit_org_label", "qualification_required",
        "appointment_required", "inspection_required",
        "atom_id", "source_atom_ids", "company_id", "factory_id",
    }
    obs = [_ob(1)]
    view = build_paid_result_pdf_view_v1(_premium(obligations=obs))
    for ob_row in view["obligations"]:
        assert not forbidden.intersection(ob_row.keys()), (
            f"forbidden 필드 발견: {forbidden.intersection(ob_row.keys())}"
        )


# ── PDF12: overview 숫자는 재계산하지 않는다 (fail-closed) ────────────────────

def test_pdf12_overview_numbers_not_recalculated():
    # obligations 3건이지만 overview 에 10/5 가 있으면 그것을 그대로 반환
    obs = [_ob(i) for i in range(3)]
    override = {
        "total_obligation_count": 10,
        "distinct_law_count": 5,
        "obligation_type_counts": {"ACTION": 10},
    }
    view = build_paid_result_pdf_view_v1(_premium(obligations=obs, overview_override=override))
    assert view["total_obligation_count"] == 10
    assert view["distinct_law_count"] == 5
    assert view["obligation_type_counts"]["ACTION"] == 10


# ── PDF13: ltn timing whitespace-only → presentation fallback ─────────────────

def test_pdf13_ltn_timing_whitespace_falls_back():
    ltn = {"version": "v1", "timing": {"source_text": "   ", "status": "OK"}}
    obs = [_ob(1, timing="presentation fallback", ltn=ltn)]
    view = build_paid_result_pdf_view_v1(_premium(obligations=obs))
    assert view["obligations"][0]["timing"] == "presentation fallback"


# ── PDF14: ltn cycle whitespace-only → presentation fallback ─────────────────

def test_pdf14_ltn_cycle_whitespace_falls_back():
    ltn = {"version": "v1", "cycle": {"source_text": "", "status": "OK"}}
    obs = [_ob(1, cycle="presentation cycle fallback", ltn=ltn)]
    view = build_paid_result_pdf_view_v1(_premium(obligations=obs))
    assert view["obligations"][0]["cycle"] == "presentation cycle fallback"


# ── PDF15: ltn non-string source_text → presentation fallback ────────────────

def test_pdf15_ltn_non_string_source_text_falls_back():
    ltn = {"version": "v1", "timing": {"source_text": 12345, "status": "OK"}}
    obs = [_ob(1, timing="presentation string", ltn=ltn)]
    view = build_paid_result_pdf_view_v1(_premium(obligations=obs))
    assert view["obligations"][0]["timing"] == "presentation string"


# ── PDF16: canonical source dedup — 같은 ref 에 2건이면 absent ────────────────

def test_pdf16_canonical_source_dedup_fail_closed():
    sources = [
        _source(ref=1, text="원문 첫 번째"),
        _source(ref=1, text="원문 두 번째"),  # 중복
    ]
    obs = [_ob(1)]
    view = build_paid_result_pdf_view_v1(_premium(obligations=obs, canonical_sources=sources))
    assert view["obligations"][0]["source_text"] is None


# ── PDF17: profile view construction ─────────────────────────────────────────

def test_pdf17_profile_view_fields():
    prem = _premium(company_name="테스트 건설", sector="CONSTRUCTION", workers=120)
    view = build_paid_result_pdf_view_v1(prem)
    p = view["profile"]
    assert p["company_name"] == "테스트 건설"
    assert p["workers"] == 120
    assert isinstance(p["has_excavation"], bool)
    assert isinstance(p["has_hazardous_material"], bool)


# ── PDF18: sector label mapping ───────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected_label", [
    ("BUILDING",         "건물"),
    ("INDUSTRY",         "산업"),
    ("INDUSTRIAL",       "산업"),
    ("MANUFACTURING",    "산업(제조)"),
    ("CONSTRUCTION",     "건설"),
    ("SPECIAL_FACILITY", "특정시설"),
])
def test_pdf18_sector_label_mapping(raw, expected_label):
    prem = _premium(sector=raw)
    view = build_paid_result_pdf_view_v1(prem)
    assert view["profile"]["sector"] == expected_label


# ── PDF19: diagnosed_at passthrough ──────────────────────────────────────────

def test_pdf19_diagnosed_at_passthrough():
    view = build_paid_result_pdf_view_v1(_premium())
    assert view["diagnosed_at"] == "2026-10-01T00:00:00+00:00"


# ── PDF20: empty premium → minimal output (no crash) ────────────────────────

def test_pdf20_empty_premium_no_crash():
    view = build_paid_result_pdf_view_v1({})
    assert view["total_obligation_count"] == 0
    assert view["distinct_law_count"] == 0
    assert view["obligations"] == []
    assert view["evidence"] == []
    assert view["obligation_type_counts"] == {}
