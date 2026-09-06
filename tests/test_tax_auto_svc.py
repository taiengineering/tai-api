"""WO-TAX-INVOICE-AUTO-01 STEP 3 — auto ORIGINAL orchestrator O1~O11 (mock provider).

정본 = services/tax_auto_svc.py (얇은 helper) — 새 엔진 0, 재사용 앵커만.
- evaluate_eligibility, create_request(source=AUTO_PAYMENT), process_tax_invoice_request 위임.
- INVOICE_LIVE OFF → 423 → outcome=GATED (mutation 0, provider 호출 0).
- fail-soft: 최상위 예외 삼킴 → outcome=ERROR (호출측 결제/환불 후처리에 영향 0).

케이스:
  O1  DirectBank + proof=TAX_INVOICE + SUCCESS → ISSUED (auto path 진입)
  O2  VBank + SUCCESS + proof=TAX_INVOICE → ISSUED
  O3  CARD → NOOP (조기 종료, provider 0)
  O4  CASH_RECEIPT (proof) → NOOP (조기 종료)
  O5  회사정보 부족 (company profile incomplete) → ELIGIBLE_DENIED, provider 0
  O6  중복 payment.success 재호출 → ORIGINAL 1 (2회차 REQUEST_CREATED_ONLY)
  O7  고객 재요청 (customer request) → ORIGINAL 1
  O8  provider 실패 → outcome=PROCESSOR_FAILED, request.status=FAILED
      + 호출측 payment/refund 상태 rollback 0 (fail-soft envelope)
  O9  INVOICE_LIVE OFF → outcome=GATED, provider 0, tax_invoices 0
      request.status 는 REQUESTED (processor 가 gate 이전 mutation 0 계약 준수)
  O10 mock provider success → outcome=ISSUED, request.status=ISSUED
  O11 orchestrator 예외 → outcome=ERROR (fail-soft), 호출측 rollback 0
"""
from __future__ import annotations

import uuid

import pytest

import services.invoice_svc as inv
import services.tax_auto_svc as auto
import services.tax_invoice_processor_svc as proc  # noqa: F401  (import 검증)


# ── FakeSupabase (test_tax_invoice_processor 와 동일 계약; 필요한 UNIQUE 추가) ──
class _Result:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count if count is not None else (len(data) if data is not None else 0)


class _Query:
    def __init__(self, store, table, log):
        self.store = store; self.table = table; self.log = log
        self._op = None; self._payload = None; self._filters = []; self._cols = "*"

    def select(self, cols="*", *a, **k):
        self._op = "select"; self._cols = cols or "*"; return self

    def insert(self, row): self._op = "insert"; self._payload = row; return self
    def update(self, patch): self._op = "update"; self._payload = patch; return self

    def eq(self, c, v): self._filters.append(("eq", c, v)); return self
    def in_(self, c, vals): self._filters.append(("in", c, list(vals))); return self
    def is_(self, c, v): self._filters.append(("is", c, v)); return self
    def limit(self, n): return self
    def order(self, *a, **k): return self
    def range(self, s, e): return self
    def or_(self, *a, **k): return self

    def _match(self, row):
        for op, c, v in self._filters:
            if op == "eq" and str(row.get(c)) != str(v):
                return False
            if op == "in" and row.get(c) not in v:
                return False
        return True

    def execute(self):
        rows = self.store.setdefault(self.table, [])
        self.log.append((self.table, self._op))
        if self._op == "select":
            cols = None if self._cols == "*" else [c.strip() for c in self._cols.split(",") if c.strip()]
            out = []
            for r in rows:
                if not self._match(r):
                    continue
                out.append(dict(r) if cols is None else {k: r.get(k) for k in cols})
            return _Result(out)
        if self._op == "insert":
            items = self._payload if isinstance(self._payload, list) else [self._payload]
            out = []
            for it in items:
                it = dict(it); it.setdefault("id", str(uuid.uuid4()))
                # UNIQUE(payment_id, doc_type) 시뮬 — create_request idempotent 경로 검증용
                if self.table == "tax_invoice_requests":
                    for r in rows:
                        if (r.get("payment_id") == it.get("payment_id")
                                and r.get("doc_type") == it.get("doc_type")):
                            raise Exception('duplicate key value violates unique constraint "tax_invoice_requests_payment_doc_unique"')
                if self.table == "tax_invoices":
                    for r in rows:
                        if r.get("doc_type") == it.get("doc_type") and r.get("mgt_key") == it.get("mgt_key"):
                            raise Exception('duplicate key value violates unique constraint "tax_invoices_doc_type_mgt_key"')
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


