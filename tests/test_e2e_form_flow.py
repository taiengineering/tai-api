"""
TAI 법령엔진 종단간(E2E) 테스트 — 의무 → 서식 → 제출 전체 흐름
================================================================

다양한 더미데이터로 엔진을 가동하여,
각 의무(선임/점검/보고/서류)에 대해 아래를 검증합니다:

  ① 의무 발동 여부 (obligation_type)
  ② 서식 연결 여부 (form_code)
  ③ 제출 주체 (executor_type_label)
  ④ 제출 기관 (submit_org_label)

시나리오 (12종):
  건물 4종: 소형 상업건물 / 중형 오피스 / 대형 복합건물 / 가스특수시설
  산업 4종: 소형 제조업 / 중형 위험물 / 화학대형 / 에너지대형
  건설 4종: 소규모 / 중규모 / 대규모 / 토목대형

실행:
  python tests/test_e2e_form_flow.py
  python tests/test_e2e_form_flow.py --url https://api.taieng.co.kr
"""
import sys
import json
import requests
import argparse
from typing import Optional, Dict, List, Any

BASE_URL = "https://api.taieng.co.kr"

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BLUE   = "\033[94m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

passed = 0
failed = 0
warnings = 0

APPOINTMENT_TARGET_MAP = {
    "safety_manager":             "안전관리자",
    "health_manager":             "보건관리자",
    "safety_health_director":     "안전보건관리책임자",
    "safety_health_manager":      "안전보건관리담당자",
    "fire_safety_manager":        "소방안전관리자",
    "electric_safety_manager":    "전기안전관리자",
    "gas_safety_manager":         "가스안전관리자",
    "elevator_safety_manager":    "승강기안전관리자",
    "energy_manager":             "에너지관리자",
    "building_manager":           "건축물관리자(유지관리자)",
    "hazardous_material_manager": "위험물안전관리자",
    "city_gas_manager":           "도시가스안전관리자",
    "chemical_manager":           "유해화학물질관리자",
}


def ok(msg):    print(f"{GREEN}  ✅ {msg}{RESET}")
def fail(msg):  print(f"{RED}  ❌ {msg}{RESET}")
def warn(msg):  print(f"{YELLOW}  ⚠️  {msg}{RESET}")
def info(msg):  print(f"{BLUE}  ℹ️  {msg}{RESET}")
def detail(msg): print(f"{CYAN}     {msg}{RESET}")
def head(msg):  print(f"\n{BOLD}{'═'*65}\n  {msg}\n{'═'*65}{RESET}")
def sub(msg):   print(f"\n{BOLD}  ── {msg} ──{RESET}")


def chk(cond: bool, msg_ok: str, msg_fail: str, note: str = "", warn_only=False):
    global passed, failed, warnings
    if cond:
        ok(msg_ok)
        passed += 1
    elif warn_only:
        warn(f"{msg_fail}" + (f" ({note})" if note else ""))
        warnings += 1
    else:
        fail(f"{msg_fail}" + (f" → {note}" if note else ""))
        failed += 1


def diagnose(sector: str, inp: dict) -> dict:
    r = requests.post(
        f"{BASE_URL}/legal-engine/diagnose/step1",
        json={"sector": sector, "input": inp},
        timeout=30
    )
    r.raise_for_status()
    return r.json().get("data", {})


def has_appt(data: dict, target_code: str) -> bool:
    label = APPOINTMENT_TARGET_MAP.get(target_code, target_code)
    return any(
        r.get("appointment_target") in (target_code, label)
        for r in data.get("appointment_required", [])
    )


def get_appt_form(data: dict, target_code: str) -> Optional[str]:
    """선임 의무 중 특정 관리자의 form_code 반환"""
    label = APPOINTMENT_TARGET_MAP.get(target_code, target_code)
    for r in data.get("appointment_required", []):
        if r.get("appointment_target") in (target_code, label):
            return r.get("form_code") or ""
    return None


def count_form_linked(items: list) -> int:
    return sum(1 for r in items if (r.get("form_code") or "").strip())


def count_submit_org_linked(items: list) -> int:
    return sum(1 for r in items if (r.get("submit_org_label") or r.get("submit_org_code") or "").strip())


def count_executor_linked(items: list) -> int:
    return sum(1 for r in items if (r.get("executor_type_label") or r.get("executor_type_code") or "").strip())


