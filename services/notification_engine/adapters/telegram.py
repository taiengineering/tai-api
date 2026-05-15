"""Telegram Delivery Adapter.

Phase 1 유일한 채널.
Fail-safe: 절대 서비스 영향 없음.
"""

import logging
import os
from typing import Tuple, Optional

logger = logging.getLogger("notification_engine.adapters.telegram")


def send(message: str) -> Tuple[bool, Optional[str]]:
    """Telegram Bot API 발송.

    Returns:
        (success: bool, error_message: str|None)
    """
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    if not bot_token or not chat_id:
        logger.warning("Telegram not configured")
        return False, "Telegram not configured (TELEGRAM_BOT_TOKEN/CHAT_ID missing)"

    try:
        import requests
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        resp = requests.post(url, json={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
        }, timeout=10)

        if resp.status_code == 200:
            logger.info("Telegram sent OK")
            return True, None
        else:
            err = f"Telegram {resp.status_code}: {resp.text[:200]}"
            logger.error(err)
            return False, err

    except Exception as e:
        err = str(e)[:200]
        logger.error("Telegram send exception: %s", err)
        return False, err
