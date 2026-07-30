"""
holiday_svc — 조직 공용 휴무 캘린더 서비스. v1.0.1

Goal: G-ms6az4y8-b88c4a
데이터: org_holiday (supabase/migrations/20260729163654_org_holiday_table_and_2026_seed.sql)

이 모듈은 특정 기능 전용이 아니다. 캘린더(작업일/휴무일)를 쓰는 모든 기능이
여기서 휴무일을 조회하고 작업일을 판정한다.
  현재 소비자: 위험성평가 상시평가 3호(매 작업일 TBM) 판정 — ra_continuous_svc
              점검 일정 다음 점검일 휴무 보정 — inspection_sets_helpers
  후속 소비자: TBM 미실시 알림, 교육 기한 산정 등
새 기능에서 "평일이면 작업일" 같은 판정을 다시 만들지 말고 이 모듈을 쓸 것.

스코프 규칙 (org_holiday)
  company_id IS NULL                → 전국 공통(법정공휴일, source=LEGAL)
  company_id 지정, factory_id NULL  → 회사 전체 휴무
  company_id + factory_id 지정      → 시설 휴무

조회 규칙 (get_holidays)
  factory_id 미지정(회사 단위 조회) → 법정 + 회사의 모든 휴무(시설별 포함).
    관리 화면이 회사의 휴무를 빠짐없이 보여주기 위함.
  factory_id 지정(특정 시설 판정)   → 법정 + 회사 전체 휴무 + 그 시설 휴무만.
    다른 시설 전용 휴무는 그 시설의 작업일에 영향을 주지 않는다.

v1.0.1 (2026-07-30) — 회사 단위 조회에서 시설별 휴무가 누락되던 것을 정정.
  종전에는 factory_id 미지정 시 시설 전용 휴무를 제외해, 휴무 캘린더 화면에
  시설 휴무가 보이지 않았다(실화면 검증에서 발견).

법정공휴일을 코드 상수가 아니라 데이터로 두는 이유
  임시공휴일·대체공휴일은 해마다 다르고 연중에도 지정된다(2026 지방선거일,
  제헌절 재지정이 그 사례). 코드에 박으면 지정될 때마다 배포가 필요해진다.
  연도별 시드는 마이그레이션으로 추가한다(git 고정 — BKP-004).
"""
from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional, Set

from db.supabase_client import get_supabase

VERSION = "1.0.1"


def get_holidays(
    company_id: Optional[str],
    factory_id: Optional[str],
    date_from: str,
    date_to: str,
) -> List[dict]:
    """스코프 병합 휴무일 목록. 테이블 미적용 환경이면 빈 목록.

    반환 행: {id, holiday_date, name, source, company_id, factory_id, note}
    """
    sb = get_supabase()
    rows: List[dict] = []
    try:
        # 전국 공통(법정) — company_id IS NULL
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
                    rows.append(r)                      # 회사 전체 휴무 — 항상 포함
                elif factory_id is None:
                    rows.append(r)                      # 회사 단위 조회 — 시설 휴무도 포함(화면용)
                elif str(fr) == str(factory_id):
                    rows.append(r)                      # 특정 시설 판정 — 그 시설 것만
                # 다른 시설 전용 휴무는 특정 시설 판정에서 제외
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


def is_workday(d: date, holidays: Optional[Iterable[date]] = None) -> bool:
    """작업일 판정: 평일이면서 휴무일이 아닌 날.

    사업장 교대제·주말 조업은 아직 반영하지 않는다 — 주말에 실적이 있으면
    소비자 쪽 집계에서 자연히 잡히므로 불이익은 없다.
    """
    if d.weekday() >= 5:
        return False
    if holidays and d in set(holidays):
        return False
    return True


def workdays_between(first: date, last: date, holidays: Optional[Iterable[date]] = None) -> List[date]:
    """구간 [first, last] 의 작업일 목록."""
    hset: Set[date] = set(holidays or [])
    out: List[date] = []
    d = first
    while d <= last:
        if is_workday(d, hset):
            out.append(d)
        d += timedelta(days=1)
    return out
