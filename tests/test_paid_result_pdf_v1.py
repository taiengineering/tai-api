"""tests/test_paid_result_pdf_v1.py — P01~P22

INPUT = premium_result_v1 only. 실 LEG/DB 0. binary pdf repo commit 0.
"""
from __future__ import annotations

import ast
import asyncio
import hashlib
import json
import os
import re

import pytest
from fastapi import HTTPException

import routers.diagnosis_report as report_router
import routers.diagnosis_result_web as rw
from services.paid_result_excel_v1 import CANONICAL_UNAVAILABLE, canonical_source_text
from services.paid_result_pdf_v1 import (
    GOTENBERG_A4,
    GOTENBERG_CONVERT_PATH,
    build_paid_result_pdf_html_v1,
    generate_paid_result_pdf_v1,
    pdf_content_disposition,
    pdf_filename,
)
from tests.test_paid_result_delivery_wiring_v1 import (
    install,
    leg_obligation,
    source_item,
    stored_rec,
)
from tests.test_paid_result_excel_v1 import (
    FORBIDDEN,
    SECRET_EVIDENCE,
    SECRET_WHAT,
    _ob,
    _premium,
)

PDF_MIME = "application/pdf"
BANNED_LEGACY = (
    "주요 리스크 TOP",
    "주요리스크TOP",
    "TOP 5",
    "TOP5",
    "최대과태료",
    "미이행 시 최대 과태료",
    "위험도",
    "월 59,000",
    "월 79,000",
    "월 145,000",
    "추천 플랜",
    "추천플랜",
    "전문가 검토",
    "전문가검토",
    "접수번호",
)
PDF_SRC = os.path.join(os.path.dirname(__file__), "..", "services", "paid_result_pdf_v1.py")
REPORT_SRC = os.path.join(os.path.dirname(__file__), "..", "routers", "diagnosis_report.py")
WEB_SRC = os.path.join(os.path.dirname(__file__), "..", "routers", "diagnosis_result_web.py")
TMPL_SRC = os.path.join(os.path.dirname(__file__), "..", "templates", "paid_result_premium_pdf_v1.html")


def _html(premium=None) -> str:
    return build_paid_result_pdf_html_v1(premium if premium is not None else _premium())


def _refs(html: str):
    return re.findall(r'data-ref="([^"]*)"', html)


def _canonical_for(html: str, ref) -> str:
    m = re.search(
        r'data-canonical-ref="{}"[^>]*>(.*?)</div>'.format(re.escape(str(ref))),
        html,
        re.S,
    )
    assert m, "canonical for ref {} missing".format(ref)
    return m.group(1)


class _FakeResp:
    def __init__(self, status_code=200, content=b"%PDF-1.4\n%%EOF\n", text="ok"):
        self.status_code = status_code
        self.content = content
        self.text = text


class _FakeClient:
    last = None

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return None

    async def post(self, url, files=None, data=None):
        _FakeClient.last = {"url": url, "files": files, "data": data}
        return _FakeResp()


def _patch_gotenberg(monkeypatch):
    _FakeClient.last = None
    monkeypatch.setattr("services.paid_result_pdf_v1.httpx.AsyncClient", _FakeClient)


def _patch_generate(monkeypatch, blob=b"%PDF-1.4\n%%EOF\n"):
    async def _gen(premium):
        _patch_generate.premium = premium
        return blob

    _patch_generate.premium = None
    monkeypatch.setattr(rw, "generate_paid_result_pdf_v1", _gen)


def test_P01_formatter_premium_only_no_db_leg_llm_datetime_random():
    src = open(PDF_SRC, encoding="utf-8").read()
    tree = ast.parse(src)
    html_fn = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "build_paid_result_pdf_html_v1":
            html_fn = node
    assert html_fn is not None
    html_src = ast.get_source_segment(src, html_fn) or ""
    assert "get_supabase" not in src
    assert "datetime.now(" not in src
    assert "now_kst" not in src
    assert "random." not in src
    assert "from datetime" not in src
    assert "import datetime" not in src
    assert "openai" not in src
    assert "leg_runtime" not in src
    assert "httpx" not in html_src
    html = _html()
    assert "data-section=\"workbench\"" in html
    assert SECRET_WHAT not in html


