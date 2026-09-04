"""CONSTRUCTION contract_amount validator + SAME_SITE price_change_log history.

50억 = 확정 운영경계. user 금액 overwrite 금지.
EXTERNAL_PROVIDER = NOT_WIRED — core 는 evidence 를 주입받아 판정한다.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from utils.logger import get_logger

log = get_logger(__name__)

THRESHOLD_EOK = 50.0
TABLE_NAME = "construction_sites"
FIELD_NAME = "contract_amount"

STATUS_PASS = "PASS"
STATUS_CROSS_50_MISMATCH = "CROSS_50_MISMATCH"
STATUS_DOWNWARD_RECHECK = "DOWNWARD_RECHECK"
STATUS_UNVERIFIED = "UNVERIFIED"

MSG_UNVERIFIED = "도급계약서상 총 도급금액을 확인했습니다."
MSG_DOWNWARD_RECHECK = (
    "이전에 확인된 동일 현장의 공사금액보다 낮으며 50억원 기준 구간이 변경되었습니다.\n"
    "도급계약서의 총 도급금액을 다시 확인해 주세요."
)
MSG_CROSS_50_MISMATCH = (
    "확인 가능한 공식 계약정보와 입력한 공사금액의 이용요금 구간이 다릅니다.\n"
    "총 도급금액을 다시 확인해 주세요."
)


def to_eok(val: Any) -> Optional[float]:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _band(eok: float) -> str:
    return "PREMIUM" if eok >= THRESHOLD_EOK else "STANDARD"


def amounts_equal(old: Any, new: Any) -> bool:
    a, b = to_eok(old), to_eok(new)
    if a is not None and b is not None:
        return a == b
    return str(old) == str(new)


def amount_to_text(val: Any) -> Optional[str]:
    if val is None:
        return None
    eok = to_eok(val)
    if eok is None:
        return str(val)
    if eok == int(eok):
        return str(int(eok))
    return str(eok)


def is_downward_crossing(previous: Any, current: Any) -> bool:
    prev, cur = to_eok(previous), to_eok(current)
    if prev is None or cur is None:
        return False
    return prev >= THRESHOLD_EOK and cur < THRESHOLD_EOK


def is_high_exact_external(external: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(external, dict):
        return False
    if not external.get("is_exact"):
        return False
    if str(external.get("confidence") or "").upper() != "HIGH":
        return False
    if to_eok(external.get("amount_eok")) is None:
        return False
    if not (external.get("same_project") and external.get("same_scope") and external.get("official_source")):
        return False
    return True


def fetch_external_contract_amount(_site: Optional[Dict[str, Any]] = None) -> None:
    """공공/민간 exact evidence provider. repo 에 실제 adapter 없음 → NOT_WIRED."""
    return None


def previous_amount_from_history(history: List[Dict[str, Any]], current: Any) -> Optional[float]:
    """SAME_SITE log 시계열에서 current 직전 금액. 타 site 행을 넣지 말 것."""
    if not history:
        return None
    series: List[float] = []
    first_old = to_eok(history[0].get("old_value"))
    if first_old is not None:
        series.append(first_old)
    for row in history:
        nv = to_eok(row.get("new_value"))
        if nv is not None:
            series.append(nv)
    cur = to_eok(current)
    if not series:
        return None
    if cur is not None and series[-1] == cur and len(series) >= 2:
        return series[-2]
    if cur is not None and series[-1] == cur:
        return None
    return series[-1]


def _result(
    status: str,
    user_amount: Optional[float],
    message: Optional[str],
    metadata: Dict[str, Any],
    reference: Any = None,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "status": status,
        "message": message,
        "user_contract_amount": user_amount,
        "metadata": metadata,
    }
    if reference is not None:
        out["reference"] = reference
    return out


def validate_contract_amount(
    user_amount: Any,
    history: List[Dict[str, Any]],
    external: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """우선순위: CROSS_50_MISMATCH → DOWNWARD_RECHECK → PASS → UNVERIFIED.

    user_amount 는 반환에 그대로 보존(자동 overwrite 금지).
    history 는 호출자가 SAME_SITE 만 넘긴다.
    """
    user = to_eok(user_amount)
    metadata: Dict[str, Any] = {
        "same_site_only": True,
        "previous": None,
        "external": None,
    }
    high_exact = is_high_exact_external(external)
    ref = to_eok(external.get("amount_eok")) if high_exact and isinstance(external, dict) else None
    if high_exact:
        metadata["external"] = {
            "amount_eok": ref,
            "confidence": "HIGH",
            "is_exact": True,
        }

    # 1) HIGH official exact + 50억 경계 반대편
    if high_exact and user is not None and ref is not None and _band(user) != _band(ref):
        pub = bool(external.get("public_reference")) if isinstance(external, dict) else False
        return _result(
            STATUS_CROSS_50_MISMATCH,
            user,
            MSG_CROSS_50_MISMATCH,
            metadata,
            reference=ref if pub else None,
        )

    # 2) SAME_SITE history downward-crossing
    prev = previous_amount_from_history(history, user)
    metadata["previous"] = prev
    if is_downward_crossing(prev, user):
        return _result(STATUS_DOWNWARD_RECHECK, user, MSG_DOWNWARD_RECHECK, metadata)

    # 3) official exact + user/reference 일관(동일 50억 구간)
    if high_exact and user is not None and ref is not None and _band(user) == _band(ref):
        return _result(STATUS_PASS, user, None, metadata)

    # 4)
    return _result(STATUS_UNVERIFIED, user, MSG_UNVERIFIED, metadata)


def fetch_same_site_amount_history(supabase, site_id: str) -> List[Dict[str, Any]]:
    """table_name+field_name+record_id=site_id 만. company/ci_hash/타 site 금지."""
    res = (
        supabase.table("price_change_log")
        .select("old_value,new_value,changed_at,record_id,table_name,field_name")
        .eq("table_name", TABLE_NAME)
        .eq("field_name", FIELD_NAME)
        .eq("record_id", site_id)
        .order("changed_at")
        .execute()
    )
    return list(res.data or [])


def maybe_log_contract_amount_change(
    supabase,
    *,
    site_id: str,
    old_amount: Any,
    new_amount: Any,
    amount_in_patch: bool,
    changed_by: Any,
    now_iso: str,
) -> bool:
    """실제 변경일 때만 1건 INSERT. 실패해도 본류를 막지 않음(best-effort)."""
    if not amount_in_patch:
        return False
    if amounts_equal(old_amount, new_amount):
        return False
    payload = {
        "table_name": TABLE_NAME,
        "record_id": site_id,
        "field_name": FIELD_NAME,
        "old_value": amount_to_text(old_amount),
        "new_value": amount_to_text(new_amount),
        "changed_at": now_iso,
        "changed_by": changed_by if changed_by else None,
    }
    try:
        supabase.table("price_change_log").insert(payload).execute()
        return True
    except Exception as e:
        log.warning("[CST-AMOUNT] price_change_log insert failed site=%s: %s", site_id, e)
        return False


def record_and_validate_site_amount(
    supabase,
    *,
    site_id: str,
    old_amount: Any,
    new_amount: Any,
    amount_in_patch: bool,
    changed_by: Any,
    now_iso: str,
    external: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    maybe_log_contract_amount_change(
        supabase,
        site_id=site_id,
        old_amount=old_amount,
        new_amount=new_amount,
        amount_in_patch=amount_in_patch,
        changed_by=changed_by,
        now_iso=now_iso,
    )
    history = fetch_same_site_amount_history(supabase, site_id)
    return validate_contract_amount(new_amount, history, external=external)
