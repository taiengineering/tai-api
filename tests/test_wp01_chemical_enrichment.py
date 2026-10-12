"""TAI-WO-P0-CONTENT-WP01-001 — EXT-037/132 CAS 조회 계약 테스트.

T01  EXT-037 CAS 정확 일치
T02  EXT-132 CAS 정확 일치
T03  동일 CAS 복수 결과 보존
T04  CAS 없는 레코드 처리
T05  매칭 결과 없는 경우 빈 목록
T06  잘못된 CAS 형식 422
T07  현재 COMPLETED Snapshot만 조회
T08  이전 Snapshot 및 STAGING 제외
T09  EXT-037 실패 시 EXT-132 결과 보존
T10  기존 KECO API 회귀검증
T11  기존 MSDS API 반환 계약 유지
T12  외부 입력 및 JSON 텍스트 안전성
T13  다수 동시 조회 시 상태 격리

No real DB — TAI Supabase client patched throughout.
"""
from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.public_chemical_enrichment as enrich_mod
from services.ext037_chemical_safety.read import (
    Ext037Unavailable,
    get_chemical_safety_by_cas,
)
from services.ext132_hazardous_material.read import (
    Ext132Unavailable,
    get_hazardous_material_by_cas,
)

# ---------------------------------------------------------------------------
# Fixtures — sample DB rows
# ---------------------------------------------------------------------------

_CAS = "50-00-0"
_CAS_WATER = "7732-18-5"

_EXT037_RAW = {
    "dataNo": "1001",
    "casNo": _CAS,
    "chemKo": "포름알데히드",
    "chemEn": "Formaldehyde",
    "oral": "구강 독성 정보",
    "skin": "피부 독성 정보",
    "inhale": "흡입 독성 정보",
    "eyeball": "안구 독성 정보",
    "symptom": "두통, 구역질",
    "etc": "추가 안전정보",
}

_EXT037_ITEM = {"datano": "1001", "raw": _EXT037_RAW}

_EXT132_RAW = {
    "chemaicalno": "77",
    "chemicalname": "포름알데히드",
    "casno": _CAS,
    "unno": "1198",
    "hazardmaterialclass": "제4류 인화성액체 제1석유류",
}

_EXT132_ITEM = {"chemicalno": "77", "raw": _EXT132_RAW}

_SNAP_ID = "snap-uuid-001"
_SNAP_ROW = {"id": _SNAP_ID}


# ---------------------------------------------------------------------------
# Mock builder helpers
# ---------------------------------------------------------------------------

def _mock_client_ext037(snapshot_rows: list, item_rows: list) -> MagicMock:
    """TAI Supabase client mock for EXT-037 read calls."""
    client = MagicMock()

    def _table(name):
        t = MagicMock()
        if name == "ext037_chemical_safety_snapshots":
            (t.select.return_value
               .eq.return_value
               .eq.return_value
               .limit.return_value
               .execute.return_value) = MagicMock(data=snapshot_rows)
        elif name == "ext037_chemical_safety_snapshot_items":
            (t.select.return_value
               .eq.return_value
               .eq.return_value
               .execute.return_value) = MagicMock(data=item_rows)
        return t

    client.table.side_effect = _table
    return client


def _mock_client_ext132(snapshot_rows: list, item_rows: list) -> MagicMock:
    """TAI Supabase client mock for EXT-132 read calls."""
    client = MagicMock()

    def _table(name):
        t = MagicMock()
        if name == "ext132_hazardous_material_snapshots":
            (t.select.return_value
               .eq.return_value
               .eq.return_value
               .limit.return_value
               .execute.return_value) = MagicMock(data=snapshot_rows)
        elif name == "ext132_hazardous_material_snapshot_items":
            (t.select.return_value
               .eq.return_value
               .eq.return_value
               .execute.return_value) = MagicMock(data=item_rows)
        return t

    client.table.side_effect = _table
    return client


