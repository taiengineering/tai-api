"""
B13-SAAS-RISK-FNC-001: POST /ra/assessments/{assessment_id}/items — 위험요인 등록 계약 검증

검증 목표:
  I1: 인증 없음 → 401
  I2: 타사 assessment_id → 404 (_ensure_assessment_own 존재 숨김)
  I3: assessment에 scale_id 없음 → 409 (고시 제9조제2항 척도 미확정)
  I4: 정상 등록 → 200, verdict + item 반환

구조:
  _ensure_assessment_own: risk_assessments.company_id 조회 → _ensure_own_company
  _get_scale_for: scale_id 없으면 즉시 409 (ra_scale 미조회)
  decide(): THREE_STEP 기법 — raw_input_json.level 직접 반영

운영 안전:
  monkeypatch + FastAPI TestClient 전용 — 운영 DB/API 미접촉
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.ra_items as ri_mod
from routers.auth import get_current_user

_ASSESSMENT_ID = "ra-b13-assessment-0001-000000000001"
_CO_A_ID       = "co-aaaa-0000-0000-0000-000000000001"
_CO_B_ID       = "co-bbbb-0000-0000-0000-000000000002"
_SCALE_ID      = "scale-b13-test-001-000000000001"
_ITEM_ID       = "item-b13-0001-0000-000000000001"

_CALLER = {
    "id":          "usr-b13-ra-001",
    "company_id":  _CO_A_ID,
    "role_code":   "010",
    "is_active":   True,
    "status_code": "ACTIVE",
}

_SCALE_THREE_STEP = {
    "id":           _SCALE_ID,
    "method":       "THREE_STEP",
    "levels_json":  [
        {"code": "LOW",  "order": 1},
        {"code": "HIGH", "order": 2},
    ],
    "acceptable_max": "LOW",
}

_VALID_ITEM_BODY = {
    "hazard":          "고소 작업 중 추락",
    "work_process":    "외벽 도장",
    "raw_input_json":  {"level": "LOW"},
}


def _make_sb_i2(assessment_co: str = _CO_B_ID) -> MagicMock:
    """I2: assessment가 타사 소유 — _ensure_assessment_own 에서 404."""
    ra_m = MagicMock()
    ra_m.select.return_value.eq.return_value.limit.return_value.execute.return_value = \
        MagicMock(data=[{"company_id": assessment_co}])

    rds_m = MagicMock()
    rds_m.select.return_value.eq.return_value.limit.return_value.execute.return_value = \
        MagicMock(data=[{"scope_type": "COMPANY"}])

    sb = MagicMock()
    sb.table.side_effect = lambda name: (
        ra_m  if name == "risk_assessments" else
        rds_m if name == "role_data_scope"  else
        MagicMock()
    )
    return sb


def _make_sb_i3() -> MagicMock:
    """I3: assessment에 scale_id 없음 → _get_scale_for 가 즉시 409."""
    ra_m = MagicMock()
    ra_m.select.return_value.eq.return_value.limit.return_value.execute.return_value = \
        MagicMock(data=[{"id": _ASSESSMENT_ID, "scale_id": None}])

    sb = MagicMock()
    sb.table.side_effect = lambda name: ra_m if name == "risk_assessments" else MagicMock()
    return sb


def _make_sb_i4() -> MagicMock:
    """I4: 정상 등록 — ra_item INSERT 성공, 재판정 이력 적재."""
    ra_m = MagicMock()
    ra_m.select.return_value.eq.return_value.limit.return_value.execute.return_value = \
        MagicMock(data=[{"id": _ASSESSMENT_ID, "scale_id": _SCALE_ID}])

    scale_m = MagicMock()
    scale_m.select.return_value.eq.return_value.limit.return_value.execute.return_value = \
        MagicMock(data=[_SCALE_THREE_STEP])

    item_m = MagicMock()
    item_m.insert.return_value.execute.return_value = MagicMock(data=[{
        "id":            _ITEM_ID,
        "assessment_id": _ASSESSMENT_ID,
        "hazard":        "고소 작업 중 추락",
        "level":         "LOW",
        "acceptable":    True,
        "escalation_json": None,
        "created_at":    "2026-11-08T00:00:00",
    }])

    rev_m = MagicMock()
    # _record_revision: SELECT seq (prior revisions — empty) + INSERT
    rev_m.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = \
        MagicMock(data=[])
    rev_m.insert.return_value.execute.return_value = MagicMock(data=[{"seq": 1}])

    sb = MagicMock()
    sb.table.side_effect = lambda name: (
        ra_m    if name == "risk_assessments"  else
        scale_m if name == "ra_scale"          else
        item_m  if name == "ra_item"           else
        rev_m   if name == "ra_item_revision"  else
        MagicMock()
    )
    return sb


def _make_app_with_user(sb: MagicMock) -> TestClient:
    app = FastAPI()
    app.include_router(ri_mod.router)
    app.dependency_overrides[get_current_user] = lambda: _CALLER
    with patch.object(ri_mod, "get_supabase", return_value=sb):
        return TestClient(app, raise_server_exceptions=False)


# ── I1: 인증 없음 → 401 ──────────────────────────────────────────────

def test_I1_no_auth_401():
    """I1: Authorization 헤더 없음 → get_current_user 401."""
    sb = MagicMock()
    with patch.object(ri_mod, "get_supabase", return_value=sb):
        app = FastAPI()
        app.include_router(ri_mod.router)
        client = TestClient(app, raise_server_exceptions=False)
        r = client.post(f"/ra/assessments/{_ASSESSMENT_ID}/items",
                        json=_VALID_ITEM_BODY)
    assert r.status_code == 401, f"예상 401, 실제 {r.status_code}: {r.text}"


# ── I2: 타사 assessment → 404 ────────────────────────────────────────

def test_I2_cross_company_404():
    """I2: 토큰 company_id와 assessment company_id 불일치 → 404 (존재 숨김)."""
    sb = _make_sb_i2(assessment_co=_CO_B_ID)
    client = _make_app_with_user(sb)
    with patch.object(ri_mod, "get_supabase", return_value=sb):
        r = client.post(f"/ra/assessments/{_ASSESSMENT_ID}/items",
                        json=_VALID_ITEM_BODY)
    assert r.status_code == 404, f"예상 404 (타사 차단), 실제 {r.status_code}: {r.text}"


# ── I3: scale_id 없음 → 409 ──────────────────────────────────────────

def test_I3_no_scale_409():
    """I3: assessment.scale_id=None → _get_scale_for 가 409 반환 (고시 제9조제2항)."""
    sb = _make_sb_i3()
    with patch.object(ri_mod, "_ensure_assessment_own"):  # 소유 확인 우회
        client = _make_app_with_user(sb)
        with patch.object(ri_mod, "get_supabase", return_value=sb):
            r = client.post(f"/ra/assessments/{_ASSESSMENT_ID}/items",
                            json=_VALID_ITEM_BODY)
    assert r.status_code == 409, f"예상 409 (척도 미지정), 실제 {r.status_code}: {r.text}"


# ── I4: 정상 등록 → 200 ──────────────────────────────────────────────

def test_I4_success_200():
    """I4: 자사 assessment + scale 지정 + 유효 입력 → 200, verdict 포함 반환."""
    sb = _make_sb_i4()
    with patch.object(ri_mod, "_ensure_assessment_own"):  # 소유 확인 우회
        client = _make_app_with_user(sb)
        with patch.object(ri_mod, "get_supabase", return_value=sb):
            r = client.post(f"/ra/assessments/{_ASSESSMENT_ID}/items",
                            json=_VALID_ITEM_BODY)
    assert r.status_code == 200, f"예상 200, 실제 {r.status_code}: {r.text}"
    body = r.json()
    assert body["status"] == "success"
    assert "data" in body
    data = body["data"]
    assert data["id"] == _ITEM_ID
    assert "verdict" in data
    assert data["verdict"]["method"] == "THREE_STEP"
    assert data["verdict"]["acceptable"] is True
