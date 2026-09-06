"""STEP 2B — 회원 견적 PDF 발급 (내부결재 첨부용) 단위테스트.

WO-MYPAGE-QUOTE-PROCESS-001. FakeSupabase(quotes/companies/documents) + Gotenberg render mock
+ document_svc storage/signed_url monkeypatch. 실 Gotenberg / 실 DB / 운영 데이터 mutation = 0.

케이스 매트릭스 :
  OWNERSHIP  PDF-01 무인증 401 · PDF-02 무회사 403 · PDF-03 타사 quote 404 · PDF-04 ALL 도 타사 404
  QUOTE TYPE PDF-05 member_custom 409 · PDF-06 status!=ISSUED 409 · PDF-07 survey_web 404
  SNAPSHOT   PDF-08 items 비었으면 409 · PDF-09 item 필드 누락 409 ·
             PDF-10 items vs row 불일치 409 · PDF-11 price_master live 재조회 0 (호출 없음 grep)
  GOTENBERG  PDF-12 정상 200 %PDF · PDF-13 network fail 503 UNAVAILABLE ·
             PDF-14 5xx 503 UNAVAILABLE · PDF-15 4xx 502 INVALID ·
             PDF-16 비 PDF 응답 502 INVALID · PDF-17 content-type 만 PDF, magic 없음 502 ·
             PDF-18 render 호출 payload : preferCssPageSize=true·printBackground=true ·
             PDF-19 render 호출 파일 이름 index.html + text/html
  DOCUMENT   PDF-20 register_generated 호출 인자 (company_id/category/linked_table/linked_id) ·
             PDF-21 generated_by=member_quote_pdf_v1 · PDF-22 tags=[quote, member_auto] ·
             PDF-23 category=general · PDF-24 source=AUTO_GENERATED (register_generated 계약) ·
             PDF-25 file_name = TAI_견적서_{quote_no}.pdf
  IDEMPOTENT PDF-26 첫 호출 generated=True · PDF-27 두 번째 generated=False (render 재호출 0) ·
             PDF-28 signed url 두 번 다 반환 · PDF-29 재사용 document_id 동일
  SECURITY   PDF-30 HTML escaping (raw 스크립트 미노출) · PDF-31 signed URL 은 소유권 검증 후에만
  INFRA      INFRA-1 base URL 은 GOTENBERG_URL env 만 사용 · INFRA-2/3 (PORT-1/2) 소스에 railway
             hostname / 포트 literal 0
  CONFIG     CONFIG-1 TAI_CEO_NAME 매핑 (invoice_svc 실측 정합) ·
             CONFIG-2 연락처 missing → QUOTE_SUPPLIER_CONFIG_MISSING ·
             CONFIG-3 공급자 값이 예외 message 에 출력되지 않음
  PORT       PORT-1 소스에 "railway.internal:8080" literal 0 ·
             PORT-2 소스에 "railway.internal:3000" literal 0 ·
             PORT-3 GOTENBERG_URL 미설정 → PDF_RENDER_CONFIG_MISSING (503), Gotenberg 호출 0
"""
from __future__ import annotations

import os
import re
import uuid

import pytest

# main import 시 필요한 env
os.environ.setdefault("INTERNAL_API_SECRET", "pytest-internal-secret")

import routers.member_quotes as mq
from services import member_quote_pdf_svc as pdf_svc
from services import gotenberg_svc

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import httpx  # noqa: F401
    _HAS_CLIENT = True
except Exception:  # noqa: BLE001
    _HAS_CLIENT = False

requires_client = pytest.mark.skipif(not _HAS_CLIENT, reason="httpx/TestClient 미설치")


# ── FakeSupabase (STEP 2A 스타일 · range/count 확장) ────────────────
class _Result:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count if count is not None else (len(data) if data is not None else 0)


