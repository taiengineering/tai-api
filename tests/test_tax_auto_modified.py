"""WO-TAX-INVOICE-AUTO-01 STEP 4 — auto MODIFIED = CASE A (CODE DELTA 0).

refund_svc.run_refund/run_partial_refund 는 이미 DONE 후 _tax_adjustment_hook →
invoice_svc.process_refund_tax_adjustment(fail-soft) 를 호출한다. 따라서 신규 배선 없이
mock provider 로 회귀 검증만 수행한다.

케이스:
  M1  전액 monetary refund DONE (refund_amount == total, cumulative == total)
      → modify_code=4 MODIFIED 발행 (음수 supply/vat/total)
  M2  부분 refund DONE (refund_amount < total)
      → modify_code=2 MODIFIED 발행 (비례 supply/vat 배분)
  M3  state-only cancel (refund_svc 미호출) → hook 미발화 → MODIFIED 0
      (계약: refund_svc 만이 유일한 hook 호출자 — 소스 grep 회귀)
  M4  subscription stop (환불 없이 계약 취소) → 동일하게 hook 미발화 → MODIFIED 0
      (M3 와 같은 회귀: refund 을 만들지 않는 시나리오)
  M5  중복 refund hook (같은 refund_id 로 재호출) → MODIFIED 1 (parent_invoice_id + refund_ref
      UNIQUE 로 idempotent)
  M6  provider 실패 (correction fail) → refund DONE 유지, MODIFIED FAILED (재시도 여지)
      + hook 자체는 예외 삼킴 (fail-soft — refund/payment rollback 0)
  M7  ORIGINAL 미발행(원본 없음) → MODIFIED 발행 0, 미발행 request CANCELLED (또는 NOOP)
"""
from __future__ import annotations

import uuid

import pytest

import services.invoice_svc as inv


# ── FakeSupabase (test_tax_auto_svc 와 동일 계약; UNIQUE 별도 시뮬) ──
class _Result:
    def __init__(self, data):
        self.data = data
        self.count = len(data) if data is not None else 0


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


class MockMod:
    """수정세금계산서 popbill mock — issue 호출수/인자 기록."""
    def __init__(self, fail=False):
        self.calls = []; self.fail = fail

    def issue(self, conf, **kw):
        self.calls.append(kw)
        if self.fail:
            raise Exception("popbill correction down")
        return {"nts": "MOD-NTS", "code": 1, "message": "ok"}


