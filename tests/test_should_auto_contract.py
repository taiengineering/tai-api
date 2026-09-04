"""CORRECTION E/§6 — 계약 자동생성 판정 + on_payment_success_sync integration 회귀.

정책(positive allowlist): 신규 SaaS 계약 자동생성은 product_type in SAAS_PRODUCT_TYPES 일 때만.
진단(DIAGNOSIS) 등 1회성 상품은 plan_code 가 있어도 계약을 만들지 않는다.
PRICE / PG / SIGNATURE 로직과 무관 — 판정 함수 + 후처리 동기 함수만 검증.

P1-P6 pure + allowlist 드리프트 방지 + P5/P6 실제 on_payment_success_sync(fake supabase).
"""
import services.payment_post_process as ppp
from services.payment_post_process import _should_auto_contract, on_payment_success_sync
from services.payment_helpers import SAAS_PRODUCT_TYPES


def _pay(**kw):
    base = {"company_id": "C1"}
    base.update(kw)
    return base


# ── 판정 함수 (pure) ──
def test_P1_diagnosis_with_plan_code_no_contract():
    assert _should_auto_contract(_pay(product_type="DIAGNOSIS", plan_code="INDUSTRY_STARTER")) is False


def test_P2_saas_industry_true():
    assert _should_auto_contract(_pay(product_type="SAAS_INDUSTRY", plan_code="INDUSTRY_STARTER")) is True


def test_P3_saas_building_true():
    assert _should_auto_contract(_pay(product_type="SAAS_BUILDING", plan_code="BUILDING_LITE")) is True


def test_P4_saas_construction_true():
    assert _should_auto_contract(_pay(product_type="SAAS_CONSTRUCTION", plan_code="CONSTRUCTION_STANDARD")) is True


def test_allowlist_matches_saas_product_types():
    for pt in SAAS_PRODUCT_TYPES:
        assert _should_auto_contract(_pay(product_type=pt)) is True


def test_plan_code_alone_no_longer_triggers_contract():
    assert _should_auto_contract(_pay(product_type="", plan_code="INDUSTRY_STARTER")) is False
    assert _should_auto_contract(_pay(product_type=None, plan_code="ANY")) is False
    assert _should_auto_contract(_pay(product_type="INAPP", plan_code="X")) is False


def test_no_company_no_contract():
    assert _should_auto_contract({"product_type": "SAAS_INDUSTRY", "plan_code": "X"}) is False


def test_existing_contract_id_not_auto_created():
    assert _should_auto_contract(_pay(product_type="SAAS_INDUSTRY", contract_id="CT1")) is False


def test_P5_diagnosis_never_auto_contract():
    assert _should_auto_contract(_pay(product_type="DIAGNOSIS")) is False
    assert _should_auto_contract(_pay(product_type="DIAGNOSIS", plan_code="INDUSTRY_STARTER")) is False


def test_P6_existing_contract_preserved_path():
    assert _should_auto_contract(_pay(product_type="SAAS_BUILDING", plan_code="BUILDING_LITE", contract_id="CT9")) is False


