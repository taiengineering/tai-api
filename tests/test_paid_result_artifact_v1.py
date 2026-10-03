"""tests/test_paid_result_artifact_v1.py — ART-PDF-01~07 · ART-XLSX-01~09 · XART-01
WO-MAIN-PAID-ARTIFACT-03

ART-PDF-01  router source: receipt_no = public_token 완전 제거
ART-PDF-02  template source: {{ receipt_no }} 완전 제거
ART-PDF-03  template source: 접수번호 텍스트 완전 제거
ART-PDF-04  happy path: X-Report-Token 헤더 없음
ART-PDF-05  happy path: Content-Disposition filename = TAI_법령진단_상세보고서.pdf
ART-PDF-06  router source: template_vars에 receipt_no 키 없음
ART-PDF-07  _render_html: receipt_no 없이 렌더링 성공, 결과에 토큰 문자열 없음

ART-XLSX-01 SHEET_NAMES[2] = "Legal Timing"
ART-XLSX-02 SHEET_NAMES[3] = "Legal Actors"
ART-XLSX-03 OBLIGATION_COLUMNS에 "action" 포함
ART-XLSX-04 Obligations 시트에 action 컬럼 헤더 존재
ART-XLSX-05 presentation.action 값이 Obligations action 셀에 도착
ART-XLSX-06 시트명 전체가 새 SHEET_NAMES와 일치
ART-XLSX-07 Legal Timing 시트 컬럼 선두 7개 확인
ART-XLSX-08 Legal Actors 시트 컬럼 선두 확인
ART-XLSX-09 구 시트명(Schedule/Assignments) 없음

XART-01     cross-artifact: excel action == pdf view title (같은 presentation.action 원천)
"""
from __future__ import annotations

import asyncio
import io
import os
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openpyxl import load_workbook

from services.paid_result_excel_v1 import (
    OBLIGATION_COLUMNS,
    SHEET_NAMES,
    build_paid_result_excel_v1,
)
from services.paid_result_pdf_view_v1 import build_paid_result_pdf_view_v1

# ── 경로 ─────────────────────────────────────────────────────────────────────

_ROUTER_SRC_PATH = os.path.join(
    os.path.dirname(__file__), "..", "routers", "diagnosis_report.py"
)
_TMPL_PATH = os.path.join(
    os.path.dirname(__file__), "..", "templates", "diagnosis_report_paid_v2.html"
)


def _router_src() -> str:
    with open(_ROUTER_SRC_PATH, encoding="utf-8") as f:
        return f.read()


def _tmpl_src() -> str:
    with open(_TMPL_PATH, encoding="utf-8") as f:
        return f.read()


# ── 픽스처 ──────────────────────────────────────────────────────────────────

def _make_rec(token: str = "abcdef0102030405") -> Dict[str, Any]:
    return {
        "id": "rec-art-001",
        "public_token": token,
        "tier_code": "CONSTRUCTION_PAID",
        "status": "ACTIVE",
        "expires_at": None,
        "created_at": "2026-10-03T00:00:00+00:00",
        "source_type": "WEB",
        "input_data": {"company_id": "co-art-001"},
        "full_result": {},
    }


