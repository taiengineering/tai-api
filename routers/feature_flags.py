"""
섹터 × 플랜 Feature Flag 라우터 — v1.0.0
prefix: /feature-flags

API:
  GET /feature-flags?sector=CONSTRUCTION&plan=BUSINESS
    → open:   섹터 일치 + 플랜 충족 (즉시 사용 가능)
    → locked: 섹터 일치, 플랜 부족 (업그레이드 유도)
    → hidden: 섹터 불일치 (완전 숨김)

플랜 순서: STARTER(1) < BUSINESS(2) < ENTERPRISE(3) < CUSTOM(4)
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from db.supabase_client import get_supabase

router = APIRouter(prefix="/feature-flags", tags=["Feature Flags"])

PLAN_ORDER = {
    'STARTER':    1,
    'BUSINESS':   2,
    'ENTERPRISE': 3,
    'CUSTOM':     4,
}

VALID_SECTORS = frozenset({'BUILDING', 'INDUSTRY', 'CONSTRUCTION', 'SPECIAL'})
VALID_PLANS   = frozenset(PLAN_ORDER.keys())


@router.get("")
async def get_feature_flags(
    sector: str = Query(..., description="BUILDING / INDUSTRY / CONSTRUCTION / SPECIAL"),
    plan:   str = Query(..., description="STARTER / BUSINESS / ENTERPRISE / CUSTOM"),
):
    """
    섹터 + 플랜 기반으로 열린 feature_code 목록 반환.

    - open:   섹터 일치 + 플랜 충족 → 전체 feature 객체 반환
    - locked: 섹터 일치, 플랜 부족  → required_plan 포함 반환
    - hidden: 섹터 불일치            → feature_code 문자열만 반환
    """
    sector_upper = sector.strip().upper()
    plan_upper   = plan.strip().upper()

    if sector_upper not in VALID_SECTORS:
        raise HTTPException(status_code=400,
            detail=f"sector는 {sorted(VALID_SECTORS)} 중 하나여야 합니다.")
    if plan_upper not in VALID_PLANS:
        raise HTTPException(status_code=400,
            detail=f"plan은 {sorted(VALID_PLANS)} 중 하나여야 합니다.")

    plan_order = PLAN_ORDER[plan_upper]

    supabase = get_supabase()
    res = supabase.table('factory_features') \
        .select('feature_code,feature_name,feature_desc,sector,'
                'min_plan_order,menu_path,menu_group,sort_order') \
        .eq('is_active', True) \
        .order('sort_order') \
        .execute()

    features = res.data or []
    result   = {'open': [], 'locked': [], 'hidden': []}

    # plan 코드 역매핑 (min_plan_order → plan 이름)
    order_to_plan = {v: k for k, v in PLAN_ORDER.items()}

    for f in features:
        f_sector = f.get('sector', 'ALL')
        f_min    = f.get('min_plan_order', 1)

        sector_match = (f_sector == 'ALL' or f_sector == sector_upper)

        if not sector_match:
            # 섹터 불일치: feature_code만 hidden 목록에
            result['hidden'].append(f['feature_code'])
        elif plan_order >= f_min:
            # 플랜 충족: 전체 객체 open 목록에
            result['open'].append(f)
        else:
            # 플랜 부족: required_plan 추가 후 locked 목록에
            result['locked'].append({
                **f,
                'required_plan': order_to_plan.get(f_min, f'PLAN_{f_min}'),
            })

    return {
        'status': 'success',
        'data': {
            'sector':       sector_upper,
            'plan':         plan_upper,
            'plan_order':   plan_order,
            'open_count':   len(result['open']),
            'locked_count': len(result['locked']),
            'hidden_count': len(result['hidden']),
            **result,
        },
    }


@router.get("/all")
async def get_all_features(
    sector: Optional[str] = Query(None, description="필터링할 섹터 (생략 시 전체)"),
):
    """
    factory_features 전체 목록 조회 (관리자·개발용).
    sector 지정 시 해당 섹터 + ALL만 반환.
    """
    supabase = get_supabase()
    q = supabase.table('factory_features') \
        .select('*') \
        .order('sort_order')

    if sector:
        sector_upper = sector.strip().upper()
        q = q.in_('sector', ['ALL', sector_upper])

    res = q.execute()
    return {
        'status': 'success',
        'data':   {'items': res.data or [], 'total': len(res.data or [])},
    }
