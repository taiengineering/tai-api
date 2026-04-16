"""
inspection_sets 자동 생성 모듈 — v1.0.1
==========================================
v1.0.1 (2026-04-16):
  - inspection_cycle_unit_code OR inspection_cycle_code 두 필드 모두 지원
    (construction.py _run_diagnosis의 raw rules 및
     legal_engine.py format_rule_result_db() 교 모두 수용)

v1.0.0 (2026-04-15):
  BE-1: diagnose/step1 완료 시 inspection_sets 자동 생성
  - master_building_legal_rules의 inspection_required / obligation_type 기준으로
    inspection_sets 레코드를 자동 생성
  - 중복 생성 방지 (legal_rule_id 기준)
  - obligation_type 정확히 반영 (INSPECT / BEFORE_WORK 구분)
"""
from typing import List, Dict, Any, Optional

# legal_engine.py에서 사용하는 공용 상수 재사용
CYCLE_CODE_MAP = {
    "001": ("day",   1),
    "002": ("week",  1),
    "003": ("month", 1),
    "004": ("month", 3),
    "005": ("month", 6),
    "006": ("year",  1),
    "007": ("year",  2),
    "008": ("year",  5),
    "009": ("year",  4),
    "010": ("year",  3),
    "011": ("year",  3),
    "012": ("year", 10),
    "013": ("year",  5),
}

CYCLE_UNIT_LABEL = {
    "year":  "년",
    "month": "개월",
    "week":  "주",
    "day":   "일",
}


def _get_schedule_type_raw(rule: dict) -> str:
    """raw DB 룰(master_building_legal_rules)에서 schedule_type 판단"""
    if rule.get("inspection_cycle_unit_code") or rule.get("inspection_cycle_code"):
        return "PERIODIC"
    if rule.get("construction_work_type"):
        return "BEFORE_WORK"
    return "ON_DEMAND"


def auto_create_inspection_sets_from_diagnosis(
    supabase,
    factory_id: str,
    company_id: Optional[str],
    applicable_rules: List[Dict[str, Any]],
) -> int:
    """
    법령 진단(diagnose/step1) 완료 시 inspection_sets 자동 생성.

    대상 룰:
      - inspection_required = True
      - 또는 obligation_type IN ('INSPECT', 'BEFORE_WORK')

    중복 생성 방지:
      - factory_id + source='LEGAL_ENGINE' + legal_rule_id 기준으로 기존 레코드 확인

    입력 호환성:
      - raw DB 룰 (master_building_legal_rules 레코드)
      - format_rule_result_db() 처리된 포맷단 모두 수용
        (inspection_cycle_unit_code OR inspection_cycle_code, rule_id OR id)

    Returns:
        생성된 레코드 수
    """
    # 1. 점검 의무 대상 필터
    insp_rules = [
        r for r in applicable_rules
        if r.get("inspection_required")
        or (r.get("obligation_type") or "").upper() in ("INSPECT", "BEFORE_WORK")
    ]
    if not insp_rules:
        return 0

    # 2. 기존 inspection_sets 확인 (중복 방지)
    try:
        existing_res = (
            supabase.table("inspection_sets")
            .select("legal_rule_id")
            .eq("factory_id", factory_id)
            .eq("source", "LEGAL_ENGINE")
            .eq("is_active", True)
            .execute()
        )
        existing_rule_ids = {
            r["legal_rule_id"]
            for r in (existing_res.data or [])
            if r.get("legal_rule_id")
        }
    except Exception as e:
        print(f"[AUTO_INSPECT_SETS] 기존 레코드 조회 실패: {e}")
        existing_rule_ids = set()

    # 3. 삽입 데이터 구성
    insert_rows = []
    for rule in insp_rules:
        # rule_id: raw rule은 rule_id, 포맷단도 rule_id 지원 (id fallback)
        rule_id = str(
            rule.get("rule_id") or rule.get("id") or ""
        ).strip()
        if not rule_id or rule_id in existing_rule_ids:
            continue

        law_name        = rule.get("law_name") or ""
        obligation_type = (rule.get("obligation_type") or "INSPECT").upper()
        # v1.0.1: inspection_cycle_unit_code(raw) OR inspection_cycle_code(formatted) 두 지월
        cycle_code      = (
            rule.get("inspection_cycle_unit_code")
            or rule.get("inspection_cycle_code")
            or ""
        )
        cycle_unit, cycle_value = CYCLE_CODE_MAP.get(cycle_code, ("year", 1))
        schedule_type   = _get_schedule_type_raw(rule)
        unit_label      = CYCLE_UNIT_LABEL.get(cycle_unit, "")
        description     = (
            rule.get("obligation_summary")
            or rule.get("description")
            or rule.get("remarks")
            or ""
        ).strip()

        cycle_guide = (
            f"마지막 점검일로부터 {cycle_value}{unit_label}마다"
            if schedule_type == "PERIODIC"
            else f"작업({rule.get('construction_work_type') or ''}) 시작 전 실시"
        )

        insert_rows.append({
            "company_id":           company_id,
            "factory_id":           factory_id,
            "inspection_set_name":  f"{law_name} 점검",
            "inspection_set_code":  rule_id,
            "legal_rule_id":        rule_id,
            "law_name":             law_name,
            "law_article":          rule.get("law_article") or "",
            "cycle_unit":           cycle_unit,
            "cycle_value":          cycle_value,
            "cycle_base_type":      "LAST_INSPECTION",
            "cycle_base_guide":     cycle_guide,
            "description":          description,
            "obligation_type":      obligation_type,
            "obligation_summary":   description,
            "source":               "LEGAL_ENGINE",
            "is_active":            True,
            "anchor_confirmed":     False,
            "status_code":          "PENDING_ANCHOR",
        })

    if not insert_rows:
        print(
            f"[AUTO_INSPECT_SETS] factory={factory_id} 신규 생성 대상 없음 "
            f"(기존={len(existing_rule_ids)}개)"
        )
        return 0

    # 4. 배치 삽입 (20건씩)
    created = 0
    for i in range(0, len(insert_rows), 20):
        batch = insert_rows[i:i + 20]
        try:
            res = supabase.table("inspection_sets").insert(batch).execute()
            created += len(res.data or [])
        except Exception as e:
            print(f"[AUTO_INSPECT_SETS] 배치 {i // 20 + 1} 삽입 실패: {e}")

    print(
        f"[AUTO_INSPECT_SETS] factory={factory_id} "
        f"생성={created}개 / 대상={len(insp_rules)}건 / 기존={len(existing_rule_ids)}건"
    )
    return created