def _make_premium() -> Dict[str, Any]:
    return {
        "version": 1,
        "contract_version": 1,
        "diagnosis": {"diagnosed_at": "2026-10-03T00:00:00+00:00"},
        "profile": {
            "company_name": "아티팩트 건설",
            "sector": "CONSTRUCTION",
            "workers": 30,
            "floor_area": None,
            "contract_amount_eok": 20,
            "construction_type": "건축",
            "building_use_type": None,
            "address": "서울시 중구",
            "has_excavation": False,
            "has_hazardous_material": False,
        },
        "materials": {
            "overview": {
                "total_obligation_count": 2,
                "distinct_law_count": 1,
                "obligation_type_counts": {"ACTION": 2},
            },
            "obligations": [
                {
                    "ref": 1,
                    "legal": {"law_name": "산업안전보건법", "law_article": "제1조"},
                    "classification": {"content_type": "OBLIGATION", "obligation_type": "ACTION"},
                    "presentation": {
                        "action": "안전난간 설치",
                        "actor": "사업주",
                        "timing": "설치 전",
                        "cycle": None,
                        "condition": None,
                        "how": None,
                        "where": None,
                    },
                    "duty": {"who": "사업주", "recipient": None, "where": None, "how": None},
                    "applicability": {"condition": None},
                    "verification": {"check_result": "VERIFIED"},
                    "timing": {"when": "설치 전", "inspection_cycle": None, "raw_cycle": None, "conflict": False},
                    "legal_time_normalized": {
                        "version": "v1",
                        "timing": {"source_text": "설치 전 원문", "status": "OK"},
                    },
                },
                {
                    "ref": 2,
                    "legal": {"law_name": "산업안전보건법", "law_article": "제2조"},
                    "classification": {"content_type": "OBLIGATION", "obligation_type": "INSPECT"},
                    "presentation": {
                        "action": "안전점검 실시",
                        "actor": "관리감독자",
                        "timing": "매월",
                        "cycle": None,
                        "condition": None,
                        "how": None,
                        "where": None,
                    },
                    "duty": {"who": "관리감독자", "recipient": None, "where": None, "how": None},
                    "applicability": {"condition": None},
                    "verification": {"check_result": "VERIFIED"},
                    "timing": {"when": "매월", "inspection_cycle": "1개월", "raw_cycle": "매월", "conflict": False},
                    "legal_time_normalized": {
                        "version": "v1",
                        "timing": {"source_text": "매월 원문", "status": "OK"},
                    },
                },
            ],
            "law_portfolio": [
                {"law_name": "산업안전보건법", "obligation_count": 2, "article_count": 2}
            ],
            "article_bundles": [],
            "legal_actor_map": [{"actor": "사업주", "count": 1}, {"actor": "관리감독자", "count": 1}],
        },
        "canonical_sources": [
            {"ref": 1, "text": "제1조 원문 텍스트"},
            {"ref": 2, "text": "제2조 원문 텍스트"},
        ],
        "evidence": {
            "articles": [
                {
                    "law_name": "산업안전보건법",
                    "article_no": 1,
                    "article_sub_no": None,
                    "article_title": "목적",
                    "article_text": "이 법은 산업 안전을 위한 것이다.",
                    "related_refs": [1, 2],
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


def _load(raw: bytes):
    return load_workbook(io.BytesIO(raw), data_only=False)


def _header(ws):
    return [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]


def _rows(ws, skip_header=True):
    values = list(ws.iter_rows(values_only=True))
    return values[1:] if skip_header and values else values


# ── ART-PDF-01~07 ────────────────────────────────────────────────────────────

def test_art_pdf_01_no_receipt_no_assignment_in_router():
    src = _router_src()
    assert "receipt_no = public_token" not in src, \
        "router: receipt_no = public_token 토큰 노출 코드 남아있음"


def test_art_pdf_02_no_receipt_no_jinja_in_template():
    src = _tmpl_src()
    assert "receipt_no" not in src, \
        "template: {{ receipt_no }} Jinja2 변수 참조 남아있음"


def test_art_pdf_03_no_접수번호_in_template():
    src = _tmpl_src()
    assert "접수번호" not in src, \
        "template: 접수번호 텍스트 남아있음"


def test_art_pdf_04_no_x_report_token_header():
    from fastapi.responses import Response
    from routers.diagnosis_report import get_paid_report_pdf

    rec = _make_rec()
    premium = _make_premium()

    with patch("routers.diagnosis_report.get_supabase", return_value=_fake_supabase(data=[rec])), \
         patch("routers.diagnosis_report.build_paid_result_product_v1", return_value={}), \
         patch("routers.diagnosis_report.build_public_premium_result_v1", return_value=premium), \
         patch("routers.diagnosis_report._render_html", return_value="<html>ok</html>"), \
         patch("routers.diagnosis_report._generate_pdf", new=AsyncMock(return_value=b"%PDF-art")), \
         patch("services.document_svc.register_generated", new=AsyncMock()):
        result = asyncio.run(get_paid_report_pdf(rec["public_token"]))

    assert isinstance(result, Response)
    assert "X-Report-Token" not in result.headers, \
        "X-Report-Token 헤더가 응답에 포함됨"


def test_art_pdf_05_fixed_filename_no_token():
    from urllib.parse import unquote
    from fastapi.responses import Response
    from routers.diagnosis_report import get_paid_report_pdf

    rec = _make_rec(token="abcdef0102030405")
    premium = _make_premium()

    with patch("routers.diagnosis_report.get_supabase", return_value=_fake_supabase(data=[rec])), \
         patch("routers.diagnosis_report.build_paid_result_product_v1", return_value={}), \
         patch("routers.diagnosis_report.build_public_premium_result_v1", return_value=premium), \
         patch("routers.diagnosis_report._render_html", return_value="<html>ok</html>"), \
         patch("routers.diagnosis_report._generate_pdf", new=AsyncMock(return_value=b"%PDF-art")), \
         patch("services.document_svc.register_generated", new=AsyncMock()):
        result = asyncio.run(get_paid_report_pdf(rec["public_token"]))

    disp = result.headers.get("Content-Disposition", "")
    disp_decoded = unquote(disp)
    assert "TAI_법령진단_상세보고서.pdf" in disp_decoded, \
        f"Content-Disposition 디코딩 후 고정 파일명 없음: {disp!r}"
    assert "abcdef01" not in disp.lower(), \
        f"Content-Disposition에 토큰 substring 노출: {disp!r}"


def test_art_pdf_06_router_template_vars_no_receipt_no():
    src = _router_src()
    import ast, re
    assert '"receipt_no"' not in src or "template_vars" not in src.split('"receipt_no"')[0].split("\n")[-1], \
        "router: template_vars에 receipt_no 키 포함 코드 존재"
    assert "'receipt_no'" not in src, \
        "router: template_vars에 receipt_no 키 포함 코드 존재 (single-quote)"


def test_art_pdf_07_render_html_no_token_in_output():
    from routers.diagnosis_report import _render_html

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

    assert html, "렌더링 결과가 비어있음"
    assert "receipt_no" not in html, "렌더링 결과에 receipt_no 문자열 노출"
    assert "접수번호" not in html, "렌더링 결과에 접수번호 문자열 노출"


# ── ART-XLSX-01~09 ───────────────────────────────────────────────────────────

def test_art_xlsx_01_legal_timing_sheet_name():
    assert SHEET_NAMES[2] == "Legal Timing", \
        f"SHEET_NAMES[2]={SHEET_NAMES[2]!r}, expected 'Legal Timing'"


def test_art_xlsx_02_legal_actors_sheet_name():
    assert SHEET_NAMES[3] == "Legal Actors", \
        f"SHEET_NAMES[3]={SHEET_NAMES[3]!r}, expected 'Legal Actors'"


def test_art_xlsx_03_obligation_columns_has_action():
    assert "action" in OBLIGATION_COLUMNS, \
        "OBLIGATION_COLUMNS에 'action' 컬럼 없음"


def test_art_xlsx_04_obligations_sheet_has_action_header():
    wb = _load(build_paid_result_excel_v1(_make_premium()))
    header = _header(wb["Obligations"])
    assert "action" in header, f"Obligations 시트 헤더에 action 없음: {header}"
    wb.close()


def test_art_xlsx_05_action_value_from_presentation():
    wb = _load(build_paid_result_excel_v1(_make_premium()))
    header = _header(wb["Obligations"])
    action_col = header.index("action")
    ref_col = header.index("ref")
    rows = _rows(wb["Obligations"])
    by_ref = {r[ref_col]: r[action_col] for r in rows}
    assert by_ref[1] == "안전난간 설치", \
        f"ref=1 action: expected '안전난간 설치', got {by_ref.get(1)!r}"
    assert by_ref[2] == "안전점검 실시", \
        f"ref=2 action: expected '안전점검 실시', got {by_ref.get(2)!r}"
    wb.close()


def test_art_xlsx_06_sheet_names_exact():
    wb = _load(build_paid_result_excel_v1(_make_premium()))
    assert tuple(wb.sheetnames) == SHEET_NAMES, \
        f"sheet names: {tuple(wb.sheetnames)} != {SHEET_NAMES}"
    wb.close()


def test_art_xlsx_07_legal_timing_columns():
    wb = _load(build_paid_result_excel_v1(_make_premium()))
    h = _header(wb["Legal Timing"])
    assert h[:7] == [
        "ref", "law_name", "law_article", "when", "inspection_cycle", "raw_cycle", "conflict",
    ], f"Legal Timing 선두 7컬럼 불일치: {h[:7]}"
    wb.close()


def test_art_xlsx_08_legal_actors_columns():
    wb = _load(build_paid_result_excel_v1(_make_premium()))
    h = _header(wb["Legal Actors"])
    assert h[:4] == [
        "ref", "law_name", "law_article", "who",
    ], f"Legal Actors 선두 4컬럼 불일치: {h[:4]}"
    wb.close()


def test_art_xlsx_09_old_sheet_names_absent():
    wb = _load(build_paid_result_excel_v1(_make_premium()))
    names = tuple(wb.sheetnames)
    assert "Schedule" not in names, f"구 시트명 'Schedule' 여전히 존재: {names}"
    assert "Assignments" not in names, f"구 시트명 'Assignments' 여전히 존재: {names}"
    wb.close()


# ── XART-01: cross-artifact parity ───────────────────────────────────────────

def test_xart_01_excel_action_equals_pdf_view_title():
    premium = _make_premium()

    wb = _load(build_paid_result_excel_v1(premium))
    header = _header(wb["Obligations"])
    action_col = header.index("action")
    ref_col = header.index("ref")
    excel_actions = {r[ref_col]: r[action_col] for r in _rows(wb["Obligations"])}
    wb.close()

    pdf_view = build_paid_result_pdf_view_v1(premium)
    pdf_titles = {ob["ref"]: ob["title"] for ob in pdf_view["obligations"]}

    for ref in excel_actions:
        assert excel_actions[ref] == pdf_titles.get(ref), (
            f"ref={ref}: excel action={excel_actions[ref]!r}, "
            f"pdf title={pdf_titles.get(ref)!r} — 두 아티팩트 간 action 불일치"
        )
