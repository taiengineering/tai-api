"""
B12-SAAS-SUP-FNC-001: POST /contacts — 고객센터 문의 계약 검증

검증 목표:
  S1: 정상 저장 → 200, data.id 또는 저장 행 반환
  S2: 필수 필드 누락(name/email/content) → 422 (Pydantic 검증)
  S3: DB 저장 오류(insert 예외) → 500
  S4: 직접 Slack 발송 없음 — 소스 계약 확인
      (WO-SLACK-EVENT-HUB-001: 직접 발송 제거, DB trigger 위임)

범위 외:
  POST /contacts/with-attachments — test_contact_attachments.py 커버
  POST /contacts/{id}/attachments — test_contact_attachments.py 커버

운영 안전:
  monkeypatch + FastAPI TestClient 전용 — 운영 DB/API 미접촉
  Slack, 이메일, 운영 DB 미접촉
"""
from __future__ import annotations

import inspect
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.site_public as sp_mod

_INQUIRY_ID = "inq-b12-0001-0000-000000000001"


def _make_app(sb: MagicMock) -> TestClient:
    app = FastAPI()
    app.include_router(sp_mod.router)
    with patch.object(sp_mod, "get_supabase", return_value=sb):
        return TestClient(app, raise_server_exceptions=False)


def _ok_sb() -> MagicMock:
    """정상 저장 Supabase 모의: inquiries.insert().execute() → [{id: ...}]"""
    sb = MagicMock()
    sb.table.return_value.insert.return_value.execute.return_value = \
        MagicMock(data=[{"id": _INQUIRY_ID, "name": "홍길동", "email": "test@example.com"}])
    return sb


# ── S1: 정상 저장 → 200 ──────────────────────────────────────────────────

def test_S1_success_200():
    """S1: name/email/content 모두 제공 → 200, status=success."""
    sb = _ok_sb()
    client = _make_app(sb)
    with patch.object(sp_mod, "get_supabase", return_value=sb):
        r = client.post("/contacts", json={
            "name": "홍길동",
            "email": "hong@example.com",
            "content": "안전 컨설팅 문의드립니다.",
        })
    assert r.status_code == 200, f"예상 200, 실제 {r.status_code}: {r.text}"
    body = r.json()
    assert body["status"] == "success"
    assert "data" in body


# ── S2: 필수 필드 누락 → 422 ─────────────────────────────────────────────

def test_S2_missing_required_fields_422():
    """S2: name/email/content 중 하나라도 누락 → Pydantic 422."""
    sb = _ok_sb()
    client = _make_app(sb)
    with patch.object(sp_mod, "get_supabase", return_value=sb):
        # content 누락
        r = client.post("/contacts", json={
            "name": "홍길동",
            "email": "hong@example.com",
            # content 없음
        })
    assert r.status_code == 422, f"예상 422 (content 누락), 실제 {r.status_code}: {r.text}"


def test_S2b_missing_email_422():
    """S2b: email 누락 → Pydantic 422."""
    sb = _ok_sb()
    client = _make_app(sb)
    with patch.object(sp_mod, "get_supabase", return_value=sb):
        r = client.post("/contacts", json={
            "name": "홍길동",
            # email 없음
            "content": "문의 내용입니다.",
        })
    assert r.status_code == 422, f"예상 422 (email 누락), 실제 {r.status_code}: {r.text}"


# ── S3: DB 저장 오류 → 500 ──────────────────────────────────────────────

def test_S3_db_error_500():
    """S3: insert 중 예외 발생 → HTTPException(500, '저장 실패')."""
    sb = MagicMock()
    sb.table.return_value.insert.return_value.execute.side_effect = Exception("DB connection lost")

    client = _make_app(sb)
    with patch.object(sp_mod, "get_supabase", return_value=sb):
        r = client.post("/contacts", json={
            "name": "홍길동",
            "email": "hong@example.com",
            "content": "문의 내용입니다.",
        })
    assert r.status_code == 500, f"예상 500, 실제 {r.status_code}: {r.text}"
    assert "저장 실패" in r.text, f"'저장 실패' 메시지 없음: {r.text}"


# ── S4: 직접 Slack 발송 없음 — 소스 계약 ───────────────────────────────

def test_S4_no_direct_slack_in_submit():
    """S4: submit_public_contact 소스에 직접 Slack 발송 코드 없음.

    WO-SLACK-EVENT-HUB-001 PR-①: writer 직접 발송 제거 완료.
    Slack 발송 = DB trigger trg_inquiries_notify → /internal/inbox/notify 경유.
    이중 발송 방지 계약 소스 확인.
    """
    src = inspect.getsource(sp_mod.submit_public_contact)

    # 직접 Slack 발송 없음 — docstring/주석의 'slack' 언급은 허용, 실제 호출 코드만 검사
    # hooks.slack.com / chat_postMessage / send_slack / slack_client 등 호출 패턴 없어야 함
    assert "hooks.slack.com" not in src, (
        "submit_public_contact에 hooks.slack.com 직접 호출 발견"
    )
    assert "chat_postMessage" not in src, (
        "submit_public_contact에 chat_postMessage 직접 호출 발견"
    )
    assert "send_slack" not in src, (
        "submit_public_contact에 send_slack 직접 호출 발견"
    )
    # 이중발송 방지 주석 존재 확인 (WO-SLACK-EVENT-HUB-001)
    assert "이중발송 금지" in src or "이중 발송 금지" in src or "WO-SLACK" in src, (
        "submit_public_contact에 Slack 이중발송 금지 주석 없음"
    )

    # inquiries 테이블 저장은 존재
    assert '"inquiries"' in src or "'inquiries'" in src, (
        "submit_public_contact에 inquiries 저장 코드 없음"
    )

    # 성공 반환 구조
    assert 'status' in src and '"success"' in src, (
        "submit_public_contact에 success 반환 없음"
    )
