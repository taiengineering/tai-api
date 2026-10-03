"""tests/test_paid_result_pdf_router_v1.py — RT01~RT08 + TMPL01 + SG01~SG04
WO-WP04-PDF-PREMIUM-CONTRACT-REPOINT-001 PATCH-1

Router unit tests: GET /diagnosis/report-pdf/{token}
DB/LEG/Gotenberg 실호출 0. asyncio.run() + patch 사용.

RT01  missing token → 404
RT02  inactive → 410
RT03  FREE tier → 402
RT04  PAID happy path → 200 application/pdf, call order verified
RT05  product builder exception → 503, no Gotenberg
RT06  projection exception → 503, no Gotenberg
RT07  Gotenberg called only on paid happy path
RT08  register_generated exception → PDF still returned

TMPL01  presenter → _render_html: key values in rendered HTML
SG01    no ob_labels / APPOINT / EDUCATE / TRAINING in template source
SG02    no raw enum customer display in rendered HTML
SG03    no forbidden legacy fields in rendered HTML
SG04    cross-output: overview numbers == view numbers
"""
from __future__ import annotations

import asyncio
import os
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── 픽스처 헬퍼 ─────────────────────────────────────────────────────────────


def _make_rec(
    *,
    token: str = "abcdef01",
    tier_code: str = "CONSTRUCTION_PAID",
    status: str = "ACTIVE",
) -> Dict[str, Any]:
    return {
        "id": "rec-uuid-001",
        "public_token": token,
        "tier_code": tier_code,
        "status": status,
        "expires_at": None,
        "created_at": "2026-10-01T00:00:00+00:00",
        "source_type": "WEB",
        "input_data": {"company_id": "co-001"},
        "full_result": {},
    }


def _make_premium(n_obligations: int = 2) -> Dict[str, Any]:
    obs = [
        {
            "ref": i,
            "legal": {"law_name": "산업안전보건법", "law_article": f"제{i}조"},
            "classification": {"obligation_type": "ACTION"},
            "presentation": {
                "action": f"조치사항 {i}",
                "actor": "사업주",
                "timing": "상시",
                "cycle": None,
                "condition": None,
                "how": None,
                "where": None,
            },
            "legal_time_normalized": {
                "version": "v1",
                "timing": {"source_text": f"  상시 원문 {i}  ", "status": "OK"},
            },
        }
        for i in range(1, n_obligations + 1)
    ]
    return {
        "version": 1,
        "contract_version": 1,
        "diagnosis": {"diagnosed_at": "2026-10-01T00:00:00+00:00"},
        "profile": {
            "company_name": "테스트 건설",
            "sector": "CONSTRUCTION",
            "workers": 50,
            "floor_area": None,
            "contract_amount_eok": 30,
            "construction_type": "건축",
            "building_use_type": None,
            "address": "서울시 강남구",
            "has_excavation": True,
            "has_hazardous_material": False,
        },
        "materials": {
            "overview": {
                "total_obligation_count": n_obligations,
                "distinct_law_count": 1,
                "obligation_type_counts": {"ACTION": n_obligations},
            },
            "obligations": obs,
            "law_portfolio": [
                {"law_name": "산업안전보건법", "obligation_count": n_obligations, "article_count": n_obligations}
            ],
            "article_bundles": [],
            "legal_actor_map": [{"actor": "사업주", "count": n_obligations}],
        },
        "canonical_sources": [{"ref": 1, "text": "제1조 원문 텍스트 그대로"}],
        "evidence": {
            "articles": [
                {
                    "law_name": "산업안전보건법",
                    "article_no": 1,
                    "article_sub_no": None,
                    "article_title": "목적",
                    "article_text": "이 법은 산업 안전을 위한 것이다.",
                    "related_refs": [1],
                }
            ]
        },
    }


def _fake_supabase(*, data=None):
    mock_execute = MagicMock()
    mock_execute.data = data if data is not None else []
    mock_table = MagicMock()
    mock_table.select.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.limit.return_value = mock_table
    mock_table.execute.return_value = mock_execute
    supabase = MagicMock()
    supabase.table.return_value = mock_table
    return supabase


# ── RT01: missing token → 404 ────────────────────────────────────────────────

def test_rt01_missing_token_404():
    from fastapi import HTTPException
    from routers.diagnosis_report import get_paid_report_pdf

    with patch("routers.diagnosis_report.get_supabase", return_value=_fake_supabase(data=[])), \
         patch("routers.diagnosis_report.build_paid_result_product_v1") as mock_prod:
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(get_paid_report_pdf("nonexistent-token"))
        assert exc_info.value.status_code == 404
        mock_prod.assert_not_called()


