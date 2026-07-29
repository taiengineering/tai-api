"""위험성평가 운영 파라미터 조회 서비스.

Goal: G-ms5zwv4v-b88c4a
설계: docs/ops/tai-risk-assessment/PLAN_risk-assessment-design_v2.md

■ 이 서비스가 존재하는 이유
  산업안전보건법 제36조제4항이 위험성평가의 "방법, 절차 및 시기"를 고용노동부 고시에
  전부 위임하고, 고시 제28조가 3년마다 재검토를 예고한다. 즉 주기·기한은 바뀐다.
  실제로 routers/risk_assessments.py 가 최초평가 기한을 "1년"으로 안내하고 있었다
  (현행 고시 제15조제1항은 "1개월이 되는 날까지 착수"). 2014년 구 고시 부칙의 잔재였고,
  상수로 박혀 있어 아무도 알아채지 못했다.
  => 값을 코드가 아니라 데이터에서 읽는다. 그래야 개정 시 데이터만 바꾸면 된다.

■ 법령 데이터 취급
  이 서비스는 법령 조문 원문을 다루지 않는다. 판정에 쓰는 값(value_num/value_unit)과
  근거 조문을 가리키는 포인터(law_article_ref)만 취급한다.
  조문 원문이 필요하면 법령엔진 API 로 조회하고 저장하지 않는다.

■ 스키마 미적용 대응
  ra_policy_param 은 보호 경로 정책상 오퍼레이터가 적용한다(WORKORDER v2).
  적용 전에는 내장 기본값(_FALLBACK)을 사용하고, 호출자에게 source="fallback" 을 알린다.
  값을 조용히 지어내지 않으면서 서비스가 멈추지 않게 하기 위함이다.

사용 예:
    from services.ra_policy_svc import get_param_value, get_param
    months = get_param_value("INITIAL_DUE", default=1)          # 1
    p = get_param("RETENTION")                                   # {"value_num":3, "value_unit":"YEAR", ...}
"""
from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any, Dict, List, Optional

from db.supabase_client import get_supabase

log = logging.getLogger(__name__)

# 캐시: 파라미터는 법 개정 시에만 바뀌므로 짧게 캐시해도 안전하다.
_CACHE_TTL_SEC = 300
_cache: Dict[str, Any] = {"at": 0.0, "as_of": None, "items": None, "source": None}

# 스키마 미적용 시 사용할 내장 기본값 (값 + 조문 포인터만, 원문 없음).
_FALLBACK: List[Dict[str, Any]] = [
    {"param_code": "INITIAL_DUE", "label": "최초평가 착수기한", "value_num": 1, "value_unit": "MONTH",
     "applies_to": None,
     "law_article_ref": {"source": "NOTICE_RISK_ASSESSMENT", "article_no": 15, "clause": "1"},
     "note": "건설업은 실착공일 기산. 1개월 미만 작업·공사는 개시 후 지체 없이."},
    {"param_code": "PERIODIC_CYCLE", "label": "정기평가 주기", "value_num": 1, "value_unit": "YEAR",
     "applies_to": None,
     "law_article_ref": {"source": "NOTICE_RISK_ASSESSMENT", "article_no": 15, "clause": "3"},
     "note": "전면 재실시가 아니라 적정성 재검토."},
    {"param_code": "CONTINUOUS_MONTHLY", "label": "상시평가 월간 요건", "value_num": 1, "value_unit": "MONTH",
     "applies_to": None,
     "law_article_ref": {"source": "NOTICE_RISK_ASSESSMENT", "article_no": 15, "clause": "4-1"},
     "note": "발굴 + 위험성결정 + 감소대책 수립·실행까지 이루어져야 충족."},
    {"param_code": "CONTINUOUS_WEEKLY", "label": "상시평가 주간 요건", "value_num": 1, "value_unit": "WEEK",
     "applies_to": None,
     "law_article_ref": {"source": "NOTICE_RISK_ASSESSMENT", "article_no": 15, "clause": "4-2"},
     "note": "참석자 직위 요건 있음. 도급 시 수급사 관리자 포함."},
    {"param_code": "CONTINUOUS_DAILY", "label": "상시평가 일간 요건", "value_num": None, "value_unit": "WORKDAY",
     "applies_to": None,
     "law_article_ref": {"source": "NOTICE_RISK_ASSESSMENT", "article_no": 15, "clause": "4-3"},
     "note": "TBM 기록으로 충족."},
    {"param_code": "RETENTION", "label": "기록 보존기간", "value_num": 3, "value_unit": "YEAR",
     "applies_to": None,
     "law_article_ref": {"law_key": "007364_271485", "article_no": 37, "clause": "2"},
     "note": "기산점은 실시 시기별 평가 완료일."},
    {"param_code": "PREP_EXEMPT_HEADCOUNT", "label": "사전준비 생략 기준(상시근로자)", "value_num": 5,
     "value_unit": "PERSON", "applies_to": None,
     "law_article_ref": {"source": "NOTICE_RISK_ASSESSMENT", "article_no": 8, "clause": "but"},
     "note": "미만 기준. 5인 이상은 사전준비 필수."},
    {"param_code": "PREP_EXEMPT_AMOUNT", "label": "사전준비 생략 기준(건설공사 금액)", "value_num": 100000000,
     "value_unit": "KRW", "applies_to": "CONSTRUCTION",
     "law_article_ref": {"source": "NOTICE_RISK_ASSESSMENT", "article_no": 8, "clause": "but"},
     "note": "1억원 미만."},
    {"param_code": "MCA_HALFYEAR_CHECK", "label": "중처법 반기 점검 주기", "value_num": 1, "value_unit": "HALF_YEAR",
     "applies_to": None,
     "law_article_ref": {"law_key": "014159_277417", "article_no": 4, "clause": "3"},
     "note": "위험성평가 실시 + 결과 보고 시 갈음 가능."},
]

