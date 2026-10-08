"""services/law_update_slack.py — OBJ-LAU-05B 60% Slack notifications

LAW_REVISION_COLLECTED event via send_slack_sync.
Test channel only — env var LAW_UPDATE_SLACK_TEST_CHANNEL.
Idempotency guard: slack_collected_notified_at checked before send.
Slack failure does not raise — caller's DB state is preserved.
"""
from __future__ import annotations

import logging
import os
from typing import Optional, Tuple

log = logging.getLogger("law_update_slack")


def _test_channel() -> Optional[str]:
    ch = os.environ.get("LAW_UPDATE_SLACK_TEST_CHANNEL", "").strip()
    return ch or None


def notify_collected(
    case_id: str,
    case_row: dict,
    leg_supabase,
) -> Tuple[bool, str]:
    """Send LAW_REVISION_COLLECTED Slack notification for a COLLECTED case.

    Returns (sent: bool, detail: str).
    Returns (False, reason) if already notified, wrong status, no channel, or error.
    Never raises — Slack failure does not affect stored data.
    """
    if case_row.get("slack_collected_notified_at"):
        return False, "ALREADY_NOTIFIED"

    if case_row.get("application_status") != "COLLECTED":
        return False, f"NOT_COLLECTED: status={case_row.get('application_status')!r}"

    ch = _test_channel()
    if not ch:
        return False, "NO_CHANNEL_CONFIGURED"

    law_name = case_row.get("law_name", "")
    new_mst = case_row.get("new_mst", "")
    announcement_date = case_row.get("announcement_date", "")
    enforcement_date = case_row.get("enforcement_date", "")
    new_version_id = case_row.get("new_version_id", "")

    title = f"[법령 원문 수집 완료] {law_name}"
    detail_text = (
        f"MST: {new_mst}\n"
        f"공포일: {announcement_date or '-'} / 시행일: {enforcement_date or '-'}\n"
        f"version_id: {new_version_id or '-'}\n"
        f"case_id: {case_id}"
    )

    resp: Optional[dict] = None
    try:
        from services.slack_dispatcher import send_slack_sync
        resp = send_slack_sync(
            event_type="LAW_REVISION_COLLECTED",
            severity="INFO",
            title=title,
            detail=detail_text,
            channel_override=ch,
        )
        if not resp or not resp.get("ok"):
            error_msg = (resp or {}).get("error", "unknown")
            log.warning("Slack send failed for case %s: %s", case_id, error_msg)
            return False, f"SLACK_ERROR: {error_msg}"
    except Exception as exc:
        log.warning("Slack send exception for case %s: %s", case_id, exc)
        return False, f"SLACK_EXCEPTION: {exc}"

    try:
        from datetime import datetime, timezone
        now_iso = datetime.now(timezone.utc).isoformat()
        ts = (resp or {}).get("ts") or None
        leg_supabase.table("law_update_case").update({
            "slack_collected_notified_at": now_iso,
            "slack_collected_message_ts": ts,
        }).eq("case_id", case_id).execute()
    except Exception as db_exc:
        log.warning("Slack DB update failed for case %s: %s", case_id, db_exc)
        return True, f"SENT_BUT_DB_UPDATE_FAILED: {db_exc}"

    return True, "SENT"