class _Query:
    def __init__(self, store, table, log):
        self.store = store; self.table = table; self.log = log
        self._op = None; self._payload = None; self._filters = []
        self._cols = "*"; self._count_exact = False; self._range = None
        self._order = None; self._limit = None

    def select(self, cols="*", *a, **k):
        self._op = "select"; self._cols = cols or "*"
        if k.get("count") == "exact":
            self._count_exact = True
        return self

    def insert(self, row): self._op = "insert"; self._payload = row; return self
    def update(self, patch): self._op = "update"; self._payload = patch; return self

    def eq(self, c, v): self._filters.append(("eq", c, v)); return self
    def in_(self, c, vals): self._filters.append(("in", c, list(vals))); return self
    def is_(self, c, v): self._filters.append(("is", c, v)); return self
    def limit(self, n): self._limit = n; return self
    def order(self, col, *, desc=False, **k): self._order = (col, desc); return self
    def range(self, s, e): self._range = (s, e); return self

    def _match(self, row):
        for op, c, v in self._filters:
            if op == "eq" and str(row.get(c)) != str(v):
                return False
            if op == "in" and row.get(c) not in v:
                return False
            if op == "is" and v == "null" and row.get(c) is not None:
                return False
        return True

    def _project(self, row):
        if not self._cols or self._cols == "*":
            return dict(row)
        keys = [c.strip() for c in self._cols.split(",") if c.strip()]
        return {k: row.get(k) for k in keys}

    def execute(self):
        rows = self.store.setdefault(self.table, [])
        self.log.append((self.table, self._op))
        if self._op == "select":
            matched = [r for r in rows if self._match(r)]
            total = len(matched)
            if self._order:
                col, desc = self._order
                matched = sorted(matched, key=lambda r: (r.get(col) or ""), reverse=desc)
            if self._range is not None:
                s, e = self._range
                matched = matched[s:e + 1]
            elif self._limit is not None:
                matched = matched[:self._limit]
            return _Result([self._project(r) for r in matched],
                           count=total if self._count_exact else None)
        if self._op == "insert":
            items = self._payload if isinstance(self._payload, list) else [self._payload]
            out = []
            for it in items:
                it = dict(it); it.setdefault("id", str(uuid.uuid4()))
                rows.append(it); out.append(dict(it))
            return _Result(out)
        if self._op == "update":
            matched = [r for r in rows if self._match(r)]
            for r in matched:
                r.update(self._payload)
            return _Result([dict(r) for r in matched])
        return _Result([])


class FakeSupabase:
    def __init__(self, store=None):
        self.store = store if store is not None else {}
        self.log = []

    def table(self, name):
        return _Query(self.store, name, self.log)

    # ── storage stub (document_svc.upload_document + get_signed_url) ──
    @property
    def storage(self):
        outer = self

        class _StorageFrom:
            def __init__(self, bucket):
                self.bucket = bucket

            def upload(self, path, file, file_options=None):
                outer.store.setdefault("_storage", []).append(
                    {"bucket": self.bucket, "path": path, "size": len(file),
                     "content_type": (file_options or {}).get("content-type")})
                return {"path": path}

            def create_signed_url(self, path, expires):
                return {"signedURL": "https://signed.example/" + path}

        class _Storage:
            def from_(self, bucket):
                return _StorageFrom(bucket)

        return _Storage()


# ── payload fixtures ────────────────────────────────────────────────
def _company_user(company_id="C-A", uid="U-1", role_code="002"):
    return {"id": uid, "company_id": company_id, "role_code": role_code,
            "factory_id": None, "team_id": None}


def _no_company_user(uid="U-N"):
    return {"id": uid, "company_id": None, "role_code": "002",
            "factory_id": None, "team_id": None}


def _issued_quote(company_id="C-A", **over):
    q = {
        "id": "q-1", "quote_no": "QT-20260906-DEADBEEF",
        "company_id": company_id, "company_name": "테스트 주식회사",
        "source": "member_auto", "status_code": "ISSUED",
        "service_type": "SAAS",
        "items": [{
            "price_id": "pm-saas-ind-biz", "service_type": "SAAS", "sector": "INDUSTRY",
            "tier_code": "INDUSTRY_BUSINESS", "display_name": "산업 비즈니스",
            "billing_unit": "MONTHLY", "unit_amount": 299000, "term_months": 12,
            "quantity": 12, "supply_amount": 3_588_000, "vat_rate": 0.1,
            "vat_amount": 358_800, "total_amount": 3_946_800,
        }],
        "supply_amount": 3_588_000, "vat_amount": 358_800, "total_amount": 3_946_800,
        "created_by": "U-1", "created_at": "2026-09-06T00:00:00+00:00",
    }
    q.update(over); return q


def _base_store(quote=None, companies=None):
    return {
        "quotes": [quote] if quote else [],
        "role_data_scope": [
            {"role_code": "001", "scope_type": "ALL"},
            {"role_code": "002", "scope_type": "COMPANY"},
        ],
        "companies": list(companies or []),
        "factories": [],
        "documents": [],
    }


