"""
법령 판정 엔진 자동 검증 스크립트 — v1.0.0
==============================================
실행: python tests/test_legal_engine.py
또는: python tests/test_legal_engine.py --url https://api.taieng.co.kr

검증 항목:
  1. 경계값 테스트 (Boundary Value) — 임계값 직전/직후 결과 변화 확인
  2. 섹터 격리 테스트 — 건설 법령이 건물/산업에 나오지 않는지
  3. 선임 의무 완전성 — 각 시나리오별 필수 관리자 존재 여부
  4. 조건 없는 룰 과다 발동 — ACTION/REPORT 건수 합리성 검증
"""
import requests
import sys
import json
from dataclasses import dataclass, field
from typing import Optional

BASE_URL = "https://api.taieng.co.kr"

# ──────────────────────────────────────────────
# 색상 출력
# ──────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BLUE   = "\033[94m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

def ok(msg):   print(f"{GREEN}  ✅ {msg}{RESET}")
def fail(msg): print(f"{RED}  ❌ {msg}{RESET}")
def warn(msg): print(f"{YELLOW}  ⚠️  {msg}{RESET}")
def info(msg): print(f"{BLUE}  ℹ️  {msg}{RESET}")
def head(msg): print(f"\n{BOLD}{'═'*60}\n  {msg}\n{'═'*60}{RESET}")
def sub(msg):  print(f"\n{BOLD}── {msg} ──{RESET}")


# ──────────────────────────────────────────────
# API 호출
# ──────────────────────────────────────────────

def diagnose(sector: str, input_data: dict) -> dict:
    r = requests.post(
        f"{BASE_URL}/legal-engine/diagnose/step1",
        json={"sector": sector, "input": input_data},
        timeout=30
    )
    r.raise_for_status()
    return r.json().get("data", {})


def get_appointment_targets(data: dict) -> set:
    return {
        r.get("appointment_target") or r.get("obligation_summary", "")[:30]
        for r in data.get("appointment_required", [])
    }


def get_law_names(data: dict) -> set:
    return set(data.get("law_badges", []))


# ──────────────────────────────────────────────
# 테스트 결과 집계
# ──────────────────────────────────────────────

passed = 0
failed = 0
warnings = 0


def assert_true(condition, msg_ok, msg_fail, is_warn=False):
    global passed, failed, warnings
    if condition:
        ok(msg_ok)
        passed += 1
    elif is_warn:
        warn(msg_fail)
        warnings += 1
    else:
        fail(msg_fail)
        failed += 1


def assert_contains(targets: set, target: str, label: str):
    found = any(target.lower() in t.lower() for t in targets)
    assert_true(found,
        f"{label} 선임의무 발동 ({target})",
        f"{label} 선임의무 미발동 — targets: {targets}")


def assert_not_contains(targets: set, target: str, label: str):
    found = any(target.lower() in t.lower() for t in targets)
    assert_true(not found,
        f"{label} 올바르게 미발동 ({target})",
        f"{label} 잘못 발동됨 — targets: {targets}")


def assert_law_isolated(law_names: set, forbidden: list, sector_label: str):
    """forbidden 법령이 해당 섹터에 나오지 않는지 확인"""
    for forbidden_kw in forbidden:
        found = [l for l in law_names if forbidden_kw in l]
        assert_true(not found,
            f"[{sector_label}] '{forbidden_kw}' 법령 미노출",
            f"[{sector_label}] '{forbidden_kw}' 법령 잘못 노출: {found}")


def assert_count_range(count: int, min_v: int, max_v: int, label: str):
    assert_true(min_v <= count <= max_v,
        f"{label} = {count}건 (정상 범위 {min_v}~{max_v})",
        f"{label} = {count}건 (범위 초과: 기대 {min_v}~{max_v})",
        is_warn=(count > max_v))


# ══════════════════════════════════════════════
# 1. 경계값 테스트 — 건물 (BUILDING)
# ══════════════════════════════════════════════