def test_P02_gotenberg_request_contract(monkeypatch):
    _patch_gotenberg(monkeypatch)
    raw = asyncio.run(generate_paid_result_pdf_v1(_premium()))
    assert raw.startswith(b"%PDF-1.4")
    last = _FakeClient.last
    assert last is not None
    assert last["url"].endswith(GOTENBERG_CONVERT_PATH)
    assert "tai-gotenberg.internal" not in last["url"]
    assert last["data"] == GOTENBERG_A4
    files = last["files"]["files"]
    assert files[0] == "index.html"
    assert files[2] == "text/html"
    assert b"data-section=" in files[1]


def test_P03_route_200_pdf_mime_and_disposition(monkeypatch):
    rec = stored_rec([leg_obligation("a0", "점검")], tier="BUILDING_V2")
    install(monkeypatch, rec, product_items=[source_item(0, "a0", "원문A")])
    _patch_generate(monkeypatch)
    resp = asyncio.run(rw.get_paid_result_pdf("tok-1"))
    assert resp.media_type == PDF_MIME
    disp = resp.headers["Content-Disposition"]
    assert disp.startswith("attachment;")
    assert "filename" in disp
    assert resp.body.startswith(b"%PDF-1.4")


def test_P04_access_parity_json_excel_pdf(monkeypatch):
    rec = stored_rec([leg_obligation("a0", "점검")], tier="BUILDING_V2")
    install(monkeypatch, rec, product_items=[source_item(0, "a0", "원문A")])
    _patch_generate(monkeypatch)
    json_ok = rw.get_paid_result_web("tok-1")
    assert json_ok["data"]["is_free"] is False
    assert "premium_result_v1" in json_ok["data"]
    xlsx = rw.get_paid_result_excel("tok-1")
    assert xlsx.media_type.endswith("spreadsheetml.sheet")
    pdf = asyncio.run(rw.get_paid_result_pdf("tok-1"))
    assert pdf.media_type == PDF_MIME

    install(monkeypatch, None)
    with pytest.raises(HTTPException) as n1:
        rw.get_paid_result_web("missing")
    with pytest.raises(HTTPException) as n2:
        rw.get_paid_result_excel("missing")
    with pytest.raises(HTTPException) as n3:
        asyncio.run(rw.get_paid_result_pdf("missing"))
    assert n1.value.status_code == n2.value.status_code == n3.value.status_code == 404

    rec_inactive = stored_rec([leg_obligation("a0", "점검")], tier="BUILDING_V2", status="INACTIVE")
    install(monkeypatch, rec_inactive, product_items=[source_item(0, "a0", "원문A")])
    with pytest.raises(HTTPException) as g1:
        rw.get_paid_result_web("tok-1")
    with pytest.raises(HTTPException) as g2:
        rw.get_paid_result_excel("tok-1")
    with pytest.raises(HTTPException) as g3:
        asyncio.run(rw.get_paid_result_pdf("tok-1"))
    assert g1.value.status_code == g2.value.status_code == g3.value.status_code == 410

    rec_free = stored_rec([leg_obligation("a0", "점검")], tier="BUILDING_FREE")
    install(monkeypatch, rec_free, product_items=[source_item(0, "a0", "원문A")])
    free_json = rw.get_paid_result_web("tok-1")
    assert free_json["data"]["is_free"] is True
    assert "premium_result_v1" not in free_json["data"]
    with pytest.raises(HTTPException) as f2:
        rw.get_paid_result_excel("tok-1")
    with pytest.raises(HTTPException) as f3:
        asyncio.run(rw.get_paid_result_pdf("tok-1"))
    assert f2.value.status_code == f3.value.status_code == 403

    rec_legacy = stored_rec(
        [leg_obligation("a0", "점검")],
        tier="BUILDING_V2",
        rules_table=[{"law_name": "L", "law_article": "1", "obligation_summary": "x",
                      "description": "x", "rule_id": "r1"}],
    )
    monkeypatch.setattr(rw, "enrich_rules_with_candidate_slots", lambda *a, **k: None)
    install(monkeypatch, rec_legacy, product_items=[source_item(0, "a0", "원문A")])
    legacy_json = rw.get_paid_result_web("tok-1")
    assert "premium_result_v1" not in legacy_json["data"]
    with pytest.raises(HTTPException) as l2:
        rw.get_paid_result_excel("tok-1")
    with pytest.raises(HTTPException) as l3:
        asyncio.run(rw.get_paid_result_pdf("tok-1"))
    assert l2.value.status_code == l3.value.status_code == 404


