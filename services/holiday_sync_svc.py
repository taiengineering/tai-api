"""
holiday_sync_svc — 공휴일 공식 API 동기화. v1.1.0

Goal: G-ms6skzj3-76dbad
정본: 공공데이터포털 「한국천문연구원_특일 정보」 getRestDeInfo
      (국경일 + 관공서 공휴일 — 대체공휴일·임시공휴일 포함)
      https://www.data.go.kr/data/15012690/openapi.do

v1.1.0 (2026-07-30) — 한국 egress 프록시 경유
  data.go.kr 은 해외 서버 IP 를 차단한다(Railway 직접 호출 시 HTTP 403,
  한국 IP 에서는 정상 — 실측 확인). KMC 본인인증·SMS 가 이미 쓰는 것과 같은
  한국 HTTP 프록시로 우회한다. 프록시는 DATA_GO_KR_HTTP_PROXY 를 우선 읽고,
  없으면 KMC_HTTP_PROXY 로 폴백한다. 둘 다 없으면 직접 호출(프록시 불필요 환경).

왜 API 동기화인가
  법정공휴일을 코드/시드로 유지하면 매년 갱신이 필요하고, 임시공휴일(예: 선거일)은
  연중에 갑자기 지정되어 수기로는 반영이 늦다. 국가 발표를 그대로 받는 이 API를 정본으로
  삼아 org_holiday 의 LEGAL 행을 주기적으로 교체한다.

동작 (sync_year)
  대상 연도의 매월을 getRestDeInfo 로 조회 → isHoliday=Y 항목 수집 →
  org_holiday 에서 그 연도의 LEGAL(company_id IS NULL) 행을 삭제하고 새로 삽입한다.
  '교체'로 두는 이유: API dateName(예: "1월1일")과 종전 수기 시드명(예: "신정")이 달라
  upsert-only 로는 같은 날짜에 이름만 다른 중복이 쌓인다. API를 단일 정본으로 두어 정합성을
  지킨다. 삭제 범위는 그 연도의 LEGAL 행에 한정하며, 사업장 휴무(COMPANY)는 건드리지 않는다.

서비스키
  DATA_GO_KR_SERVICE_KEY 환경변수에서 읽는다(하드코딩 금지). 공공데이터포털의 인코딩 키는
  '%2B' 등 URL 인코딩을 포함하므로, '%' 가 있으면 이미 인코딩된 것으로 보고 그대로 붙이고,
  없으면 quote 로 인코딩한다.

주의: 이 모듈은 tai-api 런타임에서 실행되며 org_holiday 에 직접 쓴다.
"""
import logging
import os
from datetime import date
from typing import Dict, List, Optional
from urllib.parse import quote

import requests

from db.supabase_client import get_supabase

log = logging.getLogger(__name__)

VERSION = "1.1.0"

_BASE = "https://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/getRestDeInfo"
_ENV_KEY = "DATA_GO_KR_SERVICE_KEY"
_ENV_PROXY = "DATA_GO_KR_HTTP_PROXY"
_ENV_PROXY_FALLBACK = "KMC_HTTP_PROXY"     # KMC/SMS 가 쓰는 한국 egress 프록시 재사용


class HolidaySyncError(Exception):
    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


def _service_key() -> str:
    key = os.getenv(_ENV_KEY, "").strip()
    if not key:
        raise HolidaySyncError(
            f"{_ENV_KEY} 환경변수가 없습니다. 공공데이터포털 특일정보 서비스키를 설정하십시오.")
    return key


def _key_param(key: str) -> str:
    # 인코딩 키(%포함)는 그대로, 디코딩 키는 quote 로 안전 인코딩.
    return key if "%" in key else quote(key, safe="")


def _proxies() -> Optional[dict]:
    """한국 egress 프록시. data.go.kr 해외IP 403 우회용. 없으면 None(직접 호출)."""
    p = (os.getenv(_ENV_PROXY, "") or os.getenv(_ENV_PROXY_FALLBACK, "")).strip()
    return {"http": p, "https": p} if p else None


