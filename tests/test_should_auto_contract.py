"""CORRECTION E — 계약 자동생성 판정(_should_auto_contract) 단위 회귀.

정책(positive allowlist): 신규 SaaS 계약 자동생성은 product_type in SAAS_PRODUCT_TYPES 일 때만.
진단(DIAGNOSIS) 등 1회성 상품은 plan_code 가 있어도 계약을 만들지 않는다.
PRICE / PG / SIGNATURE 로직과 무관 — 순수 판정 함수만 검증.
"""
from services.payment_post_process import _should_auto_contract
from services.payment_helpers import SAAS_PRODUCT_TYPES


def _pay(**kw):
    base = {"company_id": "C1"}
    base.update(kw)
    return base


# P1 — DIAGNOSIS + plan_code + company_id → 계약 생성 안 함
def test_P1_diagnosis_with_plan_code_no_contract():
    assert _should_auto_contract(_pay(product_type="DIAGNOSIS", plan_code="INDUSTRY_STARTER")) is False


# P2~P4 — SaaS 상품은 계약 생성
def test_P2_saas_industry_true():
    assert _should_auto_contract(_pay(product_type="SAAS_INDUSTRY", plan_code="INDUSTRY_STARTER")) is True


def test_P3_saas_building_true():
    assert _should_auto_contract(_pay(product_type="SAAS_BUILDING", plan_code="BUILDING_LITE")) is True


def test_P4_saas_construction_true():
    assert _should_auto_contract(_pay(product_type="SAAS_CONSTRUCTION", plan_code="CONSTRUCTION_STANDARD")) is True


# allowlist 자체가 SAAS_PRODUCT_TYPES 와 일치하는지(하드코딩 드리프트 방지)
def test_allowlist_matches_saas_product_types():
    for pt in SAAS_PRODUCT_TYPES:
        assert _should_auto_contract(_pay(product_type=pt)) is True


# plan_code 단독 fallback 제거 확인 — product_type 이 SaaS 가 아니면 plan_code 있어도 False
def test_plan_code_alone_no_longer_triggers_contract():
    assert _should_auto_contract(_pay(product_type="", plan_code="INDUSTRY_STARTER")) is False
    assert _should_auto_contract(_pay(product_type=None, plan_code="ANY")) is False
    # INAPP/REPAIR 등 다른 1회성 상품도 plan_code 만으로는 계약 생성 안 함
    assert _should_auto_contract(_pay(product_type="INAPP", plan_code="X")) is False


# company_id 없으면 계약 생성 안 함(기존 가드 보존)
def test_no_company_no_contract():
    assert _should_auto_contract({"product_type": "SAAS_INDUSTRY", "plan_code": "X"}) is False


# 이미 contract_id 연결된 결제는 자동생성 대상 아님(activate/renewal 경로로 감)
def test_existing_contract_id_not_auto_created():
    assert _should_auto_contract(_pay(product_type="SAAS_INDUSTRY", contract_id="CT1")) is False


# P5(논리) — DIAGNOSIS 는 어떤 조합에서도 신규 계약 자동생성 대상이 아님
def test_P5_diagnosis_never_auto_contract():
    assert _should_auto_contract(_pay(product_type="DIAGNOSIS")) is False
    assert _should_auto_contract(_pay(product_type="DIAGNOSIS", plan_code="INDUSTRY_STARTER")) is False
    assert _should_auto_contract(_pay(product_type="DIAGNOSIS", plan_code=None)) is False


# P6(논리) — 기존 contract_id 있으면(renewal/activate 대상) 자동생성 판정은 False
def test_P6_existing_contract_preserved_path():
    assert _should_auto_contract(_pay(product_type="SAAS_BUILDING", plan_code="BUILDING_LITE", contract_id="CT9")) is False