class MockTax:
    def __init__(self, fail=False):
        self.calls = []; self.fail = fail

    def issue_tax(self, conf, **kw):
        self.calls.append(kw)
        if self.fail:
            raise Exception("popbill down")
        return {"nts": "NTS-AUTO", "code": 1, "message": "ok"}

    def issue_cash(self, conf, **kw):
        self.calls.append(kw); return {"nts": "CR-AUTO", "code": 1, "message": "ok"}


# ── fixtures ──
def _payment(**kw):
    base = {
        "id": "pay-1",
        "status_code": "SUCCESS",
        "company_id": "co-1",
        "product_type": "SAAS_INDUSTRIAL",
        "pg_method": "DirectBank",
        "proof_type": "TAX_INVOICE",
        "supply_amount": 100000,
        "vat_amount": 10000,
        "total_amount": 110000,
        "paid_at": "2026-09-06T00:00:00Z",
    }
    base.update(kw)
    return base


def _company(**kw):
    base = {
        "id": "co-1",
        "name": "테스트 주식회사",
        "business_number": "1234567890",
        "representative_name": "홍길동",
        "contact_email": "biz@test.co",
        "address": "서울시 강남구",
        "business_type": "정보통신",
        "business_category": "SaaS",
    }
    base.update(kw)
    return base


def _setup(monkeypatch, store=None, *, live=True, provider_fail=False):
    """orchestrator + invoice_svc 두 곳의 supabase 를 같은 store 로 결선."""
    if store is None:
        store = {
            "payments": [_payment()],
            "companies": [_company()],
            "tax_invoice_requests": [],
            "tax_invoices": [],
        }
    fake = FakeSupabase(store)
    mock = MockTax(fail=provider_fail)

    # invoice_svc: get_supabase / invoice_live / popbill 시크릿 / popbill seam / audit stub
    monkeypatch.setattr(inv, "get_supabase", lambda: fake)
    monkeypatch.setattr(inv, "invoice_live", lambda: live)
    monkeypatch.setattr(inv, "_popbill_conf", lambda: {
        "corp_num": "7233901422", "corp_name": "TAI", "ceo_name": "심태왕",
        "corp_addr": "서울", "biz_type": "정보통신업", "biz_class": "응용SW",
        "user_id": "", "link_id": "x", "secret_key": "y", "is_test": True,
    })
    monkeypatch.setattr(inv, "_popbill_issue_tax", lambda conf, **kw: mock.issue_tax(conf, **kw))
    monkeypatch.setattr(inv, "_popbill_issue_cash", lambda conf, **kw: mock.issue_cash(conf, **kw))
    monkeypatch.setattr(inv, "audit_svc",
                        type("A", (), {"record": staticmethod(lambda *a, **k: None)}))
    return store, fake, mock


