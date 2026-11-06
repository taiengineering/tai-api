"""WO-TAI-QA-COVERAGE-WWW-WP12-001 — P1-API-DIAG-API-003 유료진단 결과 조회 API HTTP 계층 갭 보완.

기존 자산 재사용:
  test_paid_result_delivery_wiring_v1.py (T01~T19 + K1~K5 + source_index = 25건)
      — product 호출 게이팅·source-text 부착·공개 프로젝션 (내부 함수 직접 호출)
  test_paid_result_public_projection_v1.py (B1~B23 + projection = 25건)
      — premium_result_v1 공개 프로젝션 안전성 (서비스 함수 직접)
  test_free_result_additional_information_route.py (BE-T12/T13 = 2건)
      — 무료·유료 additional_information 분기

신규 갭 테스트 (HTTP 계층 미검증 항목만):
  GAP-01  PAID_RESULT_HTTP_200    — GET /diagnosis/paid-result/{token}, ACTIVE LEG 유료 → HTTP 200
  GAP-02  RESPONSE_CONTRACT       — status·public_token 일치·is_free=false·premium_result_v1 존재
  GAP-03  UNKNOWN_TOKEN_404       — 존재하지 않는 토큰 → HTTP 404
  GAP-04  INACTIVE_RESULT_410     — status!=ACTIVE → HTTP 410
  GAP-05  SAAS_RESULT_404         — source_type=saas → HTTP 404
  GAP-06  PRODUCT_FAILURE_503     — build_paid_result_product_v1 실패 → HTTP 503
  GAP-07  FREE_TIER_NO_PREMIUM    — 무료 티어 유료 경로 → HTTP 200, is_free=true, premium_result_v1 없음

운영 안전:
  PRODUCTION_API_HITS=0 / REAL_DB_READS=0 / REAL_DB_WRITES=0
"""
from __future__ import annotations

import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("INTERNAL_API_SECRET", "pytest-internal-secret")

import routers.diagnosis_result_web as rw
from tests.test_paid_result_delivery_wiring_v1 import (
    FakeQuery,
    FakeSupabase,
    install,
    leg_obligation,
    source_item,
    stored_rec,
)


# ── 토큰 조회 계약 검증용 확장 ────────────────────────────────────────────────────

class _TokenCapturingQuery(FakeQuery):
    def eq(self, field, value, **k):
        if field == "public_token":
            self._store["queried_token"] = value
        return self


class _TokenCapturingSupabase(FakeSupabase):
    def table(self, *a, **k):
        return _TokenCapturingQuery(self.store)


# ── pytest 픽스처 ────────────────────────────────────────────────────────────────

@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(rw.router)
    return TestClient(app, raise_server_exceptions=False)


# ── GAP-01+02: HTTP_200 + RESPONSE_CONTRACT ───────────────────────────────────

def test_paid_result_http_200_contract_and_token(monkeypatch, client):
    """GET /diagnosis/paid-result/{token} — ACTIVE LEG 유료 → HTTP 200, 응답 계약, 토큰 일치."""
    rec = stored_rec([leg_obligation("a0", "안전보건관리책임자 선임")], tier="BUILDING_V2")
    fake_sb = _TokenCapturingSupabase(rec)
    monkeypatch.setattr(rw, "get_supabase", lambda: fake_sb)

    calls = {"n": 0}

    def spy_product(row):
        calls["n"] += 1
        from tests.test_paid_result_delivery_wiring_v1 import fake_product
        return fake_product([source_item(0, "a0", "제38조 원문")])

    monkeypatch.setattr(rw, "build_paid_result_product_v1", spy_product)

    resp = client.get("/diagnosis/paid-result/tok-1")
    assert resp.status_code == 200

    body = resp.json()
    assert body["status"] == "success"
    data = body["data"]

    # 토큰 조회 계약 — 요청 경로 토큰이 DB 조회 조건으로 전달됨
    assert fake_sb.store.get("queried_token") == "tok-1", "토큰 조회 조건 불일치"

    # 응답 계약
    assert data["public_token"] == "tok-1",    "public_token 불일치"
    assert data["is_free"] is False,           "is_free 불일치 (유료 티어)"
    assert "premium_result_v1" in data,        "premium_result_v1 누락"
    assert isinstance(data["premium_result_v1"], dict), "premium_result_v1 타입 오류"
    assert calls["n"] == 1,                    "product assembler 1회 호출 기대"


# ── GAP-03: UNKNOWN_TOKEN_404 ─────────────────────────────────────────────────

def test_paid_result_unknown_token_404(monkeypatch, client):
    """존재하지 않는 public_token → HTTP 404."""
    monkeypatch.setattr(rw, "get_supabase", lambda: FakeSupabase(None))
    resp = client.get("/diagnosis/paid-result/tok-wp12-nonexistent")
    assert resp.status_code == 404


# ── GAP-04: INACTIVE_RESULT_410 ───────────────────────────────────────────────

def test_paid_result_inactive_410(monkeypatch, client):
    """status != ACTIVE 인 결과 → HTTP 410."""
    rec = stored_rec([leg_obligation("a0", "점검")], tier="BUILDING_V2", status="EXPIRED")
    install(monkeypatch, rec, product_items=[])
    resp = client.get("/diagnosis/paid-result/tok-1")
    assert resp.status_code == 410


# ── GAP-05: SAAS_RESULT_404 ───────────────────────────────────────────────────

def test_paid_result_saas_source_type_404(monkeypatch, client):
    """source_type=saas 인 결과 → HTTP 404 (내부 결과 비노출)."""
    rec = stored_rec([leg_obligation("a0", "점검")], tier="BUILDING_V2")
    rec["source_type"] = "saas"
    monkeypatch.setattr(rw, "get_supabase", lambda: FakeSupabase(rec))
    resp = client.get("/diagnosis/paid-result/tok-1")
    assert resp.status_code == 404


# ── GAP-06: PRODUCT_FAILURE_503 ───────────────────────────────────────────────

def test_paid_result_product_failure_503(monkeypatch, client):
    """build_paid_result_product_v1 예외 → HTTP 503 (내부 오류 메시지 미노출)."""
    rec = stored_rec([leg_obligation("a0", "점검")], tier="BUILDING_V2")
    install(monkeypatch, rec, product_exc=RuntimeError("leg runtime down"))
    resp = client.get("/diagnosis/paid-result/tok-1")
    assert resp.status_code == 503
    # 내부 오류 메시지 미노출
    assert "leg runtime down" not in resp.text


# ── GAP-07: FREE_TIER_NO_PREMIUM ─────────────────────────────────────────────

def test_paid_result_free_tier_200_no_premium(monkeypatch, client):
    """무료 티어를 유료 경로로 조회 → HTTP 200, is_free=true, premium_result_v1 없음."""
    rec = stored_rec([leg_obligation("a0", "점검")], tier="BUILDING_FREE")
    install(monkeypatch, rec, product_items=[source_item(0, "a0", "원문A")])
    resp = client.get("/diagnosis/paid-result/tok-1")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["is_free"] is True,                    "is_free 불일치 (무료 티어)"
    assert "premium_result_v1" not in data,            "무료 티어 premium_result_v1 미포함 기대"
