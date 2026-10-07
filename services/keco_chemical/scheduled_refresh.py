"""KECO Scheduled Refresh Entrypoint — Railway Cron / Scheduled Job.

Railway scheduled job에서 직접 실행하거나 collect.py --mode refresh로 호출.

사용:
  python -m services.keco_chemical.scheduled_refresh

동작:
  1. 환경변수 유효성 확인
  2. 중복 실행 lock 확인 (INITIAL_BULK or SCHEDULED_REFRESH active → skip)
  3. due targets (next_refresh_at <= now) bounded 처리
  4. 정상 종료 (exit 0)

로그:
  serviceKey / Supabase service_role 절대 출력 금지.
"""
from __future__ import annotations

import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("keco.scheduled_refresh")


def _require_env(name: str) -> str:
    val = (os.getenv(name) or "").strip()
    if not val:
        logger.error("Required environment variable missing: %s", name)
        sys.exit(1)
    return val


def _require_service_key() -> None:
    from services.keco_chemical.contract import SERVICE_KEY_ENV
    if not any((os.getenv(name) or "").strip() for name in SERVICE_KEY_ENV):
        logger.error(
            "Required environment variable missing: %s or legacy %s",
            SERVICE_KEY_ENV[0], SERVICE_KEY_ENV[1],
        )
        sys.exit(1)


def main() -> None:
    _require_service_key()
    _require_env("LEG_SUPABASE_URL")
    _require_env("LEG_SUPABASE_SERVICE_ROLE_KEY")

    from services.keco_chemical.client import KecoChemicalClient
    from services.keco_chemical.store import KecoReferenceStore
    from services.keco_chemical.sync import RequestBudget, refresh_due_targets

    client = KecoChemicalClient()
    store = KecoReferenceStore()
    budget = RequestBudget.from_env()

    logger.info("[SCHEDULED_REFRESH] Starting — budget=%d", budget.limit)

    result = refresh_due_targets(client, store, budget)

    logger.info(
        "[SCHEDULED_REFRESH] Done — status=%s processed=%d/%d requests=%d "
        "new=%d unchanged=%d changed=%d retry=%d failed=%d budget_used=%d",
        result.status,
        result.targets_processed, result.targets_selected,
        result.requests,
        result.new, result.unchanged, result.changed,
        result.retry, result.failed,
        result.budget_used,
    )


if __name__ == "__main__":
    main()