# ═════════════════════════════════════════════════════════════════════
# O1  DirectBank + TAX_INVOICE + SUCCESS → auto ISSUED
# ═════════════════════════════════════════════════════════════════════
def test_O1_directbank_tax_invoice_auto_issued(monkeypatch):
    store, fake, mock = _setup(monkeypatch)
    out = auto.maybe_auto_issue_tax_invoice(fake, "pay-1", "PAYMENT_SUCCESS")
    assert out["outcome"] == "ISSUED", out
    assert out["request_id"] is not None
    assert len(mock.calls) == 1, "provider 는 정확히 1회 호출"
    # request row = ISSUED / source = AUTO_PAYMENT
    req = store["tax_invoice_requests"][0]
    assert req["status"] == "ISSUED"
    assert req["source"] == "AUTO_PAYMENT"
    # ledger 원본 1건
    assert len([i for i in store["tax_invoices"] if i.get("invoice_kind") != "MODIFIED"]) == 1


# ═════════════════════════════════════════════════════════════════════
# O2  VBank + proof=TAX_INVOICE → auto ISSUED
# ═════════════════════════════════════════════════════════════════════
def test_O2_vbank_tax_invoice_auto_issued(monkeypatch):
    store, fake, mock = _setup(monkeypatch)
    store["payments"][0]["pg_method"] = "VBank"
    out = auto.maybe_auto_issue_tax_invoice(fake, "pay-1", "PAYMENT_SUCCESS")
    assert out["outcome"] == "ISSUED", out
    assert len(mock.calls) == 1
    assert store["tax_invoice_requests"][0]["status"] == "ISSUED"


# ═════════════════════════════════════════════════════════════════════
# O3  CARD → NOOP (조기 종료; eligibility 도 안 봄)
# ═════════════════════════════════════════════════════════════════════
def test_O3_card_noop(monkeypatch):
    store, fake, mock = _setup(monkeypatch)
    store["payments"][0]["pg_method"] = "Card"
    out = auto.maybe_auto_issue_tax_invoice(fake, "pay-1", "PAYMENT_SUCCESS")
    assert out["outcome"] == "NOOP"
    assert out["reason"] == "PAYMENT_METHOD_CARD"
    assert mock.calls == [], "카드 결제는 provider 호출 0"
    assert store["tax_invoice_requests"] == [], "카드는 request 생성 0"
    assert store["tax_invoices"] == []


# ═════════════════════════════════════════════════════════════════════
# O4  proof_type=CASH_RECEIPT → NOOP
# ═════════════════════════════════════════════════════════════════════
def test_O4_cash_receipt_noop(monkeypatch):
    store, fake, mock = _setup(monkeypatch)
    store["payments"][0]["proof_type"] = "CASH_RECEIPT"
    out = auto.maybe_auto_issue_tax_invoice(fake, "pay-1", "PAYMENT_SUCCESS")
    assert out["outcome"] == "NOOP"
    assert out["reason"] == "PROOF_NOT_TAX_INVOICE"
    assert mock.calls == []
    assert store["tax_invoice_requests"] == []


# ═════════════════════════════════════════════════════════════════════
# O5  [PATCH-1] 회사정보 부족 → 자동 복구 가능 DENY → 예외큐 REVIEW_REQUIRED
#      (계약 변경: 이전 ELIGIBLE_DENIED → 이제 ELIGIBLE_REVIEW + queue)
# ═════════════════════════════════════════════════════════════════════
def test_O5_company_incomplete_becomes_exception_queue(monkeypatch):
    store, fake, mock = _setup(monkeypatch)
    # 대표자명 제거 → 회사정보 부족
    store["companies"][0]["representative_name"] = ""
    out = auto.maybe_auto_issue_tax_invoice(fake, "pay-1", "PAYMENT_SUCCESS")
    # PATCH-1: COMPANY_PROFILE_INCOMPLETE 는 자동 복구 가능 DENY → 예외큐 생성
    assert out["outcome"] == "ELIGIBLE_REVIEW", out
    assert out["reason"] == "COMPANY_PROFILE_INCOMPLETE"
    assert out["request_id"] is not None
    # provider 는 호출되지 않음
    assert mock.calls == []
    assert store["tax_invoices"] == []
    # 예외큐 request row 생성 (REVIEW_REQUIRED)
    reqs = store["tax_invoice_requests"]
    assert len(reqs) == 1
    assert reqs[0]["status"] == "REVIEW_REQUIRED"
    assert reqs[0]["source"] == "AUTO_PAYMENT"
    assert reqs[0]["failure_code"] == "COMPANY_PROFILE_INCOMPLETE"