# ── env helpers ──────────────────────────────────────────────────────
def _set_supplier_env(monkeypatch, *, missing=None):
    fields = {
        "TAI_CORP_NAME": "TAI 산업안전보건 주식회사",
        "TAI_CEO_NAME": "홍길동",
        "TAI_CORP_NUM": "123-45-67890",
        "TAI_CORP_ADDR": "서울특별시 강남구 테헤란로 000",
        "QUOTE_SUPPLIER_TEL": "02-000-0000",
        "QUOTE_SUPPLIER_EMAIL": "sales@taieng.co.kr",
    }
    missing = set(missing or [])
    for k, v in fields.items():
        if k in missing:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, v)
    # FAX 는 선택
    monkeypatch.setenv("QUOTE_SUPPLIER_FAX", "02-000-0001")


def _set_gotenberg_env(monkeypatch, url="http://gotenberg.test:3000"):
    monkeypatch.setenv("GOTENBERG_URL", url)


# ── PDF mock helpers ────────────────────────────────────────────────
_VALID_PDF_BYTES = b"%PDF-1.4\n%mock\n1 0 obj\n<<>>\nendobj\ntrailer<<>>\n%%EOF\n"


class _RenderCallSpy:
    def __init__(self, return_bytes=_VALID_PDF_BYTES, exc=None):
        self.return_bytes = return_bytes
        self.exc = exc
        self.calls = 0
        self.last_html = None

    def __call__(self, html_content, *, trace_id=None, timeout=30.0):
        self.calls += 1
        self.last_html = html_content
        if self.exc:
            raise self.exc
        return self.return_bytes


def _client(current_user, store, monkeypatch, *, render_spy=None):
    _set_supplier_env(monkeypatch)
    _set_gotenberg_env(monkeypatch)

    app = FastAPI()
    app.include_router(mq.router)
    app.dependency_overrides[mq.get_current_user] = lambda: current_user
    fake = FakeSupabase(store)
    mq.get_supabase = lambda: fake
    # document_svc.get_supabase 도 같은 fake 로 (같은 store 공유)
    from services import document_svc as ds
    ds.get_supabase = lambda: fake
    if render_spy is not None:
        monkeypatch.setattr(pdf_svc, "render_html_pdf", render_spy)
    c = TestClient(app)
    c._fake = fake
    return c


# ════════════════════════════════════════════════════════════════════
# OWNERSHIP : PDF-01 ~ 04
# ════════════════════════════════════════════════════════════════════
@requires_client
def test_PDF01_no_auth_401(monkeypatch):
    _set_supplier_env(monkeypatch); _set_gotenberg_env(monkeypatch)
    app = FastAPI(); app.include_router(mq.router)
    fake = FakeSupabase(_base_store(_issued_quote()))
    mq.get_supabase = lambda: fake
    c = TestClient(app)
    r = c.post("/me/quotes/q-1/pdf")
    assert r.status_code == 401


@requires_client
def test_PDF02_no_company_403(monkeypatch):
    store = _base_store(_issued_quote())
    render = _RenderCallSpy()
    c = _client(_no_company_user(), store, monkeypatch, render_spy=render)
    r = c.post("/me/quotes/q-1/pdf")
    assert r.status_code == 403
    assert render.calls == 0


@requires_client
def test_PDF03_cross_company_404(monkeypatch):
    store = _base_store(_issued_quote(company_id="C-OWNER"),
                        companies=[{"id": "C-OWNER", "name": "타사"}])
    render = _RenderCallSpy()
    c = _client(_company_user("C-B", "U-B"), store, monkeypatch, render_spy=render)
    r = c.post("/me/quotes/q-1/pdf")
    assert r.status_code == 404
    assert render.calls == 0


@requires_client
def test_PDF04_all_role_cross_company_404(monkeypatch):
    store = _base_store(_issued_quote(company_id="C-OWNER"),
                        companies=[{"id": "C-OWNER", "name": "타사"},
                                    {"id": "C-A", "name": "관리자소속"}])
    render = _RenderCallSpy()
    all_user = {"id": "U-admin", "company_id": "C-A", "role_code": "001",
                "factory_id": None, "team_id": None}
    c = _client(all_user, store, monkeypatch, render_spy=render)
    r = c.post("/me/quotes/q-1/pdf")
    assert r.status_code == 404
    assert render.calls == 0


