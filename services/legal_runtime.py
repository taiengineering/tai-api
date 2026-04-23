from __future__ import annotations

from datetime import date, timedelta

from services.legal_helpers import _to_float
from services.legal_format import build_result
from services.legal_helpers import get_sector_groups
from services.legal_rules import _determine_risk_level, _evaluate_condition, _evaluate_conditions
from services.legal_article_loader import fetch_article_contexts


def _save_diagnosis_result(supabase, factory_id: str, sector: str, stage: int, input_data: dict, matched_rules: list) -> dict:
    """
    진단 결과를 factory_diagnosis_results 테이블에 저장.
    
    v5.8.0 (2026-04-23): 조문 본문 포함
      - rule_article_mapping 통해 각 rule의 article_text 배치 조회
      - result_data.rules[].article_text, article_internal_key 추가
      - 베테랑이 조문 본문을 바로 확인 가능
    """
    try:
        supabase.table("factory_diagnosis_results").update({"is_latest": False}).eq("factory_id", factory_id).eq("is_latest", True).execute()
    except Exception:
        pass
    
    # v5.8.0: 조문 본문 배치 조회
    rule_ids = [r.get("rule_id") for r in matched_rules if r.get("rule_id")]
    article_ctx = fetch_article_contexts(supabase, rule_ids) if rule_ids else {}
    
    law_categories = list(dict.fromkeys(r.get("law_name", "") for r in matched_rules if r.get("law_name")))
    key_obligations = [r.get("remarks") or r.get("obligation_summary") or r.get("rule_name", "") for r in matched_rules[:5]]
    has_appointment = any(r.get("rule_type") == "APPOINTMENT" or r.get("appointment_required") for r in matched_rules)
    
    # v5.8.0: rules 리스트에 조문 본문 포함
    rules_with_article = []
    for r in matched_rules:
        rid = r.get("rule_code") or r.get("rule_id") or ""
        # rule_id(표시용) vs rule_id(매핑 키) 분리 주의
        mapping_key = r.get("rule_id") or rid
        art = article_ctx.get(mapping_key) or {}
        rules_with_article.append({
            "rule_code":             rid,
            "rule_name":             r.get("remarks") or r.get("rule_name") or r.get("obligation_summary", ""),
            "law_name":              r.get("law_name", ""),
            "law_article":           r.get("law_article", ""),
            "obligation":            r.get("remarks") or r.get("obligation_summary") or r.get("rule_name", ""),
            "rule_type":             r.get("rule_type") or str(r.get("rule_type_code", "")),
            "stage":                 r.get("diagnosis_stage", 1),
            # v5.8.0 조문 본문 필드
            "article_id":            art.get("article_id"),
            "article_internal_key":  art.get("article_internal_key", ""),
            "article_title":         art.get("article_title", ""),
            "article_text":          art.get("article_text", ""),
            "article_type":          art.get("article_type", ""),
            "law_system":            art.get("law_system", "NOT_MAPPED"),
            "has_article_text":      bool(art.get("article_text")),
        })
    
    result_data = {
        "applicable_law_categories": law_categories,
        "appointment_required": has_appointment,
        "key_obligations": key_obligations,
        "risk_level": _determine_risk_level(len(matched_rules)),
        "rules": rules_with_article,
        # v5.8.0 메타
        "article_mapping_stats": {
            "total_rules": len(matched_rules),
            "mapped_rules": sum(1 for r in rules_with_article if r["has_article_text"]),
            "coverage_pct": round(
                (sum(1 for r in rules_with_article if r["has_article_text"]) * 100.0 / len(matched_rules))
                if matched_rules else 0, 1
            ),
        },
    }
    try:
        res = (
            supabase.table("factory_diagnosis_results")
            .insert(
                {
                    "factory_id": factory_id,
                    "sector": sector,
                    "diagnosis_stage": stage,
                    "input_data": input_data,
                    "result_data": result_data,
                    "rule_count": len(matched_rules),
                    "is_latest": True,
                }
            )
            .execute()
        )
        return res.data[0] if res.data else {}
    except Exception as e:
        print(f"[DIAGNOSIS] 결과 저장 실패: {e}")
        return {"result_data": result_data}


def _create_report_events_from_rules(supabase, factory_id: str, matched_rules: list):
    for rule in matched_rules:
        form_code = rule.get("form_code")
        if not form_code:
            continue
        try:
            if (
                supabase.table("report_events")
                .select("id")
                .eq("factory_id", factory_id)
                .eq("form_code", form_code)
                .eq("status", "PENDING")
                .execute()
                .data
            ):
                continue
        except Exception:
            pass
        due_days = rule.get("due_days") or 14
        try:
            supabase.table("report_events").insert(
                {
                    "factory_id": factory_id,
                    "rule_code": rule.get("rule_code") or rule.get("rule_id"),
                    "form_code": form_code,
                    "trigger_date": date.today().isoformat(),
                    "due_date": (date.today() + timedelta(days=due_days)).isoformat(),
                    "status": "PENDING",
                }
            ).execute()
        except Exception as e:
            print(f"[DIAGNOSIS] report_events 생성 실패: {e}")


