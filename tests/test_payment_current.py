"""
STEP 0 — payment 라우터·스키마 현재 동작 스냅샷 (분리 전 기준선).

규칙: docs/DEV_RULES_SERVICE_LAYER.md STEP 0
"""
from __future__ import annotations

import os

# main 로드 시 다른 라우터가 요구하는 최소 환경 변수
os.environ.setdefault("INTERNAL_API_SECRET", "pytest-internal-secret")

import hashlib
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from main import app
from routers import payment as pay
from schemas.payment import PrepareBody


def test_sha256_matches_known_vector():
    assert pay._sha256("abc") == hashlib.sha256(b"abc").hexdigest()


def test_calc_expired_at_adds_months_utc():
    base = "2026-01-15T12:00:00+00:00"
    out = pay._calc_expired_at(base, 1)
    dt = datetime.fromisoformat(out.replace("Z", "+00:00"))
    assert dt.month == 2
    assert dt.day == 15


def test_make_order_id_shape():
    oid = pay._make_order_id()
    assert oid.startswith("TAI")
    assert len(oid) >= 20


def test_prepare_body_valid_minimal():
    b = PrepareBody(
        user_id="u1",
        product_type="DIAGNOSIS",
        amount=10000,
        goodname="테스트",
    )
    assert b.user_id == "u1"
    assert b.amount == 10000


def test_prepare_body_rejects_blank_user_id():
    with pytest.raises(ValidationError):
        PrepareBody(
            user_id="   ",
            product_type="DIAGNOSIS",
            amount=1,
            goodname="x",
        )


def test_prepare_body_rejects_invalid_product_type():
    with pytest.raises(ValidationError):
        PrepareBody(
            user_id="u1",
            product_type="INVALID_TYPE",
            amount=1,
            goodname="x",
        )


def test_saas_product_types_snapshot():
    assert "SAAS_BUILDING" in pay.SAAS_PRODUCT_TYPES
    assert "SAAS_FACILITY" in pay.SAAS_PRODUCT_TYPES


def test_pricing_page_returns_html_200():
    client = TestClient(app)
    r = client.get("/payments/pricing")
    assert r.status_code == 200
    assert "TAI Safe 요금제" in r.text


def test_result_page_returns_html_200():
    client = TestClient(app)
    r = client.get("/payments/result")
    assert r.status_code == 200
    assert "결제 결과" in r.text


def test_billing_terms_page_returns_html_200():
    client = TestClient(app)
    r = client.get("/payments/billing/terms")
    assert r.status_code == 200
