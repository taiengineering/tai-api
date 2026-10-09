"""services/law_update_slack.py — OBJ-LAU-05B 60% Slack notifications

LAW_REVISION_COLLECTED event via direct Slack API call (httpx).
Test channel only — env var LAW_UPDATE_SLACK_TEST_CHANNEL.
Idempotency guard: slack_collected_notified_at checked before send.
Slack failure does not raise — caller's DB state is preserved.

send_slack_sync() is NOT used here: it returns None (fire-and-forget).
_post_slack_direct() calls Slack API synchronously and returns the response body.
"""
from __future__ import annotations

import logging
import os
from typing import Optional, Tuple

import httpx

log = logging.getLogger("law_update_slack")


def _test_channel() -> Optional[str]:
    ch = os.environ.get("LAW_UPDATE_SLACK_TEST_CHANNEL", "").strip()
    return ch or None


def _slack_token() -> Optional[str]:
    token = (
        os.environ.get("SLACK_BOT_TOKEN1", "")
        or os.environ.get("SLACK_BOT_TOKEN", "")
    ).strip()
    return token or None


def _post_slack_direct(channel_id: str, token: str, text: str) -> dict:
    """Call Slack chat.postMessage synchronously. Returns response body dict.

    Always returns a dict — {"ok": bool, ...}. Never raises.
    On HTTP error or exception returns {"ok": False, "error": "..."}.
    """
    try:
        resp = httpx.post(
            "https://slack.com/api/chat.postMessage",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            json={"channel": channel_id, "text": text, "unfurl_links": False},
            timeout=10.0,
        )
        if resp.status_code == 200:
            return resp.json()
        return {"ok": False, "error": f"http_{resp.status_code}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def notify_collected(
    case_id: str,
    case_row: dict,
    leg_supabase,
) -> Tuple[bool, str]:
    """Send LAW_REVISION_COLLECTED Slack notification for a COLLECTED case.

    Returns (sent: bool, detail: str).
    Returns (False, reason) if already notified, wrong status, no channel, no token, or error.
    Never raises — Slack failure does not affect stored data.
    """
    if case_row.get("slack_collected_notified_at"):
        return False, "ALREADY_NOTIFIED"

    if case_row.get("application_status") != "COLLECTED":
        return False, f"NOT_COLLECTED: status={case_row.get('application_status')!r}"

    ch = _test_channel()
    if not ch:
        return False, "NO_CHANNEL_CONFIGURED"

    token = _slack_token()
    if not token:
        return False, "NO_SLACK_TOKEN"

    law_name = case_row.get("law_name", "")
    new_mst = case_row.get("new_mst", "")
    announcement_date = case_row.get("announcement_date", "")
    enforcement_date = case_row.get("enforcement_date", "")
    new_version_id = case_row.get("new_version_id", "")

    text = (
        f"[법령 원문 수집 완료] {law_name}\n"
        f"MST: {new_mst}\n"
        f"공포일: {announcement_date or '-'} / 시행일: {enforcement_date or '-'}\n"
        f"version_id: {new_version_id or '-'}\n"
        f"case_id: {case_id}"
    )

    resp = _post_slack_direct(ch, token, text)
    if not resp.get("ok"):
        error_msg = resp.get("error", "unknown")
        log.warning("Slack send failed for case %s: %s", case_id, error_msg)
        return False, f"SLACK_ERROR: {error_msg}"

    ts = resp.get("ts") or None
    try:
        from datetime import datetime, timezone
        now_iso = datetime.now(timezone.utc).isoformat()
        result = (
            leg_supabase.table("law_update_case")
            .update({
                "slack_collected_notified_at": now_iso,
                "slack_collected_message_ts": ts,
            })
            .eq("case_id", case_id)
            .is_("slack_collected_notified_at", "null")
            .execute()
        )
        # Supabase REST returns updated rows in result.data.
        # Empty list means conditional WHERE IS NULL matched 0 rows — concurrent send raced us.
        # The Slack message was already sent; log the race but do not overwrite the winner's record.
        if hasattr(result, "data") and result.data is not None and len(result.data) == 0:
            log.warning("Slack notify race for case %s: conditional UPDATE matched 0 rows", case_id)
            return True, "SENT_RACE_DUPLICATE"
    except Exception as db_exc:
        log.warning("Slack DB update failed for case %s: %s", case_id, db_exc)
        return True, f"SENT_BUT_DB_UPDATE_FAILED: {db_exc}"

    return True, "SENT"