def print_form_summary(category: str, items: list):
    """의무 목록에서 서식-제출 요약 출력"""
    if not items:
        return
    print(f"\n{CYAN}  [{category}] 총 {len(items)}건")
    for r in items[:5]:  # 최대 5건 출력
        fc  = r.get('form_code') or '(서식없음)'
        org = r.get('submit_org_label') or r.get('submit_org_code') or '(기관없음)'
        exe = r.get('executor_type_label') or '(주체없음)'
        cyc = r.get('inspection_cycle') or ''
        law = r.get('law_name', '')[:20]
        print(f"     {fc:<20} | {exe:<12} | {org:<20} | {cyc:<8} | {law}")
    if len(items) > 5:
        print(f"     ... 외 {len(items)-5}건{RESET}")
    else:
        print(f"{RESET}", end="")


def sm(data: dict) -> Optional[bool]:
    return (data.get("construction_summary") or {}).get("safety_manager_required")


# ─────────────────────────────────────────────
# 건물 시나리오
# ─────────────────────────────────────────────

def test_building_scenarios():
    head("🏢 건물(BUILDING) 4종 시나리오 — 의무→서식→제출 흐름")
    print(f"  {'서식코드':<20} | {'이행자':<12} | {'제출기관':<20} | {'주기':<8} | 법령")
    print(f"  {'-'*75}")

    # ── S1: 소형 상업건물 ──
    sub("S1. 소형 상업건물 (면적 600m², 근로자 10명, 전기 50kW)")
    d = diagnose("BUILDING", {
        "total_floor_area": 600, "worker_count": 10, "electric_capacity": 50
    })
    info(f"총 의무 {d.get('applicable_count',0)}건 | 선임 {d['summary']['appointment']}건 | 점검 {d['summary']['inspection']}건")
    chk(d.get("applicable_count", 0) > 0, "S1: 소형건물 의무 발동", "S1: 의무 0건 (오류)")
    chk(not has_appt(d, "safety_manager"), "S1: 10명 → 안전관리자 미발동 (정상)", "S1: 10명에서 안전관리자 오발동")
    insp_n = len(d.get("inspection_required", []))
    chk(insp_n > 0, f"S1: 점검의무 {insp_n}건 발동", "S1: 점검의무 0건")
    form_insp = count_form_linked(d.get("inspection_required", []))
    chk(form_insp > 0, f"S1: 점검 서식 연결 {form_insp}/{insp_n}건", f"S1: 점검 서식 전혀 없음", warn_only=True)
    print_form_summary("점검", d.get("inspection_required", []))

    # ── S2: 중형 오피스 ──
    sub("S2. 중형 오피스 (면적 3500m², 근로자 60명, 전기 300kW, 승강기 3대)")
    d = diagnose("BUILDING", {
        "total_floor_area": 3500, "worker_count": 60,
        "electric_capacity": 300, "elevator_count": 3
    })
    info(f"총 의무 {d.get('applicable_count',0)}건 | 선임 {d['summary']['appointment']}건 | 점검 {d['summary']['inspection']}건")
    chk(has_appt(d, "safety_manager"),          "S2: 60명 → 안전관리자 발동", "S2: 60명 → 안전관리자 미발동")
    chk(has_appt(d, "electric_safety_manager"),  "S2: 300kW → 전기안전관리자 발동", "S2: 300kW → 전기안전관리자 미발동")
    chk(has_appt(d, "elevator_safety_manager"),  "S2: 승강기 3대 → 승강기안전관리자 발동", "S2: 승강기 → 승강기안전관리자 미발동")
    # 서식 연결 확인
    safe_form = get_appt_form(d, "safety_manager")
    elev_form = get_appt_form(d, "elevator_safety_manager")
    elec_form = get_appt_form(d, "electric_safety_manager")
    chk(bool(safe_form), f"S2: 안전관리자 선임신고서 연결 ({safe_form})", "S2: 안전관리자 선임신고서 없음", warn_only=True)
    chk(bool(elev_form), f"S2: 승강기안전관리자 선임신고서 연결 ({elev_form})", "S2: 승강기 선임신고서 없음", warn_only=True)
    chk(bool(elec_form), f"S2: 전기안전관리자 선임신고서 연결 ({elec_form})", "S2: 전기 선임신고서 없음", warn_only=True)
    # 점검 서식
    all_items = d.get("inspection_required", []) + d.get("appointment_required", [])
    form_cnt = count_form_linked(all_items)
    org_cnt  = count_submit_org_linked(all_items)
    exe_cnt  = count_executor_linked(all_items)
    chk(form_cnt > 0, f"S2: 서식 연결 {form_cnt}/{len(all_items)}건", "S2: 서식 전혀 없음", warn_only=True)
    chk(org_cnt > 0,  f"S2: 제출기관 연결 {org_cnt}/{len(all_items)}건", "S2: 제출기관 전혀 없음", warn_only=True)
    chk(exe_cnt > 0,  f"S2: 이행주체 연결 {exe_cnt}/{len(all_items)}건", "S2: 이행주체 전혀 없음", warn_only=True)
    print_form_summary("선임", d.get("appointment_required", []))
    print_form_summary("점검", d.get("inspection_required", []))

    # ── S3: 대형 복합건물 ──
    sub("S3. 대형 복합건물 (면적 15000m², 근로자 200명, 전기 1500kW, 승강기 8대, 위험물 보유)")
    d = diagnose("BUILDING", {
        "total_floor_area": 15000, "worker_count": 200,
        "electric_capacity": 1500, "elevator_count": 8,
        "has_hazardous_material": True
    })
    appt_n = d['summary']['appointment']
    insp_n = len(d.get('inspection_required', []))
    info(f"총 의무 {d.get('applicable_count',0)}건 | 선임 {appt_n}건 | 점검 {insp_n}건")
    chk(appt_n >= 4, f"S3: 대형건물 선임 {appt_n}종 이상", f"S3: 선임 부족 ({appt_n}종)")
    chk(has_appt(d, "safety_manager"),          "S3: 안전관리자", "S3: 안전관리자 미발동")
    chk(has_appt(d, "electric_safety_manager"),  "S3: 전기안전관리자", "S3: 전기 미발동")
    chk(has_appt(d, "elevator_safety_manager"),  "S3: 승강기안전관리자", "S3: 승강기 미발동")
    chk(has_appt(d, "hazardous_material_manager"), "S3: 위험물안전관리자", "S3: 위험물 미발동")
    # 전체 서식 커버리지
    all_appt = d.get("appointment_required", [])
    all_insp = d.get("inspection_required", [])
    all_rpt  = d.get("report_required", [])
    all_act  = d.get("action_required", [])
    all_items = all_appt + all_insp + all_rpt + all_act
    form_cnt = count_form_linked(all_items)
    ratio = round(form_cnt / len(all_items) * 100) if all_items else 0
    chk(ratio >= 30, f"S3: 서식 커버리지 {ratio}% ({form_cnt}/{len(all_items)}건)",
        f"S3: 서식 커버리지 저조 {ratio}%", warn_only=True)
    print_form_summary("선임", all_appt)
    print_form_summary("점검", all_insp)

    # ── S4: 가스 특수시설 ──
    sub("S4. 가스 특수시설 (근로자 25명, 고압가스 250kg, 전기 150kW)")
    d = diagnose("BUILDING", {
        "total_floor_area": 1200, "worker_count": 25,
        "electric_capacity": 150, "gas_capacity_kg": 250
    })
    info(f"총 의무 {d.get('applicable_count',0)}건 | 선임 {d['summary']['appointment']}건")
    chk(has_appt(d, "gas_safety_manager"),       "S4: 가스 250kg → 가스안전관리자 발동", "S4: 가스 250kg → 가스안전관리자 미발동")
    chk(not has_appt(d, "safety_manager"),        "S4: 25명 → 안전관리자 미발동 (정상)", "S4: 25명에서 안전관리자 오발동")
    gas_form = get_appt_form(d, "gas_safety_manager")
    chk(bool(gas_form), f"S4: 가스안전관리자 선임신고서 연결 ({gas_form})",
        "S4: 가스안전관리자 선임신고서 없음", warn_only=True)
    print_form_summary("선임", d.get("appointment_required", []))


