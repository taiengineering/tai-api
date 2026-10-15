"""Pytest autouse: launch secret for HTTP prepare 회귀 (PROD env 설정 아님).

--run-db-int 옵션: 격리 PostgreSQL 통합검증 실행 (Docker 필요).
환경변수 C10_TEST_DB_URL 설정 시 해당 DB 사용, 미설정 시 SKIP.
"""
from __future__ import annotations

import os

import pytest

_TEST_LAUNCH_SECRET = "test-payment-launch-secret-value-32b"


def pytest_addoption(parser):
    parser.addoption(
        "--run-db-int",
        action="store_true",
        default=False,
        help="격리 PostgreSQL 통합검증 실행 (C10_TEST_DB_URL 환경변수 필요)",
    )


@pytest.fixture(autouse=True, scope="session")
def _b7_payment_launch_secret():
    os.environ.setdefault("PAYMENT_LAUNCH_SECRET", _TEST_LAUNCH_SECRET)
    os.environ.setdefault(
        "PAYMENT_LAUNCH_URL",
        "https://taieng.co.kr/_api/payments/tier-upgrade/pay",
    )
    yield
