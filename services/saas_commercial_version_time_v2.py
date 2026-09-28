"""TAI Safe Commercial Version Temporal Semantics V2 — Pure Module.

Interval semantic:
  CV is effective at `as_of` IFF:
    cv.effective_from <= as_of
    AND (cv.superseded_at IS None OR as_of < cv.superseded_at)

Half-open interval: [effective_from, superseded_at)

At the superseded boundary:
  old version = NOT EFFECTIVE
  new version = EFFECTIVE

Owner Policy: RENEWAL_EFFECTIVE_POLICY = CURRENT_CONTRACT_END_DATE
Timezone:     Asia/Seoul (KST = UTC+9)

금지:
  - DB I/O
  - datetime.now() 직접 호출
  - ORDER BY version_no DESC LIMIT 1로 ambiguity 숨기기
  - naive datetime을 silently 허용
"""
from __future__ import annotations

import zoneinfo
from datetime import date, datetime
from typing import Any, List, Optional, Sequence

from dateutil import parser as dateutil_parser

_SEOUL_TZ = zoneinfo.ZoneInfo("Asia/Seoul")


# ── Domain Error ──────────────────────────────────────────────────────────────

class TemporalVersionError(Exception):
    """Temporal commercial version 판정 오류.

    code values:
      TEMPORAL_NAIVE_DATETIME          — timezone-naive datetime 입력
      TEMPORAL_INVALID_FIELD           — 타입 불인식 필드
      TEMPORAL_CURRENT_NOT_FOUND       — as_of 시점 effective CV 없음
      TEMPORAL_CURRENT_AMBIGUOUS       — as_of 시점 effective CV 2개 이상
    """

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        self.message = message or code
        super().__init__(self.message)


# ── Internal Helpers ──────────────────────────────────────────────────────────

def _get(obj: Any, key: str) -> Any:
    """Dict 또는 object attribute access."""
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _resolve_dt(val: Any, field_name: str) -> Optional[datetime]:
    """Any → timezone-aware datetime | None.

    None → None (superseded_at=None = open-ended).
    str  → dateutil.isoparse.
    datetime → 직접 사용.
    naive datetime → TEMPORAL_NAIVE_DATETIME 발생.
    """
    if val is None:
        return None
    if isinstance(val, str):
        try:
            dt: datetime = dateutil_parser.isoparse(val)
        except (ValueError, TypeError) as exc:
            raise TemporalVersionError(
                "TEMPORAL_INVALID_FIELD",
                f"{field_name} ISO 파싱 실패: {val!r}",
            ) from exc
    elif isinstance(val, datetime):
        dt = val
    else:
        raise TemporalVersionError(
            "TEMPORAL_INVALID_FIELD",
            f"{field_name} 타입 불인식: {type(val)!r}",
        )
    if dt.tzinfo is None:
        raise TemporalVersionError(
            "TEMPORAL_NAIVE_DATETIME",
            f"{field_name}은 timezone-aware이어야 합니다: {val!r}",
        )
    return dt


# ── Public Functions ──────────────────────────────────────────────────────────

def is_commercial_version_effective_at_v2(cv: Any, as_of: datetime) -> bool:
    """CV가 as_of 시점에 effective인지 판정.

    Interval: [effective_from, superseded_at)

    Args:
      cv     — dict 또는 SaasContractCommercialVersionV2 (Pydantic model)
      as_of  — timezone-aware datetime (naive → raises TEMPORAL_NAIVE_DATETIME)

    Returns:
      True iff effective_from <= as_of AND (superseded_at is None OR as_of < superseded_at)
    """
    as_of_dt = _resolve_dt(as_of, "as_of")  # validates tz-aware

    eff_from = _resolve_dt(_get(cv, "effective_from"), "effective_from")
    if eff_from is None:
        return False

    sup_at = _resolve_dt(_get(cv, "superseded_at"), "superseded_at")

    if eff_from > as_of_dt:
        return False
    if sup_at is None:
        return True
    return as_of_dt < sup_at


def select_effective_commercial_version_v2(versions: Sequence, as_of: datetime) -> Any:
    """as_of 시점 effective CV 선택.

    Args:
      versions — CV sequence (dict 또는 Pydantic model)
      as_of    — timezone-aware datetime

    Returns:
      effective CV (단 1개)

    Raises:
      TemporalVersionError(TEMPORAL_CURRENT_NOT_FOUND) — 0개
      TemporalVersionError(TEMPORAL_CURRENT_AMBIGUOUS) — 2개 이상
    """
    effective = [
        cv for cv in versions
        if is_commercial_version_effective_at_v2(cv, as_of)
    ]
    if len(effective) == 0:
        raise TemporalVersionError(
            "TEMPORAL_CURRENT_NOT_FOUND",
            f"as_of={as_of} 시점 effective Commercial Version 없음",
        )
    if len(effective) > 1:
        raise TemporalVersionError(
            "TEMPORAL_CURRENT_AMBIGUOUS",
            f"as_of={as_of} 시점 effective Commercial Version {len(effective)}개 — 중복 불허",
        )
    return effective[0]


def find_future_commercial_versions_v2(versions: Sequence, as_of: datetime) -> List[Any]:
    """as_of보다 미래에 effective_from인 CV 목록.

    as_of = now 기준으로 미래 예약된 Renewal Version을 탐지한다.

    Args:
      versions — CV sequence
      as_of    — timezone-aware datetime (naive → raises TEMPORAL_NAIVE_DATETIME)

    Returns:
      list of CVs where effective_from > as_of
    """
    _resolve_dt(as_of, "as_of")  # validates tz-aware

    result = []
    for cv in versions:
        eff_from = _resolve_dt(_get(cv, "effective_from"), "effective_from")
        if eff_from is not None and eff_from > as_of:
            result.append(cv)
    return result


def contract_end_date_to_effective_at_v2(end_date: Any) -> datetime:
    """contracts.end_date → Asia/Seoul 00:00:00 timezone-aware datetime.

    Owner Policy: renewal_effective_at = contracts.end_date at 00:00:00 KST

    예:
      2027-01-01 (DATE)
      → 2027-01-01T00:00:00+09:00 (KST)
      ≡ 2026-12-31T15:00:00+00:00 (UTC)

    Args:
      end_date — date / datetime / ISO string

    Returns:
      datetime with tzinfo=Asia/Seoul
    """
    if isinstance(end_date, str):
        d = dateutil_parser.parse(end_date).date()
    elif isinstance(end_date, datetime):
        d = end_date.date()
    elif isinstance(end_date, date):
        d = end_date
    else:
        raise ValueError(f"end_date 타입 불인식: {type(end_date)!r}")

    return datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=_SEOUL_TZ)
