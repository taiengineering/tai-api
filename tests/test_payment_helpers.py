"""payment_helpers 단위 테스트 (STEP 5)."""

from services.payment_helpers import (
    load_template,
    service_status_after_card_pay,
    sha256,
    split_supply_vat,
)


def test_split_supply_vat_snapshot():
    s, v = split_supply_vat(11000)
    assert s + v == 11000
    assert s == round(11000 / 1.1)


def test_service_status_after_card_pay():
    assert service_status_after_card_pay("c1") == "ACTIVE"
    assert service_status_after_card_pay(None) == "PAID"
    assert service_status_after_card_pay("") == "PAID"


def test_sha256_stable():
    assert len(sha256("x")) == 64


def test_load_template_pricing_snapshot():
    load_template.cache_clear()
    html = load_template("pricing.html")
    assert "TAI Safe 요금제" in html
    assert "<!doctype html>" in html
