"""Signed payment-launch capability (READ+VERIFY+RENDER).

WO-COMMON-TIER-PAYMENT-GATE-MODULARIZE-001 / B7-A1 OPTION C.
범용 launch token. tier pricing 판단 금지. DB mutation 금지.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import logging
import os
import time
from typing import Any, Mapping, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from services.payment_helpers import DEFAULT_CLOSE_URL, DEFAULT_RETURN_URL, load_template

log = logging.getLogger(__name__)

PURPOSE = "SAAS_TIER_UPGRADE"
TOKEN_VERSION = 1
DEFAULT_LAUNCH_URL = "https://taieng.co.kr/_api/payments/tier-upgrade/pay"
DEFAULT_TTL_SECONDS = 300
MIN_TTL_SECONDS = 60
MAX_TTL_SECONDS = 900
MIN_SECRET_BYTES = 32
MAX_TOKEN_CHARS = 8192
_IAT_FUTURE_SKEW_SECONDS = 5

PROVIDER_FIELDS = (
    "mid",
    "mKey",
    "oid",
    "price",
    "goodname",
    "buyername",
    "buyertel",
    "buyeremail",
    "timestamp",
    "signature",
    "verification",
    "use_chkfake",
    "returnUrl",
    "closeUrl",
    "charset",
    "gopaymethod",
)

_LAUNCH_FAIL_MESSAGE = (
    "결제를 시작할 수 없습니다. 다시 서비스 화면에서 결제를 시작해 주세요."
)

_SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Pragma": "no-cache",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": (
        "default-src 'none'; "
        "script-src https://stdpay.inicis.com 'unsafe-inline'; "
        "style-src 'unsafe-inline'; "
        "img-src data: https://stdpay.inicis.com; "
        "frame-src https://stdpay.inicis.com https://stgstdpay.inicis.com; "
        "form-action https://stdpay.inicis.com https://stgstdpay.inicis.com; "
        "connect-src https://stdpay.inicis.com https://stgstdpay.inicis.com; "
        "base-uri 'none'"
    ),
}


class PaymentLaunchError(Exception):
    """launch capability 오류. http_status 는 라우터가 번역한다."""

    def __init__(self, code: str, http_status: int, message: str = ""):
        self.code = code
        self.http_status = http_status
        self.message = message or _LAUNCH_FAIL_MESSAGE
        super().__init__(self.message)


class PaymentLaunchConfigError(PaymentLaunchError):
    def __init__(self, code: str = "LAUNCH_CONFIG"):
        super().__init__(code, 503)


class PaymentLaunchTokenError(PaymentLaunchError):
    def __init__(self, code: str = "TOKEN_INVALID"):
        super().__init__(code, 403)


class PaymentLaunchStateError(PaymentLaunchError):
    def __init__(self, code: str, http_status: int = 409):
        super().__init__(code, http_status)


def launch_security_headers() -> dict[str, str]:
    return dict(_SECURITY_HEADERS)


def get_payment_launch_url() -> str:
    url = (os.getenv("PAYMENT_LAUNCH_URL") or "").strip()
    return url or DEFAULT_LAUNCH_URL


def get_payment_launch_ttl() -> int:
    raw = (os.getenv("PAYMENT_LAUNCH_TTL_SECONDS") or "").strip() or str(DEFAULT_TTL_SECONDS)
    try:
        ttl = int(raw)
    except (TypeError, ValueError):
        ttl = DEFAULT_TTL_SECONDS
    if ttl < MIN_TTL_SECONDS:
        return MIN_TTL_SECONDS
    if ttl > MAX_TTL_SECONDS:
        return MAX_TTL_SECONDS
    return ttl


def _secret_bytes() -> bytes:
    raw = os.getenv("PAYMENT_LAUNCH_SECRET")
    if raw is None or raw == "":
        raise PaymentLaunchConfigError("LAUNCH_SECRET_MISSING")
    secret = raw.encode("utf-8")
    if len(secret) < MIN_SECRET_BYTES:
        raise PaymentLaunchConfigError("LAUNCH_SECRET_WEAK")
    return secret


def require_payment_launch_config() -> None:
    _secret_bytes()
    if not get_payment_launch_url():
        raise PaymentLaunchConfigError("LAUNCH_URL_MISSING")


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _provider_snapshot(provider: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in PROVIDER_FIELDS:
        if key not in provider:
            continue
        val = provider[key]
        out[key] = "" if val is None else val
    return out


def _require_provider_fields(provider: Mapping[str, Any]) -> None:
    if not isinstance(provider, dict) or not provider:
        raise PaymentLaunchTokenError("PROVIDER_MISSING")
    for key in PROVIDER_FIELDS:
        if key not in provider:
            raise PaymentLaunchTokenError("PROVIDER_FIELD_MISSING")


def build_provider_return_url(front_return_url: Optional[str] = None) -> str:
    """DEFAULT_RETURN_URL 권위에 front 힌트만 query 로 부착. 문자열 이어붙이기 금지."""
    if not front_return_url:
        return DEFAULT_RETURN_URL
    parts = urlparse(DEFAULT_RETURN_URL)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["front"] = front_return_url
    return urlunparse(
        (parts.scheme, parts.netloc, parts.path, parts.params, urlencode(query), parts.fragment)
    )


def create_payment_launch_token(
    *,
    payment_id: str,
    provider: Mapping[str, Any],
    front_return_url: Optional[str] = None,
    now: Optional[float] = None,
) -> str:
    require_payment_launch_config()
    if not payment_id:
        raise PaymentLaunchTokenError("PAYMENT_ID_MISSING")
    snap = _provider_snapshot(provider)
    _require_provider_fields(snap)
    iat = int(time.time() if now is None else now)
    envelope: dict[str, Any] = {
        "v": TOKEN_VERSION,
        "purpose": PURPOSE,
        "iat": iat,
        "exp": iat + get_payment_launch_ttl(),
        "payment_id": str(payment_id),
        "provider": snap,
    }
    if front_return_url:
        envelope["front_return_url"] = front_return_url
    encoded = _b64url_encode(_canonical_json(envelope).encode("utf-8"))
    mac = hmac.new(_secret_bytes(), encoded.encode("ascii"), hashlib.sha256).digest()
    token = encoded + "." + _b64url_encode(mac)
    if len(token) > MAX_TOKEN_CHARS:
        raise PaymentLaunchTokenError("TOKEN_OVERSIZED")
    return token


def verify_payment_launch_token(token: str, *, now: Optional[float] = None) -> dict[str, Any]:
    require_payment_launch_config()
    if not token or not isinstance(token, str):
        raise PaymentLaunchTokenError("TOKEN_MISSING")
    if len(token) > MAX_TOKEN_CHARS:
        raise PaymentLaunchTokenError("TOKEN_OVERSIZED")
    if token.count(".") != 1:
        raise PaymentLaunchTokenError("TOKEN_MALFORMED")
    encoded, mac_b64 = token.split(".", 1)
    if not encoded or not mac_b64:
        raise PaymentLaunchTokenError("TOKEN_MALFORMED")
    try:
        given_mac = _b64url_decode(mac_b64)
        expected_mac = hmac.new(_secret_bytes(), encoded.encode("ascii"), hashlib.sha256).digest()
    except Exception as e:  # noqa: BLE001
        raise PaymentLaunchTokenError("TOKEN_MALFORMED") from e
    if len(given_mac) != len(expected_mac) or not hmac.compare_digest(given_mac, expected_mac):
        raise PaymentLaunchTokenError("TOKEN_MAC")
    try:
        raw = _b64url_decode(encoded)
        envelope = json.loads(raw.decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        raise PaymentLaunchTokenError("TOKEN_PAYLOAD") from e
    if not isinstance(envelope, dict):
        raise PaymentLaunchTokenError("TOKEN_PAYLOAD")
    if envelope.get("v") != TOKEN_VERSION:
        raise PaymentLaunchTokenError("TOKEN_VERSION")
    if envelope.get("purpose") != PURPOSE:
        raise PaymentLaunchTokenError("TOKEN_PURPOSE")
    iat = envelope.get("iat")
    exp = envelope.get("exp")
    if not isinstance(iat, int) or iat <= 0:
        raise PaymentLaunchTokenError("TOKEN_IAT")
    if not isinstance(exp, int) or exp <= 0:
        raise PaymentLaunchTokenError("TOKEN_EXP")
    clock = time.time() if now is None else now
    if iat > clock + _IAT_FUTURE_SKEW_SECONDS:
        raise PaymentLaunchTokenError("TOKEN_IAT_FUTURE")
    if clock >= exp:
        raise PaymentLaunchTokenError("TOKEN_EXPIRED")
    if exp < iat:
        raise PaymentLaunchTokenError("TOKEN_TTL")
    payment_id = envelope.get("payment_id")
    if not payment_id:
        raise PaymentLaunchTokenError("PAYMENT_ID_MISSING")
    provider = envelope.get("provider")
    _require_provider_fields(provider if isinstance(provider, dict) else {})
    if not provider_callback_urls_safe(provider):
        raise PaymentLaunchTokenError("PROVIDER_URL")
    return envelope


def provider_callback_urls_safe(provider: Mapping[str, Any]) -> bool:
    return _callback_url_safe(provider.get("returnUrl"), DEFAULT_RETURN_URL) and _callback_url_safe(
        provider.get("closeUrl"), DEFAULT_CLOSE_URL
    )


def _callback_url_safe(url: Any, authority: str) -> bool:
    if not url or not isinstance(url, str):
        return False
    try:
        parts = urlparse(url)
        allowed = urlparse(authority)
    except Exception:  # noqa: BLE001
        return False
    if parts.scheme not in ("https", "http"):
        return False
    host = (parts.hostname or "").lower()
    allowed_host = (allowed.hostname or "").lower()
    if not host:
        return False
    if host == allowed_host:
        return True
    if host == "taieng.co.kr" or host.endswith(".taieng.co.kr"):
        return True
    return False


def attach_tier_upgrade_launch(
    prepared: Mapping[str, Any],
    *,
    front_return_url: Optional[str] = None,
    now: Optional[float] = None,
) -> dict[str, Any]:
    """prepare 응답에 launch 만 추가. prepare 본문(status/data/upgrade) 유지."""
    data = dict((prepared or {}).get("data") or {})
    payment_id = data.get("payment_id")
    if not payment_id:
        raise PaymentLaunchConfigError("PAYMENT_ID_MISSING")
    provider = _provider_snapshot(data)
    if front_return_url:
        provider["returnUrl"] = build_provider_return_url(front_return_url)
    token = create_payment_launch_token(
        payment_id=str(payment_id),
        provider=provider,
        front_return_url=front_return_url,
        now=now,
    )
    out = dict(prepared)
    out["launch"] = {
        "method": "POST",
        "url": get_payment_launch_url(),
        "token": token,
    }
    return out


def assert_launchable_payment(payment: Optional[Mapping[str, Any]], provider: Mapping[str, Any]) -> None:
    if not payment:
        raise PaymentLaunchStateError("PAYMENT_NOT_FOUND", 404)
    if (payment.get("status_code") or "").upper() != "PENDING":
        raise PaymentLaunchStateError("NOT_PENDING", 409)
    if (payment.get("payment_type") or "").upper() != "UPGRADE":
        raise PaymentLaunchStateError("NOT_UPGRADE", 409)
    if str(payment.get("inicis_order_id") or "") != str(provider.get("oid") or ""):
        raise PaymentLaunchStateError("OID_MISMATCH", 409)
    if str(payment.get("total_amount") if payment.get("total_amount") is not None else "") != str(
        provider.get("price") or ""
    ):
        raise PaymentLaunchStateError("PRICE_MISMATCH", 409)


def assert_launchable_transition(transition: Optional[Mapping[str, Any]], payment_id: str) -> None:
    if not transition:
        raise PaymentLaunchStateError("TRANSITION_MISSING", 409)
    if str(transition.get("payment_id") or "") != str(payment_id):
        raise PaymentLaunchStateError("TRANSITION_MISMATCH", 409)
    if (transition.get("status") or "").upper() != "PREPARED":
        raise PaymentLaunchStateError("TRANSITION_NOT_PREPARED", 409)


def render_launch_success(provider: Mapping[str, Any]) -> str:
    tpl = load_template("tier_upgrade_pay.html")
    for key in PROVIDER_FIELDS:
        raw = provider.get(key, "")
        text = "" if raw is None else str(raw)
        tpl = tpl.replace(f"__{key}__", html.escape(text, quote=True))
    return tpl


def render_launch_failure() -> str:
    msg = html.escape(_LAUNCH_FAIL_MESSAGE, quote=True)
    return (
        "<!DOCTYPE html><html lang=\"ko\"><head><meta charset=\"UTF-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">"
        f"<title>결제</title></head><body><p>{msg}</p></body></html>"
    )
