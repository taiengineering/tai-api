"""
법령 엔진 QA 자동 진단 라우터
============================
POST /legal-engine/qa-run
  - 4개 섹터 × 정방향/역방향 테스트 케이스 자동 실행
  - 조건 정확도, 섹터 격리, 선임 방향성 점수 산출
  - 문제 룰(condition=NULL APPOINT, 섹터 혼입) 자동 감지
"""
from fastapi import APIRouter
from typing import Any, Dict, List
from datetime import datetime

from db.supabase_client import get_supabase

router = APIRouter(prefix="/legal-engine", tags=["엔진QA"])

QA_VERSION = "1.1.0"  # v1.1.0: 전체 커버 시 100점, DB이슈 감점 방식

# ══════════════════════════════════════════════
# 테스트 케이스 정의
# ══════════════════════════════════════════════

QA_TEST_CASES: List[Dict[str, Any]] = [

    # ─────────────── BUILDING ───────────────
    {"id": "BLD-F1", "sector": "BUILDING", "direction": "forward",
     "label": "대형건물: 5000㎡+200명+300kW+위험물",
     "input": {"total_floor_area": 5000, "worker_count": 200, "electric_capacity": 300,
                "has_hazardous_material": True, "has_high_pressure_gas": True},
     "expect": {"appoint_min": 3},
     "note": "전기안전관리자+소방안전관리자+위험물안전관리자 이상 선임"},

    {"id": "BLD-F2", "sector": "BUILDING", "direction": "forward",
     "label": "중형건물: 1000㎡+100명+75kW",
     "input": {"total_floor_area": 1000, "worker_count": 100, "electric_capacity": 75},
     "expect": {"appoint_min": 1},
     "note": "전기안전관리자 이상 선임"},

    {"id": "BLD-R1", "sector": "BUILDING", "direction": "reverse",
     "label": "초소형: 100㎡+5명+5kW",
     "input": {"total_floor_area": 100, "worker_count": 5, "electric_capacity": 5},
     "expect": {"appoint_max": 0},
     "note": "모든 조건 기준 미달 — 선임 0"},

    {"id": "BLD-R2", "sector": "BUILDING", "direction": "reverse",
     "label": "빈 입력",
     "input": {},
     "expect": {"appoint_max": 0},
     "note": "아무 입력 없음 — 선임 0"},

    # ─────────────── MANUFACTURING ───────────────
    {"id": "MFG-F1", "sector": "MANUFACTURING", "direction": "forward",
     "label": "대형공장: 300명+위험물+가스+에너지+면적15000",
     "input": {"worker_count": 300, "electric_capacity": 500,
                "has_hazardous_material": True, "has_high_pressure_gas": True,
                "is_factory_registered": True, "annual_energy_toe": 2000,
                "gas_capacity_m3": 100, "building_area": 15000},
     "expect": {"appoint_min": 5},
     "note": "안전관리자+보건관리자+에너지관리자+소방안전관리자+위험물안전관리자"},

    {"id": "MFG-F2", "sector": "MANUFACTURING", "direction": "forward",
     "label": "중형공장: 50명+100kW",
     "input": {"worker_count": 50, "electric_capacity": 100},
     "expect": {"appoint_min": 1},
     "note": "안전관리자 선임 기준(50인 이상 위험업종)"},

    {"id": "MFG-F3", "sector": "MANUFACTURING", "direction": "forward",
     "label": "소형공장: 30명+위험물",
     "input": {"worker_count": 30, "has_hazardous_material": True},
     "expect": {"appoint_min": 1},
     "note": "위험물안전관리자 발동"},

    {"id": "MFG-R1", "sector": "MANUFACTURING", "direction": "reverse",
     "label": "극소형: 4명+10kW",
     "input": {"worker_count": 4, "electric_capacity": 10},
     "expect": {"appoint_max": 0},
     "note": "모든 선임 기준 미달"},

    {"id": "MFG-R2", "sector": "MANUFACTURING", "direction": "reverse",
     "label": "빈 입력",
     "input": {},
     "expect": {"appoint_max": 0},
     "note": "조건 없음 — 선임 0"},

    # ─────────────── CONSTRUCTION ───────────────
    {"id": "CON-F1", "sector": "CONSTRUCTION", "direction": "forward",
     "label": "대형건축: 200억+300명",
     "input": {"construction_type": "건축", "contract_amount_eok": 200,
                "direct_workers": 200, "subcon_workers": 100},
     "expect": {"appoint_min": 2, "sm_required": True},
     "note": "안전관리자+안전보건관리책임자"},

    {"id": "CON-F2", "sector": "CONSTRUCTION", "direction": "forward",
     "label": "건축 150억+50명 (최소임계)",
     "input": {"construction_type": "건축", "contract_amount_eok": 150,
                "direct_workers": 30, "subcon_workers": 20},
     "expect": {"appoint_min": 1, "sm_required": True},
     "note": "150억 이상 안전관리자 선임"},

    {"id": "CON-F3", "sector": "CONSTRUCTION", "direction": "forward",
     "label": "토목 120억+48명 (금액기준)",
     "input": {"construction_type": "토목", "contract_amount_eok": 120,
                "direct_workers": 30, "subcon_workers": 18},
     "expect": {"appoint_min": 1, "sm_required": True},
     "note": "토목 120억 이상 안전관리자"},

    {"id": "CON-F4", "sector": "CONSTRUCTION", "direction": "forward",
     "label": "50명+0억 (인원기준)",
     "input": {"construction_type": "건축", "contract_amount_eok": 10,
                "direct_workers": 30, "subcon_workers": 20},
     "expect": {"sm_required": True},
     "note": "50명 이상이면 금액 무관 안전관리자"},

    {"id": "CON-R1", "sector": "CONSTRUCTION", "direction": "reverse",
     "label": "건축 149억+49명 (임계 바로 아래)",
     "input": {"construction_type": "건축", "contract_amount_eok": 149,
                "direct_workers": 30, "subcon_workers": 19},
     "expect": {"sm_required": False},
     "note": "149억+49명 — 안전관리자 선임 불필요"},

    {"id": "CON-R2", "sector": "CONSTRUCTION", "direction": "reverse",
     "label": "토목 119억+49명",
     "input": {"construction_type": "토목", "contract_amount_eok": 119,
                "direct_workers": 30, "subcon_workers": 19},
     "expect": {"sm_required": False},
     "note": "토목 119억+49명 — 선임 불필요"},

    {"id": "CON-R3", "sector": "CONSTRUCTION", "direction": "reverse",
     "label": "빈 건설현장 (0억 0명)",
     "input": {"construction_type": "건축", "contract_amount_eok": 0,
                "direct_workers": 0, "subcon_workers": 0},
     "expect": {"appoint_max": 0, "sm_required": False},
     "note": "아무 조건 없음"},

    # ─────────────── SPECIAL_FACILITY ───────────────
    {"id": "SPF-F1", "sector": "SPECIAL_FACILITY", "direction": "forward",
     "label": "대형병원: 병상300+200명+500kW",
     "input": {"hospital_beds": 300, "worker_count": 200,
                "electric_capacity": 500, "total_floor_area": 10000},
     "expect": {"appoint_min": 2},
     "note": "의료기관 안전관리자+소방안전관리자"},

    {"id": "SPF-F2", "sector": "SPECIAL_FACILITY", "direction": "forward",
     "label": "학교: 학생1000명+근로자50",
     "input": {"student_count": 1000, "worker_count": 50, "total_floor_area": 5000},
     "expect": {"appoint_min": 1},
     "note": "학교안전관리자 선임"},

    {"id": "SPF-R1", "sector": "SPECIAL_FACILITY", "direction": "reverse",
     "label": "빈 입력",
     "input": {},
     "expect": {"appoint_max": 0},
     "note": "아무 조건 없음 — 선임 0"},

    {"id": "SPF-R2", "sector": "SPECIAL_FACILITY", "direction": "reverse",
     "label": "극소: 1명+10㎡+병상0+학생0",
     "input": {"worker_count": 1, "total_floor_area": 10,
                "hospital_beds": 0, "student_count": 0},
     "expect": {"appoint_max": 0},
     "note": "모든 기준 미달 — 선임 0"},
]