async def _evaluate_equipment_conditions(factory_id, factory_context, rules, supabase):
    eq_res = (
        supabase.table("equipment_assets")
        .select("equipment_type_code, quantity, capacity_value")
        .eq("factory_id", factory_id)
        .execute()
    )
    extra = dict(factory_context)
    for eq in (eq_res.data or []):
        tc = eq.get("equipment_type_code", "")
        if tc in ("elevator", "elev"):
            extra["elevator_count"] = max(extra.get("elevator_count", 0), 1)
        elif tc == "boiler":
            extra["boiler_capacity_kw"] = max(extra.get("boiler_capacity_kw", 0), _to_float(eq.get("capacity_value")) or 1)
        elif tc in ("gas", "gas_tank"):
            extra["gas_capacity_kg"] = max(extra.get("gas_capacity_kg", 0), 1)
        elif tc in ("hazmat", "chemical"):
            extra["is_hazardous_material"] = 1
        elif tc in ("electric", "transformer"):
            cap = _to_float(eq.get("capacity_value"))
            if cap:
                extra["electrical_capacity_kw"] = max(extra.get("electrical_capacity_kw", 0), cap)
                extra["transformer_capacity_kva"] = max(extra.get("transformer_capacity_kva", 0), cap)
    matched = [r for r in rules if _evaluate_condition(r, extra)]
    not_matched = [r for r in rules if r not in matched]
    return matched, not_matched


async def _evaluate_process_conditions(factory_id, factory_context, rules, supabase):
    proc_res = supabase.table("factory_process").select("process_id, source").eq("factory_id", factory_id).eq("is_active", True).execute()
    process_ids = [r["process_id"] for r in (proc_res.data or []) if r.get("source") != "MANUAL"]
    if not process_ids:
        return [], rules
    eq_res = (
        supabase.table("v_equipment_unified")
        .select("facility_name_std, match_band")
        .in_("process_id", process_ids)
        .in_("match_band", ["MUST", "CORE"])
        .execute()
    )
    inferred = set(r["facility_name_std"] for r in (eq_res.data or []))
    extra = dict(factory_context)
    for name in inferred:
        nl = name.lower()
        if "승강기" in nl or "엘리베이터" in nl:
            extra["elevator_count"] = max(extra.get("elevator_count", 0), 1)
        if "보일러" in nl:
            extra["boiler_capacity_kw"] = max(extra.get("boiler_capacity_kw", 0), 1)
        if "가스" in nl:
            extra["gas_capacity_kg"] = max(extra.get("gas_capacity_kg", 0), 1)
        if "위험물" in nl or "화학" in nl:
            extra["is_hazardous_material"] = 1
    matched = [r for r in rules if _evaluate_condition(r, extra)]
    not_matched = [r for r in rules if r not in matched]
    return matched, not_matched