# ═════════════════════════════════════════════════════════════════════
# O6  중복 payment.success 재호출 → ORIGINAL 1 (2회차 REQUEST_CREATED_ONLY)
# ═════════════════════════════════════════════════════════════════════
def test_O6_duplicate_payment_success_original_once(monkeypatch):
    store, fake, mock = _setup(monkeypatch)
    # 1회차
    out1 = auto.maybe_auto_issue_tax_invoice(fake, "pay-1", "PAYMENT_SUCCESS")
    assert out1["outcome"] == "ISSUED"
    assert len(mock.calls) == 1
    # 2회차 (동일 payment_id 로 재호출)
    out2 = auto.maybe_auto_issue_tax_invoice(fake, "pay-1", "PAYMENT_SUCCESS")
    assert out2["outcome"] == "REQUEST_CREATED_ONLY"
    assert out2["reason"] == "ISSUED"       # 재사용된 request 는 이미 ISSUED
    assert len(mock.calls) == 1, "재사용은 provider 재호출 금지 (ORIGINAL 1)"
    # request row / ledger 각 1건 유지
    assert len(store["tax_invoice_requests"]) == 1
    assert len([i for i in store["tax_invoices"] if i.get("invoice_kind") != "MODIFIED"]) == 1


# ═════════════════════════════════════════════════════════════════════
# O7  고객 재요청(CUSTOMER_REQUEST 반복) → ORIGINAL 1
# ═════════════════════════════════════════════════════════════════════
def test_O7_customer_re_request_original_once(monkeypatch):
    store, fake, mock = _setup(monkeypatch)
    # 1회차 (payment_success)
    out1 = auto.maybe_auto_issue_tax_invoice(fake, "pay-1", "PAYMENT_SUCCESS")
    assert out1["outcome"] == "ISSUED"
    # 2회차 (customer request 재클릭)
    out2 = auto.maybe_auto_issue_tax_invoice(fake, "pay-1", "CUSTOMER_REQUEST")
    assert out2["outcome"] == "REQUEST_CREATED_ONLY"
    assert len(mock.calls) == 1
    assert len(store["tax_invoice_requests"]) == 1


# ═════════════════════════════════════════════════════════════════════
# O8  provider 실패 → PROCESSOR_FAILED / request FAILED / 호출측 rollback 0
# ═════════════════════════════════════════════════════════════════════
def test_O8_provider_failure_no_rollback(monkeypatch):
    store, fake, mock = _setup(monkeypatch, provider_fail=True)
    # payment SUCCESS 상태 유지 확인
    pre_pay_status = store["payments"][0]["status_code"]
    out = auto.maybe_auto_issue_tax_invoice(fake, "pay-1", "PAYMENT_SUCCESS")
    assert out["outcome"] == "PROCESSOR_FAILED", out
    # request row 는 FAILED 로 mark 됨 (processor 계약)
    req = store["tax_invoice_requests"][0]
    assert req["status"] == "FAILED"
    assert req.get("failure_code")
    # payment 는 여전히 SUCCESS (orchestrator 는 payment 를 만지지 않음)
    assert store["payments"][0]["status_code"] == pre_pay_status
    # provider 1회 호출 후 실패
    assert len(mock.calls) == 1