# ── RT02: inactive → 410 ─────────────────────────────────────────────────────

def test_rt02_inactive_410():
    from fastapi import HTTPException
    from routers.diagnosis_report import get_paid_report_pdf

    rec = _make_rec(status="INACTIVE")
    with patch("routers.diagnosis_report.get_supabase", return_value=_fake_supabase(data=[rec])), \
         patch("routers.diagnosis_report.build_paid_result_product_v1") as mock_prod, \
         patch("routers.diagnosis_report._generate_pdf") as mock_pdf:
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(get_paid_report_pdf(rec["public_token"]))
        assert exc_info.value.status_code == 410
        mock_prod.assert_not_called()
        mock_pdf.assert_not_called()


# ── RT03: FREE tier → 402 ─────────────────────────────────────────────────────

@pytest.mark.parametrize("tier_code", [
    "BUILDING_FREE", "INDUSTRY_FREE", "CONSTRUCTION_FREE", "free", "FREE",
    "SOMETHING_FREE_TIER",
])
def test_rt03_free_tier_402(tier_code):
    from fastapi import HTTPException
    from routers.diagnosis_report import get_paid_report_pdf

    rec = _make_rec(tier_code=tier_code)
    with patch("routers.diagnosis_report.get_supabase", return_value=_fake_supabase(data=[rec])), \
         patch("routers.diagnosis_report.build_paid_result_product_v1") as mock_prod, \
         patch("routers.diagnosis_report._generate_pdf") as mock_pdf:
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(get_paid_report_pdf(rec["public_token"]))
        assert exc_info.value.status_code == 402
        mock_prod.assert_not_called()
        mock_pdf.assert_not_called()


# ── RT04: PAID happy path → 200 application/pdf ──────────────────────────────

def test_rt04_paid_happy_path():
    from fastapi.responses import Response
    from routers.diagnosis_report import get_paid_report_pdf

    rec = _make_rec()
    premium = _make_premium()
    call_log = []

    def fake_product(row):
        call_log.append("product")
        return {"_product": True}

    def fake_projection(product):
        call_log.append("projection")
        return premium

    def fake_view(prem):
        from services.paid_result_pdf_view_v1 import build_paid_result_pdf_view_v1
        call_log.append("view")
        return build_paid_result_pdf_view_v1(prem)

    def fake_render(template_vars):
        call_log.append("render")
        return "<html>fake</html>"

    async def fake_generate_pdf(html):
        call_log.append("gotenberg")
        return b"%PDF-fake"

    with patch("routers.diagnosis_report.get_supabase", return_value=_fake_supabase(data=[rec])), \
         patch("routers.diagnosis_report.build_paid_result_product_v1", side_effect=fake_product), \
         patch("routers.diagnosis_report.build_public_premium_result_v1", side_effect=fake_projection), \
         patch("routers.diagnosis_report.build_paid_result_pdf_view_v1", side_effect=fake_view), \
         patch("routers.diagnosis_report._render_html", side_effect=fake_render), \
         patch("routers.diagnosis_report._generate_pdf", new=fake_generate_pdf), \
         patch("services.document_svc.register_generated", new=AsyncMock()):
        result = asyncio.run(get_paid_report_pdf(rec["public_token"]))

    assert isinstance(result, Response)
    assert result.media_type == "application/pdf"
    assert result.body == b"%PDF-fake"
    assert call_log[:4] == ["product", "projection", "view", "render"]
    assert "gotenberg" in call_log


# ── RT05: product builder exception → 503, no Gotenberg ─────────────────────

def test_rt05_product_failure_503():
    from fastapi import HTTPException
    from routers.diagnosis_report import get_paid_report_pdf

    rec = _make_rec()
    gotenberg_called = []

    async def spy_gotenberg(html):
        gotenberg_called.append(True)
        return b"%PDF"

    with patch("routers.diagnosis_report.get_supabase", return_value=_fake_supabase(data=[rec])), \
         patch("routers.diagnosis_report.build_paid_result_product_v1",
               side_effect=RuntimeError("product build failed")), \
         patch("routers.diagnosis_report._generate_pdf", new=spy_gotenberg):
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(get_paid_report_pdf(rec["public_token"]))
    assert exc_info.value.status_code == 503
    assert gotenberg_called == []


# ── RT06: projection exception → 503 ─────────────────────────────────────────