# ════════════════════════════════════════════════════════════════════
# QUOTE TYPE : PDF-05 ~ 07
# ════════════════════════════════════════════════════════════════════
@requires_client
def test_PDF05_member_custom_409(monkeypatch):
    store = _base_store(_issued_quote(source="member_custom", status_code="REQUESTED"),
                        companies=[{"id": "C-A", "name": "TAI"}])
    render = _RenderCallSpy()
    c = _client(_company_user("C-A"), store, monkeypatch, render_spy=render)
    r = c.post("/me/quotes/q-1/pdf")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "PDF_NOT_AVAILABLE"
    assert render.calls == 0


@requires_client
def test_PDF06_status_not_issued_409(monkeypatch):
    store = _base_store(_issued_quote(status_code="DRAFT"),
                        companies=[{"id": "C-A", "name": "TAI"}])
    render = _RenderCallSpy()
    c = _client(_company_user("C-A"), store, monkeypatch, render_spy=render)
    r = c.post("/me/quotes/q-1/pdf")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "PDF_NOT_AVAILABLE"


@requires_client
def test_PDF07_survey_web_source_404(monkeypatch):
    """member_svc.get_member_quote 는 source in (member_auto, member_custom) 만 반환 → 404."""
    store = _base_store(_issued_quote(source="survey_web"),
                        companies=[{"id": "C-A", "name": "TAI"}])
    c = _client(_company_user("C-A"), store, monkeypatch, render_spy=_RenderCallSpy())
    r = c.post("/me/quotes/q-1/pdf")
    assert r.status_code == 404


# ════════════════════════════════════════════════════════════════════
# SNAPSHOT : PDF-08 ~ 11
# ════════════════════════════════════════════════════════════════════
@requires_client
def test_PDF08_items_empty_409(monkeypatch):
    q = _issued_quote(); q["items"] = []
    store = _base_store(q, companies=[{"id": "C-A", "name": "TAI"}])
    c = _client(_company_user("C-A"), store, monkeypatch, render_spy=_RenderCallSpy())
    r = c.post("/me/quotes/q-1/pdf")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "QUOTE_SNAPSHOT_INCOMPLETE"


@requires_client
def test_PDF09_item_missing_fields_409(monkeypatch):
    q = _issued_quote(); q["items"][0]["total_amount"] = None
    store = _base_store(q, companies=[{"id": "C-A", "name": "TAI"}])
    c = _client(_company_user("C-A"), store, monkeypatch, render_spy=_RenderCallSpy())
    r = c.post("/me/quotes/q-1/pdf")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "QUOTE_SNAPSHOT_INCOMPLETE"


@requires_client
def test_PDF10_row_item_mismatch_409(monkeypatch):
    q = _issued_quote(); q["total_amount"] = 1   # row 만 위조
    store = _base_store(q, companies=[{"id": "C-A", "name": "TAI"}])
    c = _client(_company_user("C-A"), store, monkeypatch, render_spy=_RenderCallSpy())
    r = c.post("/me/quotes/q-1/pdf")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "QUOTE_SNAPSHOT_INVALID"


def test_PDF11_no_price_master_live_re_lookup():
    """PDF svc 소스에 price_master 조회 코드가 없다 — 정본은 frozen snapshot 만."""
    import inspect
    src = inspect.getsource(pdf_svc)
    assert "price_master" not in src, "PDF 발급 경로에서 price_master 재조회 금지 (frozen snapshot only)"
    assert 'table("companies")' not in src and "table('companies')" not in src, (
        "PDF svc 는 companies 재조회 없이 quotes.company_name snapshot 만 사용해야 한다"
    )


# ════════════════════════════════════════════════════════════════════
# GOTENBERG : PDF-12 ~ 19
# ════════════════════════════════════════════════════════════════════
@requires_client
def test_PDF12_success_200_pdf_magic(monkeypatch):
    store = _base_store(_issued_quote(), companies=[{"id": "C-A", "name": "TAI"}])
    render = _RenderCallSpy()
    c = _client(_company_user("C-A"), store, monkeypatch, render_spy=render)
    r = c.post("/me/quotes/q-1/pdf")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["generated"] is True
    assert data["file_name"] == "TAI_견적서_QT-20260906-DEADBEEF.pdf"
    assert data["url"].startswith("https://signed.example/")
    assert data["expires_in"] == 3600
    assert render.calls == 1


