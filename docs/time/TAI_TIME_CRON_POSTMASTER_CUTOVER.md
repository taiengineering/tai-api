# TAI TIME — pg_cron postmaster timezone cutover

**EXECUTED = NO.** This document is an artifact only. Do not run `ALTER SYSTEM`, do not restart Postmaster, do not mutate TAI Supabase `vwlahtguyggrhvslabax`.

| Field | Value |
| --- | --- |
| Parameter | `cron.timezone` |
| From | `GMT` |
| To | `Asia/Seoul` |
| Context | postmaster |
| Restart required | YES |
| Managed Supabase mechanism | NOT EXECUTED |
| `ALTER SYSTEM` | forbidden (do not guess / do not run) |

After a future operator-approved restart, `pg_cron` interprets job schedules in `Asia/Seoul`. Schedule expressions in `docs/sql/20260831_tai_time_cron_kst_cutover.sql` are written as KST wall-clock (Constitution C6). Job `active` flags stay exact. This file does not change `cron.job` rows.