async def run_apply_engine_runtime(
    supabase,
    factory_id: str,
    mode: str,
    engine_version: str,
    now_iso_fn,
    factory_to_context_fn,
    get_effective_worker_count_fn,
    get_construction_amount_threshold_fn,
):
    """
    v5.8.0: build_result 호출 시 supabase 전달하여 조문 본문 포함.
    """
    if mode not in ("facility", "process", "equipment", "all"):
        raise ValueError("mode는 facility/process/equipment/all 중 하나여야 합니다.")
    fac_res = supabase.table("factories").select("*").eq("id", factory_id).single().execute()
    if not fac_res.data:
        raise LookupError("시설을 찾을 수 없습니다.")
    factory = fac_res.data
    sector_groups = get_sector_groups(str(factory.get("sector") or "BUILDING").upper())
    all_rules = supabase.table("master_building_legal_rules").select("*").eq("is_active", True).in_("sector", sector_groups).execute().data or []
    evaluated_at = now_iso_fn()
    context = factory_to_context_fn(factory)
    triggered_by_source = {"factory_condition": 0, "registered_equipment": 0, "process_recommended": 0, "sector_groups": sector_groups}
    sec = str(factory.get("sector") or factory.get("site_type") or "").upper()
    if sec == "CONSTRUCTION":
        triggered_by_source.update(
            {
                "construction_type": factory.get("construction_type"),
                "total_worker_count": get_effective_worker_count_fn(factory),
                "subcontractor_count": int(factory.get("subcontractor_worker_count") or 0),
                "threshold_used": get_construction_amount_threshold_fn(factory),
            }
        )
    if mode == "facility":
        applicable, not_applicable = _evaluate_conditions(context, all_rules)
        triggered_by_source["factory_condition"] = len(applicable)
        source_pairs = None
    elif mode == "process":
        applicable, not_applicable = await _evaluate_process_conditions(factory_id, context, all_rules, supabase)
        triggered_by_source["process_recommended"] = len(applicable)
        source_pairs = None
    elif mode == "equipment":
        applicable, not_applicable = await _evaluate_equipment_conditions(factory_id, context, all_rules, supabase)
        triggered_by_source["registered_equipment"] = len(applicable)
        source_pairs = None
    else:
        fac_app, _ = _evaluate_conditions(context, all_rules)
        eq_app, _ = await _evaluate_equipment_conditions(factory_id, context, all_rules, supabase)
        proc_app, _ = await _evaluate_process_conditions(factory_id, context, all_rules, supabase)
        triggered_by_source["factory_condition"] = len(fac_app)
        triggered_by_source["registered_equipment"] = len(eq_app)
        triggered_by_source["process_recommended"] = len(proc_app)
        rule_map = {}
        for r in fac_app:
            rule_map[r["rule_id"]] = (r, "🏢 시설조건")
        for r in eq_app:
            rule_map.setdefault(r["rule_id"], (r, "⚙️ 등록설비"))
        for r in proc_app:
            rule_map.setdefault(r["rule_id"], (r, "🔄 공정추천"))
        source_pairs = list(rule_map.values())
        applicable_ids = {r["rule_id"] for r, _ in source_pairs}
        not_applicable = [r for r in all_rules if r["rule_id"] not in applicable_ids]
        applicable = []
    
    # v5.8.0: build_result에 supabase 전달 (조문 본문 조회)
    result_for_db = build_result(
        applicable, not_applicable, all_rules, mode, evaluated_at, engine_version,
        source_pairs=source_pairs, include_not_applicable=True,
        factory_id=factory_id, triggered_by_source=triggered_by_source,
        supabase=supabase,
    )
    result_for_response = build_result(
        applicable, not_applicable, all_rules, mode, evaluated_at, engine_version,
        source_pairs=source_pairs, include_not_applicable=False,
        factory_id=factory_id, triggered_by_source=triggered_by_source,
        supabase=supabase,
    )
    try:
        supabase.table("factories").update({"legal_result_json": result_for_db, "last_diagnosis_at": evaluated_at, "diagnosis_status": "DONE", "legal_applicable_count": result_for_db.get("applicable_count", 0), "updated_at": evaluated_at}).eq("id", factory_id).execute()
    except Exception as e:
        print(f"[LEGAL ENGINE] factories 저장 실패: {e}")
    try:
        supabase.table("legal_applications").upsert({"factory_id": factory_id, "engine_version": engine_version, "mode": mode, "result_json": result_for_db, "evaluated_at": evaluated_at}, on_conflict="factory_id,mode").execute()
    except Exception as e:
        print(f"[LEGAL ENGINE] legal_applications 저장 실패 (무시): {e}")
    return {"status": "success", "data": result_for_response}


def run_apply_quote_runtime(supabase, quote_id: str, engine_version: str, parse_survey_data_fn, survey_to_context_fn, now_iso_fn):
    """v5.8.0: build_result에 supabase 전달."""
    qres = supabase.table("quotes").select("id, quote_no, survey_data").eq("id", quote_id).single().execute()
    if not qres.data:
        raise LookupError("견적을 찾을 수 없습니다.")
    sd = parse_survey_data_fn(qres.data.get("survey_data"))
    if not sd:
        raise ValueError("survey_data가 없습니다.")
    context = survey_to_context_fn(sd)
    all_rules = supabase.table("master_building_legal_rules").select("*").eq("is_active", True).execute().data or []
    evaluated_at = now_iso_fn()
    applicable, not_applicable = _evaluate_conditions(context, all_rules)
    result_data = build_result(
        applicable, not_applicable, all_rules, "facility", evaluated_at, engine_version,
        include_not_applicable=False,
        quote_id=quote_id, quote_no=qres.data.get("quote_no"), source="quote_survey",
        not_applicable_total=len(not_applicable),
        triggered_by_source={"factory_condition": len(applicable)},
        supabase=supabase,
    )
    try:
        supabase.table("quotes").update({"legal_result_json": result_data, "legal_evaluated_at": evaluated_at, "legal_applicable_count": result_data["applicable_count"], "updated_at": evaluated_at}).eq("id", quote_id).execute()
    except Exception as e:
        print(f"[LEGAL ENGINE] quotes 저장 실패: {e}")
    return {"status": "success", "data": result_data}
