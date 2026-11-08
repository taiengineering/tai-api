"""
B15-SAAS-WORKER-FNC-002: POST /worker-registry/bulk-import — 작업자 일괄 등록 계약 검증

검증 목표:
  W1: factory_id 미존재 → 404
  W2: 빈 파일 (헤더만) → 422 데이터 없음
  W3: 유효 CSV 정상 등록 → 200, created=1, updated=0
  W4: 중복 전화번호 → 200, updated=1, created=0
  W5: 이름/연락처 누락 행 포함 → 200, failed≥1 (나머지 행 등록 성공)
  W6: 직종 미매핑 → 200, mapping_failed≥1, 등록은 WJT020으로 성공

구조:
  인증 불필요 — bulk-import 는 factory_id Form + file UploadFile 전용
  supabase.table("factories")  → 시설 존재·company_id 조회
  supabase.table("worker_registry") → 중복 확인·insert·update
  CSV 포맷으로만 테스트 (pandas 의존 없음)

운영 안전:
  monkeypatch + FastAPI TestClient 전용 — 운영 DB/API 미접촉
  실제 파일 파싱 로직은 Python 표준 csv 모듈 사용 (외부 네트워크 없음)
"""
from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.worker_registry as wr_mod

_FAC_ID = "fac00000-0000-0000-0000-000000000001"
_CO_ID  = "co000000-0000-0000-0000-000000000001"
_WKR_ID = "wkr00000-0000-0000-0000-000000000001"

# ── CSV fixtures ──────────────────────────────────────────────────────────────

_CSV_HEADER_ONLY = "이름(필수),연락처(필수),직종(필수)\n".encode("utf-8")

_CSV_VALID = (
    "이름(필수),연락처(필수),직종(필수)\n"
    "홍길동,010-1234-5678,용접공\n"
).encode("utf-8")

_CSV_DUPLICATE_PHONE = (
    "이름(필수),연락처(필수),직종(필수)\n"
    "홍길동,010-1234-5678,용접공\n"
).encode("utf-8")

_CSV_MISSING_PHONE = (
    "이름(필수),연락처(필수),직종(필수)\n"
    "실패자,,용접공\n"
    "정상자,010-9876-5432,목공\n"
).encode("utf-8")

_CSV_UNKNOWN_JOB = (
    "이름(필수),연락처(필수),직종(필수)\n"
    "홍길동,010-1234-5678,알수없는직종XYZ\n"
).encode("utf-8")


# ── Mock 헬퍼 ──────────────────────────────────────────────────────────────────

def _fac_m_found():
    """시설 존재 — company_id 반환."""
    m = MagicMock()
    m.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
        data={"company_id": _CO_ID}
    )
    return m


def _fac_m_not_found():
    """시설 없음 — None 반환."""
    m = MagicMock()
    m.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
        data=None
    )
    return m


def _wr_m_new():
    """worker_registry — 중복 없음, insert 성공."""
    m = MagicMock()
    # dup check: .select().eq().eq().limit(1).execute() → no data
    m.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[]
    )
    # insert → new row
    m.insert.return_value.execute.return_value = MagicMock(data=[{"id": _WKR_ID}])
    return m


def _wr_m_dup():
    """worker_registry — 중복 존재, update 성공."""
    m = MagicMock()
    # dup check: returns existing row
    m.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{"id": _WKR_ID}]
    )
    # update chain: .update().eq().execute()
    m.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
    return m


def _make_sb(fac_m, wr_m) -> MagicMock:
    sb = MagicMock()
    sb.table.side_effect = lambda name: fac_m if name == "factories" else wr_m
    return sb


def _make_app() -> TestClient:
    app = FastAPI()
    app.include_router(wr_mod.router)
    return TestClient(app, raise_server_exceptions=False)


def _post(client: TestClient, csv_bytes: bytes, fac_id: str = _FAC_ID):
    return client.post(
        "/worker-registry/bulk-import",
        data={"factory_id": fac_id},
        files={"file": ("workers.csv", io.BytesIO(csv_bytes), "text/csv")},
    )


# ── W1: factory_id 미존재 → 404 ───────────────────────────────────────────────