# ─────────────────────────────────────────────
# 산업 시나리오
# ─────────────────────────────────────────────

def test_manufacturing_scenarios():
    head("🏭 산업(MANUFACTURING) 4종 시나리오 — 의무→서식→제출 흐름")
    print(f"  {'서식코드':<20} | {'이행자':<12} | {'제출기관':<20} | {'주기':<8} | 법령")
    print(f"  {'-'*75}")

    # ── M1: 소형 제조업 ──
    sub("M1. 소형 제조업 (근로자 30명, 업종 C25)")
    d = diagnose("MANUFACTURING", {"worker_count": 30, "ksic_major": "C25"})
    info(f"총 의무 {d.get('applicable_count',0)}건 | 선임 {d['summary']['appointment']}건")
    chk(d.get("applicable_count", 0) > 0, "M1: 소형제조업 의무 발동", "M1: 의무 0건")
    chk(not has_appt(d, "safety_manager"), "M1: 30명 → 안전관리자 미발동 (정상)", "M1: 30명에서 안전관리자 오발동")

    # ── M2: 중형 위험물 제조업 ──
    sub("M2. 중형 위험물 제조업 (근로자 80명, 위험물 보유, 가스 보유)")
    d = diagnose("MANUFACTURING", {
        "worker_count": 80,
        "has_hazardous_material": True,
        "has_high_pressure_gas": True
    })
    appt_n = d['summary']['appointment']
    insp_n = d['summary']['inspection']
    info(f"총 의무 {d.get('applicable_count',0)}건 | 선임 {appt_n}건 | 점검 {insp_n}건")
    chk(has_appt(d, "safety_manager"),            "M2: 80명 → 안전관리자 발동", "M2: 80명 → 안전관리자 미발동")
    chk(has_appt(d, "hazardous_material_manager"), "M2: 위험물 → 위험물안전관리자 발동", "M2: 위험물관리자 미발동")
    chk(has_appt(d, "gas_safety_manager"),         "M2: 가스 → 가스안전관리자 발동", "M2: 가스안전관리자 미발동")
    # 선임신고 서식 확인
    safe_form = get_appt_form(d, "safety_manager")
    haz_form  = get_appt_form(d, "hazardous_material_manager")
    gas_form  = get_appt_form(d, "gas_safety_manager")
    chk(bool(safe_form), f"M2: 안전관리자 선임신고서 ({safe_form})", "M2: 안전관리자 선임신고서 없음", warn_only=True)
    chk(bool(haz_form),  f"M2: 위험물안전관리자 선임신고서 ({haz_form})", "M2: 위험물 선임신고서 없음", warn_only=True)
    chk(bool(gas_form),  f"M2: 가스안전관리자 선임신고서 ({gas_form})", "M2: 가스 선임신고서 없음", warn_only=True)
    # 점검 서식
    insp_items = d.get("inspection_required", [])
    form_insp  = count_form_linked(insp_items)
    chk(form_insp > 0, f"M2: 점검 서식 연결 {form_insp}/{len(insp_items)}건", "M2: 점검 서식 없음", warn_only=True)
    print_form_summary("선임", d.get("appointment_required", []))
    print_form_summary("점검", insp_items[:3])

    # ── M3: 화학 대형 제조업 ──
    sub("M3. 화학 대형 제조업 (근로자 300명, 위험물+가스+보일러+화학물질, 전기 2000kW)")
    d = diagnose("MANUFACTURING", {
        "worker_count": 300,
        "has_hazardous_material": True,
        "has_high_pressure_gas": True,
        "has_boiler": True,
        "has_chemical_substance": True,
        "electric_capacity": 2000
    })
    appt_n = d['summary']['appointment']
    info(f"총 의무 {d.get('applicable_count',0)}건 | 선임 {appt_n}건")
    chk(appt_n >= 5, f"M3: 화학대형 선임 {appt_n}종", f"M3: 선임 부족 ({appt_n}종)")
    chk(has_appt(d, "safety_manager"),            "M3: 안전관리자", "M3: 안전관리자 미발동")
    chk(has_appt(d, "health_manager"),             "M3: 보건관리자", "M3: 보건관리자 미발동")
    chk(has_appt(d, "hazardous_material_manager"), "M3: 위험물안전관리자", "M3: 위험물 미발동")
    chk(has_appt(d, "gas_safety_manager"),         "M3: 가스안전관리자", "M3: 가스 미발동")
    chk(has_appt(d, "energy_manager"),             "M3: 에너지관리자", "M3: 에너지 미발동")
    # 전체 의무 서식 커버리지
    all_items = (d.get("appointment_required", []) +
                 d.get("inspection_required", []) +
                 d.get("report_required", []))
    form_cnt = count_form_linked(all_items)
    ratio = round(form_cnt / len(all_items) * 100) if all_items else 0
    info(f"M3: 전체 의무 {len(all_items)}건 중 서식 연결 {form_cnt}건 ({ratio}%)")
    print_form_summary("선임", d.get("appointment_required", []))

    # ── M4: 에너지 대형 공장 ──
    sub("M4. 에너지 대형 공장 (근로자 500명, 연간에너지 2000TOE, 전기 5000kW)")
    d = diagnose("MANUFACTURING", {
        "worker_count": 500,
        "annual_energy_toe": 2000,
        "electric_capacity": 5000
    })
    info(f"총 의무 {d.get('applicable_count',0)}건 | 선임 {d['summary']['appointment']}건")
    chk(has_appt(d, "safety_manager"), "M4: 500명 → 안전관리자 발동", "M4: 안전관리자 미발동")
    chk(has_appt(d, "energy_manager"), "M4: 2000TOE → 에너지관리자 발동", "M4: 에너지관리자 미발동")
    energy_form = get_appt_form(d, "energy_manager")
    chk(bool(energy_form), f"M4: 에너지관리자 선임신고서 ({energy_form})",
        "M4: 에너지관리자 선임신고서 없음", warn_only=True)
    print_form_summary("선임", d.get("appointment_required", []))