@requires_client
def test_PDF13_network_fail_503(monkeypatch):
    from services.gotenberg_svc import PdfRenderError
    render = _RenderCallSpy(exc=PdfRenderError("PDF_RENDER_UNAVAILABLE", "network", 503))
    store = _base_store(_issued_quote(), companies=[{"id": "C-A", "name": "TAI"}])
    c = _client(_company_user("C-A"), store, monkeypatch, render_spy=render)
    r = c.post("/me/quotes/q-1/pdf")
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "PDF_RENDER_UNAVAILABLE"


@requires_client
def test_PDF14_5xx_503_unavailable(monkeypatch):
    """5xx 응답 → 503 PDF_RENDER_UNAVAILABLE (gotenberg_svc unit level)."""
    class _R:
        status_code = 502
        headers = {"content-type": "text/plain"}
        content = b"bad gateway"

    monkeypatch.setattr("services.gotenberg_svc.httpx.post", lambda *a, **k: _R())
    monkeypatch.setenv("GOTENBERG_URL", "http://x")
    from services.gotenberg_svc import render_html_pdf, PdfRenderError
    with pytest.raises(PdfRenderError) as exc:
        render_html_pdf("<html/>")
    assert exc.value.code == "PDF_RENDER_UNAVAILABLE"
    assert exc.value.http_status == 503


@requires_client
def test_PDF15_4xx_502_invalid(monkeypatch):
    class _R:
        status_code = 400
        headers = {"content-type": "text/plain"}
        content = b"bad request"

    monkeypatch.setattr("services.gotenberg_svc.httpx.post", lambda *a, **k: _R())
    monkeypatch.setenv("GOTENBERG_URL", "http://x")
    from services.gotenberg_svc import render_html_pdf, PdfRenderError
    with pytest.raises(PdfRenderError) as exc:
        render_html_pdf("<html/>")
    assert exc.value.code == "PDF_RENDER_INVALID"
    assert exc.value.http_status == 502


@requires_client
def test_PDF16_non_pdf_content_type_502(monkeypatch):
    class _R:
        status_code = 200
        headers = {"content-type": "text/html"}
        content = b"%PDF-fake"

    monkeypatch.setattr("services.gotenberg_svc.httpx.post", lambda *a, **k: _R())
    monkeypatch.setenv("GOTENBERG_URL", "http://x")
    from services.gotenberg_svc import render_html_pdf, PdfRenderError
    with pytest.raises(PdfRenderError) as exc:
        render_html_pdf("<html/>")
    assert exc.value.code == "PDF_RENDER_INVALID"


@requires_client
def test_PDF17_pdf_content_type_but_no_magic_502(monkeypatch):
    class _R:
        status_code = 200
        headers = {"content-type": "application/pdf"}
        content = b"NOT_PDF"

    monkeypatch.setattr("services.gotenberg_svc.httpx.post", lambda *a, **k: _R())
    monkeypatch.setenv("GOTENBERG_URL", "http://x")
    from services.gotenberg_svc import render_html_pdf, PdfRenderError
    with pytest.raises(PdfRenderError) as exc:
        render_html_pdf("<html/>")
    assert exc.value.code == "PDF_RENDER_INVALID"


def test_PDF18_PDF19_render_call_payload_and_file(monkeypatch):
    """gotenberg_svc.render_html_pdf 가 (a) preferCssPageSize/printBackground 를 문자열 true 로 넘기고,
    (b) files=('index.html', ..., 'text/html') 로 업로드하는지 실제 호출 파라미터 검사."""
    captured = {}

    class _R:
        status_code = 200
        headers = {"content-type": "application/pdf"}
        content = _VALID_PDF_BYTES

    def _post(url, files=None, data=None, timeout=None):
        captured["url"] = url
        captured["files"] = files
        captured["data"] = data
        captured["timeout"] = timeout
        return _R()

    monkeypatch.setattr("services.gotenberg_svc.httpx.post", _post)
    monkeypatch.setenv("GOTENBERG_URL", "http://gb.example:3000")
    from services.gotenberg_svc import render_html_pdf
    render_html_pdf("<html>ok</html>")

    assert captured["url"] == "http://gb.example:3000/forms/chromium/convert/html"
    fname, fbytes, ctype = captured["files"]["files"]
    assert fname == "index.html"
    assert ctype == "text/html"
    assert fbytes == b"<html>ok</html>"
    assert captured["data"] == {"preferCssPageSize": "true", "printBackground": "true"}