# ═════════════════════════════════════════════════════════════════════
# O9  INVOICE_LIVE OFF → GATED (423), provider 0, ledger 0, request 상태 보존
# ═════════════════════════════════════════════════════════════════════
def test_O9_invoice_live_off_gated(monkeypatch):
    store, fake, mock = _setup(monkeypatch, live=False)
    out = auto.maybe_auto_issue_tax_invoice(fake, "pay-1", "PAYMENT_SUCCESS")
    assert out["outcome"] == "GATED", out
    assert out["reason"] == "INVOICE_GATED"
    # provider 0, ledger 0
    assert mock.calls == []
    assert store["tax_invoices"] == []
    # request row 는 생성됨 (create_request 는 gate 이전 실행). 상태는 REQUESTED 보존
    # (processor 가 gate 이전 mutation 0 계약 준수 → PROCESSING 마킹 없음)
    req = store["tax_invoice_requests"][0]
    assert req["status"] == "REQUESTED"
    assert req["source"] == "AUTO_PAYMENT"


# ═════════════════════════════════════════════════════════════════════
# O10  mock provider success → ISSUED
# (O1 과 유사하지만 명시적으로 tax_invoices 원장 필드 검증)
# ═════════════════════════════════════════════════════════════════════
def test_O10_mock_provider_success_issued(monkeypatch):
    store, fake, mock = _setup(monkeypatch)
    out = auto.maybe_auto_issue_tax_invoice(fake, "pay-1", "PAYMENT_SUCCESS")
    assert out["outcome"] == "ISSUED"
    # 원장 원본 1건 ISSUED
    originals = [i for i in store["tax_invoices"] if i.get("invoice_kind") != "MODIFIED"]
    assert len(originals) == 1
    assert originals[0]["status"] == "ISSUED"
    assert originals[0]["nts_confirm_num"] == "NTS-AUTO"
    # 금액 = payments SoT 그대로 (재계산 0)
    assert originals[0]["supply_cost"] == 100000
    assert originals[0]["tax"] == 10000
    assert originals[0]["total_amount"] == 110000


# ═════════════════════════════════════════════════════════════════════
# O11  orchestrator 예외 → outcome=ERROR (fail-soft), 호출측 rollback 0
# ═════════════════════════════════════════════════════════════════════
def test_O11_orchestrator_exception_fail_soft(monkeypatch):
    store, fake, mock = _setup(monkeypatch)

    # evaluate_eligibility 를 강제로 예외 발생하게 monkeypatch
    def boom(*a, **k):
        raise RuntimeError("simulated infrastructure failure")

    monkeypatch.setattr("services.tax_invoice_request_svc.evaluate_eligibility", boom)

    pre_pay_status = store["payments"][0]["status_code"]
    out = auto.maybe_auto_issue_tax_invoice(fake, "pay-1", "PAYMENT_SUCCESS")
    # 최상위 fail-soft envelope 이 예외를 삼키고 ERROR outcome 반환
    assert out["outcome"] == "ERROR", out
    assert "simulated" in (out.get("reason") or "")
    # payment / ledger / request 모두 무영향
    assert store["payments"][0]["status_code"] == pre_pay_status
    assert store["tax_invoice_requests"] == []
    assert store["tax_invoices"] == []
    assert mock.calls == []


# ═════════════════════════════════════════════════════════════════════
# 추가 안전: source 계약 (AUTO_PAYMENT 만 사용, MYPAGE/SAAS 아님)
# ═════════════════════════════════════════════════════════════════════
def test_auto_source_allowed():
    from services.tax_invoice_request_svc import _ALLOWED_SOURCES
    assert "AUTO_PAYMENT" in _ALLOWED_SOURCES
    # MYPAGE/SAAS 는 그대로 (기존 고객 경로 무변동)
    assert "MYPAGE" in _ALLOWED_SOURCES
    assert "SAAS" in _ALLOWED_SOURCES


