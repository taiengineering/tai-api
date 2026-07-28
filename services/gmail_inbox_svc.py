"""Gmail 수신 폴링 서비스 (WO-8B).

Goal: G-ms4je4z3-33eada
- Gmail 받은편지함 → mail_logs(direction=inbound) 적재.
- 중복 방지: resend_id(=Gmail message id) 부분 UNIQUE 인덱스 + 선조회.
- 신규만 적재: 이미 저장된 gmail id는 건너뜀.
- 자동화 훅 자리 예약(on_inbound): WO-12 자동화엔진에서 트리거로 사용.
- Gmail 미설정·미설치 시 GmailError(501) → 안전.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from db.supabase_client import get_supabase
from services import gmail_channel

log = logging.getLogger(__name__)


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
        # UNIQUE 위반(이미 존재) 등
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
                _on_inbound(new_id, parsed)  # 자동화 훅
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


def _on_inbound(mail_log_id: str, parsed: Dict[str, Any]) -> None:
    """수신 메일 자동화 훅 (WO-12 예약).

    현재는 no-op 로그. WO-12 자동화엔진 도입 시
    event('mail.inbound', {...}) 발화 지점.
    """
    log.info("[GMAIL-INBOX] 수신 적재 %s from=%s subj=%s",
             mail_log_id, parsed.get("from_email"), parsed.get("subject"))
    # TODO(WO-12): automation_svc.fire("mail.inbound", {"mail_log_id": mail_log_id, ...})
