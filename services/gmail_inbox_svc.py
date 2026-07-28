"""Gmail 수신 폴링 서비스 (WO-8B).

Goal: G-ms4je4z3-33eada
- Gmail 받은편지함 → mail_logs(direction=inbound) 적재.
- 중복 방지: resend_id(=Gmail message id) 부분 UNIQUE 인덱스 + 선조회.
- 신규만 적재: 이미 저장된 gmail id는 건너뜀.
- 자동화 훅(on_inbound): 콜백 등록 시 수신 건마다 호출(WO-12 자동화엔진 결합 지점).
- Gmail 미설정·미설치 시 GmailError(501) → 안전.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from db.supabase_client import get_supabase
from services import gmail_channel

log = logging.getLogger(__name__)

# 수신 콜백 레지스트리. 외부(WO-12 자동화엔진 등)가 register_inbound_handler로 등록.
# 등록이 없으면 적재만 하고 콜백은 발화하지 않는다.
_INBOUND_HANDLERS: List[Callable[[str, Dict[str, Any]], None]] = []


def register_inbound_handler(handler: Callable[[str, Dict[str, Any]], None]) -> None:
    """수신 메일 콜백 등록. handler(mail_log_id, parsed) 시그니처."""
    if handler not in _INBOUND_HANDLERS:
        _INBOUND_HANDLERS.append(handler)


def _existing_ids(gmail_ids: List[str]) -> set:
    """이미 mail_logs(inbound)에 있는 gmail id 집합."""
    if not gmail_ids:
        return set()
    res = (
        get_supabase().table("mail_logs")
        .select("resend_id")
        .eq("direction", "inbound")
        .in_("resend_id", gmail_ids)
        .execute()
    )
    return {r["resend_id"] for r in (res.data or []) if r.get("resend_id")}


def _insert_inbound(parsed: Dict[str, Any]) -> Optional[str]:
    """파싱된 수신 메일을 mail_logs에 적재. 중복(UNIQUE 위반)이면 None."""
    row = {
        "from_email": parsed["from_email"],
        "to_emails": parsed["to_emails"],
        "cc_emails": parsed["cc_emails"],
        "subject": parsed["subject"],
        "html_body": parsed["html_body"],
        "text_body": parsed["text_body"],
        "resend_id": parsed["gmail_id"],   # 외부 메일ID 공용 컬럼(=Gmail message id)
        "status": "sent",
        "direction": "inbound",
        "read": False,
        "deleted": False,
        "attachments": [],
    }
    try:
        res = get_supabase().table("mail_logs").insert(row).execute()
        return res.data[0]["id"] if res.data else None
    except Exception as e:  # noqa: BLE001 — UNIQUE 위반 등은 조용히 스킵
        msg = str(e)
        if "text_body" in msg:
            row.pop("text_body", None)
            try:
                res = get_supabase().table("mail_logs").insert(row).execute()
                return res.data[0]["id"] if res.data else None
            except Exception as e2:  # noqa: BLE001
                log.warning("[GMAIL-INBOX] 적재 실패(text_body 제외 후도): %s", e2)
                return None
        log.info("[GMAIL-INBOX] 스킵(중복/오류): %s", msg[:120])
        return None


def pull_inbox(query: str = "in:inbox", max_results: int = 50) -> Dict[str, Any]:
    """Gmail 받은편지함 신규 메일을 mail_logs에 적재.

    반환: {fetched, new, skipped, inserted_ids}
    """
    ids = gmail_channel.list_new_messages(query=query, max_results=max_results)
    if not ids:
        return {"fetched": 0, "new": 0, "skipped": 0, "inserted_ids": []}

    already = _existing_ids(ids)
    to_fetch = [i for i in ids if i not in already]

    inserted: List[str] = []
    for gid in to_fetch:
        try:
            msg = gmail_channel.get_message(gid)
            parsed = gmail_channel.parse_message(msg)
            new_id = _insert_inbound(parsed)
            if new_id:
                inserted.append(new_id)
                _fire_inbound(new_id, parsed)
        except gmail_channel.GmailError:
            raise
        except Exception as e:  # noqa: BLE001
            log.warning("[GMAIL-INBOX] 메시지 처리 실패 %s: %s", gid, e)

    return {
        "fetched": len(ids),
        "new": len(inserted),
        "skipped": len(already),
        "inserted_ids": inserted,
    }


def _fire_inbound(mail_log_id: str, parsed: Dict[str, Any]) -> None:
    """등록된 수신 콜백을 발화. 콜백 예외는 격리(적재 흐름 보호)."""
    log.info("[GMAIL-INBOX] 수신 적재 %s from=%s subj=%s",
             mail_log_id, parsed.get("from_email"), parsed.get("subject"))
    for handler in _INBOUND_HANDLERS:
        try:
            handler(mail_log_id, parsed)
        except Exception as e:  # noqa: BLE001
            log.warning("[GMAIL-INBOX] 수신 콜백 실패: %s", e)
