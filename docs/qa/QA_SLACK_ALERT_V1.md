---
title: QA Slack Alert V1
version: 1.1.0
work_order: WO-QA-CONTROL-PHASE2C-001 / WO-QA-LIVE-HOURLY-OPS-001
status: IMPLEMENTED
---

# QA Slack Alert V1

## Architecture

```
routers/internal_qa.py          ← orchestrator (async)
    │
    ├─► services/qa_control_svc.py   ← transition calc, notification payload assembly
    │         apply_results()
    │         returns: { notifications: [...], run_notification: {...} | None }
    │
    ├─► services/qa_notify_svc.py    ← formatter only (no HTTP, no credentials)
    │         build_qa_slack_payload(notif, *, is_run=False)
    │         returns: { event_type, severity, title, detail, blocks }
    │
    └─► services/slack_dispatcher.py ← Slack client; QA events routed to #auto-qa (CHANNEL_QA)
              send_slack(**payload)
```

No new Slack client. `qa_notify_svc` holds zero credentials and makes zero HTTP calls.

## Status Transition Contract

`_latest_run_effective_status(by_run)` finds the run with the latest `checked_at` and derives:

| Final attempt status                | Effective status |
|-------------------------------------|-----------------|
| FAIL                                | FAIL             |
| PASS + any earlier attempt = FAIL   | FLAKY            |
| PASS only                           | PASS             |
| BLOCKED                             | BLOCKED          |
| SKIPPED                             | SKIPPED          |
| No results at all                   | NEVER_RUN        |

"Final attempt" = the attempt with the highest `attempt` number in that run.
Derived by `derive_effective_status` in `qa_control_svc.py`.

## Event Types

| Event                 | Trigger (prev → new)                                              | Severity |
|-----------------------|-------------------------------------------------------------------|----------|
| `QA_FAIL_DETECTED`    | NEVER_RUN/PASS/SKIPPED/BLOCKED/FLAKY → FAIL                       | HIGH     |
| `QA_BLOCKED_DETECTED` | NEVER_RUN/PASS/SKIPPED/FAIL/FLAKY → BLOCKED                       | HIGH     |
| `QA_FLAKY_DETECTED`   | NEVER_RUN/PASS/SKIPPED/FAIL/BLOCKED → FLAKY                       | WARNING  |
| `QA_RECOVERED`        | FAIL/BLOCKED/FLAKY → PASS                                         | INFO     |
| `QA_RUN_ERROR`        | run_status=ERROR transition (QUEUED/RUNNING → ERROR)              | HIGH     |

No notification is emitted for:
- FAIL → FAIL
- BLOCKED → BLOCKED
- PASS → PASS
- FLAKY → FLAKY
- Any → SKIPPED

## Channel Routing (updated: WO-QA-LIVE-HOURLY-OPS-001)

All five QA event types route to `#auto-qa` via `EVENT_TYPE_CHANNEL` in `slack_dispatcher.py`,
**regardless of severity**. This takes priority over severity-based routing.

| Event                 | Channel    | Env var       | Channel ID (ops) |
|-----------------------|-----------|---------------|------------------|
| `QA_FAIL_DETECTED`    | `#auto-qa` | `SLACK_CH_QA` | `C0C6EV30CBG`    |
| `QA_BLOCKED_DETECTED` | `#auto-qa` | `SLACK_CH_QA` | `C0C6EV30CBG`    |
| `QA_FLAKY_DETECTED`   | `#auto-qa` | `SLACK_CH_QA` | `C0C6EV30CBG`    |
| `QA_RECOVERED`        | `#auto-qa` | `SLACK_CH_QA` | `C0C6EV30CBG`    |
| `QA_RUN_ERROR`        | `#auto-qa` | `SLACK_CH_QA` | `C0C6EV30CBG`    |

Scheduler dispatch failure also sends `QA_RUN_ERROR` → `#auto-qa` directly from
`qa_scheduler_svc.scheduler_tick()` (no callback path). Slack failure is absorbed; scheduler result is unaffected.

The severity field is preserved in the Slack message text for readability but does not affect routing.

## Replay Suppression

Notification is suppressed when `prev_eff == new_eff`:

1. **Exact replay**: identical payload already inserted (idempotency skip) → `to_insert` is empty → no history query → no notification.
2. **Stale callback**: incoming result belongs to an older run whose `checked_at` is earlier than a newer run already in DB → `_latest_run_effective_status` returns the newer run's status both before and after → same prev/new → no notification.

## Run Error Notification

`run_notification` is populated when `new_status == "ERROR"` and the run is not already in a final state. It carries `event_type = "QA_RUN_ERROR"` and is dispatched separately after the per-item `notifications` loop.

`is_run=True` is passed to `build_qa_slack_payload` → item-specific fields (site_code, scenario_id, name, status transition) are omitted from the Slack block.

## Message Contract

`build_qa_slack_payload` returns:

```python
{
    "event_type": str,   # e.g. "QA_FAIL_DETECTED"
    "severity":   str,   # "HIGH" | "WARNING" | "INFO"
    "title":      str,   # Korean title string
    "detail":     "",    # always empty (fields are in blocks)
    "blocks":     [{"type": "section", "text": {"type": "mrkdwn", "text": ...}}],
}
```

Block text includes (per-item): severity header, site_code, scenario_id, name, status transition, trigger_type, run_id, github_run_id, head_sha (first 8 chars), duration_ms, error_summary.

## Security / Redaction

Error details are inherited from `qa_run_results.error_summary` which is already redacted at the ingestion layer (`routers/internal_qa.py` truncation/redaction). `qa_notify_svc` passes `error_summary` verbatim from the notification dict — no additional processing.

## Slack Fail-Safe

```python
try:
    sent = await send_slack(**payload)
except Exception as exc:
    log.warning("[qa_notify] Slack exception: %s", exc)
```

Slack failure never raises to the caller. The callback always returns HTTP 200 with `data` intact. `slack.failed` counter in the response reflects send failures.

## Admin Link

All five QA event types resolve to `/auto-qa-dashboard` via `EVENT_TYPE_ADMIN_PATH` in `slack_dispatcher.py`.

`qa_notify_svc` provides a section-only `blocks` list. `slack_dispatcher` detects no `actions` block in QA payloads and appends the "어드민에서 보기" button pointing to `https://admin.taieng.co.kr/auto-qa-dashboard`. Events that already include an `actions` block in their provided `blocks` (e.g., INQUIRY/WISH) are not modified — no duplicate button.

## Known Limitation — No Persistent Outbox

Slack dispatch is fire-and-send with no retry queue. A transient Slack API failure causes a silent drop (warning log only). A persistent outbox / retry mechanism is deferred to Phase 2-D.

## Phase 2-D Handoff

- Persistent Slack outbox with retry
- Admin QA Dashboard UI path update (if `/auto-qa-dashboard` changes)
- Per-item mute / suppression rules
- QA_RUN_COMPLETED event (run-level success notification)