def test_rt06_projection_failure_503():
    from fastapi import HTTPException
    from routers.diagnosis_report import get_paid_report_pdf

    rec = _make_rec()
    gotenberg_called = []

    async def spy_gotenberg(html):
        gotenberg_called.append(True)
        return b"%PDF"

    with patch("routers.diagnosis_report.get_supabase", return_value=_fake_supabase(data=[rec])), \
         patch("routers.diagnosis_report.build_paid_result_product_v1", return_value={}), \
         patch("routers.diagnosis_report.build_public_premium_result_v1",
               side_effect=RuntimeError("projection failed")), \
         patch("routers.diagnosis_report._generate_pdf", new=spy_gotenberg):
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(get_paid_report_pdf(rec["public_token"]))
    assert exc_info.value.status_code == 503
    assert gotenberg_called == []


# ── RT07: Gotenberg called only on paid happy path ───────────────────────────

def test_rt07_gotenberg_only_on_paid_path():
    from fastapi import HTTPException
    from routers.diagnosis_report import get_paid_report_pdf

    gotenberg_calls = []

    async def spy_gotenberg(html):
        gotenberg_calls.append(html)
        return b"%PDF"

    # FREE
    rec_free = _make_rec(tier_code="FREE")
    with patch("routers.diagnosis_report.get_supabase", return_value=_fake_supabase(data=[rec_free])), \
         patch("routers.diagnosis_report._generate_pdf", new=spy_gotenberg):
        with pytest.raises(HTTPException):
            asyncio.run(get_paid_report_pdf(rec_free["public_token"]))
    assert gotenberg_calls == []

    # inactive
    rec_inactive = _make_rec(status="INACTIVE")
    with patch("routers.diagnosis_report.get_supabase", return_value=_fake_supabase(data=[rec_inactive])), \
         patch("routers.diagnosis_report._generate_pdf", new=spy_gotenberg):
        with pytest.raises(HTTPException):
            asyncio.run(get_paid_report_pdf(rec_inactive["public_token"]))
    assert gotenberg_calls == []

    # missing
    with patch("routers.diagnosis_report.get_supabase", return_value=_fake_supabase(data=[])), \
         patch("routers.diagnosis_report._generate_pdf", new=spy_gotenberg):
        with pytest.raises(HTTPException):
            asyncio.run(get_paid_report_pdf("missing-token"))
    assert gotenberg_calls == []

    # product failure
    rec_paid = _make_rec()
    with patch("routers.diagnosis_report.get_supabase", return_value=_fake_supabase(data=[rec_paid])), \
         patch("routers.diagnosis_report.build_paid_result_product_v1",
               side_effect=RuntimeError("fail")), \
         patch("routers.diagnosis_report._generate_pdf", new=spy_gotenberg):
        with pytest.raises(HTTPException):
            asyncio.run(get_paid_report_pdf(rec_paid["public_token"]))
    assert gotenberg_calls == []


# ── RT08: register_generated exception → PDF still returned ──────────────────

def test_rt08_document_registration_failure_pdf_ok():
    from fastapi.responses import Response
    from routers.diagnosis_report import get_paid_report_pdf

    rec = _make_rec()
    premium = _make_premium()

    with patch("routers.diagnosis_report.get_supabase", return_value=_fake_supabase(data=[rec])), \
         patch("routers.diagnosis_report.build_paid_result_product_v1", return_value={}), \
         patch("routers.diagnosis_report.build_public_premium_result_v1", return_value=premium), \
         patch("routers.diagnosis_report._render_html", return_value="<html>ok</html>"), \
         patch("routers.diagnosis_report._generate_pdf", new=AsyncMock(return_value=b"%PDF-ok")), \
         patch("services.document_svc.register_generated",
               new=AsyncMock(side_effect=RuntimeError("storage failure"))):
        result = asyncio.run(get_paid_report_pdf(rec["public_token"]))

    assert isinstance(result, Response)
    assert result.media_type == "application/pdf"
    assert result.body == b"%PDF-ok"


# ── TMPL01: presenter → _render_html — key values in rendered HTML ───────────

