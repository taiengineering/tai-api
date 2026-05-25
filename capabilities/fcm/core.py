"""FCM Capability Core — v1.0.0

FCM push dispatch capability. DB 모름. firebase_admin만 사용.

사용:
  from capabilities.fcm.core import send_push
"""
import logging
from typing import Optional

log = logging.getLogger(__name__)


def send_push(fcm_token: str, title: str, body: str, data: Optional[dict] = None) -> str:
    """FCM push 발송. DB/Framework 모름. firebase_admin만 사용."""
    from utils.fcm_utils import send_push as _firebase_send
    return _firebase_send(fcm_token=fcm_token, title=title, body=body, data=data)