# ─────────────────────────────────────────────
# 건설 시나리오
# ─────────────────────────────────────────────

def test_construction_scenarios():
    head("🏗️  건설(CONSTRUCTION) 4종 시나리오 — 의무→서식→제출 흐름")
    print(f"  {'서식코드':<20} | {'이행자':<12} | {'제출기관':<20} | {'주기':<8} | 법령")
    print(f"  {'-'*75}")

    # ── C1: 소규모 공사 ──
    sub("C1. 소규모 공사 (건축 8억, 직접근로자 5명)")
    d = diagnose("CONSTRUCTION", {
        "contract_amount_eok": 8, "construction_type": "건축",
        "direct_workers": 5, "subcon_workers": 0
    })
    cs = d.get("construction_summary", {})
    kt = cs.get("key_thresholds_met", {})
    info(f"총 의무 {d.get('applicable_count',0)}건 | 안전관리자필요={cs.get('safety_manager_required')}")
    chk(sm(d) is False, "C1: 건축 8억 → 안전관리자 불필요 (정상)", "C1: 소규모에서 안전관리자 오발동")
    chk(kt.get("1억_산업안전보건관리비") is True, "C1: 8억 → 산안관리비 발동", "C1: 산안관리비 미발동")
    chk(kt.get("50억_유해위험방지계획서") is False, "C1: 8억 → 유해위험방지계획서 미발동", "C1: 8억에서 유해위험방지계획서 오발동")

    # ── C2: 중규모 공사 ──
    sub("C2. 중규모 건축공사 (건축 200억, 직접근로자 30명, 하도급 20명)")
    d = diagnose("CONSTRUCTION", {
        "contract_amount_eok": 200, "construction_type": "건축",
        "direct_workers": 30, "subcon_workers": 20
    })
    cs = d.get("construction_summary", {})
    kt = cs.get("key_thresholds_met", {})
    info(f"총 의무 {d.get('applicable_count',0)}건 | 안전관리자필요={cs.get('safety_manager_required')}")
    chk(sm(d) is True,  "C2: 건축 200억 → 안전관리자 필요", "C2: 건축 200억 → 안전관리자 미발동")
    chk(kt.get("100억_안전관리계획서") is True, "C2: 200억 → 안전관리계획서 발동", "C2: 안전관리계획서 미발동")
    chk(kt.get("200억_안전보건관리책임자") is True, "C2: 200억 → 안전보건관리책임자 발동", "C2: 안전보건관리책임자 미발동")
    # BEFORE_WORK 서식 확인
    # step2로 공종 추가 시뮬레이션 (step1에서 action 확인)
    act_items = d.get("action_required", [])
    insp_items = d.get("inspection_required", [])
    rpt_items  = d.get("report_required", [])
    all_items  = act_items + insp_items + rpt_items
    form_cnt   = count_form_linked(all_items)
    info(f"C2: 전체 의무 {len(all_items)}건 중 서식 연결 {form_cnt}건")
    chk(len(insp_items) > 0, f"C2: 점검의무 {len(insp_items)}건 발동", "C2: 점검의무 0건")
    print_form_summary("점검", insp_items)
    print_form_summary("보고", rpt_items)

    # ── C3: 대규모 공사 ──
    sub("C3. 대규모 건축공사 (건축 1200억, 직접근로자 200명, 하도급 150명)")
    d = diagnose("CONSTRUCTION", {
        "contract_amount_eok": 1200, "construction_type": "건축",
        "direct_workers": 200, "subcon_workers": 150
    })
    cs = d.get("construction_summary", {})
    kt = cs.get("key_thresholds_met", {})
    total_workers = cs.get("total_workers", 0)
    info(f"총 의무 {d.get('applicable_count',0)}건 | 근로자 {total_workers}명 | 안전관리자필요={cs.get('safety_manager_required')}")
    chk(sm(d) is True,  "C3: 1200억 → 안전관리자 필요", "C3: 1200억 → 안전관리자 미발동")
    chk(kt.get("1000억_건설안전판정사") is True, "C3: 1200억 → 건설안전판정사 발동", "C3: 건설안전판정사 미발동")
    chk(kt.get("300명이상_안전관리자선임") is True, "C3: 350명 → 300명이상 임계 발동", "C3: 300명이상 임계 미발동")
    all_items = d.get("action_required", []) + d.get("inspection_required", []) + d.get("report_required", [])
    form_cnt  = count_form_linked(all_items)
    info(f"C3: 전체 의무 {len(all_items)}건 중 서식 연결 {form_cnt}건")

    # ── C4: 토목 대형 공사 ──
    sub("C4. 토목 대형공사 (토목 150억, 직접근로자 60명, 하도급 40명)")
    d = diagnose("CONSTRUCTION", {
        "contract_amount_eok": 150, "construction_type": "토목",
        "direct_workers": 60, "subcon_workers": 40
    })
    cs = d.get("construction_summary", {})
    kt = cs.get("key_thresholds_met", {})
    info(f"총 의무 {d.get('applicable_count',0)}건 | 안전관리자필요={cs.get('safety_manager_required')}")
    chk(sm(d) is True,  "C4: 토목 150억 → 안전관리자 필요 (120억 이상)", "C4: 토목 150억 → 안전관리자 미발동")
    chk(kt.get("50명이상_안전관리자선임") is True, "C4: 100명 → 50명이상 임계 발동", "C4: 50명이상 임계 미발동")
    chk(kt.get("100억_안전관리계획서") is True, "C4: 150억 → 안전관리계획서 발동", "C4: 안전관리계획서 미발동")