# 회귀: helper 소스에 새 발행/새 popbill import 없음 (엔진 재작성 금지)
def test_no_new_engine_imports():
    """AST 로 실제 import 확인 (docstring 언급은 허용)."""
    import ast
    import inspect
    src = inspect.getsource(auto)
    tree = ast.parse(src)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for a in node.names:
                imported.add(f"{mod}.{a.name}" if mod else a.name)
        elif isinstance(node, ast.Import):
            for a in node.names:
                imported.add(a.name)
    # popbill/발행함수 직접 import 금지
    banned = {name for name in imported if "popbill" in name.lower()}
    assert banned == set(), f"auto helper 는 popbill 직접 import 금지: {banned}"
    assert "services.invoice_svc.issue_tax_invoice" not in imported
    assert "services.invoice_svc.issue_cash_receipt" not in imported
    # 사용해야 할 앵커는 반드시 참조 (함수 본문 grep — import 는 지연 import 라 tree 에 없을 수 있음)
    assert "evaluate_eligibility" in src
    assert "create_request" in src
    assert "process_tax_invoice_request" in src


# ═════════════════════════════════════════════════════════════════════
# [PATCH-1 A-P5] E1~E9 — AUTO 예외큐 완결성 + supply_date 추정 금지 + fallback 정합
# ═════════════════════════════════════════════════════════════════════

# E1: REVIEW_REQUIRED eligibility → tax_invoice_requests REVIEW_REQUIRED 1건, processor 0
def test_E1_review_required_creates_exception_queue(monkeypatch):
    store, fake, mock = _setup(monkeypatch)
    # LEGACY_PROOF_UNKNOWN: ACCOUNT_TRANSFER + proof=None → REVIEW_REQUIRED
    store["payments"][0]["pg_method"] = "DirectBank"
    store["payments"][0]["proof_type"] = "TAX_INVOICE"
    # 다른 결제에 이미 CASH_RECEIPT ISSUED 이력 남기면 CASH_RECEIPT_HISTORY_REVIEW 유도 대신,
    # 직접 payment.proof_type = None 로 LEGACY_PROOF_UNKNOWN 유도
    store["payments"][0]["proof_type"] = None
    out = auto.maybe_auto_issue_tax_invoice(fake, "pay-1", "PAYMENT_SUCCESS")
    # 사전 필터에서 걸릴 것 (proof != TAX_INVOICE)
    assert out["outcome"] == "NOOP"
    assert store["tax_invoice_requests"] == []
    # → REVIEW_REQUIRED 검증은 eligibility 가 REVIEW_REQUIRED 를 돌려주는 명확한 케이스로 재구성
    #   TAX_INVOICE 이력만 존재 + FAILED (E4 케이스 유사) 로 CASH_RECEIPT_HISTORY_REVIEW 유도
    store["payments"][0]["proof_type"] = "TAX_INVOICE"
    store["tax_invoices"] = [{"payment_id": "pay-1", "doc_type": "CASH_RECEIPT",
                              "status": "CANCELLED", "invoice_kind": "ORIGINAL"}]
    out2 = auto.maybe_auto_issue_tax_invoice(fake, "pay-1", "PAYMENT_SUCCESS")
    # eligibility → CASH_RECEIPT_HISTORY_REVIEW (REVIEW_REQUIRED)
    assert out2["outcome"] == "ELIGIBLE_REVIEW", out2
    assert out2["reason"] == "CASH_RECEIPT_HISTORY_REVIEW"
    assert out2["request_id"] is not None
    reqs = store["tax_invoice_requests"]
    assert len(reqs) == 1
    assert reqs[0]["status"] == "REVIEW_REQUIRED"
    assert reqs[0]["source"] == "AUTO_PAYMENT"
    assert reqs[0]["failure_code"] == "CASH_RECEIPT_HISTORY_REVIEW"
    assert mock.calls == []