def test_W1_factory_not_found_404():
    """W1: 존재하지 않는 factory_id → 404 시설 없음."""
    sb = _make_sb(_fac_m_not_found(), MagicMock())
    client = _make_app()
    with patch.object(wr_mod, "get_supabase", return_value=sb):
        r = _post(client, _CSV_VALID)
    assert r.status_code == 404, f"예상 404, 실제 {r.status_code}: {r.text}"
    assert "시설을 찾을 수 없습니다" in r.text


# ── W2: 빈 파일 (헤더만) → 422 ───────────────────────────────────────────────

def test_W2_empty_file_422():
    """W2: 헤더만 있는 CSV → 422 데이터 없음."""
    sb = _make_sb(_fac_m_found(), MagicMock())
    client = _make_app()
    with patch.object(wr_mod, "get_supabase", return_value=sb):
        r = _post(client, _CSV_HEADER_ONLY)
    assert r.status_code == 422, f"예상 422, 실제 {r.status_code}: {r.text}"
    assert "데이터가 없습니다" in r.text


# ── W3: 정상 등록 → 200, created=1, updated=0 ────────────────────────────────

def test_W3_success_created_200():
    """W3: 유효 CSV 1행 → 200, created=1, updated=0."""
    wr_m = _wr_m_new()
    sb = _make_sb(_fac_m_found(), wr_m)
    client = _make_app()
    with patch.object(wr_mod, "get_supabase", return_value=sb):
        r = _post(client, _CSV_VALID)
    assert r.status_code == 200, f"예상 200, 실제 {r.status_code}: {r.text}"
    body = r.json()
    assert body["status"] == "success"
    data = body["data"]
    assert data["created"] == 1
    assert data["updated"] == 0
    assert data["failed"] == []


# ── W4: 중복 전화번호 → 200, updated=1, created=0 ────────────────────────────

def test_W4_duplicate_phone_updated():
    """W4: 중복 전화번호(factory_id+phone 일치) → 200, updated=1."""
    wr_m = _wr_m_dup()
    sb = _make_sb(_fac_m_found(), wr_m)
    client = _make_app()
    with patch.object(wr_mod, "get_supabase", return_value=sb):
        r = _post(client, _CSV_DUPLICATE_PHONE)
    assert r.status_code == 200, f"예상 200, 실제 {r.status_code}: {r.text}"
    data = r.json()["data"]
    assert data["updated"] == 1
    assert data["created"] == 0


# ── W5: 이름/연락처 누락 행 → 200, failed≥1 ──────────────────────────────────

def test_W5_missing_phone_partial_fail():
    """W5: 첫 행 연락처 없음 → failed 1건, 두 번째 행은 정상 등록."""
    wr_m = _wr_m_new()
    sb = _make_sb(_fac_m_found(), wr_m)
    client = _make_app()
    with patch.object(wr_mod, "get_supabase", return_value=sb):
        r = _post(client, _CSV_MISSING_PHONE)
    assert r.status_code == 200, f"예상 200, 실제 {r.status_code}: {r.text}"
    data = r.json()["data"]
    assert len(data["failed"]) >= 1, f"failed 없음: {data}"
    assert data["created"] >= 1, f"정상 행 등록 실패: {data}"


# ── W6: 직종 미매핑 → mapping_failed≥1, 등록 성공 (WJT020) ──────────────────

def test_W6_unknown_job_mapping_failed():
    """W6: 직종명 미매핑 → mapping_failed 기록, 작업자는 WJT020으로 등록."""
    wr_m = _wr_m_new()
    sb = _make_sb(_fac_m_found(), wr_m)
    client = _make_app()
    with patch.object(wr_mod, "get_supabase", return_value=sb):
        r = _post(client, _CSV_UNKNOWN_JOB)
    assert r.status_code == 200, f"예상 200, 실제 {r.status_code}: {r.text}"
    data = r.json()["data"]
    assert len(data["mapping_failed"]) >= 1, f"mapping_failed 없음: {data}"
    assert data["created"] == 1, f"WJT020 등록 실패: {data}"
    # insert 실제 호출 확인 — job_type_code 가 WJT020
    call_args = wr_m.insert.call_args
    inserted = call_args[0][0]
    assert inserted.get("job_type_code") == "WJT020", f"WJT020 아님: {inserted.get('job_type_code')}"