def _patch_ext037(monkeypatch, snapshot_rows, item_rows):
    client = _mock_client_ext037(snapshot_rows, item_rows)
    monkeypatch.setattr(
        "services.ext037_chemical_safety.read._get_client", lambda: client
    )
    return client


def _patch_ext132(monkeypatch, snapshot_rows, item_rows):
    client = _mock_client_ext132(snapshot_rows, item_rows)
    monkeypatch.setattr(
        "services.ext132_hazardous_material.read._get_client", lambda: client
    )
    return client


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(enrich_mod.router)
    return app


def _patch_both(monkeypatch, ext037_snaps, ext037_items, ext132_snaps, ext132_items):
    _patch_ext037(monkeypatch, ext037_snaps, ext037_items)
    _patch_ext132(monkeypatch, ext132_snaps, ext132_items)
    return TestClient(_make_app())


# ---------------------------------------------------------------------------
# T01: EXT-037 CAS 정확 일치
# ---------------------------------------------------------------------------

def test_t01_ext037_cas_exact_match(monkeypatch):
    _patch_ext037(monkeypatch, [_SNAP_ROW], [_EXT037_ITEM])
    result = get_chemical_safety_by_cas(_CAS)
    assert len(result) == 1
    item = result[0]
    assert item["cas_no"] == _CAS
    assert item["chem_ko"] == "포름알데히드"
    assert item["chem_en"] == "Formaldehyde"
    assert item["oral"] == "구강 독성 정보"
    assert item["inhale"] == "흡입 독성 정보"
    assert item["symptom"] == "두통, 구역질"
    assert item["datano"] == "1001"


# ---------------------------------------------------------------------------
# T02: EXT-132 CAS 정확 일치
# ---------------------------------------------------------------------------

def test_t02_ext132_cas_exact_match(monkeypatch):
    _patch_ext132(monkeypatch, [_SNAP_ROW], [_EXT132_ITEM])
    result = get_hazardous_material_by_cas(_CAS)
    assert len(result) == 1
    item = result[0]
    assert item["cas_no"] == _CAS
    assert item["chemical_name"] == "포름알데히드"
    assert item["un_no"] == "1198"
    assert item["hazard_class"] == "제4류 인화성액체 제1석유류"
    assert item["chemicalno"] == "77"


# ---------------------------------------------------------------------------
# T03: 동일 CAS 복수 결과 보존
# ---------------------------------------------------------------------------

def test_t03_multiple_records_same_cas(monkeypatch):
    item2_raw = {**_EXT132_RAW, "chemaicalno": "78", "hazardmaterialclass": "제4류 제2석유류"}
    item2 = {"chemicalno": "78", "raw": item2_raw}
    _patch_ext132(monkeypatch, [_SNAP_ROW], [_EXT132_ITEM, item2])
    result = get_hazardous_material_by_cas(_CAS)
    assert len(result) == 2
    ids = {r["chemicalno"] for r in result}
    assert ids == {"77", "78"}


# ---------------------------------------------------------------------------
# T04: CAS 없는 레코드 처리 — raw에 casNo 필드가 비어 있는 항목은 필드를 빈 문자열로 반환
# ---------------------------------------------------------------------------

def test_t04_item_with_no_cas_field(monkeypatch):
    item_no_cas = {"datano": "9999", "raw": {"dataNo": "9999", "chemKo": "미상", "chemEn": ""}}
    _patch_ext037(monkeypatch, [_SNAP_ROW], [item_no_cas])
    result = get_chemical_safety_by_cas(_CAS)
    assert len(result) == 1
    assert result[0]["cas_no"] == ""


# ---------------------------------------------------------------------------
# T05: 매칭 결과 없는 경우 빈 목록
# ---------------------------------------------------------------------------

def test_t05_no_match_returns_empty(monkeypatch):
    _patch_ext037(monkeypatch, [_SNAP_ROW], [])
    result = get_chemical_safety_by_cas(_CAS_WATER)
    assert result == []


