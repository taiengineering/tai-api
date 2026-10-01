"""QA Slack notification formatter — WO-QA-CONTROL-PHASE2C-001.

Formatter only. No HTTP clients, no credentials, no Slack API calls.
Status transition events are computed by qa_control_svc.apply_results.
Actual dispatch: routers/internal_qa.py → slack_dispatcher.send_slack.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

QA_FAIL_DETECTED    = "QA_FAIL_DETECTED"
QA_BLOCKED_DETECTED = "QA_BLOCKED_DETECTED"
QA_FLAKY_DETECTED   = "QA_FLAKY_DETECTED"
QA_RECOVERED        = "QA_RECOVERED"
QA_RUN_ERROR        = "QA_RUN_ERROR"

EVENT_SEVERITY: Dict[str, str] = {
    QA_FAIL_DETECTED:    "HIGH",
    QA_BLOCKED_DETECTED: "HIGH",
    QA_FLAKY_DETECTED:   "WARNING",
    QA_RECOVERED:        "INFO",
    QA_RUN_ERROR:        "HIGH",
}

_EVENT_TITLE: Dict[str, str] = {
    QA_FAIL_DETECTED:    "QA 이상 감지",
    QA_BLOCKED_DETECTED: "QA BLOCKED 감지",
    QA_FLAKY_DETECTED:   "QA FLAKY 감지",
    QA_RECOVERED:        "QA 정상 복구",
    QA_RUN_ERROR:        "QA 실행 오류",
}

_SEVERITY_EMOJI: Dict[str, str] = {
    "CRITICAL": "🔴",
    "HIGH":     "🔴",
    "WARNING":  "🟡",
    "INFO":     "✅",
}


def _blocks_text(notif: Dict[str, Any], *, is_run: bool = False) -> str:
    event_type = notif["event_type"]
    severity   = notif.get("severity", EVENT_SEVERITY.get(event_type, "HIGH"))
    title      = _EVENT_TITLE.get(event_type, event_type)
    emoji      = _SEVERITY_EMOJI.get(severity, "⚪")
    header     = f"{emoji} [{severity}] {title}"
    lines: List[str] = [f"*{header}*"]

    if not is_run:
        if notif.get("site_code"):
            lines.append(f"사이트\t\t{notif['site_code']}")
        if notif.get("scenario_id"):
            lines.append(f"QA ID\t\t{notif['scenario_id']}")
        if notif.get("name"):
            lines.append(f"항목\t\t{notif['name']}")
        lines.append(f"상태\t\t{notif.get('previous_status', '')} → {notif.get('new_status', '')}")

    if notif.get("trigger_type"):
        lines.append(f"Trigger\t\t{notif['trigger_type']}")
    if notif.get("run_id"):
        lines.append(f"Run ID\t\t{notif['run_id']}")
    if notif.get("github_run_id"):
        lines.append(f"GitHub Run\t{notif['github_run_id']}")
    if notif.get("head_sha"):
        lines.append(f"HEAD\t\t{notif['head_sha'][:8]}")
    if not is_run and notif.get("duration_ms") is not None:
        lines.append(f"소요시간\t\t{notif['duration_ms'] / 1000:.1f}s")
    if notif.get("error_summary"):
        lines.append(f"\n오류\n{notif['error_summary']}")

    return "\n".join(lines)


def build_qa_slack_payload(
    notif: Dict[str, Any],
    *,
    is_run: bool = False,
) -> Dict[str, Any]:
    """Build kwargs dict for slack_dispatcher.send_slack (no Slack calls here)."""
    event_type = notif["event_type"]
    severity   = notif.get("severity", EVENT_SEVERITY.get(event_type, "HIGH"))
    title      = _EVENT_TITLE.get(event_type, event_type)
    text       = _blocks_text(notif, is_run=is_run)
    blocks     = [{"type": "section", "text": {"type": "mrkdwn", "text": text}}]
    return {
        "event_type": event_type,
        "severity":   severity,
        "title":      title,
        "detail":     "",
        "blocks":     blocks,
    }