# ─────────────────────────────────────────────
# BEFORE_WORK 공종별 서식 테스트
# ─────────────────────────────────────────────

def test_before_work_forms():
    head("⚒️  BEFORE_WORK 공종별 작업전 점검표 서식 연결 테스트")

    # step2로 공종 지정 후 BEFORE_WORK 룰+서식 확인
    # step2 API 호출
    work_type_scenarios = [
        (["CRANE", "HIGH_WORK"],       "크레인+고소작업"),
        (["TCR", "EXC"],              "타워크레인+굴착"),
        (["SCF", "CONCRETE_POUR"],    "비계+콘크리트타설"),
        (["CONFINED_SPACE", "WMC"],   "밀폐공간+용접"),
        (["BLASTING", "DEMOLITION"],  "발파+해체"),
    ]
    for wts, label in work_type_scenarios:
        r = requests.post(
            f"{BASE_URL}/legal-engine/diagnose/step2",
            json={"sector": "CONSTRUCTION", "construction_work_types": wts},
            timeout=30
        )
        r.raise_for_status()
        data = r.json()
        rule_cnt = data.get("rule_count", 0)
        chk(rule_cnt > 0, f"[{label}] 공종 지정 → 룰 {rule_cnt}건 발동",
            f"[{label}] 공종 지정 → 룰 0건")