def test_building_boundary():
    head("TEST 1: 건물(BUILDING) 경계값 테스트")

    # ── 1-1. 근로자 수 경계값 (안전관리자: 50명)
    sub("1-1. 근로자 수 — 안전관리자 선임 경계값 (50명)")
    d_49 = diagnose("BUILDING", {"total_floor_area": 5000, "worker_count": 49, "electric_capacity": 100})
    d_50 = diagnose("BUILDING", {"total_floor_area": 5000, "worker_count": 50, "electric_capacity": 100})
    t_49 = get_appointment_targets(d_49)
    t_50 = get_appointment_targets(d_50)
    assert_not_contains(t_49, "safety_manager", "49명")
    assert_contains(t_50,     "safety_manager", "50명")

    # ── 1-2. 수전용량 경계값 (전기안전관리자: 75kW)
    sub("1-2. 수전용량 — 전기안전관리자 경계값 (75kW)")
    d_74 = diagnose("BUILDING", {"total_floor_area": 3000, "worker_count": 10, "electric_capacity": 74})
    d_75 = diagnose("BUILDING", {"total_floor_area": 3000, "worker_count": 10, "electric_capacity": 75})
    t_74 = get_appointment_targets(d_74)
    t_75 = get_appointment_targets(d_75)
    assert_not_contains(t_74, "electric_safety_manager", "74kW")
    assert_contains(t_75,     "electric_safety_manager", "75kW")

    # ── 1-3. 위험물 없음 vs 있음
    sub("1-3. 위험물 유무 — 위험물안전관리자")
    d_no  = diagnose("BUILDING", {"total_floor_area": 3000, "worker_count": 10, "has_hazardous_material": False})
    d_yes = diagnose("BUILDING", {"total_floor_area": 3000, "worker_count": 10, "has_hazardous_material": True})
    assert_not_contains(get_appointment_targets(d_no),  "hazardous_material", "위험물 없음")
    assert_contains(get_appointment_targets(d_yes),     "hazardous_material", "위험물 있음")

    # ── 1-4. 소규모 건물 — 선임 없어야
    sub("1-4. 소규모 건물 (300㎡, 10명) — 선임 0건")
    d_small = diagnose("BUILDING", {"total_floor_area": 300, "worker_count": 10, "electric_capacity": 30})
    n_appt = d_small["summary"]["appointment"]
    assert_true(n_appt == 0,
        f"소규모 건물 선임 0건",
        f"소규모 건물 선임 {n_appt}건 (0이어야 함)")

    # ── 1-5. 섹터 격리 — 건물에 건설 법령 없어야
    sub("1-5. 섹터 격리 — 건물에 건설 전용 법령 미노출")
    d_bld = diagnose("BUILDING", {"total_floor_area": 5000, "worker_count": 60, "electric_capacity": 300})
    assert_law_isolated(get_law_names(d_bld),
        ["건설기계", "건설기술 진흥", "건설산업기본", "건설공사"], "건물")


# ══════════════════════════════════════════════
# 2. 경계값 테스트 — 산업 (MANUFACTURING)
# ══════════════════════════════════════════════

def test_manufacturing_boundary():
    head("TEST 2: 산업(MANUFACTURING) 경계값 테스트")

    # ── 2-1. 근로자 49명 vs 50명 (안전관리자)
    sub("2-1. 근로자 수 경계값 (안전관리자: 50명)")
    d_49 = diagnose("MANUFACTURING", {"worker_count": 49, "electric_capacity": 100})
    d_50 = diagnose("MANUFACTURING", {"worker_count": 50, "electric_capacity": 100})
    assert_not_contains(get_appointment_targets(d_49), "safety_manager", "산업 49명")
    assert_contains(get_appointment_targets(d_50),     "safety_manager", "산업 50명")

    # ── 2-2. 위험물 없음 vs 있음 (위험물안전관리자)
    sub("2-2. 위험물 유무 — 위험물안전관리자")
    d_no  = diagnose("MANUFACTURING", {"worker_count": 30, "has_hazardous_material": False})
    d_yes = diagnose("MANUFACTURING", {"worker_count": 30, "has_hazardous_material": True})
    assert_not_contains(get_appointment_targets(d_no),  "hazardous", "위험물 없음")
    assert_contains(get_appointment_targets(d_yes),     "hazardous", "위험물 있음")

    # ── 2-3. 고압가스 없음 vs 있음 (가스안전관리자)
    sub("2-3. 고압가스 유무 — 가스안전관리자")
    d_no  = diagnose("MANUFACTURING", {"worker_count": 30, "has_high_pressure_gas": False})
    d_yes = diagnose("MANUFACTURING", {"worker_count": 30, "has_high_pressure_gas": True})
    assert_not_contains(get_appointment_targets(d_no),  "gas_safety", "가스 없음")
    assert_contains(get_appointment_targets(d_yes),     "gas",        "가스 있음")

    # ── 2-4. 보일러 없음 vs 있음 (에너지관리자)
    sub("2-4. 보일러 유무 — 에너지관리자")
    d_no  = diagnose("MANUFACTURING", {"worker_count": 30, "has_boiler": False})
    d_yes = diagnose("MANUFACTURING", {"worker_count": 30, "has_boiler": True})
    # 에너지관리자는 에너지이용 합리화법 기준 (일정 용량 이상)
    info(f"보일러 없음 선임: {get_appointment_targets(d_no)}")
    info(f"보일러 있음 선임: {get_appointment_targets(d_yes)}")

    # ── 2-5. 섹터 격리 — 산업에 건설 법령 없어야
    sub("2-5. 섹터 격리 — 산업에 건설 전용 법령 미노출")
    d_mfg = diagnose("MANUFACTURING", {"worker_count": 100, "has_hazardous_material": True})
    assert_law_isolated(get_law_names(d_mfg),
        ["건설기계", "건설기술 진흥", "건설공사"], "산업")

    # ── 2-6. 조치 의무 건수 합리성
    sub("2-6. 조치 의무 건수 합리성 (소규모 20명)")
    d_small = diagnose("MANUFACTURING", {"worker_count": 20})
    s = d_small["summary"]
    assert_count_range(s["action"], 0, 100, "산업_소규모 조치의무")
    assert_count_range(s["report"] + s["notify"], 0, 120, "산업_소규모 신고/보고")


