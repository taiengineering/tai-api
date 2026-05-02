"""Slack 요청 서명 검증 (Interactions / Events 공통)."""

from __future__ import annotations

import hashlib
import hmac
import time


def verify_slack_signing_secret(
    signing_secret: str,
    timestamp_header: str | None,
    signature_header: str | None,
    raw_body: bytes,
    *,
    max_age_seconds: int = 300,
) -> bool:
    """
    X-Slack-Signature (v0=...) 및 X-Slack-Request-Timestamp 검증.
    """
    if not signing_secret or not timestamp_header or not signature_header:
        return False
    try:
        ts = int(timestamp_header)
    except ValueError:
        return False
    if abs(time.time() - ts) > max_age_seconds:
        return False
    try:
        body_text = raw_body.decode("utf-8")
    except UnicodeDecodeError:
        return False
    sig_basestring = f"v0:{timestamp_header}:{body_text}"
    digest = hmac.new(
        signing_secret.encode("utf-8"),
        sig_basestring.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    expected = f"v0={digest}"
    return hmac.compare_digest(expected, signature_header)
