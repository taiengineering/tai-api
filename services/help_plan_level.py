# -*- coding: utf-8 -*-
"""계약 등급 리졸버 — user 의 company_id 로 활성 계약을 찾아 plan_code 를 등급(level)으로 옮긴다.

왜 필요한가
  헬프센터 게이팅(help_node.min_level)은 서버가 판정해야 한다. 그런데 contracts 에는
  숫자 등급 컬럼이 없고 문자열 plan_code 만 있다. 그 매핑표는 결제 알림 라벨용으로
  services/payment_post_process.PLAN_MAP 에만 있었다. 이 모듈은 그 표를 게이팅에 쓸 수 있게
  옮겨 온 것이며, payment_post_process 의 기존 동작은 건드리지 않는다.

payment_post_process.PLAN_MAP 과 다른 점 — 의도된 차이
  거기서는 매핑에 없는 plan_code 를 {sector: INDUSTRIAL, level: 3} 으로 폴백한다.
  알림 라벨이라 틀려도 손해가 없기 때문이다. 게이팅은 다르다. 틀리면 볼 수 없어야 할 문서를
  보여주거나 반대로 막는다. 그래서 이 모듈은 **폴백하지 않고 level 을 None 으로 둔다.**

실측 근거 (2026-08-15, tai-db 활성 계약 6건)
  INDUSTRY_PRO(3) · INDUSTRY_STARTER_V2(1) — 매핑 있음
  CONSTRUCTION_STANDARD(1) · STANDARD(1)   — 매핑 없음 → level None
  CONSTRUCTION_STANDARD 는 표의 CONSTRUCTION_STANDARD_V2 와 표기가 다르고,
  STANDARD 는 업종조차 유추할 근거가 없다. 추측해서 채우지 않는다.

  근본 해결(plan_code 표기 통일 또는 contracts 등급 컬럼 신설)은 결제 도메인이라 별도 과제다.
"""
import logging
import re
from datetime import date
from typing import Any, Dict, Optional

from db.supabase_client import get_supabase

log = logging.getLogger(__name__)

# plan_code → 업종·등급. payment_post_process.PLAN_MAP 과 같은 출처를 공유한다.
PLAN_LEVELS: Dict[str, Dict[str, Any]] = {
    "BUILDING_LITE": {"sector": "FACILITY", "level": 1},
    "BUILDING_BASIC": {"sector": "FACILITY", "level": 2},
    "BUILDING_STANDARD": {"sector": "FACILITY", "level": 3},
    "BUILDING_CUSTOM": {"sector": "FACILITY", "level": 4},
    "INDUSTRY_STARTER": {"sector": "INDUSTRIAL", "level": 1},
    "INDUSTRY_BUSINESS": {"sector": "INDUSTRIAL", "level": 2},
    "INDUSTRY_PRO": {"sector": "INDUSTRIAL", "level": 3},
    "INDUSTRY_CUSTOM": {"sector": "INDUSTRIAL", "level": 4},
    "CONSTRUCTION_STANDARD": {"sector": "CONSTRUCTION", "level": 1},
    "CONSTRUCTION_PREMIUM": {"sector": "CONSTRUCTION", "level": 2},
    "CONSTRUCTION_CUSTOM": {"sector": "CONSTRUCTION", "level": 3},
}

_ACTIVE_STATUS = ("ACTIVE",)


def normalize_plan_code(plan_code: Optional[str]) -> str:
    """계약 plan_code 표기 정규화 — 끝의 _V<숫자> 접미어만 제거한다.

    INDUSTRY_STARTER_V2 → INDUSTRY_STARTER. 접미어가 없으면 그대로 둔다.
    routers/payment_plan_resolver._normalize_tier 과 같은 규칙이다.
    """
    code = (plan_code or "").strip().upper()
    return re.sub(r"_V\d+$", "", code)


def level_of_plan(plan_code: Optional[str]) -> Optional[Dict[str, Any]]:
    """plan_code → {plan_code, normalized, sector, level}. 매핑에 없으면 None.

    추측하지 않는다. 모르면 None 을 돌려주고, 호출부가 '등급 미상'으로 다룬다.
    """
    normalized = normalize_plan_code(plan_code)
    if not normalized:
        return None
    hit = PLAN_LEVELS.get(normalized)
    if not hit:
        log.warning("[helpcenter] 미등록 plan_code — 등급 미상으로 처리합니다: %s", plan_code)
        return None
    return {
        "plan_code": plan_code,
        "normalized": normalized,
        "sector": hit["sector"],
        "level": hit["level"],
    }


def resolve_for_company(company_id: Optional[str]) -> Dict[str, Any]:
    """company_id → 활성 계약 → 등급. 반환은 항상 dict, 모르면 level 이 None 이다.

    반환: {level, sector, plan_code, reason}
      reason 은 level 이 None 인 사유다 — no_company / no_contract / unmapped_plan.
    """
    empty = {"level": None, "sector": None, "plan_code": None, "reason": "no_company"}
    if not company_id:
        return empty

    try:
        sb = get_supabase()
        res = (
            sb.table("contracts")
            .select("plan_code, status_code, is_active, end_date, created_at")
            .eq("company_id", company_id)
            .eq("is_active", True)
            .in_("status_code", list(_ACTIVE_STATUS))
            .order("created_at", desc=True)
            .limit(10)
            .execute()
        )
    except Exception as e:  # noqa: BLE001
        log.error("[helpcenter] 계약 조회 실패 company_id=%s: %s", company_id, e)
        return {**empty, "reason": "no_contract"}

    rows = res.data or []
    if not rows:
        return {**empty, "reason": "no_contract"}

    today = date.today().isoformat()
    # 만료되지 않은 계약을 먼저 본다. end_date 가 비어 있으면 만료 판단 근거가 없으므로 유효로 본다.
    rows.sort(key=lambda r: (r.get("end_date") or "9999-12-31") >= today, reverse=True)

    best: Optional[Dict[str, Any]] = None
    for row in rows:
        info = level_of_plan(row.get("plan_code"))
        if info and (best is None or info["level"] > best["level"]):
            best = info

    if not best:
        return {
            "level": None,
            "sector": None,
            "plan_code": rows[0].get("plan_code"),
            "reason": "unmapped_plan",
        }

    return {
        "level": best["level"],
        "sector": best["sector"],
        "plan_code": best["plan_code"],
        "reason": None,
    }
