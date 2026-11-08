"""
B11-SAAS-WORKER-FNC-002: POST /worker-registry/bulk-import — 작업자 일괄 등록 계약 검증

검증 목표:
  W1: 사업장(factory) 없음 → 404
  W2: 빈 CSV(헤더만, 데이터 없음) → 422
  W3: 이름·연락처 누락 행 → failed 목록에 포함, created=0
  W4: bulk-import에 Depends(get_current_user) 미선언 — B10-WF-001 연장 소스 확인

판정:
  COVERAGE_DEBT — bulk-import도 per-route 인증·company_id 소유권 검증 없음.
  B10-WF-001 연장 (CROSS_TENANT_BULK_REGISTER_RISK). 보안 수정은 별도 Owner 승인 필요.

W1 주의:
  .single().execute() 반환 data=None 경로 (PostgREST 호환 mock).
  실제 운영 환경에서 .single()이 예외를 발생시키는 경우는 별도 경로이며 여기서 측정하지 않는다.

운영 안전:
  monkeypatch + FastAPI TestClient 전용 — 운영 DB/API 미접촉
"""
from __future__ import annotations

import inspect
import io
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.worker_registry as wr


def _make_app(sb: MagicMock) -> TestClient:
    app = FastAPI()
    app.include_router(wr.router)
    return TestClient(app, raise_server_exceptions=False)


def _csv(rows: list[list[str]], headers: list[str] | None = None) -> bytes:
    """CSV bytes 생성. headers=None이면 기본 작업자 헤더 사용."""
    if headers is None:
        headers = ["이름", "연락처", "직종"]
    lines = [",".join(headers)]
    lines += [",".join(r) for r in rows]
    return "\n".join(lines).encode("utf-8-sig")


# ── W1: 사업장 없음 → 404 ────────────────────────────────────────────────────

def test_W1_factory_not_found_404():
    """W1: 존재하지 않는 factory_id → 404 (시설을 찾을 수 없습니다).

    .single().execute() 가 data=None 을 반환하는 경우의 404 처리.
    """
    sb = MagicMock()
    # .single().execute() → data=None (factory 미존재 시뮬레이션)
    sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = \
        MagicMock(data=None)

    with patch.object(wr, "get_supabase", return_value=sb):
        client = _make_app(sb)
        csv_bytes = _csv([["홍길동", "01011112222", "용접공"]])
        r = client.post(
            "/worker-registry/bulk-import",
            data={"factory_id": "fac-nonexistent-0000"},
            files={"file": ("workers.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
    assert r.status_code == 404, f"예상 404, 실제 {r.status_code}: {r.text}"


# ── W2: 빈 CSV → 422 ─────────────────────────────────────────────────────────

def test_W2_empty_csv_422():
    """W2: 헤더만 있고 데이터 행 없는 CSV → 422 (파일에 데이터가 없습니다)."""
    sb = MagicMock()
    # factory 조회 성공
    sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = \
        MagicMock(data={"company_id": "co-aaa"})

    with patch.object(wr, "get_supabase", return_value=sb):
        client = _make_app(sb)
        empty_csv = _csv([])  # 헤더만, 데이터 없음
        r = client.post(
            "/worker-registry/bulk-import",
            data={"factory_id": "fac-b11-0001"},
            files={"file": ("workers.csv", io.BytesIO(empty_csv), "text/csv")},
        )
    assert r.status_code == 422, f"예상 422, 실제 {r.status_code}: {r.text}"


# ── W3: 이름·연락처 누락 행 → failed 포함, created=0 ─────────────────────

def test_W3_missing_name_phone_in_failed():
    """W3: 이름·연락처 누락 행 → failed 목록에 기록, created=0.

    worker_registry 소스: `if not name or not phone_raw: failed.append(...)`
    """
    sb = MagicMock()
    # factory 조회 성공
    sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = \
        MagicMock(data={"company_id": "co-aaa"})
    # 중복 체크 (dup select chain) — 비어 있음
    sb.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = \
        MagicMock(data=[])

    with patch.object(wr, "get_supabase", return_value=sb):
        client = _make_app(sb)
        # 행 1: 이름 없음 / 행 2: 연락처 없음
        bad_csv = _csv([
            ["", "01011112222", "용접공"],  # 이름 없음
            ["김철수", "", "생산직(일반)"], # 연락처 없음
        ])
        r = client.post(
            "/worker-registry/bulk-import",
            data={"factory_id": "fac-b11-0001"},
            files={"file": ("workers.csv", io.BytesIO(bad_csv), "text/csv")},
        )

    assert r.status_code == 200, f"예상 200(부분실패), 실제 {r.status_code}: {r.text}"
    data = r.json()["data"]
    assert data["created"] == 0, f"created가 0이어야 함. 실제: {data['created']}"
    assert len(data["failed"]) == 2, (
        f"failed 항목이 2개여야 함. 실제: {data['failed']}"
    )
    # 각 행의 실패 이유 포함 확인
    reasons = [f.get("reason", "") for f in data["failed"]]
    assert all("누락" in r for r in reasons), (
        f"'누락' 메시지가 포함되어야 함. 실제 reasons: {reasons}"
    )


# ── W4: 소스 계약 — Depends(get_current_user) 미선언, company_id 소유권 없음 ─

def test_W4_bulk_import_no_auth_no_company_ownership():
    """W4: bulk_import_workers 소스에 Depends(get_current_user) 미선언.

    B10-WF-001 연장:
    - bulk-import도 per-route 인증 미선언
    - factory → company_id 역참조 있으나 caller company_id 대조 없음
    판정: COVERAGE_DEBT (보안 수정 별도 Owner 승인 필요)
    """
    src = inspect.getsource(wr.bulk_import_workers)

    # per-route 인증 미선언 확인
    assert "get_current_user" not in src, (
        "bulk_import_workers에 get_current_user Depends가 추가됐습니다 "
        "— B10-WF-001 보안 수정이 적용됐을 수 있음. COVERED 재분류 검토 필요."
    )

    # company_id 소유권 검증 없음 — caller와 factory.company_id 비교 없음
    assert "_assert_worker_company" not in src
    assert "_ensure_factory_own" not in src
    assert 'current_user.get("company_id")' not in src

    # factory → company_id 역참조는 존재 (등록 대상 회사 식별용)
    assert "factory_id" in src
    assert "company_id" in src