# ══════════════════════════════════════════════
# DB 품질 진단
# ══════════════════════════════════════════════

def _run_db_quality_checks(supabase) -> List[Dict[str, Any]]:
    """DB에서 직접 데이터 품질 이슈를 탐지"""
    issues = []

    # 1. condition=NULL인 APPOINT 룰 (역방향에서 선임이 잘못 발동될 위험)
    res1 = supabase.table("master_building_legal_rules") \
        .select("rule_id, sector, law_name, law_article, obligation_type") \
        .eq("is_active", True) \
        .eq("diagnosis_stage", 1) \
        .eq("obligation_type", "APPOINT") \
        .is_("condition_code", "null") \
        .execute()
    for r in (res1.data or []):
        issues.append({
            "type": "NULL_CONDITION_APPOINT",
            "severity": "HIGH",
            "rule_id": r["rule_id"],
            "sector": r["sector"],
            "law": f"{r['law_name']} {r['law_article']}",
            "desc": "APPOINT 룰에 condition 없음 → 역방향 오발동 위험"
        })

    # 2. NOTIFY인데 appointment_required=True (분류 혼입 위험)
    res2 = supabase.table("master_building_legal_rules") \
        .select("rule_id, sector, law_name, law_article, obligation_type") \
        .eq("is_active", True) \
        .eq("diagnosis_stage", 1) \
        .eq("obligation_type", "NOTIFY") \
        .eq("appointment_required", True) \
        .is_("condition_code", "null") \
        .execute()
    for r in (res2.data or []):
        issues.append({
            "type": "NOTIFY_AS_APPOINT",
            "severity": "MEDIUM",
            "rule_id": r["rule_id"],
            "sector": r["sector"],
            "law": f"{r['law_name']} {r['law_article']}",
            "desc": "NOTIFY인데 appointment_required=True + condition 없음"
        })

    # 3. 섹터별 룰 분포 불균형 (CONSTRUCTION이 너무 적은지 확인)
    res3 = supabase.table("master_building_legal_rules") \
        .select("sector") \
        .eq("is_active", True) \
        .eq("diagnosis_stage", 1) \
        .execute()
    sector_counts: Dict[str, int] = {}
    for r in (res3.data or []):
        s = r["sector"]
        sector_counts[s] = sector_counts.get(s, 0) + 1

    total = sum(sector_counts.values())
    for sector, cnt in sector_counts.items():
        pct = round(cnt / total * 100, 1) if total else 0
        if sector == "CONSTRUCTION" and cnt < 50:
            issues.append({
                "type": "LOW_RULE_COUNT",
                "severity": "HIGH",
                "rule_id": "-",
                "sector": sector,
                "law": "-",
                "desc": f"CONSTRUCTION 룰이 {cnt}개({pct}%)로 부족 — 건설 법령 수집 필요"
            })

    return issues, sector_counts, total