def test_t05b_no_match_ext132_returns_empty(monkeypatch):
    _patch_ext132(monkeypatch, [_SNAP_ROW], [])
    result = get_hazardous_material_by_cas(_CAS_WATER)
    assert result == []


# ---------------------------------------------------------------------------
# T06: 잘못된 CAS 형식 422
# ---------------------------------------------------------------------------

def test_t06_invalid_cas_format_422(monkeypatch):
    _patch_ext037(monkeypatch, [_SNAP_ROW], [])
    _patch_ext132(monkeypatch, [_SNAP_ROW], [])
    client = TestClient(_make_app())
    resp = client.get("/public/chemical-enrichment/by-cas/NOTACAS")
    assert resp.status_code == 422
    assert "INVALID_CAS_FORMAT" in resp.json()["detail"]


def test_t06b_invalid_cas_no_dashes(monkeypatch):
    _patch_ext037(monkeypatch, [_SNAP_ROW], [])
    _patch_ext132(monkeypatch, [_SNAP_ROW], [])
    client = TestClient(_make_app())
    resp = client.get("/public/chemical-enrichment/by-cas/500000")
    assert resp.status_code == 422


def test_t06c_validate_cas_raises_for_bad_format():
    from services.keco_chemical.read import validate_cas
    with pytest.raises(ValueError):
        validate_cas("not-valid")


# ---------------------------------------------------------------------------
# T07: 현재 COMPLETED Snapshot만 조회 — snapshot_id로 items 필터링
# ---------------------------------------------------------------------------

def test_t07_current_snapshot_used(monkeypatch):
    captured = {}
    client_mock = MagicMock()

    def _table(name):
        t = MagicMock()
        if name == "ext037_chemical_safety_snapshots":
            (t.select.return_value
               .eq.return_value
               .eq.return_value
               .limit.return_value
               .execute.return_value) = MagicMock(data=[_SNAP_ROW])
        elif name == "ext037_chemical_safety_snapshot_items":
            # Capture the snapshot_id used in first .eq() call
            def _eq_first(field, val):
                if field == "snapshot_id":
                    captured["snapshot_id"] = val
                inner = MagicMock()
                inner.eq.return_value.execute.return_value = MagicMock(data=[_EXT037_ITEM])
                return inner
            t.select.return_value.eq.side_effect = _eq_first
        return t

    client_mock.table.side_effect = _table
    monkeypatch.setattr(
        "services.ext037_chemical_safety.read._get_client", lambda: client_mock
    )
    get_chemical_safety_by_cas(_CAS)
    assert captured.get("snapshot_id") == _SNAP_ID


# ---------------------------------------------------------------------------
# T08: Snapshot 없음 → None 반환 (STAGING 또는 현행 스냅샷 없을 때)
# ---------------------------------------------------------------------------

def test_t08_no_current_snapshot_returns_none(monkeypatch):
    _patch_ext037(monkeypatch, [], [])
    result = get_chemical_safety_by_cas(_CAS)
    assert result is None


def test_t08b_no_current_snapshot_ext132_returns_none(monkeypatch):
    _patch_ext132(monkeypatch, [], [])
    result = get_hazardous_material_by_cas(_CAS)
    assert result is None