# E2: COMPANY_PROFILE_INCOMPLETE → 예외큐 REVIEW_REQUIRED (failure_code 정확), processor 0
def test_E2_company_incomplete_exception_queued(monkeypatch):
    store, fake, mock = _setup(monkeypatch)
    store["companies"][0]["representative_name"] = ""
    out = auto.maybe_auto_issue_tax_invoice(fake, "pay-1", "PAYMENT_SUCCESS")
    assert out["outcome"] == "ELIGIBLE_REVIEW"
    assert out["reason"] == "COMPANY_PROFILE_INCOMPLETE"
    reqs = store["tax_invoice_requests"]
    assert len(reqs) == 1
    assert reqs[0]["status"] == "REVIEW_REQUIRED"
    assert reqs[0]["failure_code"] == "COMPANY_PROFILE_INCOMPLETE"
    # 금액 snapshot 은 payments SoT 그대로 (재계산 0)
    assert reqs[0]["supply_amount"] == 100000
    assert reqs[0]["vat_amount"] == 10000
    assert reqs[0]["total_amount"] == 110000
    assert mock.calls == []
    assert store["tax_invoices"] == []


# E3: 영구 DENY (CARD_RECEIPT_IS_EVIDENCE) → 예외큐 미생성
def test_E3_permanent_deny_card_no_queue(monkeypatch):
    store, fake, mock = _setup(monkeypatch)
    # 사전 필터로 이미 CARD 는 NOOP — 그러나 사전 필터 우회 시(예: canonical_payment_instrument 가 CARD 반환)
    # eligibility CARD_RECEIPT_IS_EVIDENCE 로 진입해도 예외큐 미생성이 계약이어야 함.
    # canonical_payment_instrument 는 method=CARD 로 반환 → 사전 필터에 걸림 = NOOP 이며 큐 0 이 유지
    store["payments"][0]["pg_method"] = "Card"
    out = auto.maybe_auto_issue_tax_invoice(fake, "pay-1", "PAYMENT_SUCCESS")
    assert out["outcome"] == "NOOP"
    assert store["tax_invoice_requests"] == [], "카드 결제는 예외큐 생성 0"


# E4: 영구 DENY (CASH_RECEIPT_SELECTED) → 예외큐 미생성
def test_E4_permanent_deny_cash_receipt_no_queue(monkeypatch):
    store, fake, mock = _setup(monkeypatch)
    # proof=CASH_RECEIPT 는 사전 필터에서 걸림 (proof != TAX_INVOICE) → NOOP
    store["payments"][0]["proof_type"] = "CASH_RECEIPT"
    out = auto.maybe_auto_issue_tax_invoice(fake, "pay-1", "PAYMENT_SUCCESS")
    assert out["outcome"] == "NOOP"
    assert store["tax_invoice_requests"] == [], "현금영수증 선택은 예외큐 생성 0"


# E4b: 영구 DENY (TAX_INVOICE_ALREADY_EXISTS) → 예외큐 미생성 (사전 필터 통과 후 eligibility DENY)
def test_E4b_permanent_deny_tax_invoice_already_no_queue(monkeypatch):
    store, fake, mock = _setup(monkeypatch)
    # 원본 세금계산서가 이미 ISSUED → TAX_INVOICE_ALREADY_EXISTS (permanent)
    store["tax_invoices"] = [{"payment_id": "pay-1", "doc_type": "TAX_INVOICE",
                              "status": "ISSUED", "invoice_kind": "ORIGINAL"}]
    out = auto.maybe_auto_issue_tax_invoice(fake, "pay-1", "PAYMENT_SUCCESS")
    assert out["outcome"] == "ELIGIBLE_DENIED"
    assert out["reason"] == "TAX_INVOICE_ALREADY_EXISTS"
    # 예외큐 생성 0 (큐 오염 방지)
    assert store["tax_invoice_requests"] == []
    assert mock.calls == []


# E5: 중복 REVIEW event → 예외큐 1건 (멱등)
def test_E5_duplicate_review_events_idempotent(monkeypatch):
    store, fake, mock = _setup(monkeypatch)
    store["companies"][0]["representative_name"] = ""  # COMPANY_PROFILE_INCOMPLETE 유도
    out1 = auto.maybe_auto_issue_tax_invoice(fake, "pay-1", "PAYMENT_SUCCESS")
    out2 = auto.maybe_auto_issue_tax_invoice(fake, "pay-1", "PAYMENT_SUCCESS")
    assert out1["outcome"] == "ELIGIBLE_REVIEW"
    assert out2["outcome"] == "ELIGIBLE_REVIEW"
    # UNIQUE(payment_id, doc_type) → 예외 request 는 하나만
    reqs = store["tax_invoice_requests"]
    assert len(reqs) == 1
    assert reqs[0]["status"] == "REVIEW_REQUIRED"
    assert reqs[0]["failure_code"] == "COMPANY_PROFILE_INCOMPLETE"