_MISSING_TABLE_HINTS = ("does not exist", "relation", "42p01", "schema cache", "not find the table")


def _is_missing_table(err: Exception) -> bool:
    s = str(err).lower()
    return any(h in s for h in _MISSING_TABLE_HINTS)


def list_params(on_date: Optional[str] = None, use_cache: bool = True) -> Dict[str, Any]:
    """기준일 시점의 현행 파라미터 목록.

    effective_from <= 기준일 < effective_to 인 행만 반환하므로,
    과거 시점의 판정도 당시 값으로 재현할 수 있다.
    반환: {"items": [...], "source": "db"|"fallback", "as_of": "YYYY-MM-DD"}
    """
    ref = on_date or date.today().isoformat()

    if use_cache and _cache["items"] is not None and _cache["as_of"] == ref \
            and (time.time() - _cache["at"]) < _CACHE_TTL_SEC:
        return {"items": _cache["items"], "source": _cache["source"], "as_of": ref}

    try:
        res = (get_supabase().table("ra_policy_param").select("*")
               .eq("is_active", True).lte("effective_from", ref)
               .order("param_code").execute())
        rows = [r for r in (res.data or [])
                if not r.get("effective_to") or str(r["effective_to"]) > ref]
        source = "db"
        if not rows:
            # 테이블은 있으나 시드가 없는 경우 — 값 없이 동작하면 판정이 틀어지므로 fallback.
            log.warning("[RA-POLICY] ra_policy_param 에 유효 행이 없어 fallback 사용")
            rows, source = _FALLBACK, "fallback"
    except Exception as e:  # noqa: BLE001
        if not _is_missing_table(e):
            log.warning("[RA-POLICY] 조회 실패(%s) — fallback 사용", e)
        rows, source = _FALLBACK, "fallback"

    _cache.update({"at": time.time(), "as_of": ref, "items": rows, "source": source})
    return {"items": rows, "source": source, "as_of": ref}


def get_param(param_code: str, on_date: Optional[str] = None,
              applies_to: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """단건 조회. applies_to 가 주어지면 해당 대상 전용 행을 우선한다."""
    data = list_params(on_date)
    items = [r for r in data["items"] if r.get("param_code") == param_code]
    if not items:
        return None
    if applies_to:
        scoped = [r for r in items if r.get("applies_to") == applies_to]
        if scoped:
            return {**scoped[0], "source": data["source"]}
    generic = [r for r in items if not r.get("applies_to")]
    chosen = generic[0] if generic else items[0]
    return {**chosen, "source": data["source"]}


def get_param_value(param_code: str, default: Optional[float] = None,
                    on_date: Optional[str] = None,
                    applies_to: Optional[str] = None) -> Optional[float]:
    """판정에 쓰는 수치만 꺼낸다. 없으면 default.

    default 는 '값을 못 찾았을 때의 안전망'이며, 법정 기준의 정본이 아니다.
    정본은 ra_policy_param(미적용 시 _FALLBACK)이다.
    """
    p = get_param(param_code, on_date=on_date, applies_to=applies_to)
    if not p or p.get("value_num") is None:
        return default
    try:
        return float(p["value_num"])
    except (TypeError, ValueError):
        return default


def invalidate_cache() -> None:
    """파라미터 변경 후 캐시 무효화."""
    _cache.update({"at": 0.0, "as_of": None, "items": None, "source": None})