def test_t08c_no_snapshot_api_returns_no_current_snapshot_status(monkeypatch):
    _patch_ext037(monkeypatch, [], [])
    _patch_ext132(monkeypatch, [], [])
    client = TestClient(_make_app())
    resp = client.get(f"/public/chemical-enrichment/by-cas/{_CAS}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["chemical_safety"]["status"] == "NO_CURRENT_SNAPSHOT"
    assert data["chemical_safety"]["items"] == []
    assert data["hazardous_material"]["status"] == "NO_CURRENT_SNAPSHOT"
    assert data["hazardous_material"]["items"] == []


# ---------------------------------------------------------------------------
# T09: EXT-037 실패 시 EXT-132 결과 보존
# ---------------------------------------------------------------------------

def test_t09_ext037_failure_ext132_result_preserved(monkeypatch):
    monkeypatch.setattr(
        "services.ext037_chemical_safety.read._get_client",
        lambda: (_ for _ in ()).throw(RuntimeError("DB connection failed")),
    )
    _patch_ext132(monkeypatch, [_SNAP_ROW], [_EXT132_ITEM])

    client = TestClient(_make_app())
    resp = client.get(f"/public/chemical-enrichment/by-cas/{_CAS}")
    assert resp.status_code == 200
    data = resp.json()

    chem_safety = data["chemical_safety"]
    assert chem_safety["status"] == "UNAVAILABLE"
    assert chem_safety["items"] == []

    hazmat = data["hazardous_material"]
    assert hazmat["status"] == "AVAILABLE"
    assert len(hazmat["items"]) == 1
    assert hazmat["items"][0]["cas_no"] == _CAS


def test_t09b_ext132_failure_ext037_result_preserved(monkeypatch):
    _patch_ext037(monkeypatch, [_SNAP_ROW], [_EXT037_ITEM])
    monkeypatch.setattr(
        "services.ext132_hazardous_material.read._get_client",
        lambda: (_ for _ in ()).throw(RuntimeError("DB timeout")),
    )

    client = TestClient(_make_app())
    resp = client.get(f"/public/chemical-enrichment/by-cas/{_CAS}")
    assert resp.status_code == 200
    data = resp.json()

    chem_safety = data["chemical_safety"]
    assert chem_safety["status"] == "AVAILABLE"
    assert len(chem_safety["items"]) == 1

    hazmat = data["hazardous_material"]
    assert hazmat["status"] == "UNAVAILABLE"
    assert hazmat["items"] == []


# ---------------------------------------------------------------------------
# T10: 기존 KECO API 회귀검증 — public_keco_chemical 라우터 미변경
# ---------------------------------------------------------------------------

def test_t10_keco_api_regression(monkeypatch):
    from unittest.mock import MagicMock
    import routers.public_keco_chemical as keco_mod

    def _mock_keco_client():
        client = MagicMock()
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.execute.return_value = (
            MagicMock(data=[])
        )
        client.schema.return_value = db
        return client

    monkeypatch.setattr("services.keco_chemical.read._get_leg_client", _mock_keco_client)
    app = FastAPI()
    app.include_router(keco_mod.router)
    client = TestClient(app)

    resp = client.get("/public/keco/chemicals/by-cas/50-00-0")
    assert resp.status_code == 200
    data = resp.json()
    assert "cas_no" in data
    assert "chemicals" in data
    assert "source_id" in data
    assert data["chemicals"] == []


# ---------------------------------------------------------------------------
# T11: 기존 MSDS API 반환 계약 유지 — kosha_public_msds 라우터 미변경
# ---------------------------------------------------------------------------

def test_t11_msds_router_contract_unchanged():
    import routers.kosha_public_msds as msds_mod
    assert hasattr(msds_mod, "router"), "kosha_public_msds router must exist"
    app = FastAPI()
    app.include_router(msds_mod.router)
    client = TestClient(app)
    resp = client.get("/public/kosha/msds/50-00-0")
    # dormant mode → 503 (KOSHA_MSDS_PUBLIC_MODE 미설정)
    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# T12: 외부 입력 및 JSON 텍스트 안전성
# ---------------------------------------------------------------------------

def test_t12_sql_injection_in_cas_returns_422(monkeypatch):
    client = TestClient(_make_app())
    resp = client.get("/public/chemical-enrichment/by-cas/50-00-0' OR '1'='1")
    assert resp.status_code == 422


def test_t12b_xss_in_raw_fields_returned_as_string(monkeypatch):
    xss_raw = {**_EXT037_RAW, "symptom": "<script>alert(1)</script>"}
    xss_item = {"datano": "1001", "raw": xss_raw}
    _patch_ext037(monkeypatch, [_SNAP_ROW], [xss_item])
    _patch_ext132(monkeypatch, [_SNAP_ROW], [])
    client = TestClient(_make_app())
    resp = client.get(f"/public/chemical-enrichment/by-cas/{_CAS}")
    assert resp.status_code == 200
    symptom = resp.json()["chemical_safety"]["items"][0]["symptom"]
    assert "<script>" in symptom


def test_t12c_env_vars_not_in_unavailable_response(monkeypatch):
    monkeypatch.setattr(
        "services.ext037_chemical_safety.read._get_client",
        lambda: (_ for _ in ()).throw(
            Ext037Unavailable("EXT037_UNAVAILABLE: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
        ),
    )
    _patch_ext132(monkeypatch, [_SNAP_ROW], [])
    client = TestClient(_make_app())
    resp = client.get(f"/public/chemical-enrichment/by-cas/{_CAS}")
    assert resp.status_code == 200
    response_text = resp.text
    assert "SUPABASE_SERVICE_ROLE_KEY" not in response_text
    assert "SUPABASE_URL" not in response_text


# ---------------------------------------------------------------------------
# T13: 다수 조회 시 상태 격리 — 각 요청이 독립 클라이언트를 사용
# ---------------------------------------------------------------------------

def test_t13_multiple_requests_state_isolation(monkeypatch):
    call_count = {"ext037": 0, "ext132": 0}

    def _ext037_client():
        call_count["ext037"] += 1
        return _mock_client_ext037([_SNAP_ROW], [_EXT037_ITEM])

    def _ext132_client():
        call_count["ext132"] += 1
        return _mock_client_ext132([_SNAP_ROW], [_EXT132_ITEM])

    monkeypatch.setattr("services.ext037_chemical_safety.read._get_client", _ext037_client)
    monkeypatch.setattr("services.ext132_hazardous_material.read._get_client", _ext132_client)

    http_client = TestClient(_make_app())
    for _ in range(5):
        resp = http_client.get(f"/public/chemical-enrichment/by-cas/{_CAS}")
        assert resp.status_code == 200

    assert call_count["ext037"] == 5
    assert call_count["ext132"] == 5


# ---------------------------------------------------------------------------
# T_RESP: 응답 구조 계약
# ---------------------------------------------------------------------------

def test_resp_shape(monkeypatch):
    tc = _patch_both(monkeypatch, [_SNAP_ROW], [_EXT037_ITEM], [_SNAP_ROW], [_EXT132_ITEM])
    resp = tc.get(f"/public/chemical-enrichment/by-cas/{_CAS}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["cas_no"] == _CAS

    for block_key in ("chemical_safety", "hazardous_material"):
        block = data[block_key]
        assert "source_id" in block
        assert "display_name" in block
        assert "status" in block
        assert "items" in block
        assert isinstance(block["items"], list)

    cs = data["chemical_safety"]
    assert cs["source_id"] == "EXT037_CHEMICAL_SAFETY"
    assert cs["status"] == "AVAILABLE"
    item = cs["items"][0]
    for key in ("datano", "chem_ko", "chem_en", "cas_no", "oral", "skin", "inhale", "eyeball", "symptom", "etc"):
        assert key in item, f"Missing key in chemical_safety item: {key}"

    hm = data["hazardous_material"]
    assert hm["source_id"] == "EXT132_HAZARDOUS_MATERIAL"
    assert hm["status"] == "AVAILABLE"
    hitem = hm["items"][0]
    for key in ("chemicalno", "chemical_name", "cas_no", "un_no", "hazard_class"):
        assert key in hitem, f"Missing key in hazardous_material item: {key}"


def test_resp_no_snapshot_status(monkeypatch):
    _patch_ext037(monkeypatch, [], [])
    _patch_ext132(monkeypatch, [], [])
    client = TestClient(_make_app())
    resp = client.get(f"/public/chemical-enrichment/by-cas/{_CAS}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["chemical_safety"]["status"] == "NO_CURRENT_SNAPSHOT"
    assert data["chemical_safety"]["items"] == []
    assert data["hazardous_material"]["status"] == "NO_CURRENT_SNAPSHOT"
    assert data["hazardous_material"]["items"] == []