# ════════════════════════════════════════════════════════════════════
# DOCUMENT : PDF-20 ~ 25
# ════════════════════════════════════════════════════════════════════
@requires_client
def test_PDF20_PDF25_register_generated_call_contract(monkeypatch):
    """document_svc.register_generated 호출 인자 계약 : company_id/category/linked_table/linked_id/
    generated_by/tags/source/file_name/mime_type."""
    from services import document_svc as ds
    # PDF-24 source=AUTO_GENERATED 계약 검증 : 원본 register_generated 소스 캡처 (override 전).
    import inspect
    _orig_register_src = inspect.getsource(ds.register_generated)

    captured = {}
    async def fake_register(**kwargs):
        captured.update(kwargs)
        return {"id": "doc-1", "company_id": kwargs["company_id"],
                "file_name": kwargs["file_name"]}
    async def fake_url(doc_id, ttl):
        return "https://signed.example/" + doc_id

    monkeypatch.setattr(ds, "register_generated", fake_register)
    monkeypatch.setattr(ds, "get_signed_url", fake_url)
    # document_svc.get_attachments 를 stub (기존 문서 없음)
    async def fake_get_attachments(t, i):
        return []
    monkeypatch.setattr(ds, "get_attachments", fake_get_attachments)

    _set_supplier_env(monkeypatch); _set_gotenberg_env(monkeypatch)
    monkeypatch.setattr(pdf_svc, "render_html_pdf", _RenderCallSpy())

    store = _base_store(_issued_quote(company_id="C-A"),
                        companies=[{"id": "C-A", "name": "테스트"}])
    app = FastAPI(); app.include_router(mq.router)
    app.dependency_overrides[mq.get_current_user] = lambda: _company_user("C-A", "U-1")
    fake = FakeSupabase(store); mq.get_supabase = lambda: fake; ds.get_supabase = lambda: fake
    c = TestClient(app)
    r = c.post("/me/quotes/q-1/pdf")
    assert r.status_code == 200

    assert captured["company_id"] == "C-A"                              # PDF-20
    assert captured["category"] == "general"                             # PDF-23
    assert captured["linked_table"] == "quotes"                          # PDF-20
    assert captured["linked_id"] == "q-1"                                # PDF-20
    assert captured["generated_by"] == "member_quote_pdf_v1"             # PDF-21
    assert captured["tags"] == ["quote", "member_auto"]                  # PDF-22
    assert captured["file_name"] == "TAI_견적서_QT-20260906-DEADBEEF.pdf"  # PDF-25
    assert captured["mime_type"] == "application/pdf"
    # PDF-24 source=AUTO_GENERATED : register_generated 원본 소스에 강제 문구 존재 (override 전 캡처)
    assert 'source="AUTO_GENERATED"' in _orig_register_src, (
        "register_generated 는 source=AUTO_GENERATED 를 강제해야 한다"
    )


# ════════════════════════════════════════════════════════════════════
# IDEMPOTENT : PDF-26 ~ 29
# ════════════════════════════════════════════════════════════════════
@requires_client
def test_PDF26_29_idempotent_reuse(monkeypatch):
    """1st call → generated=True, 2nd call → generated=False, render 재호출 0, document_id 동일."""
    from services import document_svc as ds

    docs = []
    async def fake_register(**kwargs):
        doc = {"id": "doc-" + str(len(docs) + 1),
               "company_id": kwargs["company_id"],
               "file_name": kwargs["file_name"],
               "generated_by": kwargs["generated_by"],
               "source": "AUTO_GENERATED",
               "linked_table": kwargs["linked_table"],
               "linked_id": kwargs["linked_id"]}
        docs.append(doc)
        return doc
    async def fake_url(doc_id, ttl):
        return "https://signed.example/" + doc_id
    async def fake_get_attachments(t, i):
        return list(docs)

    monkeypatch.setattr(ds, "register_generated", fake_register)
    monkeypatch.setattr(ds, "get_signed_url", fake_url)
    monkeypatch.setattr(ds, "get_attachments", fake_get_attachments)

    _set_supplier_env(monkeypatch); _set_gotenberg_env(monkeypatch)
    render = _RenderCallSpy()
    monkeypatch.setattr(pdf_svc, "render_html_pdf", render)

    store = _base_store(_issued_quote(company_id="C-A"),
                        companies=[{"id": "C-A", "name": "테스트"}])
    app = FastAPI(); app.include_router(mq.router)
    app.dependency_overrides[mq.get_current_user] = lambda: _company_user("C-A", "U-1")
    fake = FakeSupabase(store); mq.get_supabase = lambda: fake; ds.get_supabase = lambda: fake
    c = TestClient(app)

    r1 = c.post("/me/quotes/q-1/pdf")
    assert r1.status_code == 200 and r1.json()["data"]["generated"] is True    # PDF-26
    assert render.calls == 1
    doc_id_1 = r1.json()["data"]["document_id"]

    r2 = c.post("/me/quotes/q-1/pdf")
    assert r2.status_code == 200 and r2.json()["data"]["generated"] is False   # PDF-27
    assert render.calls == 1, "재사용 시 Gotenberg 재호출 금지"                  # PDF-27
    assert r2.json()["data"]["url"].startswith("https://signed.example/")      # PDF-28
    assert r2.json()["data"]["document_id"] == doc_id_1                        # PDF-29


