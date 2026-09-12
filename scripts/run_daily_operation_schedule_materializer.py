#!/usr/bin/env python3
"""Stage3 physical daily trigger.

WO-SAFE-DAILY-SCHEDULE-STAGE3-PHYSICAL-TRIGGER-001

Thin CLI: invoke the official orchestrator once and exit.
"""
from __future__ import annotations

import json
import sys

from services.time import now_kst


def main() -> int:
    started_at = now_kst().isoformat()
    try:
        from services.inspection_sets_svc.schedules import generate_schedules_all

        result = generate_schedules_all()
        finished_at = now_kst().isoformat()
        print(
            json.dumps(
                {
                    "started_at": started_at,
                    "finished_at": finished_at,
                    "status": (result or {}).get("status"),
                    "result": result,
                },
                ensure_ascii=False,
                default=str,
            )
        )
        if not isinstance(result, dict) or result.get("status") != "success":
            return 1
        return 0
    except Exception as exc:
        finished_at = now_kst().isoformat()
        print(
            json.dumps(
                {
                    "started_at": started_at,
                    "finished_at": finished_at,
                    "status": "error",
                    "error": str(exc),
                },
                ensure_ascii=False,
                default=str,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
