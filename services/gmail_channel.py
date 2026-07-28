"""Gmail 채널 — 서비스계정 도메인 위임 발송/수신 (WO-8 NotifyDispatcher).

Goal: G-ms4je4z3-33eada
- 서비스계정 도메인 위임(DWD)으로 tai@taieng.co.kr 가장(impersonate).
- 발송: Gmail API messages.send (RFC822 MIME base64url).
- 수신(WO-8B): messages.list→get→파싱(parse_message).
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


# ── 수신 (WO-8B) ─────────────────────────────────────────────────────
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
    """메시지 상세 (헤더·본문 raw)."""
    svc = _service()
    try:
        return svc.users().messages().get(userId="me", id=msg_id, format="full").execute()
    except Exception as e:  # noqa: BLE001
        raise GmailError(502, f"Gmail 메시지 조회 실패: {e}") from e


def _header(headers: List[Dict[str, str]], name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _decode_part(data: str) -> str:
    try:
        return base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return ""


def _extract_bodies(payload: Dict[str, Any]) -> Dict[str, str]:
    """페이로드에서 text/plain·text/html 본문 추출 (재귀)."""
    result = {"text": "", "html": ""}

    def walk(part: Dict[str, Any]) -> None:
        mime = part.get("mimeType", "")
        body = part.get("body", {})
        data = body.get("data")
        if mime == "text/plain" and data and not result["text"]:
            result["text"] = _decode_part(data)
        elif mime == "text/html" and data and not result["html"]:
            result["html"] = _decode_part(data)
        for sub in part.get("parts", []) or []:
            walk(sub)

    walk(payload)
    return result


def parse_message(msg: Dict[str, Any]) -> Dict[str, Any]:
    """Gmail get_message 응답 → mail_logs 적재용 dict."""
    payload = msg.get("payload", {})
    headers = payload.get("headers", [])
    bodies = _extract_bodies(payload)

    from_email = _header(headers, "From")
    to_raw = _header(headers, "To")
    cc_raw = _header(headers, "Cc")
    subject = _header(headers, "Subject") or "(제목 없음)"

    to_emails = [e.strip() for e in to_raw.split(",") if e.strip()]
    cc_emails = [e.strip() for e in cc_raw.split(",") if e.strip()]

    html_body = bodies["html"]
    text_body = bodies["text"]
    if not html_body and text_body:
        import html as html_escape
        html_body = f"<pre style='white-space:pre-wrap;font-family:inherit;margin:0;'>{html_escape.escape(text_body)}</pre>"

    return {
        "gmail_id": msg.get("id"),
        "thread_id": msg.get("threadId"),
        "from_email": from_email,
        "to_emails": to_emails,
        "cc_emails": cc_emails,
        "subject": subject,
        "html_body": html_body,
        "text_body": text_body,
        "snippet": msg.get("snippet", ""),
    }