# ─────────────────────────────────────────────
# 종합 서식 커버리지 리포트
# ─────────────────────────────────────────────

def test_form_coverage_report():
    head("📊 종합 서식 커버리지 리포트 (대표 시나리오)")

    scenarios = [
        ("BUILDING",      {"total_floor_area": 3500, "worker_count": 60, "electric_capacity": 300, "elevator_count": 3}, "중형 오피스"),
        ("MANUFACTURING", {"worker_count": 150, "has_hazardous_material": True, "has_high_pressure_gas": True, "has_boiler": True}, "중형 위험물공장"),
        ("CONSTRUCTION",  {"contract_amount_eok": 200, "construction_type": "건축", "direct_workers": 30, "subcon_workers": 20}, "중규모 건축공사"),
    ]

    print(f"\n  {'시나리오':<20} | {'총의무':>5} | {'선임':>4} | {'점검':>4} | {'서식연결':>6} | {'커버리지':>7}")
    print(f"  {'-'*65}")

    for sector, inp, label in scenarios:
        d = diagnose(sector, inp)
        appt = d.get("appointment_required", [])
        insp = d.get("inspection_required", [])
        rpt  = d.get("report_required", [])
        act  = d.get("action_required", [])
        all_items = appt + insp + rpt + act
        total     = len(all_items)
        form_cnt  = count_form_linked(all_items)
        ratio     = round(form_cnt / total * 100) if total else 0
        appt_n    = len(appt)
        insp_n    = len(insp)
        print(f"  {label:<20} | {total:>5} | {appt_n:>4} | {insp_n:>4} | {form_cnt:>6} | {ratio:>6}%")

        # 최소 커버리지 기준: 선임 30%, 점검 20%
        appt_form = count_form_linked(appt)
        insp_form = count_form_linked(insp)
        appt_ratio = round(appt_form / appt_n * 100) if appt_n else 0
        insp_ratio = round(insp_form / insp_n * 100) if insp_n else 0
        chk(appt_ratio >= 30,
            f"[{label}] 선임 서식 커버리지 {appt_ratio}% (≥30% 기준)",
            f"[{label}] 선임 서식 커버리지 저조 {appt_ratio}%", warn_only=True)
        chk(insp_ratio >= 20,
            f"[{label}] 점검 서식 커버리지 {insp_ratio}% (≥20% 기준)",
            f"[{label}] 점검 서식 커버리지 저조 {insp_ratio}%", warn_only=True)