# ════════════════════════════════════════════════════════════════════
# SECURITY : PDF-30 ~ 31
# ════════════════════════════════════════════════════════════════════
def test_PDF30_html_autoescape(monkeypatch):
    """company_name / product_name 등에 스크립트가 있어도 raw <script>가 렌더 HTML 에 포함되지 않는다."""
    _set_supplier_env(monkeypatch); _set_gotenberg_env(monkeypatch)
    q = _issued_quote(company_id="C-A")
    q["company_name"] = "<script>alert(1)</script>주식회사"
    from services.member_quote_pdf_svc import _render_html, _supplier_config, _validate_snapshot, _quote_date_kst
    supplier = _supplier_config()
    item = _validate_snapshot(q)
    html = _render_html(q, item, supplier, _quote_date_kst(q["created_at"]))
    # jinja2 autoescape → <script> 는 &lt;script&gt; 로.
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


@requires_client
def test_PDF31_signed_url_only_after_ownership(monkeypatch):
    """소유권 실패 시 signed URL 이 절대 만들어지지 않는다 — document_svc 호출 0."""
    from services import document_svc as ds
    called = {"reg": 0, "url": 0, "att": 0}

    async def fake_register(**k):
        called["reg"] += 1; return {"id": "d", "company_id": k["company_id"], "file_name": "x"}
    async def fake_url(d, t):
        called["url"] += 1; return "https://x"
    async def fake_att(t, i):
        called["att"] += 1; return []

    monkeypatch.setattr(ds, "register_generated", fake_register)
    monkeypatch.setattr(ds, "get_signed_url", fake_url)
    monkeypatch.setattr(ds, "get_attachments", fake_att)

    store = _base_store(_issued_quote(company_id="C-OWNER"),
                        companies=[{"id": "C-OWNER", "name": "A"}])
    render = _RenderCallSpy()
    c = _client(_company_user("C-B", "U-B"), store, monkeypatch, render_spy=render)
    r = c.post("/me/quotes/q-1/pdf")
    assert r.status_code == 404
    assert called["reg"] == 0 and called["url"] == 0 and called["att"] == 0
    assert render.calls == 0


# ════════════════════════════════════════════════════════════════════
# INFRA / CONFIG / PORT
# ════════════════════════════════════════════════════════════════════
def test_INFRA1_base_url_env_only(monkeypatch):
    """GOTENBERG_URL 만 SoT. 다른 env / 하드코딩 없음."""
    monkeypatch.setenv("GOTENBERG_URL", "http://custom.example:9999")
    assert gotenberg_svc._base_url() == "http://custom.example:9999"


def test_PORT1_no_railway_hostname_port_8080_in_sources():
    """소스에 gotenberg.railway.internal:8080 literal 부재."""
    import inspect
    for mod in (gotenberg_svc, pdf_svc):
        src = inspect.getsource(mod)
        assert "gotenberg.railway.internal:8080" not in src, (
            "포트 8080 literal 이 코드에 박혀서는 안 된다 (env SoT)"
        )