def test_P05_obligation_cardinality_and_ref_order():
    p = _premium()
    p["materials"]["obligations"] = [_ob(18), _ob(17), _ob(4)]
    p["materials"]["overview"]["total_obligation_count"] = 3
    html = _html(p)
    refs = _refs(html)
    assert refs == ["18", "17", "4"]
    assert len(refs) == p["materials"]["overview"]["total_obligation_count"]


def test_P06_article375_two_to_two():
    html = _html(_premium())
    refs = _refs(html)
    assert refs == ["17", "18"]
    assert "관련 의무 17, 18" in html
    assert html.count('data-article-no="375"') == 1


def test_P07_canonical_exact():
    html = _html(_premium())
    assert _canonical_for(html, 17) == "원문-17-EXACT"
    assert _canonical_for(html, 18) == "원문-18-EXACT"
    assert canonical_source_text(_premium(), 17) == "원문-17-EXACT"


def test_P08_canonical_missing_fail_closed():
    p = _premium()
    p["canonical_sources"] = [{"ref": 99, "text": "다른원문"}]
    html = _html(p)
    assert _canonical_for(html, 17) == CANONICAL_UNAVAILABLE
    assert _canonical_for(html, 18) == CANONICAL_UNAVAILABLE
    assert SECRET_WHAT not in html
    assert SECRET_EVIDENCE not in html
    assert "다른원문" not in html


def test_P09_canonical_duplicate_fail_closed():
    p = _premium()
    p["materials"]["obligations"] = [_ob(17)]
    p["canonical_sources"] = [{"ref": 17, "text": "A"}, {"ref": 17, "text": "A"}]
    html = _html(p)
    assert _canonical_for(html, 17) == CANONICAL_UNAVAILABLE


def test_P10_canonical_empty_unavailable():
    p = _premium()
    p["materials"]["obligations"] = [_ob(17)]
    p["canonical_sources"] = [{"ref": 17, "text": ""}]
    html = _html(p)
    assert _canonical_for(html, 17) == CANONICAL_UNAVAILABLE


def test_P11_canonical_whitespace_kept_exact():
    p = _premium()
    p["materials"]["obligations"] = [_ob(17)]
    p["canonical_sources"] = [{"ref": 17, "text": "   "}]
    html = _html(p)
    assert _canonical_for(html, 17) == "   "


def test_P12_duty_what_not_exposed_or_fallback():
    src = open(PDF_SRC, encoding="utf-8").read()
    assert '.get("what")' not in src
    assert "['what']" not in src
    assert '["what"]' not in src
    html = _html(_premium())
    assert SECRET_WHAT not in html
    assert "data-fact=\"what\"" not in html


def test_P13_forbidden_internals_absent():
    src = open(PDF_SRC, encoding="utf-8").read()
    html = _html(_premium())
    for key in FORBIDDEN:
        assert key not in src, key
        assert key not in html, key


def test_P14_evidence_article_text_exact():
    p = _premium()
    original = p["evidence"]["articles"][0]["article_text"]
    html = _html(p)
    assert original in html
    assert "제375조 원문 그대로" in html


def test_P15_subarticle_221_kept_distinct():
    html = _html(_premium())
    assert 'data-article-no="221" data-article-sub-no="2"' in html
    assert 'data-article-no="221" data-article-sub-no="3"' in html
    assert 'data-article-no="221" data-article-sub-no="4"' in html
    assert 'data-article-no="221" data-article-sub-no="5"' in html
    assert "제221조의2" in html
    assert "제221조의3" in html
    assert "제221조의4" in html
    assert "제221조의5" in html