# ══════════════════════════════════════════════
# 3. 경계값 테스트 — 건설 (CONSTRUCTION)
# ══════════════════════════════════════════════

def test_construction_boundary():
    head("TEST 3: 건설(CONSTRUCTION) 경계값 테스트")

    # ── 3-1. 공사금액 건축 경계값 (150억)
    sub("3-1. 공사금액 건축 경계값 (안전관리자: 150억)")
    d_149 = diagnose("CONSTRUCTION", {"contract_amount_eok": 149, "construction_type": "건축", "direct_workers": 5, "subcon_workers": 5})
    d_150 = diagnose("CONSTRUCTION", {"contract_amount_eok": 150, "construction_type": "건축", "direct_workers": 5, "subcon_workers": 5})
    cs_149 = d_149.get("construction_summary", {})
    cs_150 = d_150.get("construction_summary", {})
    assert_true(cs_149.get("safety_manager_required") == False,
        "건축 149억 — 안전관리자 불필요",
        f"건축 149억 — 안전관리자가 필요로 잘못 판정")
    assert_true(cs_150.get("safety_manager_required") == True,
        "건축 150억 — 안전관리자 필요",
        f"건축 150억 — 안전관리자 미판정")

    # ── 3-2. 공사금액 토목 경계값 (120억)
    sub("3-2. 공사금액 토목 경계값 (안전관리자: 120억)")
    d_119 = diagnose("CONSTRUCTION", {"contract_amount_eok": 119, "construction_type": "토목", "direct_workers": 5, "subcon_workers": 5})
    d_120 = diagnose("CONSTRUCTION", {"contract_amount_eok": 120, "construction_type": "토목", "direct_workers": 5, "subcon_workers": 5})
    cs_119 = d_119.get("construction_summary", {})
    cs_120 = d_120.get("construction_summary", {})
    assert_true(cs_119.get("safety_manager_required") == False,
        "토목 119억 — 안전관리자 불필요",
        "토목 119억 — 안전관리자가 필요로 잘못 판정")
    assert_true(cs_120.get("safety_manager_required") == True,
        "토목 120억 — 안전관리자 필요",
        "토목 120억 — 안전관리자 미판정")

    # ── 3-3. 근로자 수 경계값 (하도급 포함 50명)
    sub("3-3. 근로자 수 경계값 (하도급 포함 50명)")
    d_49  = diagnose("CONSTRUCTION", {"contract_amount_eok": 30, "construction_type": "건축", "direct_workers": 25, "subcon_workers": 24})  # 총 49명
    d_50  = diagnose("CONSTRUCTION", {"contract_amount_eok": 30, "construction_type": "건축", "direct_workers": 25, "subcon_workers": 25})  # 총 50명
    cs_49 = d_49.get("construction_summary", {})
    cs_50 = d_50.get("construction_summary", {})
    assert_true(cs_49.get("safety_manager_required") == False,
        "건설 총 49명(직25+하24) — 안전관리자 불필요",
        f"건설 총 49명 — 안전관리자가 필요로 잘못 판정: {cs_49}")
    assert_true(cs_50.get("safety_manager_required") == True,
        "건설 총 50명(직25+하25) — 안전관리자 필요",
        f"건설 총 50명 — 안전관리자 미판정: {cs_50}")

    # ── 3-4. 산업안전보건관리비 경계값 (1억)
    sub("3-4. 산업안전보건관리비 계상 경계값 (1억)")
    d_99  = diagnose("CONSTRUCTION", {"contract_amount_eok": 0.99, "construction_type": "건축", "direct_workers": 3})
    d_100 = diagnose("CONSTRUCTION", {"contract_amount_eok": 1,    "construction_type": "건축", "direct_workers": 3})
    cs_99  = d_99.get("construction_summary", {}).get("key_thresholds_met", {})
    cs_100 = d_100.get("construction_summary", {}).get("key_thresholds_met", {})
    assert_true(cs_99.get("1억_산업안전보건관리비") == False,
        "9900만원 — 산안관리비 불필요",
        "9900만원 — 산안관리비가 필요로 잘못 판정")
    assert_true(cs_100.get("1억_산업안전보건관리비") == True,
        "1억 — 산안관리비 필요",
        "1억 — 산안관리비 미판정")

    # ── 3-5. 유해위험방지계획서 경계값 (50억)
    sub("3-5. 유해위험방지계획서 경계값 (50억)")
    d_49  = diagnose("CONSTRUCTION", {"contract_amount_eok": 49,  "construction_type": "건축", "direct_workers": 5})
    d_50  = diagnose("CONSTRUCTION", {"contract_amount_eok": 50,  "construction_type": "건축", "direct_workers": 5})
    cs_49 = d_49.get("construction_summary", {}).get("key_thresholds_met", {})
    cs_50 = d_50.get("construction_summary", {}).get("key_thresholds_met", {})
    assert_true(cs_49.get("50억_유해위험방지계획서") == False, "49억 — 유해위험방지계획서 불필요", "49억 잘못 판정")
    assert_true(cs_50.get("50억_유해위험방지계획서") == True,  "50억 — 유해위험방지계획서 필요",  "50억 미판정")

    # ── 3-6. 섹터 격리 — 건설에 건물 전용 법령 없어야
    sub("3-6. 섹터 격리 — 건설에 건물/산업 전용 법령 과도 노출 점검")
    d_con = diagnose("CONSTRUCTION", {"contract_amount_eok": 200, "construction_type": "건축", "direct_workers": 30, "subcon_workers": 40})
    law_names = get_law_names(d_con)
    # 건설 섹터에서 나오면 안 되는 법령
    assert_law_isolated(law_names, ["승강기 안전관리", "건축물관리법", "시설물의 안전"], "건설")


