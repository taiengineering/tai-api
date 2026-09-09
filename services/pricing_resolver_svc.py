"""price_master 조회 + 기준값 플랜 산정 (순수 서비스).

WO-COMMON-TIER-PAYMENT-GATE-MODULARIZE-001 / B1.
routers/public_pricing.py 의 _load / resolve_price 본문을 이관. 로직 변경 0.
라우터/HTTP 의존 없음 — supabase 는 호출측에서 주입한다.
"""

PRICE_MASTER_FIELDS = (
    "id, service_type, sector, tier_code, criteria_type, criteria_min, criteria_max,"
    "amount, vat_included, vat_rate, billing_unit, display_name, sub_label, icon,"
    "is_recommended, is_active, sort_order"
)


def load_prices(supabase, service_type, sector=None) -> list:
    """price_master에서 service_type(+sector) 활성 행을 features와 함께 로드."""
    q = (
        supabase.table("price_master")
        .select(PRICE_MASTER_FIELDS)
        .eq("service_type", service_type)
        .eq("is_active", True)
    )
    if sector:
        q = q.eq("sector", sector.upper())
    rows = q.order("sort_order").execute().data or []

    ids = [r["id"] for r in rows]
    feat_map: dict = {}
    if ids:
        feats = (
            supabase.table("price_service_feature")
            .select("price_id, feature_text, feature_type, icon, sort_order, is_active")
            .in_("price_id", ids)
            .eq("is_active", True)
            .order("sort_order")
            .execute()
            .data or []
        )
        for f in feats:
            feat_map.setdefault(f["price_id"], []).append(f["feature_text"])

    for r in rows:
        r["features"] = feat_map.get(r["id"], [])
    return rows


def resolve_plan(supabase, service_type, sector, value=None) -> dict:
    """기준값으로 적용 플랜을 산정.

    - service_type: DIAGNOSIS / SAAS
    - sector: BUILDING(연면적) / INDUSTRY(근로자수) / CONSTRUCTION(공사금액)
    - value: 기준값. criteria_min <= value < criteria_max 인 행을 반환(FLAT은 value 무관).
    """
    rows = load_prices(supabase, service_type.upper(), sector.upper())
    if not rows:
        return {"status": "not_found", "data": None}

    if value is None:
        # 기준값 미입력 → 추천 우선, 없으면 첫 행
        chosen = next((r for r in rows if r.get("is_recommended")), rows[0])
        return {"status": "success", "data": chosen, "matched_by": "default"}

    match = None
    for r in rows:
        cmin = r.get("criteria_min")
        cmax = r.get("criteria_max")
        lo_ok = cmin is None or value >= float(cmin)
        hi_ok = cmax is None or value < float(cmax)
        if r.get("criteria_type") == "FLAT":
            continue
        if lo_ok and hi_ok:
            match = r
            break
    if match is None:
        # 구간 초과 시 FLAT(맞춤) 또는 마지막 행
        match = next((r for r in rows if r.get("criteria_type") == "FLAT"), rows[-1])
    return {"status": "success", "data": match, "matched_by": "criteria"}