def test_P16_legacy_top5_risk_penalty_plan_absent():
    html = _html(_premium())
    tmpl = open(TMPL_SRC, encoding="utf-8").read()
    blob = html + "\n" + tmpl
    for banned in BANNED_LEGACY:
        assert banned not in blob, banned
    assert "csia_applicable" not in html
    assert "risk-HIGH" not in html
    assert "recommended_plan" not in html


def test_P17_db_storage_write_zero():
    report = open(REPORT_SRC, encoding="utf-8").read()
    pdf_src = open(PDF_SRC, encoding="utf-8").read()
    web = open(WEB_SRC, encoding="utf-8").read()
    pdf_route = web.split("async def get_paid_result_pdf")[1].split("def get_paid_result_web")[0]
    assert "register_generated" not in report
    assert "register_generated" not in pdf_src
    assert "register_generated" not in pdf_route
    assert "pdf_url" not in pdf_src


def test_P18_legacy_alias_reuses_canonical_generator(monkeypatch):
    rec = stored_rec([leg_obligation("a0", "점검")], tier="BUILDING_V2")
    install(monkeypatch, rec, product_items=[source_item(0, "a0", "원문A")])
    _patch_generate(monkeypatch, blob=b"%PDF-ALIAS%")
    canonical = asyncio.run(rw.get_paid_result_pdf("tok-1"))
    alias = asyncio.run(report_router.get_paid_report_pdf("tok-1"))
    assert canonical.body == alias.body == b"%PDF-ALIAS%"
    assert canonical.media_type == alias.media_type == PDF_MIME
    report = open(REPORT_SRC, encoding="utf-8").read()
    assert "convert/html" not in report
    assert "GOTENBERG" not in report
    assert "full_result" not in report
    assert "get_paid_result_pdf" in report


def test_P19_filename_stored_values_only_no_token():
    p = _premium()
    name = pdf_filename(p)
    assert name.startswith("TAI_법령진단_샘플 건설현장_")
    assert name.endswith(".pdf")
    assert "tok" not in name
    assert "uuid" not in name.lower()
    empty = _premium()
    empty["profile"]["company_name"] = None
    assert pdf_filename(empty) == "결과.pdf"
    html = _html(p)
    assert "tok-1" not in html
    assert "public_token" not in html
    assert "접수번호" not in html
    assert p["diagnosis"]["diagnosed_at"] in html
    assert "attachment;" in pdf_content_disposition(name)


def test_P20_single_omits_empty_glance_and_landscape():
    p = _premium()
    p["materials"]["obligations"] = [_ob(17)]
    p["materials"]["overview"]["total_obligation_count"] = 1
    html = _html(p)
    assert 'data-section="glance"' not in html
    assert 'data-section="landscape"' not in html
    assert 'data-section="workbench"' in html
    assert 'data-section="cover"' in html


def test_P21_long_recipient_condition_canonical_not_trimmed():
    long_recipient = "수급인 " + ("갑을병정" * 40)
    long_condition = "굴착작업 및 " + ("해당 조건 " * 40)
    long_canon = "원문 본문\n" + ("법령원문줄 " * 80) + "끝"
    p = _premium()
    p["materials"]["obligations"] = [
        _ob(17, recipient=long_recipient, condition=long_condition),
        _ob(18),
    ]
    p["canonical_sources"] = [{"ref": 17, "text": long_canon}, {"ref": 18, "text": "원문-18-EXACT"}]
    html = _html(p)
    assert long_recipient in html
    assert long_condition in html
    assert long_canon in html
    assert "끝" in html


def test_P22_endpoint_exact_and_no_duplicate_generator():
    web = open(WEB_SRC, encoding="utf-8").read()
    report = open(REPORT_SRC, encoding="utf-8").read()
    pdf_src = open(PDF_SRC, encoding="utf-8").read()
    assert '@router.get("/paid-result/{public_token}/pdf")' in web
    assert '@router.get("/report-pdf/{public_token}")' in report
    assert pdf_src.count("def generate_paid_result_pdf_v1") == 1
    assert pdf_src.count("def build_paid_result_pdf_html_v1") == 1
    assert "http://gotenberg.railway.internal:3000" in pdf_src
    assert "tai-gotenberg.internal" not in pdf_src
    assert "tai-gotenberg.internal" not in report