# ── fake supabase (호출 기록 스파이) ──
class _Query:
    def __init__(self, table_name, rec):
        self.t = table_name
        self.rec = rec
        self._filters = {}

    def select(self, *a, **k):
        return self

    def eq(self, col, val):
        self._filters[col] = val
        return self

    def neq(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def order(self, *a, **k):
        return self

    def insert(self, payload):
        self.rec["insert"].setdefault(self.t, []).append(payload)
        self._ins = payload
        return self

    def update(self, payload):
        self.rec["update"].setdefault(self.t, []).append(payload)
        return self

    def execute(self):
        # payments select → 시나리오가 넣어둔 pay row 반환
        if self.t == "payments" and not getattr(self, "_ins", None) and "update" not in str(self._filters):
            return type("R", (), {"data": [self.rec["pay"]]})()
        # contracts insert → 생성 id 반환
        if self.t == "contracts" and getattr(self, "_ins", None):
            return type("R", (), {"data": [{"id": "NEW_CT"}]})()
        # contracts select(end_date...) for renewal
        if self.t == "contracts" and not getattr(self, "_ins", None):
            return type("R", (), {"data": [self.rec.get("contract_row", {"end_date": "2027-01-01"})]})()
        return type("R", (), {"data": []})()


class _FakeSB:
    def __init__(self, rec):
        self.rec = rec

    def table(self, name):
        return _Query(name, self.rec)


def _install_fake(monkeypatch, pay, contract_row=None):
    rec = {"insert": {}, "update": {}, "pay": pay, "contract_row": contract_row or {"end_date": "2027-01-01"}}
    fake = _FakeSB(rec)
    monkeypatch.setattr(ppp, "get_supabase", lambda: fake)
    # 알림·automation 은 부수효과라 무력화(계약 검증에 집중)
    monkeypatch.setattr(ppp, "send_payment_notification", lambda *a, **k: rec.setdefault("notify", 0) or rec.update(notify=rec.get("notify", 0) + 1))
    monkeypatch.setattr(ppp, "_fire_automation", lambda *a, **k: None)
    return rec


# ── P5: DIAGNOSIS 결제 후처리 → 계약 INSERT 0, 알림 유지 ──
def test_P5_diagnosis_post_process_no_contract_insert(monkeypatch):
    pay = {"id": "P1", "status_code": "SUCCESS", "product_type": "DIAGNOSIS",
           "company_id": "C1", "plan_code": "INDUSTRY_STARTER", "contract_id": None,
           "total_amount": 163900, "supply_amount": 149000, "vat_amount": 14900}
    rec = _install_fake(monkeypatch, pay)
    on_payment_success_sync("P1")
    assert "contracts" not in rec["insert"]          # 계약 생성 0
    assert rec.get("notify", 0) == 1                  # 알림 1회
    # payment 에 contract_id update 도 없어야(계약 생성 안 했으므로)
    assert all("contract_id" not in u for u in rec["update"].get("payments", []))


# ── P6-A: 기존 contract_id + 일반 activation → 신규 INSERT 0 ──
def test_P6A_existing_contract_activate(monkeypatch):
    pay = {"id": "P2", "status_code": "SUCCESS", "product_type": "SAAS_INDUSTRY",
           "company_id": "C1", "plan_code": "INDUSTRY_STARTER_V2", "contract_id": "CT_EXIST",
           "payment_type": "CARD", "total_amount": 100, "paid_at": "2026-09-04T00:00:00+09:00",
           "period_months": 12}
    rec = _install_fake(monkeypatch, pay)
    on_payment_success_sync("P2")
    assert "contracts" not in rec["insert"]           # 신규 계약 생성 0
    # 기존 계약 activate(update) 발생
    assert any(u.get("status_code") == "ACTIVE" for u in rec["update"].get("contracts", []))
    assert rec.get("notify", 0) == 1


# ── P6-B: 기존 contract_id + RENEWAL → 신규 INSERT 0, 연장 update ──
def test_P6B_existing_contract_renewal(monkeypatch):
    pay = {"id": "P3", "status_code": "SUCCESS", "product_type": "SAAS_INDUSTRY",
           "company_id": "C1", "plan_code": "INDUSTRY_STARTER_V2", "contract_id": "CT_EXIST",
           "payment_type": "RENEWAL", "total_amount": 100, "paid_at": "2026-09-04T00:00:00+09:00",
           "period_months": 12}
    rec = _install_fake(monkeypatch, pay, contract_row={"end_date": "2027-01-01", "start_date": "2026-01-01", "status_code": "ACTIVE"})
    on_payment_success_sync("P3")
    assert "contracts" not in rec["insert"]           # 신규 계약 생성 0
    assert any("end_date" in u for u in rec["update"].get("contracts", []))  # 연장 update
    assert rec.get("notify", 0) == 1


# ── SAAS 신규(계약 없음) → 계약 INSERT 1 (positive path 회귀) ──
def test_saas_new_creates_contract(monkeypatch):
    pay = {"id": "P4", "status_code": "SUCCESS", "product_type": "SAAS_BUILDING",
           "company_id": "C1", "plan_code": "BUILDING_LITE", "contract_id": None,
           "total_amount": 100, "supply_amount": 90, "vat_amount": 10, "period_months": 12}
    rec = _install_fake(monkeypatch, pay)
    on_payment_success_sync("P4")
    assert len(rec["insert"].get("contracts", [])) == 1   # 신규 계약 1
    assert rec["insert"]["contracts"][0]["service_type"] == "SAAS"
