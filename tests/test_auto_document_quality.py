"""WO-AUTO-REUSE-RELEASE-QA-001-002 — item_name fallback + CSS inline + template quality.

N1-N8: QA-001 — item_name canonical fallback + Jinja2 finalize
T1-T14: QA-002 — CSS inlining + template ABNORMAL/date/law correctness
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import services.document_engine.fetchers.inspection_fetcher as F  # noqa: E402
import services.document_engine.renderer as R  # noqa: E402


# ── Fake infrastructure ──────────────────────────────────────────────────────

class _FakeItemsResult:
    def __init__(self, data):
        self.data = data


class _FakeItemsQuery:
    def __init__(self, items_map, should_raise):
        self._map = items_map
        self._raise = should_raise
        self._ids: list = []

    def select(self, _):
        return self

    def in_(self, col, vals):
        self._ids = list(vals)
        return self

    def execute(self):
        if self._raise:
            raise RuntimeError("simulated inspection_set_items error")
        data = [{"id": k, "item_name": v} for k, v in self._map.items() if k in self._ids]
        return _FakeItemsResult(data)


class _FakeSBItems:
    """Blocks base ledger; serves inspection_set_items from map."""

    def __init__(self, items_map=None, raise_on_items=False):
        self._map = items_map or {}
        self._raise = raise_on_items

    def table(self, name):
        if name in ("safety_inspections", "safety_inspection_results"):
            raise AssertionError(f"BASE READ FORBIDDEN: {name!r}")
        if name == "inspection_set_items":
            return _FakeItemsQuery(self._map, self._raise)
        raise AssertionError(f"unexpected table: {name!r}")


class _PatchItems:
    def __init__(self, record, items_map=None, raise_on_items=False):
        self._rec = record
        self._sb = _FakeSBItems(items_map, raise_on_items)
        self._orig: dict = {}

    def __enter__(self):
        self._orig = {"g": F.get_supabase, "r": F.resolve_inspection_record}
        F.get_supabase = lambda: self._sb
        F.resolve_inspection_record = lambda iid, sb=None: self._rec
        return self

    def __exit__(self, *a):
        F.get_supabase = self._orig["g"]
        F.resolve_inspection_record = self._orig["r"]
        return False


def _record(**over):
    rec = {
        "inspection_id": "insp-1",
        "revision": 0,
        "is_active": True,
        "inspection_status": "COMPLETED",
        "legacy_raw_status_code": "completed",
        "assignment_id": None,
        "asset_id": None,
        "inspector_id": None,
        "inspection_date": "2026-05-14T00:00:00",
        "submitted_by": None,
        "factory_id": None,
        "results": [],
        "overall_result": None,
    }
    rec.update(over)
    return rec


def _result(rid, code, is_active=True, item_name=None, inspection_set_item_id=None, **over):
    r = {
        "result_id": rid,
        "is_active": is_active,
        "inspection_set_item_id": inspection_set_item_id,
        "item_name": item_name,
        "result_code": code,
        "value_text": None,
        "value_number": None,
        "note": "",
        "checked_at": "2026-05-14T07:49:43+00:00",
        "photo_url": None,
        "photo_urls": [],
        "created_at": "2026-05-14T07:49:44",
    }
    r.update(over)
    return r


def _fetch_items(record, items_map=None, raise_on_items=False):
    fetcher = F.InspectionFetcher.__new__(F.InspectionFetcher)
    with _PatchItems(record=record, items_map=items_map, raise_on_items=raise_on_items):
        return asyncio.run(fetcher.fetch({"inspection_id": "insp-1"}))


# ── N1-N8: QA-001 ────────────────────────────────────────────────────────────

def test_N1_item_name_from_result_used_as_is():
    """Direct item_name in result returned without batch lookup."""
    rec = _record(results=[_result("r1", "NORMAL", item_name="전기설비 점검")])
    out = _fetch_items(rec)
    assert out["items"][0]["item_name"] == "전기설비 점검"


def test_N2_item_name_none_fallback_from_inspection_set_items():
    """item_name=None → batch lookup from inspection_set_items."""
    rec = _record(results=[_result("r1", "NORMAL", item_name=None, inspection_set_item_id="set-1")])
    out = _fetch_items(rec, items_map={"set-1": "화재예방 점검"})
    assert out["items"][0]["item_name"] == "화재예방 점검"


def test_N3_item_name_none_no_item_id_returns_default():
    """item_name=None, no inspection_set_item_id → '항목명 미등록'."""
    rec = _record(results=[_result("r1", "NORMAL", item_name=None, inspection_set_item_id=None)])
    out = _fetch_items(rec)
    assert out["items"][0]["item_name"] == "항목명 미등록"


def test_N4_item_name_none_id_not_in_db_returns_default():
    """item_name=None, ID present but not found in DB → '항목명 미등록'."""
    rec = _record(results=[_result("r1", "NORMAL", item_name=None, inspection_set_item_id="missing-id")])
    out = _fetch_items(rec, items_map={})
    assert out["items"][0]["item_name"] == "항목명 미등록"


def test_N5_batch_fetch_error_graceful_fallback():
    """inspection_set_items fetch error → graceful '항목명 미등록'."""
    rec = _record(results=[_result("r1", "NORMAL", item_name=None, inspection_set_item_id="set-1")])
    out = _fetch_items(rec, raise_on_items=True)
    assert out["items"][0]["item_name"] == "항목명 미등록"


def test_N6_document_finalize_none_to_empty_string():
    """_document_finalize: None → '' ; other values pass through."""
    assert R._document_finalize(None) == ""
    assert R._document_finalize("") == ""
    assert R._document_finalize("hello") == "hello"
    assert R._document_finalize(0) == 0
    assert R._document_finalize(False) is False


def test_N7_doc_insp_html_uses_abnormal_not_issue_for_row_class():
    """DOC-INSP.html: row class uses ABNORMAL, not ISSUE."""
    src = (R.TEMPLATE_DIR / "DOC-INSP.html").read_text(encoding="utf-8")
    assert "== 'ABNORMAL'" in src
    assert "== 'ISSUE'" not in src


def test_N8_doc_insp_html_has_item_name_fallback():
    """DOC-INSP.html: item.item_name has '항목명 미등록' fallback."""
    src = (R.TEMPLATE_DIR / "DOC-INSP.html").read_text(encoding="utf-8")
    assert "항목명 미등록" in src


# ── T1-T14: QA-002 ───────────────────────────────────────────────────────────

def _render(doc_id, data=None):
    return asyncio.run(R.render_document_html(doc_id, data or {}))


def _insp_data(**over):
    d: dict = {"items": [], "issue_items": []}
    d.update(over)
    return d


def _tbm_data(**over):
    d: dict = {"risk_items": [], "attendees": [], "empty_rows": []}
    d.update(over)
    return d


def test_T1_css_link_replaced_with_style_in_insp():
    """DOC-INSP.html render: <link href=_base.css> replaced with <style>."""
    html = _render("DOC-INSP", _insp_data())
    assert '<link rel="stylesheet" href="_base.css">' not in html
    assert "<style>" in html


def test_T2_css_content_present_in_insp():
    """DOC-INSP.html render: actual CSS rules are inlined."""
    html = _render("DOC-INSP", _insp_data())
    assert ".doc-header" in html
    assert "Pretendard" in html


def test_T3_none_values_render_as_empty_not_none_string():
    """Jinja2 finalize: None variable renders as '' not 'None'."""
    html = _render("DOC-INSP", _insp_data(company_name=None))
    assert ">None<" not in html


def test_T4_insp_abnormal_item_gets_issue_row_class():
    """DOC-INSP.html: ABNORMAL item row gets issue-row class."""
    items = [{"item_name": "전기점검", "result_code": "ABNORMAL", "note": ""}]
    html = _render("DOC-INSP", _insp_data(items=items))
    assert "issue-row" in html


def test_T5_insp_normal_item_no_issue_message():
    """DOC-INSP.html: all NORMAL, no issue_items → '점검 결과 이상 없음'."""
    items = [{"item_name": "전기점검", "result_code": "NORMAL", "note": ""}]
    html = _render("DOC-INSP", _insp_data(items=items, issue_items=[]))
    assert "점검 결과 이상 없음" in html


def test_T6_insp_no_items_shows_no_issue_message():
    """DOC-INSP.html: empty items + empty issue_items → '점검 결과 이상 없음'."""
    html = _render("DOC-INSP", _insp_data(items=[], issue_items=[]))
    assert "점검 결과 이상 없음" in html


def test_T7_css_inlined_in_tbm():
    """DOC-OSH-056.html render: <link href=_base.css> replaced with <style>."""
    html = _render("DOC-OSH-056", _tbm_data())
    assert '<link rel="stylesheet" href="_base.css">' not in html
    assert "<style>" in html


def test_T8_base_css_has_print_thead_rule():
    """_base.css has @media print thead { display: table-header-group }."""
    css = (R.TEMPLATE_DIR / "_base.css").read_text(encoding="utf-8")
    assert "table-header-group" in css


def test_T9_base_css_has_print_break_inside_rule():
    """_base.css has @media print break-inside: avoid."""
    css = (R.TEMPLATE_DIR / "_base.css").read_text(encoding="utf-8")
    assert "break-inside" in css


def test_T10_doc_insp_no_hardcoded_law():
    """DOC-INSP.html: hardcoded '산업안전보건법 제38조' is removed."""
    src = (R.TEMPLATE_DIR / "DOC-INSP.html").read_text(encoding="utf-8")
    assert "산업안전보건법 제38조" not in src


def test_T11_doc_law_not_rendered_when_not_provided():
    """DOC-INSP.html: doc-law block absent when doc_law not passed."""
    html = _render("DOC-INSP", _insp_data())
    assert 'class="doc-law"' not in html


def test_T12_doc_law_rendered_when_provided():
    """DOC-INSP.html: doc_law variable renders in doc-law block."""
    html = _render("DOC-INSP", _insp_data(doc_law="산업안전보건법 제38조"))
    assert "산업안전보건법 제38조" in html
    assert 'class="doc-law"' in html


def test_T13_inline_css_function_replaces_link_tag():
    """_inline_document_base_css: replaces <link> with <style> block."""
    fake_html = '<head><link rel="stylesheet" href="_base.css"></head>'
    result = R._inline_document_base_css(fake_html)
    assert '<link rel="stylesheet" href="_base.css">' not in result
    assert "<style>" in result
    assert "</style>" in result


def test_T14_inline_css_noop_when_no_link_tag():
    """_inline_document_base_css: returns html unchanged if no link tag present."""
    fake_html = "<html><head></head><body>content</body></html>"
    result = R._inline_document_base_css(fake_html)
    assert result == fake_html


if __name__ == "__main__":
    g = dict(globals())
    tests = sorted((n, f) for n, f in g.items() if n.startswith("test_") and callable(f))
    passed = failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
            passed += 1
        except Exception as e:  # noqa: BLE001
            print(f"FAIL {name}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n== {passed} passed, {failed} failed / {passed + failed} total ==")
    sys.exit(1 if failed else 0)