def _fetch_month(year: int, month: int) -> List[dict]:
    """특정 연·월의 공휴일 항목 조회. isHoliday=Y 만 반환."""
    key = _key_param(_service_key())
    url = (f"{_BASE}?serviceKey={key}"
           f"&solYear={year}&solMonth={month:02d}&numOfRows=100&_type=json")
    try:
        resp = requests.get(url, timeout=20, proxies=_proxies())
    except Exception as e:
        raise HolidaySyncError(f"{year}-{month:02d} 특일정보 호출 실패: {e}")

    if resp.status_code >= 400:
        hint = ""
        if resp.status_code in (401, 403):
            hint = (" — data.go.kr 은 해외 IP 를 차단합니다. "
                    "DATA_GO_KR_HTTP_PROXY(또는 KMC_HTTP_PROXY)에 한국 egress 프록시를 설정하십시오.")
        raise HolidaySyncError(
            f"{year}-{month:02d} 특일정보 HTTP {resp.status_code}: {resp.text[:150]}{hint}")

    try:
        body = resp.json()["response"]["body"]
    except Exception:
        # 인증 실패 등은 XML 로 온다 — 원문 앞부분을 그대로 노출해 원인 파악을 돕는다.
        raise HolidaySyncError(
            f"{year}-{month:02d} 응답 파싱 실패(서비스키 확인 필요): {resp.text[:200]}")

    items = (body or {}).get("items") or ""
    if not items:
        return []
    item = items.get("item")
    if item is None:
        return []
    rows = item if isinstance(item, list) else [item]

    out: List[dict] = []
    for r in rows:
        if str(r.get("isHoliday", "")).upper() != "Y":
            continue
        loc = str(r.get("locdate") or "").strip()
        if len(loc) != 8:
            continue
        iso = f"{loc[:4]}-{loc[4:6]}-{loc[6:8]}"
        name = str(r.get("dateName") or "공휴일").strip()
        out.append({"holiday_date": iso, "name": name})
    return out


def fetch_year(year: int) -> List[dict]:
    """대상 연도 전체 공휴일 목록(중복 날짜+이름 제거)."""
    seen = set()
    result: List[dict] = []
    for m in range(1, 13):
        for h in _fetch_month(year, m):
            k = (h["holiday_date"], h["name"])
            if k in seen:
                continue
            seen.add(k)
            result.append(h)
    return result


def sync_year(year: int, created_by: Optional[str] = None) -> Dict:
    """대상 연도 LEGAL 공휴일을 API 결과로 교체(삭제 후 삽입)."""
    fetched = fetch_year(year)
    if not fetched:
        raise HolidaySyncError(
            f"{year}년 공휴일이 0건 조회됐습니다. 서비스키·연도를 확인하십시오(교체 중단).")

    sb = get_supabase()
    lo, hi = f"{year}-01-01", f"{year}-12-31"

    # 기존 LEGAL(전국 공통) 행만 교체 대상. 사업장 휴무(COMPANY)는 보존.
    before = (sb.table("org_holiday").select("id", count="exact")
              .eq("source", "LEGAL").is_("company_id", "null")
              .gte("holiday_date", lo).lte("holiday_date", hi).execute()).count or 0

    (sb.table("org_holiday").delete()
     .eq("source", "LEGAL").is_("company_id", "null")
     .gte("holiday_date", lo).lte("holiday_date", hi).execute())

    rows = [{
        "company_id": None, "factory_id": None,
        "holiday_date": h["holiday_date"], "name": h["name"],
        "source": "LEGAL", "created_by": created_by,
    } for h in fetched]

    inserted = 0
    for i in range(0, len(rows), 50):
        res = sb.table("org_holiday").insert(rows[i:i + 50]).execute()
        inserted += len(res.data or [])

    log.info(f"[HOLIDAY_SYNC] {year} 교체: 이전 {before} → 신규 {inserted}")
    return {
        "year": year,
        "fetched": len(fetched),
        "deleted": before,
        "inserted": inserted,
        "source": "KASI getRestDeInfo",
    }


def sync_current_and_next(created_by: Optional[str] = None) -> Dict:
    """올해와 내년을 함께 동기화(스케줄러 기본 동작). 내년 달력은 연말에 확정된다."""
    y = date.today().year
    return {"results": [sync_year(y, created_by), sync_year(y + 1, created_by)]}