# ══════════════════════════════════════════════
# 4. 엔진 버전 확인
# ══════════════════════════════════════════════

def test_engine_version():
    head("TEST 4: 엔진 상태 확인")
    r = requests.get(f"{BASE_URL}/", timeout=10)
    version = r.json().get("version", "?")
    info(f"API 버전: {version}")

    # step1 결과에서 engine_version 확인
    d = diagnose("BUILDING", {"total_floor_area": 1000, "worker_count": 10})
    ev = d.get("engine_version", "?")
    info(f"엔진 버전: {ev}")
    assert_true(ev >= "5.5",
        f"엔진 버전 {ev} (5.5 이상)",
        f"엔진 버전 {ev} 낮음")


# ══════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="https://api.taieng.co.kr", help="API base URL")
    args = parser.parse_args()
    BASE_URL = args.url.rstrip("/")

    print(f"{BOLD}\n{'='*60}")
    print(f"  TAI 법령엔진 자동 검증 v1.0")
    print(f"  대상: {BASE_URL}")
    print(f"{'='*60}{RESET}")

    try:
        test_engine_version()
        test_building_boundary()
        test_manufacturing_boundary()
        test_construction_boundary()
    except requests.exceptions.ConnectionError:
        print(f"{RED}\n❌ API 서버 연결 실패: {BASE_URL}{RESET}")
        sys.exit(1)
    except Exception as e:
        print(f"{RED}\n❌ 예외 발생: {e}{RESET}")
        import traceback; traceback.print_exc()
        sys.exit(1)

    # ── 최종 결과
    total = passed + failed + warnings
    print(f"\n{BOLD}{'='*60}")
    print(f"  결과: {passed}통과 / {failed}실패 / {warnings}경고 / {total}전체")
    print(f"{'='*60}{RESET}")

    if failed > 0:
        print(f"{RED}{BOLD}  ❌ 테스트 실패 {failed}건 — 수정 필요{RESET}")
        sys.exit(1)
    elif warnings > 0:
        print(f"{YELLOW}{BOLD}  ⚠️  경고 {warnings}건 — 검토 권장{RESET}")
    else:
        print(f"{GREEN}{BOLD}  ✅ 모든 테스트 통과{RESET}")
