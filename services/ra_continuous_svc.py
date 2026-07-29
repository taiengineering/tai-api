"""
ra_continuous_svc — 상시평가 3요건 간주 판정. v1.0.0

Goal: G-ms5zwv4v-b88c4a

법적 근거 — 「사업장 위험성평가에 관한 지침」 제15조제4항:
  사업주가 다음 각 호의 활동을 모두 실시하는 경우 수시평가와 정기평가를
  실시한 것으로 본다(간주).
    1. 월 1회 이상: 근로자 참여 하에 유해·위험요인을 발굴하여 위험성 결정·
       감소대책 수립·실행 (→ ra_item 등록 실적으로 판정)
    2. 매주 1회 이상: 합동안전점검회의 등에서 제1호 실행 상황을 논의·점검
       (→ work_schedules 점검 완료 실적으로 판정)
    3. 매 작업일: 작업 전 안전점검회의(TBM) 등으로 근로자에게 공유·주지
       (→ tbm_meetings 실적으로 판정)

설계 원칙
  · 판정은 순수 함수(judge_continuous)로 두고 데이터 조회와 분리한다 —
    ra_decision_svc 와 같은 구조. 화면은 판정하지 않고 결과만 표시한다.
  · '작업일' 캘린더가 없는 사업장이 대부분이므로 평일(월~금)을 작업일로
    간주한다. 주말에 TBM 실적이 있으면 그날도 실시일로 집계된다(불이익 없음).
    이 한계는 응답의 criteria 에 명시해 화면이 그대로 안내한다.
  · 오늘은 아직 끝나지 않은 날이므로 TBM 결측 판정에서 제외한다.
    진행 중인 주도 같은 이유로 '미성립'이 아니라 '진행중'으로 표시한다.
"""
from datetime import date, timedelta
from typing import Iterable, List, Optional, Set

VERSION = "1.0.0"


def _month_range(month: str) -> tuple:
    """'YYYY-MM' → (첫날, 말일)."""
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
) -> dict:
    """상시평가 3요건 간주 판정.

    month           'YYYY-MM' 판정 대상 월
    discovery_dates 요인 발굴(ra_item 등록) 일자들
    review_dates    논의·점검(점검 완료) 일자들
    tbm_dates       TBM 실시 일자들
    today           기준일(테스트 주입용). 기본 오늘.
    """
    today = today or date.today()
    first, last = _month_range(month)

    # 판정 구간: 월 첫날 ~ min(월 말일, 오늘). 미래 월이면 구간 없음.
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
    # 월요일 시작 주 단위로 구간을 나눈다. 월 경계에 걸친 주는 월내 부분만 본다.
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
                "ongoing": ongoing,     # 아직 끝나지 않은 주 — 미성립으로 치지 않음
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
    # 작업일 = 평일(월~금) 간주. 오늘은 판정에서 제외(아직 실시 가능).
    tbm_judge_end = min(end, today - timedelta(days=1))
    workdays: List[date] = []
    d = first
    while d <= tbm_judge_end:
        if d.weekday() < 5:
            workdays.append(d)
        d += timedelta(days=1)
    missing = sorted(x.isoformat() for x in workdays if x not in tbm)
    daily = {
        "met": len(workdays) > 0 and len(missing) == 0,
        "workdays_elapsed": len(workdays),
        "tbm_days": len(tbm),
        "missing_days": missing[:15],
        "missing_total": len(missing),
        "today_done": today in tbm,
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
            "TBM: 작업일은 평일(월~금)로 간주합니다. 사업장 휴무일은 반영되지 않으므로 휴무일 결측은 무시하고 판단하십시오. 오늘은 판정에서 제외합니다.",
        ],
    }