# ══════════════════════════════════════════════
# 테스트 케이스 실행
# ══════════════════════════════════════════════

def _run_single_test(supabase, tc: Dict[str, Any]) -> Dict[str, Any]:
    """테스트 케이스 1건 실행 — diagnose/step1 로직 직접 호출"""
    from routers.legal_engine import (
        get_sector_groups, _normalize_sector_db,
        _input_to_facility_context, _evaluate_facility_conditions_db,
        _classify_rules_db, format_rule_result_db, _get_construction_summary
    )

    sector_raw = tc["sector"]
    inp = dict(tc["input"])
    expect = tc["expect"]

    # 룰 조회
    sector_db = _normalize_sector_db(sector_raw)
    sector_groups = get_sector_groups(sector_db)
    rules_res = (
        supabase.table("master_building_legal_rules")
        .select("*")
        .eq("is_active", True)
        .in_("sector", sector_groups)
        .eq("diagnosis_stage", 1)
        .execute()
    )
    all_rules = rules_res.data or []

    # 조건 평가
    facility_ctx = _input_to_facility_context(sector_raw, inp)
    applicable, not_applicable = _evaluate_facility_conditions_db(
        facility_ctx, all_rules, sector_raw
    )

    # 분류 (dedup 포함)
    triggered: Dict[str, list] = {
        "appointment": [], "inspection": [], "notify": [],
        "report": [], "action": [], "not_applicable": [],
    }
    _classify_rules_db(applicable, triggered)

    appoint_cnt = len(triggered["appointment"])
    total_applicable = (
        appoint_cnt + len(triggered["inspection"]) +
        len(triggered["notify"]) + len(triggered["report"]) +
        len(triggered["action"])
    )

    # 건설 선임 판정
    sm_required = None
    if sector_raw == "CONSTRUCTION":
        cs = _get_construction_summary(facility_ctx)
        sm_required = cs.get("safety_manager_required")

    # PASS/FAIL 판정
    fail_reasons = []
    if "appoint_min" in expect and appoint_cnt < expect["appoint_min"]:
        fail_reasons.append(f"선임 부족: {appoint_cnt}개 (기대 {expect['appoint_min']}개 이상)")
    if "appoint_max" in expect and appoint_cnt > expect["appoint_max"]:
        fail_reasons.append(f"선임 초과: {appoint_cnt}개 (기대 {expect['appoint_max']}개 이하)")
    if "sm_required" in expect and sm_required != expect["sm_required"]:
        fail_reasons.append(
            f"안전관리자 판정 오류: {sm_required} (기대 {expect['sm_required']})"
        )

    passed = len(fail_reasons) == 0

    return {
        "id":            tc["id"],
        "sector":        sector_raw,
        "direction":     tc["direction"],
        "label":         tc["label"],
        "note":          tc.get("note", ""),
        "passed":        passed,
        "fail_reasons":  fail_reasons,
        "result": {
            "appoint":   appoint_cnt,
            "inspect":   len(triggered["inspection"]),
            "action":    len(triggered["action"]),
            "notify":    len(triggered["notify"]),
            "total":     total_applicable,
            "rules_checked": len(all_rules),
            "sm_required":   sm_required,
        },
        "appoint_rules": [
            {"rule_id": r["rule_id"], "law": r["law_name"], "article": r["law_article"],
             "obligation_type": r["obligation_type"]}
            for r in triggered["appointment"]
        ],
    }