def _payment(**kw):
    base = {
        "id": "pay-1",
        "status_code": "CANCELLED",
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


def _original_issued(**kw):
    base = {
        "id": "inv-orig",
        "payment_id": "pay-1",
        "company_id": "co-1",
        "doc_type": "TAX_INVOICE",
        "invoice_kind": "ORIGINAL",
        "status": "ISSUED",
        "nts_confirm_num": "NTS-ORIG",
        "supply_cost": 100000, "tax": 10000, "total_amount": 110000,
        "mgt_key": "TX-orig",
    }
    base.update(kw)
    return base


def _issued_request_snapshot(**kw):
    """MODIFIED invoicee resolution 이 tax_invoice_requests snapshot 을 우선 사용."""
    base = {
        "id": "req-orig",
        "payment_id": "pay-1",
        "company_id": "co-1",
        "doc_type": "TAX_INVOICE",
        "status": "ISSUED",
        "invoicee_business_number": "1234567890",
        "invoicee_company_name": "테스트 주식회사",
        "invoicee_representative_name": "홍길동",
        "invoicee_email": "biz@test.co",
        "invoicee_address": "서울시 강남구",
        "invoicee_business_type": "정보통신",
        "invoicee_business_category": "SaaS",
    }
    base.update(kw)
    return base


def _refund_done(refund_type="FULL", amount=110000, cumulative=110000, refund_id="ref-1"):
    return {
        "id": refund_id,
        "payment_id": "pay-1",
        "refund_type": refund_type,
        "amount": amount,
        "cumulative_refunded": cumulative,
        "status": "DONE",
        "reason_text": "고객 요청 취소",
        "created_at": "2026-09-06T00:00:00+09:00",
    }


def _setup_mod(monkeypatch, *, live=True, provider_fail=False, with_original=True):
    """monkeypatch invoice_svc + supabase + mock provider."""
    store = {
        "payments": [_payment()],
        "companies": [{
            "id": "co-1", "name": "테스트 주식회사", "business_number": "1234567890",
            "representative_name": "홍길동", "contact_email": "biz@test.co",
            "address": "서울시 강남구",
            "business_type": "정보통신", "business_category": "SaaS",
        }],
        "tax_invoice_requests": [_issued_request_snapshot()],
        "tax_invoices": [_original_issued()] if with_original else [],
        "refunds": [],
    }
    fake = FakeSupabase(store)
    mock = MockMod(fail=provider_fail)
    monkeypatch.setattr(inv, "get_supabase", lambda: fake)
    monkeypatch.setattr(inv, "invoice_live", lambda: live)
    monkeypatch.setattr(inv, "_popbill_conf", lambda: {
        "corp_num": "7233901422", "corp_name": "TAI", "ceo_name": "심태왕",
        "corp_addr": "서울", "biz_type": "정보통신업", "biz_class": "응용SW",
        "user_id": "", "link_id": "x", "secret_key": "y", "is_test": True,
    })
    monkeypatch.setattr(inv, "_popbill_issue_modified_tax", lambda conf, **kw: mock.issue(conf, **kw))
    monkeypatch.setattr(inv, "audit_svc",
                        type("A", (), {"record": staticmethod(lambda *a, **k: None)}))
    return store, fake, mock


# ═════════════════════════════════════════════════════════════════════
# M1  전액 monetary refund DONE → code4 MODIFIED
# ═════════════════════════════════════════════════════════════════════
def test_M1_full_refund_code4(monkeypatch):
    store, fake, mock = _setup_mod(monkeypatch)
    store["refunds"].append(_refund_done("FULL", 110000, 110000))
    res = inv.process_refund_tax_adjustment("ref-1")
    assert res["outcome"] == "ISSUED"
    assert res["modify_code"] == 4
    assert len(mock.calls) == 1
    # 음수 (전액 취소) → -110000
    modifieds = [i for i in store["tax_invoices"] if i.get("invoice_kind") == "MODIFIED"]
    assert len(modifieds) == 1
    assert modifieds[0]["total_amount"] == -110000
    assert modifieds[0]["supply_cost"] == -100000
    assert modifieds[0]["tax"] == -10000


# ═════════════════════════════════════════════════════════════════════
# M2  부분 refund DONE → code2 MODIFIED (비례 배분)
# ═════════════════════════════════════════════════════════════════════
def test_M2_partial_refund_code2(monkeypatch):
    store, fake, mock = _setup_mod(monkeypatch)
    # 22,000원 (20% 부분) — 원본 100k+10k=110k 의 20%
    store["refunds"].append(_refund_done("PARTIAL", 22000, 22000))
    res = inv.process_refund_tax_adjustment("ref-1")
    assert res["outcome"] == "ISSUED"
    assert res["modify_code"] == 2
    modifieds = [i for i in store["tax_invoices"] if i.get("invoice_kind") == "MODIFIED"]
    assert len(modifieds) == 1
    # 22,000 = 20,000 supply + 2,000 vat (invoice_svc 계약: round(refund*supply/total))
    #   round(22000 * 100000 / 110000) = round(20000) = 20000
    assert modifieds[0]["total_amount"] == -22000
    assert modifieds[0]["supply_cost"] == -20000
    assert modifieds[0]["tax"] == -2000


# ═════════════════════════════════════════════════════════════════════
# M3 / M4  state-only cancel / subscription stop
#          hook 은 refund_svc.run_refund/run_partial_refund 성공 경로에서만 발화.
#          다른 취소 경로에서 hook 발화하면 안 됨 → 소스 grep 회귀.
# ═════════════════════════════════════════════════════════════════════
def test_M3_M4_hook_only_from_refund_svc():
    """refund_svc 외부에서 _tax_adjustment_hook 을 호출하지 않는다 (소스 grep 회귀)."""
    import inspect
    from services import refund_svc

    # refund_svc 안: run_refund + run_partial_refund 성공 분기 2회 호출
    src = inspect.getsource(refund_svc)
    assert src.count("_tax_adjustment_hook(") >= 3, (
        "hook 호출부 확인: 정의 1 + run_refund 성공분기 1 + run_partial_refund 성공분기 1 = 최소 3"
    )

    # 다른 서비스/라우터에서 hook 호출 금지 (state-only cancel / subscription stop 경로에서
    # 실수로 MODIFIED 발행되지 않도록)
    import pathlib
    root = pathlib.Path(inv.__file__).parent.parent
    hits = []
    for p in list((root / "services").glob("*.py")) + list((root / "routers").glob("*.py")):
        if p.name == "refund_svc.py":
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            continue
        if "_tax_adjustment_hook" in text:
            hits.append(p.name)
    assert hits == [], f"refund_svc 외부에서 _tax_adjustment_hook 호출 금지 (M3/M4 계약): {hits}"


# ═════════════════════════════════════════════════════════════════════
# M5  중복 refund hook → MODIFIED 1 (parent_invoice_id + refund_ref UNIQUE)
# ═════════════════════════════════════════════════════════════════════
def test_M5_duplicate_hook_modified_once(monkeypatch):
    store, fake, mock = _setup_mod(monkeypatch)
    store["refunds"].append(_refund_done("FULL", 110000, 110000))

    res1 = inv.process_refund_tax_adjustment("ref-1")
    assert res1["outcome"] == "ISSUED"
    assert len(mock.calls) == 1

    # 재호출 (재실행 시나리오) — 같은 refund_id → 기존 modified 재사용, ISSUED 그대로
    res2 = inv.process_refund_tax_adjustment("ref-1")
    assert res2["outcome"] == "ISSUED"
    # provider 재호출 금지 (idempotent)
    assert len(mock.calls) == 1, "이미 ISSUED 인 modified 는 provider 재호출 금지"
    modifieds = [i for i in store["tax_invoices"] if i.get("invoice_kind") == "MODIFIED"]
    assert len(modifieds) == 1


# ═════════════════════════════════════════════════════════════════════
# M6  provider 실패 → refund DONE 유지 / MODIFIED FAILED / hook 예외 삼킴 (fail-soft)
# ═════════════════════════════════════════════════════════════════════
def test_M6_correction_fail_refund_intact(monkeypatch):
    from services import refund_svc

    store, fake, mock = _setup_mod(monkeypatch, provider_fail=True)
    store["refunds"].append(_refund_done("FULL", 110000, 110000))

    # 직접 호출 시 InvoiceError 발생 → refund 상태는 조회만 (DONE 유지)
    with pytest.raises(inv.InvoiceError):
        inv.process_refund_tax_adjustment("ref-1")
    assert store["refunds"][0]["status"] == "DONE", "correction 실패가 refund 상태를 rollback 하면 안 됨"

    # MODIFIED row 는 FAILED 로 mark
    modifieds = [i for i in store["tax_invoices"] if i.get("invoice_kind") == "MODIFIED"]
    assert len(modifieds) == 1
    assert modifieds[0]["status"] == "FAILED"

    # refund_svc._tax_adjustment_hook 은 예외를 삼켜야 함 (fail-soft)
    # (hook 은 process_refund_tax_adjustment 호출을 try/except 로 감싼다)
    # hook 을 직접 호출해 예외가 밖으로 새지 않는지 확인
    try:
        refund_svc._tax_adjustment_hook("ref-1", actor_id=None)
    except Exception as e:  # noqa: BLE001
        pytest.fail(f"_tax_adjustment_hook 은 fail-soft 여야 하는데 예외 전파: {e}")


# ═════════════════════════════════════════════════════════════════════
# M7  ORIGINAL 미발행 → MODIFIED 0 (미발행 request CANCELLED / NOOP)
# ═════════════════════════════════════════════════════════════════════
def test_M7_no_original_no_modified(monkeypatch):
    store, fake, mock = _setup_mod(monkeypatch, with_original=False)
    # 원본 request 는 아직 REQUESTED 상태로 남아있음
    store["tax_invoice_requests"] = [{
        "id": "req-pending", "payment_id": "pay-1", "doc_type": "TAX_INVOICE",
        "status": "REQUESTED",
    }]
    store["refunds"].append(_refund_done("FULL", 110000, 110000))

    res = inv.process_refund_tax_adjustment("ref-1")
    # 원본 없으니 REQUEST_CANCELLED (미발행 request 1개 취소) 또는 NOOP
    assert res["outcome"] in ("REQUEST_CANCELLED", "NOOP"), res
    assert res.get("modified_invoice_id") is None
    # provider 는 호출되지 않음
    assert mock.calls == []
    # MODIFIED invoice 는 생성되지 않음
    modifieds = [i for i in store["tax_invoices"] if i.get("invoice_kind") == "MODIFIED"]
    assert modifieds == []


# ═════════════════════════════════════════════════════════════════════
# 회귀 — STEP 4 계약: refund_svc 안에 새 발행 엔진 도입 금지
# ═════════════════════════════════════════════════════════════════════
def test_STEP4_no_new_engine_in_refund_svc():
    """refund_svc 는 여전히 _tax_adjustment_hook → invoice_svc.process_refund_tax_adjustment
    만 사용. 새 popbill 직접호출 / 새 세액계산 / 새 lock 도입 금지."""
    import ast
    import inspect
    from services import refund_svc

    src = inspect.getsource(refund_svc)
    tree = ast.parse(src)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for a in node.names:
                imports.add(f"{mod}.{a.name}" if mod else a.name)
        elif isinstance(node, ast.Import):
            for a in node.names:
                imports.add(a.name)
    banned = {n for n in imports if "popbill" in n.lower()}
    assert banned == set(), f"refund_svc 는 popbill 직접 import 금지: {banned}"
    # process_refund_tax_adjustment 는 hook 내부에서 지연 import (계약 유지)
    assert "process_refund_tax_adjustment" in src