def test_local_pdf_visual_qa_portfolio(tmp_path, monkeypatch):
    """실 HTML 3모드. Gotenberg 가 있으면 PDF/PNG. repo commit 0."""
    fixtures = {
        "P-SINGLE": 1,
        "P-COMPACT": 4,
        "P-PORTFOLIO": 23,
    }
    stats = {}
    for name, n in fixtures.items():
        obs = [
            _ob(
                100 + i,
                article="375" if i in (0, 1) and n >= 2 else str(100 + i),
                recipient=("아주 긴 수신 대상 상호명 " * 8) if i == 0 else None,
                condition=("굴착작업 및 해당 조건 상세 " * 6) if i == 0 else None,
            )
            for i in range(n)
        ]
        if n >= 2:
            obs[0] = _ob(17, article="375", recipient="수급인 " + ("갑" * 40), condition="조건 " + ("상세" * 30))
            obs[1] = _ob(18, article="375")
        sources = [{"ref": ob["ref"], "text": "원문-{}".format(ob["ref"])} for ob in obs]
        sources[0]["text"] = "원문 본문\n" + ("법령원문 " * 60) + "끝마커"
        p = _premium()
        p["profile"]["company_name"] = "시각QA {}".format(name)
        p["materials"]["obligations"] = obs
        p["materials"]["overview"]["total_obligation_count"] = n
        p["canonical_sources"] = sources
        html = build_paid_result_pdf_html_v1(p)
        html_path = tmp_path / "{}.html".format(name)
        html_path.write_text(html, encoding="utf-8")
        entry = {
            "obligation_count": html.count("data-ref="),
            "has_glance": 'data-section="glance"' in html,
            "has_landscape": 'data-section="landscape"' in html,
            "html_sha256": hashlib.sha256(html.encode("utf-8")).hexdigest(),
            "html_size": len(html.encode("utf-8")),
        }
        if n == 1:
            assert entry["has_glance"] is False
            assert entry["has_landscape"] is False
        stats[name] = entry
        assert "끝마커" in html
        assert SECRET_WHAT not in html
        for banned in BANNED_LEGACY:
            assert banned not in html

    gotenberg = os.environ.get("GOTENBERG_URL") or os.environ.get("TAI_PDF_GOTENBERG_URL")
    if gotenberg:
        monkeypatch.setattr("services.paid_result_pdf_v1.GOTENBERG_URL", gotenberg.rstrip("/"))
        p = _premium()
        p["materials"]["overview"]["total_obligation_count"] = 23
        raw = asyncio.run(generate_paid_result_pdf_v1(p))
        pdf_path = tmp_path / "P-PORTFOLIO.pdf"
        pdf_path.write_bytes(raw)
        stats["P-PORTFOLIO"].update({
            "pdf_size": len(raw),
            "pdf_sha256": hashlib.sha256(raw).hexdigest(),
            "pdf_header": raw[:8].decode("latin-1", errors="replace"),
        })
        assert raw.startswith(b"%PDF")
        page_count = len(re.findall(rb"/Type\s*/Page[^s]", raw))
        stats["P-PORTFOLIO"]["page_count_hint"] = page_count
        png_dir = tmp_path / "png"
        png_dir.mkdir()
        try:
            import subprocess
            subprocess.run(
                ["pdftoppm", "-png", str(pdf_path), str(png_dir / "page")],
                check=False, capture_output=True, timeout=60,
            )
            pngs = sorted(png_dir.glob("*.png"))
            stats["P-PORTFOLIO"]["png_count"] = len(pngs)
        except (FileNotFoundError, OSError):
            stats["P-PORTFOLIO"]["png_count"] = 0

    (tmp_path / "visual_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    os.environ["TAI_PDF_VISUAL_STATS"] = json.dumps(stats, ensure_ascii=False)
    print("LOCAL_PDF_VISUAL", json.dumps(stats, ensure_ascii=False))
    assert stats["P-SINGLE"]["obligation_count"] == 1
    assert stats["P-COMPACT"]["obligation_count"] == 4
    assert stats["P-PORTFOLIO"]["obligation_count"] == 23
