"""
holiday_svc — 조직 공용 휴무/작업일 캘린더 서비스. v1.1.0

Goal: G-ms6az4y8-b88c4a(휴무) / G-ms6zml74-76dbad(조업요일 정책)
데이터: org_holiday(휴무), org_work_policy(조업요일)

이 모듈은 특정 기능 전용이 아니다. 캘린더(작업일/휴무일)를 쓰는 모든 기능이
여기서 휴무일·조업요일을 조회하고 작업일을 판정한다.
  현재 소비자: 위험성평가 상시평가 3호(매 작업일 TBM) 판정 — ra_continuous_svc
              점검 일정 다음 점검일 휴무 보정 — inspection_sets_helpers
  후속 소비자: TBM 미실시 알림, 교육 기한 산정 등
새 기능에서 "평일이면 작업일" 같은 판정을 다시 만들지 말고 이 모듈을 쓸 것.

작업일 판정 (v1.1.0)
  작업일 = 조업요일이면서 휴무일이 아닌 날.
  조업요일은 org_work_policy.work_weekdays(ISO 1=월…7=일)로 사업장이 정한다.
  주말 조업·교대제 사업장은 토·일을 포함할 수 있다. 정책 미설정/테이블 미적용이면
  기본 월~금({1,2,3,4,5})으로 폴백한다(종전 동작과 동일).
  스코프: 시설 정책(factory_id 일치)이 회사 정책(factory_id NULL)을 우선한다.

휴무 스코프 규칙 (org_holiday)
  company_id IS NULL = 전국 공통(법정공휴일), company_id 지정·factory_id NULL = 회사 전체,
  둘 다 지정 = 시설 휴무.
"""
from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional, Set

from db.supabase_client import get_supabase

VERSION = "1.1.0"

DEFAULT_WORK_WEEKDAYS = {1, 2, 3, 4, 5}   # ISO 월~금


# ── 휴무 조회 ────────────────────────────────────────────────────────
def get_holidays(
    company_id: Optional[str],
    factory_id: Optional[str],
    date_from: str,
    date_to: str,
) -> List[dict]:
    """스코프 병합 휴무일 목록. 테이블 미적용 환경이면 빈 목록.

    factory_id 미지정(회사 단위) → 법정 + 회사의 모든 휴무(시설별 포함).
    factory_id 지정(특정 시설)  → 법정 + 회사 전체 + 그 시설 휴무만.
    """
    sb = get_supabase()
    rows: List[dict] = []
    try:
        legal = (sb.table("org_holiday").select("*")
                 .is_("company_id", "null")
                 .gte("holiday_date", date_from).lte("holiday_date", date_to)
                 .execute().data) or []
        rows.extend(legal)

        if company_id:
            comp = (sb.table("org_holiday").select("*")
                    .eq("company_id", company_id)
                    .gte("holiday_date", date_from).lte("holiday_date", date_to)
                    .execute().data) or []
            for r in comp:
                fr = r.get("factory_id")
                if not fr:
                    rows.append(r)
                elif factory_id is None:
                    rows.append(r)
                elif str(fr) == str(factory_id):
                    rows.append(r)
    except Exception:
        return []
    return rows


def holiday_map(
    company_id: Optional[str],
    factory_id: Optional[str],
    date_from: str,
    date_to: str,
) -> Dict[date, List[str]]:
    """날짜 → 휴무 이름 목록. 판정·표시용."""
    out: Dict[date, List[str]] = {}
    for r in get_holidays(company_id, factory_id, date_from, date_to):
        try:
            d = date.fromisoformat(str(r["holiday_date"])[:10])
        except Exception:
            continue
        out.setdefault(d, []).append(r.get("name") or "휴무")
    return out


# ── 조업요일 정책 ────────────────────────────────────────────────────
def _normalize_weekdays(values) -> Set[int]:
    out: Set[int] = set()
    for v in values or []:
        try:
            n = int(v)
        except (TypeError, ValueError):
            continue
        if 1 <= n <= 7:
            out.add(n)
    return out or set(DEFAULT_WORK_WEEKDAYS)


def get_work_weekdays(company_id: Optional[str], factory_id: Optional[str]) -> Set[int]:
    """사업장 조업요일(ISO 1~7). 시설 정책 우선, 없으면 회사, 없으면 기본 월~금.

    org_work_policy 테이블 미적용/조회 실패 시에도 기본값으로 폴백한다.
    """
    if not company_id:
        return set(DEFAULT_WORK_WEEKDAYS)
    try:
        rows = (get_supabase().table("org_work_policy").select("factory_id, work_weekdays")
                .eq("company_id", company_id).execute().data) or []
    except Exception:
        return set(DEFAULT_WORK_WEEKDAYS)
    if not rows:
        return set(DEFAULT_WORK_WEEKDAYS)

    factory_row = next((r for r in rows if factory_id and str(r.get("factory_id")) == str(factory_id)), None)
    company_row = next((r for r in rows if not r.get("factory_id")), None)
    chosen = factory_row or company_row or rows[0]
    return _normalize_weekdays(chosen.get("work_weekdays"))


# ── 작업일 판정 ──────────────────────────────────────────────────────
def is_workday(d: date, holidays: Optional[Iterable[date]] = None,
               work_weekdays: Optional[Iterable[int]] = None) -> bool:
    """작업일 판정: 조업요일이면서 휴무일이 아닌 날.

    work_weekdays 는 ISO 요일 집합(1=월…7=일). 미지정 시 기본 월~금.
    """
    wd = _normalize_weekdays(work_weekdays) if work_weekdays is not None else set(DEFAULT_WORK_WEEKDAYS)
    if d.isoweekday() not in wd:
        return False
    if holidays and d in set(holidays):
        return False
    return True


def workdays_between(first: date, last: date,
                     holidays: Optional[Iterable[date]] = None,
                     work_weekdays: Optional[Iterable[int]] = None) -> List[date]:
    """구간 [first, last] 의 작업일 목록."""
    hset: Set[date] = set(holidays or [])
    wd = _normalize_weekdays(work_weekdays) if work_weekdays is not None else set(DEFAULT_WORK_WEEKDAYS)
    out: List[date] = []
    d = first
    while d <= last:
        if d.isoweekday() in wd and d not in hset:
            out.append(d)
        d += timedelta(days=1)
    return out
