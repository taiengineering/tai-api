"""INDUSTRIAL 상시근로자 수 vs 근로복지공단 상시인원 검증.

user_worker_count overwrite 금지. client 실패는 API_ERROR, 진단 중단 금지.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from clients.comwel_worker_client import (
    SOURCE,
    ComwelApiError,
    get_worker_reference,
    normalize_business_number,
)
from utils.logger import get_logger

log = get_logger(__name__)

STATUS_PASS = "PASS"
STATUS_RECHECK_REQUIRED = "RECHECK_REQUIRED"
STATUS_NO_DATA = "NO_DATA"
STATUS_API_ERROR = "API_ERROR"

THRESHOLD = 0.10

MSG_RECHECK = (
    "입력한 상시근로자 수가 근로복지공단 상시인원과 10% 이상 차이가 있습니다. "
    "다시 확인해 주세요."
)
MSG_RECHECK_BLANKET = (
    MSG_RECHECK + "\n일괄적용 사업장 기준일 수 있어 참고용입니다."
)
MSG_NO_DATA = "근로복지공단 상시인원을 확인할 수 없어 입력값으로 진단을 진행합니다."
MSG_API_ERROR = "근로복지공단 조회에 실패했습니다. 입력값으로 진단을 진행합니다."


def _to_int(val: Any) -> Optional[int]:
    if val is None or val == "":
        return None
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return None


def _payload(
    *,
    user: Optional[int],
    ref_count: Optional[int],
    difference: Optional[int],
    difference_rate: Optional[float],
    status: str,
    message: Optional[str],
    source: Optional[str],
    reference_date: Optional[str],
    is_blanket: Optional[bool],
) -> Dict[str, Any]:
    return {
        "user_worker_count": user,
        "external_reference_count": ref_count,
        "difference": difference,
        "difference_rate": difference_rate,
        "status": status,
        "message": message,
        "source": source,
        "reference_date": reference_date,
        "is_blanket": is_blanket,
    }


def compare(user_worker_count: Any, ref: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    user = _to_int(user_worker_count)
    if not isinstance(ref, dict):
        return _payload(
            user=user, ref_count=None, difference=None, difference_rate=None,
            status=STATUS_NO_DATA, message=MSG_NO_DATA, source=None,
            reference_date=None, is_blanket=None,
        )
    ref_count = _to_int(ref.get("external_reference_count"))
    if ref_count is None or ref_count <= 0:
        return _payload(
            user=user, ref_count=ref_count, difference=None, difference_rate=None,
            status=STATUS_NO_DATA, message=MSG_NO_DATA,
            source=ref.get("source") or SOURCE,
            reference_date=ref.get("reference_date"),
            is_blanket=bool(ref.get("is_blanket")) if ref.get("is_blanket") is not None else None,
        )
    user_for_diff = user if user is not None else 0
    diff = user_for_diff - ref_count
    rate = abs(diff) / float(ref_count)
    is_blanket = bool(ref.get("is_blanket"))
    if rate < THRESHOLD:
        status, message = STATUS_PASS, None
    else:
        status = STATUS_RECHECK_REQUIRED
        message = MSG_RECHECK_BLANKET if is_blanket else MSG_RECHECK
    return _payload(
        user=user, ref_count=ref_count, difference=diff, difference_rate=rate,
        status=status, message=message, source=ref.get("source") or SOURCE,
        reference_date=ref.get("reference_date"), is_blanket=is_blanket,
    )


def api_error_payload(user_worker_count: Any) -> Dict[str, Any]:
    return _payload(
        user=_to_int(user_worker_count), ref_count=None, difference=None,
        difference_rate=None, status=STATUS_API_ERROR, message=MSG_API_ERROR,
        source=SOURCE, reference_date=None, is_blanket=None,
    )


def lookup_company_business_number(supabase, body, current_user) -> Optional[str]:
    cid = (getattr(body, "company_id", None) or "").strip() or None
    if not cid and isinstance(current_user, dict):
        cid = (current_user.get("company_id") or "").strip() or None
    if not cid:
        return None
    try:
        res = (
            supabase.table("companies")
            .select("business_number")
            .eq("id", cid)
            .limit(1)
            .execute()
        )
    except Exception as e:
        log.warning("[IND-WORKER] companies.business_number lookup failed: %s", e)
        return None
    if not res.data:
        return None
    return normalize_business_number(res.data[0].get("business_number"))


def build_worker_validation(
    supabase,
    body,
    current_user,
    user_worker_count: Any,
    fetch_ref: Callable[..., Optional[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """진단 중단 없이 worker_validation dict 반환. user 값 불변."""
    user = _to_int(user_worker_count)
    bn = lookup_company_business_number(supabase, body, current_user)
    if not bn:
        return compare(user, None)
    fetch = fetch_ref or get_worker_reference
    try:
        ref = fetch(bn, boheom_fg=1, timeout=5)
    except ComwelApiError as e:
        log.warning("[IND-WORKER] ComwelApiError (continue diagnosis): %s", e)
        return api_error_payload(user)
    except Exception as e:
        log.warning("[IND-WORKER] unexpected client error (continue diagnosis): %s", e)
        return api_error_payload(user)
    return compare(user, ref)