# E6: paid_at null → business_today 사용 0, REVIEW_REQUIRED(SUPPLY_DATE_UNRESOLVED), processor 0
def test_E6_paid_at_null_supply_date_unresolved(monkeypatch):
    store, fake, mock = _setup(monkeypatch)
    store["payments"][0]["paid_at"] = None

    # business_today 를 호출하면 실패하도록 감시
    called = {"business_today": 0}
    from services import time as time_svc
    orig_bt = time_svc.business_today

    def _spy():
        called["business_today"] += 1
        return orig_bt()

    monkeypatch.setattr(time_svc, "business_today", _spy)

    out = auto.maybe_auto_issue_tax_invoice(fake, "pay-1", "PAYMENT_SUCCESS")
    assert out["outcome"] == "SUPPLY_DATE_UNRESOLVED", out
    assert out["reason"] == "SUPPLY_DATE_UNRESOLVED"
    assert out["request_id"] is not None
    # provider 호출 0
    assert mock.calls == []
    # 예외큐 request row 생성
    reqs = store["tax_invoice_requests"]
    assert len(reqs) == 1
    assert reqs[0]["status"] == "REVIEW_REQUIRED"
    assert reqs[0]["failure_code"] == "SUPPLY_DATE_UNRESOLVED"
    # business_today 는 orchestrator 경로에서 호출되지 않음 (PATCH-1 A-P2)
    #   ※ 다른 서비스 (계약 자동생성 등) 는 별개 — 여기서는 orchestrator 만 실행
    assert called["business_today"] == 0, "AUTO 경로에서 supply_date 추정용 business_today 호출 금지"


# E7: paid_at malformed → REVIEW_REQUIRED(SUPPLY_DATE_UNRESOLVED), processor 0
def test_E7_paid_at_malformed_supply_date_unresolved(monkeypatch):
    store, fake, mock = _setup(monkeypatch)
    store["payments"][0]["paid_at"] = "not-a-date"

    out = auto.maybe_auto_issue_tax_invoice(fake, "pay-1", "PAYMENT_SUCCESS")
    assert out["outcome"] == "SUPPLY_DATE_UNRESOLVED"
    assert out["reason"] == "SUPPLY_DATE_UNRESOLVED"
    assert mock.calls == []
    reqs = store["tax_invoice_requests"]
    assert len(reqs) == 1
    assert reqs[0]["status"] == "REVIEW_REQUIRED"
    assert reqs[0]["failure_code"] == "SUPPLY_DATE_UNRESOLVED"


# 회귀: business_today import 부재 (AST) — A-P2 계약 검증
def test_E6b_no_business_today_import_in_auto_svc():
    """PATCH-1 A-P2: tax_auto_svc 는 supply_date 추정을 위해 business_today 를 import 하지 않는다."""
    import ast
    import inspect
    src = inspect.getsource(auto)
    tree = ast.parse(src)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for a in node.names:
                imported.add(a.name)
        elif isinstance(node, ast.Import):
            for a in node.names:
                imported.add(a.name)
    assert "business_today" not in imported, (
        "PATCH-1 A-P2: business_today import 금지 — supply_date 추정 금지"
    )


# E8/E9: detail 3분할 fallback 정합은 tests/test_tax_auto_amount_projection.py 에 추가로 커버.
# (여기 파일은 orchestrator 단위 테스트 범위 — E8/E9 는 admin detail 라우터 통합이라 별도 파일)
