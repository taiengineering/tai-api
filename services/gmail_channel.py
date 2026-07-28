"""Gmail 채널 — 서비스계정 도메인 위임 발송/수신 (WO-8 NotifyDispatcher).

Goal: G-ms4je4z3-33eada
- 서비스계정 도메인 위임(DWD)으로 tai@taieng.co.kr 가장(impersonate).
- 발송: Gmail API messages.send (RFC822 MIME base64url).
- 수신(WO-8B): messages.list→get→mail_logs 적재.
- SDK/키 지연 로딩: 미설정·미설치 시 GmailError(501) → 배포 `/health` 안전.
- env(Railway 단일): GMAIL_SA_JSON 또는 GMAIL_SA_JSON_B64, GMAIL_SENDER.
"""
from __future__ import annotations

import base64
import json
import logging
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

# 좁은 스코프 (mail.google.com 전체 회피 — CASA Tier2 심사 회피)
_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]


class GmailError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _load_sa_info() -> Dict[str, Any]:
    """서비스계정 JSON 로딩 (평문 또는 base64)."""
    raw = os.getenv("GMAIL_SA_JSON", "").strip()
    if not raw:
        b64 = os.getenv("GMAIL_SA_JSON_B64", "").strip()
        if b64:
            try:
                raw = base64.b64decode(b64).decode("utf-8")
            except Exception as e:  # noqa: BLE001
                raise GmailError(500, f"GMAIL_SA_JSON_B64 디코딩 실패: {e}") from e
    if not raw:
        raise GmailError(501, "Gmail 서비스계정(GMAIL_SA_JSON/_B64)이 설정되지 않았습니다.")
    try:
        return json.loads(raw)
    except Exception as e:  # noqa: BLE001
        raise GmailError(500, f"GMAIL_SA_JSON 파싱 실패: {e}") from e


def _sender() -> str:
    s = os.getenv("GMAIL_SENDER", "").strip()
    if not s:
        raise GmailError(501, "발신 계정(GMAIL_SENDER)이 설정되지 않았습니다.")
    return s


def _service():
    """도메인 위임 Gmail 서비스 (지연 import)."""
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except Exception as e:  # noqa: BLE001
        raise GmailError(501, f"Gmail SDK 미설치(google-api-python-client/google-auth): {e}") from e

    info = _load_sa_info()
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=_SCOPES
    ).with_subject(_sender())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _build_mime(to: List[str], subject: str, *, html: Optional[str] = None,
                text: Optional[str] = None, cc: Optional[List[str]] = None,
                reply_to: Optional[List[str]] = None) -> str:
    """RFC822 MIME → base64url raw."""
    msg = MIMEMultipart("alternative")
    msg["To"] = ", ".join(to)
    msg["From"] = _sender()
    msg["Subject"] = subject
    if cc:
        msg["Cc"] = ", ".join(cc)
    if reply_to:
        msg["Reply-To"] = ", ".join(reply_to)
    if text:
        msg.attach(MIMEText(text, "plain", "utf-8"))
    if html:
        msg.attach(MIMEText(html, "html", "utf-8"))
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    return raw


def send(to: List[str], subject: str, *, html: Optional[str] = None,
         text: Optional[str] = None, cc: Optional[List[str]] = None,
         reply_to: Optional[List[str]] = None) -> Dict[str, Any]:
    """Gmail API로 메일 발송. 반환: {id, threadId}."""
    if not to:
        raise GmailError(400, "수신자(to)가 비어 있습니다.")
    if not (html or text):
        raise GmailError(400, "본문(html 또는 text)이 필요합니다.")
    svc = _service()
    raw = _build_mime(to, subject, html=html, text=text, cc=cc, reply_to=reply_to)
    try:
        result = svc.users().messages().send(userId="me", body={"raw": raw}).execute()
    except Exception as e:  # noqa: BLE001
        raise GmailError(502, f"Gmail 발송 실패: {e}") from e
    return {"id": result.get("id"), "threadId": result.get("threadId")}


# ── 수신 폴링 (WO-8B) ────────────────────────────────────────────────
def list_new_messages(query: str = "in:inbox", max_results: int = 50) -> List[str]:
    """수신 메시지 ID 목록 (신규 필터는 호출부에서 관리)."""
    svc = _service()
    try:
        res = svc.users().messages().list(
            userId="me", q=query, maxResults=max_results
        ).execute()
    except Exception as e:  # noqa: BLE001
        raise GmailError(502, f"Gmail 목록 조회 실패: {e}") from e
    return [m["id"] for m in res.get("messages", [])]


def get_message(msg_id: str) -> Dict[str, Any]:
    """메시지 상세 (헤더·본문)."""
    svc = _service()
    try:
        return svc.users().messages().get(userId="me", id=msg_id, format="full").execute()
    except Exception as e:  # noqa: BLE001
        raise GmailError(502, f"Gmail 메시지 조회 실패: {e}") from e
