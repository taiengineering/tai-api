"""WO-TAI-QA-COVERAGE-WWW-WP11-001 — P1-API-DIAG-API-001 무료진단 결과 조회 API HTTP 계층 갭 보완.

기존 자산 재사용:
  test_free_result_additional_information_route.py (BE-T12/T13)
      — 무료·유료 additional_information 분기 (_build_result_payload 직접 호출)
  test_diagnosis_result_input_projection.py (API-T2~T12)
      — 입력 스냅샷 projection (서비스 함수 직접)
  test_free_result_review_required_projection.py (R-01~R-10)
      — review_required 길이 집계 (헬퍼 직접)

신규 갭 테스트 (HTTP 계층 미검증 항목만):
  GAP-01  HTTP_ROUTE_200          — GET /diagnosis/result/{token}, ACTIVE FREE → HTTP 200
  GAP-02  RESPONSE_CONTRACT       — status·public_token·is_free·free_obligations·free_obligation_count
  GAP-03  UNKNOWN_TOKEN_404       — 존재하지 않는 토큰 → HTTP 404
  GAP-04  INACTIVE_RESULT_410     — status!=ACTIVE → HTTP 410
  GAP-05  SAAS_RESULT_404         — source_type=saas → HTTP 404 (내부 결과 비노출)

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


# ── 공통 FakeSupabase ──────────────────────────────────────────────────────────

class _FakeTableQuery:
    def __init__(self, rows):
        self._rows = rows

    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def in_(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def order(self, *a, **k): return self

    def execute(self):
        rows = self._rows
        class R:
            data = rows
        return R()


class _FakeSupabase:
    """anonymous_diagnosis_results → result_rows; 나머지 테이블 → 빈 목록."""
    def __init__(self, result_rows):
        self._result_rows = result_rows

    def table(self, name, *a, **k):
        if name == "anonymous_diagnosis_results":
            return _FakeTableQuery(self._result_rows)
        return _FakeTableQuery([])


def _make_free_active_rec():
    return {
        "id": "res-wp11-001",
        "public_token": "tok-wp11-free",
        "tier_code": "BUILDING_FREE",
        "status": "ACTIVE",
        "source_type": None,
        "expires_at": None,
        "created_at": "2026-11-06T00:00:00+00:00",
        "input_data": {"company_name": "WP11테스트", "sector": "BUILDING"},
        "full_result": {
            "sector": "BUILDING",
            "obligations_raw": [
                {
                    "law_name": "산업안전보건법",
                    "law_article": "제38조",
                    "obligation_detail": {"what": "안전보건관리책임자 선임"},
                    "enrichment": {
                        "obligation_type": "APPOINT",
                        "usable_for_evaluation": True,
                    },
                    "applicability": "APPLICABLE",
                    "atom_id": "atom-wp11-001",
                }
            ],
        },
    }


# ── pytest 픽스처 ────────────────────────────────────────────────────────────────

@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(rw.router)
    return TestClient(app, raise_server_exceptions=False)


# ── GAP-01: HTTP_ROUTE_200 ────────────────────────────────────────────────────

def test_diagnosis_result_http_route_is_200_for_active_free(monkeypatch, client):
    """GET /diagnosis/result/{token} — ACTIVE FREE 결과 → HTTP 200."""
    monkeypatch.setattr(rw, "get_supabase", lambda: _FakeSupabase([_make_free_active_rec()]))
    resp = client.get("/diagnosis/result/tok-wp11-free")
    assert resp.status_code == 200


# ── GAP-02: RESPONSE_CONTRACT ─────────────────────────────────────────────────

def test_diagnosis_result_response_contract_free(monkeypatch, client):
    """성공 응답에 status·public_token·is_free·free_obligations·free_obligation_count 가 포함된다."""
    monkeypatch.setattr(rw, "get_supabase", lambda: _FakeSupabase([_make_free_active_rec()]))
    resp = client.get("/diagnosis/result/tok-wp11-free")
    assert resp.status_code == 200
    body = resp.json()

    assert body["status"] == "success"
    data = body["data"]
    assert data["public_token"] == "tok-wp11-free", "public_token 불일치"
    assert data["is_free"] is True,                 "is_free 불일치"

    assert "free_obligations" in data,                             "free_obligations 누락"
    assert "free_obligation_count" in data,                        "free_obligation_count 누락"
    assert isinstance(data["free_obligations"], list),             "free_obligations 타입 오류"
    assert isinstance(data["free_obligation_count"], int),         "free_obligation_count 타입 오류"
    assert data["free_obligation_count"] == len(data["free_obligations"]), \
        "free_obligation_count != len(free_obligations)"
    assert data["free_obligation_count"] >= 1, "obligations_raw 1건 → 1 이상 기대"
    assert "summary" in data,                                      "summary 누락"


# ── GAP-03: UNKNOWN_TOKEN_404 ─────────────────────────────────────────────────

def test_diagnosis_result_unknown_token_is_404(monkeypatch, client):
    """존재하지 않는 public_token → HTTP 404."""
    monkeypatch.setattr(rw, "get_supabase", lambda: _FakeSupabase([]))
    resp = client.get("/diagnosis/result/tok-wp11-nonexistent")
    assert resp.status_code == 404


# ── GAP-04: INACTIVE_RESULT_410 ───────────────────────────────────────────────

def test_diagnosis_result_inactive_is_410(monkeypatch, client):
    """status != ACTIVE 인 결과 → HTTP 410."""
    rec = _make_free_active_rec()
    rec["status"] = "EXPIRED"
    monkeypatch.setattr(rw, "get_supabase", lambda: _FakeSupabase([rec]))
    resp = client.get("/diagnosis/result/tok-wp11-free")
    assert resp.status_code == 410


# ── GAP-05: SAAS_RESULT_404 ───────────────────────────────────────────────────

def test_diagnosis_result_saas_source_type_is_404(monkeypatch, client):
    """source_type=saas 인 결과 → HTTP 404 (내부 결과 비노출)."""
    rec = _make_free_active_rec()
    rec["source_type"] = "saas"
    monkeypatch.setattr(rw, "get_supabase", lambda: _FakeSupabase([rec]))
    resp = client.get("/diagnosis/result/tok-wp11-free")
    assert resp.status_code == 404
