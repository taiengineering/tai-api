from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.legal_article_loader import fetch_article_contexts


def build_step1_result_data(
    sector_raw: str,
    sector_groups,
    engine_version: str,
    evaluated_at: str,
    facility_ctx,
    applicable,
    not_applicable,
    classify_rules_db_fn,
    format_rule_result_db_fn,
    risk_level_fn,
    construction_summary_fn,
    supabase=None,  # v5.8.0: 조문 본문 조회용
):
    """
    v5.8.0 (2026-04-23): supabase 전달 시 조문 본문 자동 포함.
      - applicable rules의 rule_id들을 배치 조회
      - classify_rules_db_fn에 article_contexts 주입
      - not_applicable은 본문 불필요 (조문 매칭 안 됨)
    """
    triggered: Dict[str, List] = {"appointment": [], "inspection": [], "notify": [], "report": [], "action": [], "not_applicable": []}
    
    # v5.8.0: 조문 본문 배치 조회
    article_ctx: Optional[Dict[str, Any]] = None
    if supabase is not None:
        try:
            rule_ids = [r.get("rule_id") for r in applicable if r.get("rule_id")]
            if rule_ids:
                article_ctx = fetch_article_contexts(supabase, rule_ids)
        except Exception as e:
            print(f"[STEP1_BUILDER] 조문 본문 조회 실패 (무시): {e}")
            article_ctx = None
    
    # article_contexts 주입 (있으면)
    try:
        classify_rules_db_fn(applicable, triggered, article_ctx)
    except TypeError:
        # 하위 호환: article_contexts 파라미터 없는 구 함수
        classify_rules_db_fn(applicable, triggered)
    
    for r in not_applicable:
        triggered["not_applicable"].append(format_rule_result_db_fn(r))
    total_applicable = sum(len(triggered[k]) for k in ("appointment", "inspection", "notify", "report", "action"))
    law_names = sorted({x.get("law_name") for x in applicable if x.get("law_name")})
    obligations: List[Dict[str, Any]] = []
    for key, label in [("appointment", "선임"), ("inspection", "점검"), ("action", "조치")]:
        if triggered[key]:
            obligations.append({"category": key, "label": label, "items": triggered[key]})
    if triggered["report"]:
        obligations.append({"category": "report", "label": "신고", "items": triggered["report"]})
    if triggered["notify"]:
        obligations.append({"category": "notify", "label": "보고", "items": triggered["notify"]})
    rules_table: List[Dict[str, Any]] = []
    for key, label in [("appointment", "선임"), ("inspection", "점검"), ("action", "조치")]:
        for row in triggered[key]:
            rules_table.append({"category": label, **row})
    for row in triggered["report"]:
        rules_table.append({"category": "신고", **row})
    for row in triggered["notify"]:
        rules_table.append({"category": "보고", **row})
    appointment_n = len(triggered["appointment"])
    risk = risk_level_fn(total_applicable, appointment_n)
    law_cats: List[str] = []
    seen: set = set()
    for x in applicable:
        c = (x.get("law_category_code") or x.get("law_name") or "").strip()
        if c and c not in seen:
            seen.add(c)
            law_cats.append(c)
    key_obligations: List[str] = []
    for x in applicable[:20]:
        t = (x.get("remarks") or x.get("obligation_summary") or "").strip()
        if t and t not in key_obligations:
            key_obligations.append(t)
    insp_by_type = {
        "PERIODIC": [r for r in triggered["inspection"] if r.get("schedule_type") == "PERIODIC"],
        "BEFORE_WORK": [r for r in triggered["inspection"] if r.get("schedule_type") == "BEFORE_WORK"],
        "ON_DEMAND": [r for r in triggered["inspection"] if r.get("schedule_type") == "ON_DEMAND"],
    }
    all_items_flat = triggered["appointment"] + triggered["inspection"] + triggered["action"] + triggered["report"] + triggered["notify"]
    urgent_count = len([r for r in all_items_flat if (r.get("due_info") or {}).get("urgency") == "URGENT"])
    max_pen = next(
        (
            r.get("penalty_summary") or r.get("penalty_amount") or ""
            for r in all_items_flat
            if (r.get("penalty_summary") or r.get("penalty_amount") or "").strip()
            and "확인 필요" not in (r.get("penalty_summary") or "")
            and "부과 가능" not in (r.get("penalty_summary") or "")
        ),
        "",
    )
    risk_reason = f"적용 법령 {len(law_names)}개, 법적 의무 {total_applicable}건"
    if urgent_count > 0:
        risk_reason += f", 긴급 이행 {urgent_count}건"
    if max_pen:
        risk_reason += f", 최대 {max_pen}"
    
    # v5.8.0: 조문 매핑 통계 추가
    mapped_count = sum(1 for item in all_items_flat if item.get("has_article_text"))
    article_mapping_stats = {
        "total_rules": total_applicable,
        "mapped_rules": mapped_count,
        "coverage_pct": round(mapped_count * 100.0 / total_applicable, 1) if total_applicable else 0,
    }
    
    result_data = {
        "sector": sector_raw,
        "sector_groups": sector_groups,
        "step": 1,
        "engine_version": engine_version,
        "evaluated_at": evaluated_at,
        "facility_context": facility_ctx,
        "risk_level": risk,
        "risk_reason": risk_reason,
        "applicable_law_categories": law_cats,
        "appointment_required_flag": appointment_n > 0,
        "key_obligations": key_obligations,
        "law_badges": law_names,
        "obligations": obligations,
        "rules_table": rules_table,
        "appointment_required": triggered["appointment"],
        "inspection_required": triggered["inspection"],
        "action_required": triggered["action"],
        "report_required": triggered["report"] + triggered["notify"],
        "not_applicable": triggered["not_applicable"][:100],
        "not_applicable_total": len(not_applicable),
        "total_rules_checked": len(applicable) + len(not_applicable),
        "applicable_count": total_applicable,
        "article_mapping_stats": article_mapping_stats,  # v5.8.0
        "inspection_schedule_ready": {
            "periodic_count": len(insp_by_type["PERIODIC"]),
            "before_work_count": len(insp_by_type["BEFORE_WORK"]),
            "on_demand_count": len(insp_by_type["ON_DEMAND"]),
            "periodic": insp_by_type["PERIODIC"],
            "before_work": insp_by_type["BEFORE_WORK"],
        },
        "summary": {
            "total": total_applicable,
            "appointment": len(triggered["appointment"]),
            "inspection": len(triggered["inspection"]),
            "action": len(triggered["action"]),
            "report": len(triggered["report"]),
            "notify": len(triggered["notify"]),
            "form_linked": sum(1 for r in applicable if (r.get("form_code") or "").strip()),
        },
    }
    if sector_raw == "CONSTRUCTION":
        result_data["construction_summary"] = construction_summary_fn(facility_ctx)
    return result_data