def test_tmpl01_render_html_contains_key_values():
    from routers.diagnosis_report import _render_html
    from services.paid_result_pdf_view_v1 import build_paid_result_pdf_view_v1

    premium = _make_premium(n_obligations=2)
    view = build_paid_result_pdf_view_v1(premium)

    template_vars = {
        "report_date": "2026년 10월 03일",
        "diagnosed_at": view["diagnosed_at"],
        "profile": view["profile"],
        "total_obligation_count": view["total_obligation_count"],
        "distinct_law_count": view["distinct_law_count"],
        "obligation_type_counts": view["obligation_type_counts"],
        "obligations": view["obligations"],
        "law_portfolio": view["law_portfolio"],
        "article_bundles": view["article_bundles"],
        "legal_actor_map": view["legal_actor_map"],
        "evidence": view["evidence"],
    }
    html = _render_html(template_vars)

    assert "조치사항 1" in html                     # presentation.action
    assert "산업안전보건법" in html                   # law_name
    assert "제1조" in html                          # law_article
    assert "사업주" in html                          # actor
    assert "상시 원문 1" in html                     # Legal Time source_text EXACT
    assert "제1조 원문 텍스트 그대로" in html           # canonical source_text
    assert "이 법은 산업 안전을 위한 것이다" in html    # evidence article_text


# ── SG01: no PDF-only type dictionary in template source ─────────────────────

def test_sg01_no_ob_labels_in_template():
    tmpl_path = os.path.join(
        os.path.dirname(__file__), "..", "templates", "diagnosis_report_paid_v2.html"
    )
    with open(tmpl_path, encoding="utf-8") as f:
        source = f.read()

    forbidden = ["ob_labels", "EDUCATE", "TRAINING", "ob-APPOINT", "ob-PROHIBIT"]
    for token in forbidden:
        assert token not in source, f"forbidden token in template: {token!r}"


# ── SG02: no raw enum customer display in rendered HTML ──────────────────────

def test_sg02_no_raw_enum_in_rendered_html():
    from routers.diagnosis_report import _render_html
    from services.paid_result_pdf_view_v1 import build_paid_result_pdf_view_v1

    premium = _make_premium()
    premium["materials"]["obligations"][0]["classification"]["obligation_type"] = "APPOINT"
    premium["materials"]["overview"]["obligation_type_counts"] = {"APPOINT": 2}
    view = build_paid_result_pdf_view_v1(premium)

    template_vars = {
        "report_date": "2026년 10월 03일",
        "diagnosed_at": view["diagnosed_at"],
        "profile": view["profile"],
        "total_obligation_count": view["total_obligation_count"],
        "distinct_law_count": view["distinct_law_count"],
        "obligation_type_counts": view["obligation_type_counts"],
        "obligations": view["obligations"],
        "law_portfolio": view["law_portfolio"],
        "article_bundles": view["article_bundles"],
        "legal_actor_map": view["legal_actor_map"],
        "evidence": view["evidence"],
    }
    html = _render_html(template_vars)

    for raw_enum in ("APPOINT", "INSPECT", "PROHIBIT", "EDUCATE"):
        assert raw_enum not in html, f"raw enum exposed in HTML: {raw_enum!r}"


# ── SG03: no forbidden legacy fields in rendered HTML ─────────────────────────

def test_sg03_no_legacy_fields_in_html():
    from routers.diagnosis_report import _render_html
    from services.paid_result_pdf_view_v1 import build_paid_result_pdf_view_v1

    premium = _make_premium()
    view = build_paid_result_pdf_view_v1(premium)

    template_vars = {
        "report_date": "2026년 10월 03일",
        "diagnosed_at": view["diagnosed_at"],
        "profile": view["profile"],
        "total_obligation_count": view["total_obligation_count"],
        "distinct_law_count": view["distinct_law_count"],
        "obligation_type_counts": view["obligation_type_counts"],
        "obligations": view["obligations"],
        "law_portfolio": view["law_portfolio"],
        "article_bundles": view["article_bundles"],
        "legal_actor_map": view["legal_actor_map"],
        "evidence": view["evidence"],
    }
    html = _render_html(template_vars)

    for field in (
        "penalty_summary", "submit_org_label", "qualification_required",
        "compiler_penalties", "compiler_schedule_hints", "risk_level",
        "rules_table", "applicable_rules",
    ):
        assert field not in html, f"legacy field in rendered HTML: {field!r}"


# ── SG04: cross-output — overview numbers == view numbers ────────────────────

def test_sg04_cross_output_overview_parity():
    from services.paid_result_pdf_view_v1 import build_paid_result_pdf_view_v1

    premium = _make_premium(n_obligations=3)
    view = build_paid_result_pdf_view_v1(premium)

    assert view["total_obligation_count"] == premium["materials"]["overview"]["total_obligation_count"]
    assert view["distinct_law_count"] == premium["materials"]["overview"]["distinct_law_count"]

    for i, ob_row in enumerate(view["obligations"]):
        src = premium["materials"]["obligations"][i]
        assert ob_row["ref"] == src["ref"]
        assert ob_row["law_name"] == src["legal"]["law_name"]
        assert ob_row["law_article"] == src["legal"]["law_article"]