def test_PORT2_no_railway_hostname_port_3000_in_sources():
    """소스에 gotenberg.railway.internal:3000 literal 부재."""
    import inspect
    for mod in (gotenberg_svc, pdf_svc):
        src = inspect.getsource(mod)
        assert "gotenberg.railway.internal:3000" not in src, (
            "운영 URL 은 Railway env 로만 바인딩 — 코드에 hostname/포트 literal 금지"
        )


def test_PORT3_missing_env_config_missing_no_gotenberg_call(monkeypatch):
    """GOTENBERG_URL 미설정 → PDF_RENDER_CONFIG_MISSING(503). localhost/public fallback 시도 0."""
    monkeypatch.delenv("GOTENBERG_URL", raising=False)
    posted = {"n": 0}

    def _post(*a, **k):
        posted["n"] += 1
        raise AssertionError("Gotenberg 호출이 발생하면 안 된다 (env 없음)")

    monkeypatch.setattr("services.gotenberg_svc.httpx.post", _post)
    from services.gotenberg_svc import render_html_pdf, PdfRenderError
    with pytest.raises(PdfRenderError) as exc:
        render_html_pdf("<html/>")
    assert exc.value.code == "PDF_RENDER_CONFIG_MISSING"
    assert exc.value.http_status == 503
    assert posted["n"] == 0


def test_CONFIG1_supplier_uses_tai_ceo_name(monkeypatch):
    """대표자 = TAI_CEO_NAME (invoice_svc 실측 정합). TAI_CORP_CEO 아님."""
    monkeypatch.setenv("TAI_CORP_NAME", "co")
    monkeypatch.setenv("TAI_CEO_NAME", "홍길동")
    monkeypatch.setenv("TAI_CORP_NUM", "1")
    monkeypatch.setenv("TAI_CORP_ADDR", "a")
    monkeypatch.setenv("QUOTE_SUPPLIER_TEL", "t")
    monkeypatch.setenv("QUOTE_SUPPLIER_EMAIL", "e")
    monkeypatch.delenv("QUOTE_SUPPLIER_FAX", raising=False)
    # TAI_CORP_CEO 는 설정해도 무시돼야 함
    monkeypatch.setenv("TAI_CORP_CEO", "무시대상")
    cfg = pdf_svc._supplier_config()
    assert cfg["representative"] == "홍길동"


def test_CONFIG1b_source_uses_tai_ceo_name_symbol():
    """svc 소스에 TAI_CEO_NAME 참조 + TAI_CORP_CEO 미참조."""
    import inspect
    src = inspect.getsource(pdf_svc)
    assert "TAI_CEO_NAME" in src
    assert "TAI_CORP_CEO" not in src, "TAI_CORP_CEO 는 존재하지 않는 env — 코드에 참조 금지"


@pytest.mark.parametrize("missing_key", [
    "TAI_CORP_NAME", "TAI_CEO_NAME", "TAI_CORP_NUM", "TAI_CORP_ADDR",
    "QUOTE_SUPPLIER_TEL", "QUOTE_SUPPLIER_EMAIL",
])
def test_CONFIG2_missing_supplier_raises(monkeypatch, missing_key):
    _set_supplier_env(monkeypatch, missing={missing_key})
    with pytest.raises(pdf_svc.QuotePdfError) as exc:
        pdf_svc._supplier_config()
    assert exc.value.code == "QUOTE_SUPPLIER_CONFIG_MISSING"
    assert exc.value.http_status == 503


def test_CONFIG2_fax_is_optional(monkeypatch):
    """FAX 는 선택 — 없어도 QUOTE_SUPPLIER_CONFIG_MISSING 미발동."""
    _set_supplier_env(monkeypatch)
    monkeypatch.delenv("QUOTE_SUPPLIER_FAX", raising=False)
    cfg = pdf_svc._supplier_config()
    assert cfg["fax"] == ""      # 빈 값 허용


def test_CONFIG3_missing_message_does_not_leak_values(monkeypatch):
    """예외 message 에 공급자 실제 값(대표자명 등)이 포함되지 않는다."""
    _set_supplier_env(monkeypatch, missing={"QUOTE_SUPPLIER_EMAIL"})
    with pytest.raises(pdf_svc.QuotePdfError) as exc:
        pdf_svc._supplier_config()
    # 다른 필드 값(홍길동/사업자번호 등)이 message 에 노출되면 안 된다
    msg = exc.value.message
    assert "홍길동" not in msg
    assert "123-45-67890" not in msg
    assert "테헤란로" not in msg
