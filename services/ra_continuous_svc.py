"""
ra_continuous_svc — 상시평가 3요건 간주 판정. v1.2.0

Goal: G-ms5zwv4v-b88c4a(v1.0) / G-ms6az4y8(v1.1 휴무) / G-ms6zml74-76dbad(v1.2 조업요일)

v1.2.0 (2026-07-30) — 조업요일 반영
  3호(매 작업일 TBM) 판정의 작업일을 평일 고정이 아니라 사업장 조업요일(work_weekdays,
  ISO 1~7)로 산정한다. 주말 조업·교대제 사업장은 토·일이 작업일이 될 수 있다.
  work_weekdays 는 호출자가 holiday_svc.get_work_weekdays 로 조회해 넘긴다(미지정 시 월~금).

v1.1.0 (2026-07-30) — 휴무 캘린더 반영(법정공휴일·사업장 휴무일을 작업일에서 제외).

법적 근거 — 「사업장 위험성평가에 관한 지침」 제15조제4항:
  다음을 모두 실시하면 수시·정기평가를 실시한 것으로 본다(간주).
    1. 월 1회 이상 유해·위험요인 발굴 (→ ra_item 등록 실적)
    2. 매주 1회 이상 논의·점검 (→ work_schedules 점검 완료 실적)
    3. 매 작업일 TBM (→ tbm_meetings 실적, 작업일 = 조업요일 - 휴무)

설계 원칙
  판정은 순수 함수(judge_continuous). 휴무·조업요일은 호출자가 조회해 넘긴다(테스트 주입 가능).
  오늘은 아직 끝나지 않은 날이므로 TBM 결측 판정에서 제외한다. 진행 중인 주도 미성립으로 치지 않는다.
"""
from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional, Set

from services.holiday_svc import DEFAULT_WORK_WEEKDAYS, workdays_between
from services.time import business_today

VERSION = "1.2.0"

_WD_LABEL = {1: "월", 2: "화", 3: "수", 4: "목", 5: "금", 6: "토", 7: "일"}


def _month_range(month: str) -> tuple:
    y, m = int(month[:4]), int(month[5:7])
    first = date(y, m, 1)
    last = (date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)) - timedelta(days=1)
    return first, last


def _to_date_set(values: Iterable) -> Set[date]:
    out: Set[date] = set()
    for v in values or []:
        if not v:
            continue
        try:
            out.add(date.fromisoformat(str(v)[:10]))
        except Exception:
            continue
    return out


def judge_continuous(
    month: str,
    discovery_dates: Iterable,
    review_dates: Iterable,
    tbm_dates: Iterable,
    today: Optional[date] = None,
    holidays: Optional[Dict[date, List[str]]] = None,
    work_weekdays: Optional[Iterable[int]] = None,
) -> dict:
    """상시평가 3요건 간주 판정.

    work_weekdays  ISO 조업요일 집합(1=월…7=일). 미지정 시 기본 월~금.
    holidays       날짜→휴무 이름 목록(holiday_svc.holiday_map). 작업일에서 제외·표시.
    """
    today = today or business_today()
    first, last = _month_range(month)
    holidays = holidays or {}
    wd: Set[int] = set(int(x) for x in work_weekdays) if work_weekdays is not None else set(DEFAULT_WORK_WEEKDAYS)

    end = min(last, today)
    in_progress_month = last > today >= first
    future_month = first > today

    discovery = {d for d in _to_date_set(discovery_dates) if first <= d <= last}
    review    = {d for d in _to_date_set(review_dates)    if first <= d <= last}
    tbm       = {d for d in _to_date_set(tbm_dates)       if first <= d <= last}

    # ── 1호: 월 1회 이상 발굴 ─────────────────────────────────
    monthly = {
        "met": len(discovery) >= 1,
        "count": len(discovery),
        "dates": sorted(d.isoformat() for d in discovery),
        "label": "월 1회 이상 유해·위험요인 발굴 (제15조제4항제1호)",
    }

    # ── 2호: 매주 1회 이상 논의·점검 ─────────────────────────
    weeks: List[dict] = []
    if not future_month:
        cursor = first - timedelta(days=first.weekday())   # 해당 주 월요일
        while cursor <= end:
            w_start = max(cursor, first)
            w_end_full = cursor + timedelta(days=6)
            w_end = min(w_end_full, last)
            ongoing = w_end_full >= today and in_progress_month
            hits = [d for d in review if w_start <= d <= w_end]
            weeks.append({
                "week_start": w_start.isoformat(),
                "week_end": w_end.isoformat(),
                "count": len(hits),
                "met": len(hits) >= 1,
                "ongoing": ongoing,
            })
            cursor += timedelta(days=7)
    weekly_met = all(w["met"] for w in weeks if not w["ongoing"]) and bool(weeks)
    weekly = {
        "met": weekly_met,
        "weeks": weeks,
        "count": len(review),
        "label": "매주 1회 이상 논의·점검 (제15조제4항제2호)",
    }

    # ── 3호: 매 작업일 TBM ────────────────────────────────────
    # 작업일 = 조업요일 - 휴무. 오늘은 판정에서 제외(아직 실시 가능).
    tbm_judge_end = min(end, today - timedelta(days=1))
    workdays: List[date] = []
    if tbm_judge_end >= first:
        workdays = workdays_between(first, tbm_judge_end, holidays.keys(), wd)
    missing = sorted(x.isoformat() for x in workdays if x not in tbm)

    excluded_holidays = [
        {"date": d.isoformat(), "names": names}
        for d, names in sorted(holidays.items())
        if first <= d <= (tbm_judge_end if tbm_judge_end >= first else end) and d.isoweekday() in wd
    ]

    daily = {
        "met": len(workdays) > 0 and len(missing) == 0,
        "workdays_elapsed": len(workdays),
        "tbm_days": len(tbm),
        "missing_days": missing[:15],
        "missing_total": len(missing),
        "today_done": today in tbm,
        "excluded_holidays": excluded_holidays,
        "work_weekdays": sorted(wd),
        "work_weekdays_label": "·".join(_WD_LABEL[n] for n in sorted(wd)),
        "label": "매 작업일 TBM 실시 (제15조제4항제3호)",
    }

    deemed = monthly["met"] and weekly["met"] and daily["met"]

    return {
        "month": month,
        "judged_through": end.isoformat() if not future_month else None,
        "in_progress": in_progress_month,
        "requirements": {"monthly_discovery": monthly, "weekly_review": weekly, "daily_tbm": daily},
        "deemed": deemed,
        "deemed_meaning": ("3요건이 모두 충족되어 이 달의 수시·정기평가를 실시한 것으로 봅니다"
                           "(고시 제15조제4항)." if deemed else
                           "3요건이 모두 충족될 때 수시·정기평가를 실시한 것으로 봅니다"
                           "(고시 제15조제4항). 미충족 요건을 확인하십시오."),
        "criteria": [
            "발굴: 해당 월에 등록된 유해·위험요인(ra_item)을 실적으로 봅니다.",
            "논의·점검: 점검관리에서 완료 처리된 점검을 실적으로 봅니다. 월요일 시작 주 단위로 판정하며, 진행 중인 주는 미성립으로 치지 않습니다.",
            f"TBM: 작업일은 사업장 조업요일({daily['work_weekdays_label']})에서 법정공휴일·사업장 휴무일을 뺀 날입니다. 조업요일과 휴무일은 위험성평가 > 휴무 캘린더에서 관리합니다. 오늘은 판정에서 제외합니다.",
        ],
    }