# ══════════════════════════════════════════════
# API 엔드포인트
# ══════════════════════════════════════════════

@router.post("/qa-run")
def run_engine_qa():
    """
    법령 엔진 품질 자동 진단
    - 4개 섹터 × 정방향/역방향 테스트 케이스 실행
    - 전체 커버 시 100점, DB이슈 발생 시 감점
    - DB 데이터 품질 이슈 자동 탐지
    """
    supabase = get_supabase()
    started_at = datetime.now().isoformat()

    # ── 1. 테스트 케이스 실행 ──
    test_results = []
    for tc in QA_TEST_CASES:
        try:
            result = _run_single_test(supabase, tc)
        except Exception as e:
            result = {
                "id": tc["id"], "sector": tc["sector"], "direction": tc["direction"],
                "label": tc["label"], "note": tc.get("note", ""),
                "passed": False, "fail_reasons": [f"실행 오류: {str(e)}"],
                "result": {}, "appoint_rules": []
            }
        test_results.append(result)

    # ── 2. DB 품질 진단 ──
    try:
        db_issues, sector_counts, total_rules = _run_db_quality_checks(supabase)
    except Exception as e:
        db_issues, sector_counts, total_rules = [{"type": "ERROR", "desc": str(e)}], {}, 0

    # ── 3. 점수 계산 (v1.1.0: 전체 커버 시 100점, DB이슈 감점) ──
    total_cases   = len(test_results)
    passed_cases  = sum(1 for r in test_results if r["passed"])
    forward_total = sum(1 for r in test_results if r["direction"] == "forward")
    forward_pass  = sum(1 for r in test_results if r["direction"] == "forward" and r["passed"])
    reverse_total = sum(1 for r in test_results if r["direction"] == "reverse")
    reverse_pass  = sum(1 for r in test_results if r["direction"] == "reverse" and r["passed"])

    high_issues   = sum(1 for i in db_issues if i.get("severity") == "HIGH")
    medium_issues = sum(1 for i in db_issues if i.get("severity") == "MEDIUM")

    # 점수 구성 (v1.1.0):
    # - 전체 커버 시 100점 만점
    # - DB 이슈 감점: HIGH -5점, MEDIUM -2점
    # - 최종 = max(0, 테스트점수 - DB이슈감점)
    test_score  = round(passed_cases / total_cases * 100, 1) if total_cases else 0
    db_deduct   = high_issues * 5 + medium_issues * 2
    total_score = max(0, round(test_score - db_deduct, 1))
    db_score    = max(0, 100 - db_deduct)  # 이슈 없을 때 DB 기준 최대점

    # 섹터별 결과
    sector_summary: Dict[str, Dict] = {}
    for r in test_results:
        s = r["sector"]
        if s not in sector_summary:
            sector_summary[s] = {"total": 0, "passed": 0, "forward": {"total":0,"passed":0},
                                  "reverse": {"total":0,"passed":0}}
        sector_summary[s]["total"] += 1
        sector_summary[s][r["direction"]]["total"] += 1
        if r["passed"]:
            sector_summary[s]["passed"] += 1
            sector_summary[s][r["direction"]]["passed"] += 1

    for s in sector_summary:
        t = sector_summary[s]["total"]
        p = sector_summary[s]["passed"]
        sector_summary[s]["score"] = round(p / t * 100, 1) if t else 0

    return {
        "status": "success",
        "qa_version":  QA_VERSION,
        "started_at":  started_at,
        "finished_at": datetime.now().isoformat(),

        "score": {
            "total":        total_score,
            "grade":        "A" if total_score >= 90 else ("B" if total_score >= 75 else ("C" if total_score >= 60 else "D")),
            "test_score":   test_score,
            "db_deduct":    db_deduct,
            "db_score":     db_score,
            "passed":       passed_cases,
            "total_cases":  total_cases,
            "pass_rate":    round(passed_cases / total_cases * 100, 1) if total_cases else 0,
            "forward_pass": f"{forward_pass}/{forward_total}",
            "reverse_pass": f"{reverse_pass}/{reverse_total}",
        },

        "sector_summary": sector_summary,

        "test_results": test_results,

        "db_quality": {
            "total_active_rules": total_rules,
            "sector_distribution": sector_counts,
            "issues": db_issues,
            "issue_count": {
                "high":   high_issues,
                "medium": medium_issues,
                "total":  len(db_issues)
            }
        },
    }
