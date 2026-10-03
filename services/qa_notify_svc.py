"""QA Slack notification formatter — WO-QA-CONTROL-PHASE2C-001 / WO-QA-SLACK-DIAGNOSTIC-CONTEXT-001.

Formatter only. No HTTP clients, no credentials, no Slack API calls.
Status transition events are computed by qa_control_svc.apply_results.
Actual dispatch: routers/internal_qa.py → slack_dispatcher.send_slack.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.qa_control_svc import _SERVICE_LABELS, _AREA_LABELS, _QA_TYPE_LABELS

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
    QA_RUN_ERROR:        "QA 실행 시스템 오류",
}

_SEVERITY_EMOJI: Dict[str, str] = {
    "CRITICAL": "🔴",
    "HIGH":     "🔴",
    "WARNING":  "🟡",
    "INFO":     "✅",
}

_ALERT_EVENTS = frozenset({QA_FAIL_DETECTED, QA_BLOCKED_DETECTED, QA_FLAKY_DETECTED})


def _blocks_text(notif: Dict[str, Any], *, is_run: bool = False) -> str:
    event_type = notif["event_type"]
    severity   = notif.get("severity", EVENT_SEVERITY.get(event_type, "HIGH"))
    title      = _EVENT_TITLE.get(event_type, event_type)
    emoji      = _SEVERITY_EMOJI.get(severity, "⚪")
    lines: List[str] = [f"*{emoji} [{severity}] {title}*"]

    if is_run:
        # QA 인프라 실패 — item context 없음
        lines.append("")
        lines.append("구간\t\tScheduler → GitHub Actions")
        if notif.get("trigger_type"):
            lines.append(f"Trigger\t\t{notif['trigger_type']}")
        if notif.get("run_id"):
            lines.append(f"Run ID\t\t{notif['run_id']}")
        if notif.get("error_summary"):
            lines.append(f"\n오류\n{notif['error_summary']}")
        return "\n".join(lines)

    # ── 1. 위치 ───────────────────────────────────────────────────────────
    service_code  = notif.get("service_code") or ""
    area_code     = notif.get("area_code") or ""
    site_code     = notif.get("site_code") or ""
    service_label = _SERVICE_LABELS.get(service_code, service_code)
    area_label    = _AREA_LABELS.get(area_code, area_code)

    if service_label or area_label or site_code:
        lines.append("")
        if service_label and area_label:
            lines.append(f"위치\t\t{service_label} > {area_label}")
        elif service_label:
            lines.append(f"위치\t\t{service_label}")
        if site_code:
            lines.append(f"실행 Host\t{site_code}")

    # ── 2. 어떤 테스트 ────────────────────────────────────────────────────
    scenario_id   = notif.get("scenario_id") or ""
    name          = notif.get("name") or ""
    qa_type       = notif.get("qa_type") or ""
    qa_type_label = _QA_TYPE_LABELS.get(qa_type, qa_type)

    if scenario_id or name or qa_type_label:
        lines.append("")
        if scenario_id:
            lines.append(f"QA ID\t\t{scenario_id}")
        if name:
            lines.append(f"테스트\t\t{name}")
        if qa_type_label:
            lines.append(f"종류\t\t{qa_type_label}")

    # ── 3. 검증 대상 / 기대 결과 ──────────────────────────────────────────
    description      = notif.get("description") or ""
    expected_summary = notif.get("expected_summary") or ""
    if description or expected_summary:
        lines.append("")
        if description:
            lines.append(f"검증 대상\n{description}")
        if expected_summary:
            lines.append(f"\n기대 결과\n{expected_summary}")

    # ── 4. 실제 오류 (FAIL / BLOCKED / FLAKY) ────────────────────────────
    if event_type in _ALERT_EVENTS:
        error_summary = notif.get("error_summary") or ""
        if error_summary:
            lines.append(f"\n실제 오류\n{error_summary}")
            if notif.get("http_status"):
                lines.append(f"HTTP\t\t{notif['http_status']}")
            if notif.get("error_code"):
                lines.append(f"Error Code\t{notif['error_code']}")

    # ── 5. 상태 및 실행 증거 ──────────────────────────────────────────────
    lines.append("")
    lines.append(f"상태\t\t{notif.get('previous_status', '')} → {notif.get('new_status', '')}")
    if notif.get("duration_ms") is not None:
        lines.append(f"소요시간\t\t{notif['duration_ms'] / 1000:.1f}s")
    if notif.get("trigger_type"):
        lines.append(f"Trigger\t\t{notif['trigger_type']}")
    if notif.get("run_id"):
        lines.append(f"Run ID\t\t{notif['run_id']}")
    if notif.get("github_run_id"):
        lines.append(f"GitHub Run\t{notif['github_run_id']}")
    if notif.get("head_sha"):
        lines.append(f"HEAD\t\t{notif['head_sha'][:8]}")

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
