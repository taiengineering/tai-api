# TAI Time Constitution v1

**CONST-TIME-001.** Canonical business timezone is `Asia/Seoul`.  
Cross-repo normative source of truth. Frontend repos hold adapters and guards only; they must not duplicate this document.

## Purpose

Block **new** time debt (UTC/GMT/naive/browser-tz) from entering TAI systems. Existing debt is observed as a ratchet baseline in PHASE 1. Existing debt is not rewritten here.

## Clauses

### C1 — Business Time = Asia/Seoul

All business-facing time uses `Asia/Seoul`:

- “today”, deadlines, expiry, midnight
- week / month boundaries
- schedules
- inspections, reports, alerts, statistics days

### C2 — Absolute Instant = timestamptz

Internal storage of an absolute instant is timezone-aware (`timestamptz`).  
Storage timezone is not the same thing as business timezone.

### C3 — Naive is forbidden (new)

- New `timestamp without time zone` DDL = 0
- New business-code naive `datetime` = 0

### C4 — API = +09:00 aware ISO-8601

Public API datetime strings are timezone-aware ISO-8601 with `+09:00`.  
Naive datetime strings are **INVALID**.

### C5 — Frontend = Asia/Seoul, OS/browser TZ independent

UI date/time display and “today” must not follow the operator’s browser timezone. Always `Asia/Seoul`.

### C6 — Scheduler = Asia/Seoul expression

Cron / schedule expressions are written in `Asia/Seoul`.  
Do not encode KST wall-clock by shifting GMT (example: do not write `18:27 GMT` to obtain `03:27 KST`).

### C7 — External = boundary adapter

External clocks and naive payloads enter through an explicit adapter: aware instant → TAI contract. Do not leak foreign timezone assumptions into business code.

### C8 — Enforcement

CI violation of the time contract **blocks merge**.

## Two-Phase Cutover

| Phase | Scope |
| --- | --- |
| **PHASE 1** | Enforcement foundation (this change): provider, adapters, scanners, baseline ratchet. No production datetime rewrite. |
| **PHASE 2** | Existing-debt liquidation, DB timezone, `pg_cron` KST. Not authorized in PHASE 1. |

PHASE 1 success criterion: **can new code introduce the same time debt after today?** → **NO**.  
Success is not “has every call already been converted to KST”.