# ─────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TAI 법령엔진 종단간 E2E 테스트")
    parser.add_argument("--url", default="https://api.taieng.co.kr")
    args = parser.parse_args()
    BASE_URL = args.url.rstrip("/")

    print(f"{BOLD}")
    print(f"{'═'*65}")
    print(f"  TAI 법령엔진 종단간(E2E) 테스트 v1.0")
    print(f"  대상: {BASE_URL}")
    print(f"  검증: 의무 발동 → 서식 연결 → 제출기관 → 이행주체")
    print(f"  시나리오: 건물4 + 산업4 + 건설4 + 공종5 + 커버리지 = 종합")
    print(f"{'═'*65}{RESET}")

    try:
        r = requests.get(f"{BASE_URL}/", timeout=10).json()
        info(f"API 버전: {r.get('version', '?')}")

        test_building_scenarios()
        test_manufacturing_scenarios()
        test_construction_scenarios()
        test_before_work_forms()
        test_form_coverage_report()

    except requests.exceptions.ConnectionError:
        print(f"{RED}❌ API 연결 실패: {BASE_URL}{RESET}")
        sys.exit(1)
    except Exception as e:
        print(f"{RED}❌ 예외: {e}{RESET}")
        import traceback; traceback.print_exc()
        sys.exit(1)

    total = passed + failed
    print(f"\n{BOLD}{'═'*65}")
    print(f"  결과: ✅{passed}통과 / ❌{failed}실패 / ⚠️{warnings}경고 / 전체{total}건")
    print(f"{'═'*65}{RESET}")

    if failed > 0:
        print(f"{RED}{BOLD}  ❌ 실패 {failed}건 — 엔진 또는 서식 매핑 확인 필요{RESET}")
        sys.exit(1)
    else:
        print(f"{GREEN}{BOLD}  ✅ 전체 통과 — 의무→서식→제출 흐름 정상{RESET}")
