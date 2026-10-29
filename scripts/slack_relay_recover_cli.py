"""Slack Relay 복구 Worker 수동 실행 CLI — WO-TAI-SLACK-BOT-UNIFIED-001-R3.

COR-F01: 외부 HTTP 경로 대신 격리된 CLI 진입점으로 제공.
--run 플래그 없이 실행하면 도움말을 출력하고 종료.

사용법:
    python -m scripts.slack_relay_recover_cli --run  # 권장 (패키지 루트에서 실행)
    python scripts/slack_relay_recover_cli.py --run  # 직접 실행 (PYTHONPATH 설정 필요)
"""
from __future__ import annotations

import sys


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(
        description="Slack Relay PENDING/RETRY 행 수동 복구 Worker"
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="복구를 실행합니다. 이 플래그 없이는 동작하지 않습니다.",
    )
    args = parser.parse_args(argv)

    if not args.run:
        parser.print_help(sys.stderr)
        return 1

    from services.slack_relay_svc import run_relay_recovery_once
    import asyncio

    processed = asyncio.run(run_relay_recovery_once())
    print(f"[RELAY] 복구 완료: {processed}건 처리됨")
    return 0


if __name__ == "__main__":
    sys.exit(main())
