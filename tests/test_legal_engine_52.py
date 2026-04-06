"""
TAI 법령엔진 무결성 검증 — 52건 (v1.0)
==========================================

기존 26건과 완전히 다른 수치/조건으로 추가 검증합니다.
- 정방향 26건: 더 높은 수치, 복합 조건, 극단값
- 역방향 26건: 임계값 아래 다른 수치, 조건 선택적 해제

고정 기준일: 2026-04-06
엔진 버전:   v5.5.5 이상

실행:
  python tests/test_legal_engine_52.py
  python tests/test_legal_engine_52.py --url https://api.taieng.co.kr

이 52건도 항상 통과해야 합니다.
"""
import requests
import sys
from typing import Optional

BASE_URL = "https://api.taieng.co.kr"

GREEN = "\033[92m"
RED   = "\033[91m"
BLUE  = "\033[94m"
RESET = "\033[0m"
BOLD  = "\033[1m"

def ok(msg):   print(f"{GREEN}  ✅ {msg}{RESET}")
def fail(msg): print(f"{RED}  ❌ {msg}{RESET}")
def info(msg): print(f"{BLUE}  ℹ️  {msg}{RESET}")
def head(msg): print(f"\n{BOLD}{'═'*60}\n  {msg}\n{'═'*60}{RESET}")
def sub(msg):  print(f"\n{BOLD}── {msg} ──{RESET}")

passed = 0
failed = 0


def check(condition: bool, msg_ok: str, msg_fail: str, note: str = ""):
    global passed, failed
    if condition:
        ok(msg_ok)
        passed += 1
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
    """정확히 일치하는 appointment_target 존재 여부"""
    return any(
        r.get("appointment_target") == target_code
        for r in data.get("appointment_required", [])
    )


def sm(data: dict) -> Optional[bool]:
    return (data.get("construction_summary") or {}).get("safety_manager_required")


def th(data: dict, key: str) -> Optional[bool]:
    t = (data.get("construction_summary") or {}).get("key_thresholds_met") or {}
    return t.get(key)


def appt_n(data: dict) -> int:
    return data.get("summary", {}).get("appointment", 0)


def total_n(data: dict) -> int:
    return data.get("summary", {}).get("total", 0)


# ══════════════════════════════════════════════
# 정방향 26건 — 기존과 다른 조건값
# ══════════════════════════════════════════════

def test_forward_52():
    head("정방향 26건 — 기존과 다른 수치/복합조건/극단값")

    sub("건물(BUILDING) — 8건")
    bf1 = diagnose("BUILDING", {"total_floor_area": 5000, "worker_count": 100, "electric_capacity": 50})
    bf2 = diagnose("BUILDING", {"total_floor_area": 5000, "worker_count": 500, "electric_capacity": 50})
    bf3 = diagnose("BUILDING", {"total_floor_area": 5000, "worker_count": 10,  "electric_capacity": 300})
    bf4 = diagnose("BUILDING", {"total_floor_area": 5000, "worker_count": 10,  "electric_capacity": 1000})
    bf5 = diagnose("BUILDING", {"total_floor_area": 5000, "worker_count": 10,  "has_high_pressure_gas": True})
    bf6 = diagnose("BUILDING", {"total_floor_area": 5000, "worker_count": 100, "has_hazardous_material": True})
    bf7 = diagnose("BUILDING", {"total_floor_area": 5000, "worker_count": 10,  "electric_capacity": 300, "has_hazardous_material": True})
    bf8 = diagnose("BUILDING", {"total_floor_area": 5000, "worker_count": 100, "electric_capacity": 300,
                                 "has_hazardous_material": True, "has_high_pressure_gas": True})

    check(has_appt(bf1, "safety_manager"),             "건물 100명 → 안전관리자",              "건물 100명 → 안전관리자 미발동")
    check(has_appt(bf2, "safety_manager"),             "건물 500명 → 안전관리자",              "건물 500명 → 안전관리자 미발동")
    check(has_appt(bf3, "electric_safety_manager"),    "건물 300kW → 전기안전관리자",          "건물 300kW → 전기안전관리자 미발동")
    check(has_appt(bf4, "electric_safety_manager"),    "건물 1000kW → 전기안전관리자",         "건물 1000kW → 전기안전관리자 미발동")
    check(has_appt(bf5, "gas_safety_manager"),         "건물 가스있음 → 가스안전관리자",        "건물 가스있음 → 가스안전관리자 미발동")
    check(has_appt(bf6, "safety_manager") and has_appt(bf6, "hazardous_material_manager"),
          "건물 100명+위험물 → 안전관리자+위험물관리자 복합", "건물 100명+위험물 → 복합 미발동")
    check(has_appt(bf7, "electric_safety_manager") and has_appt(bf7, "hazardous_material_manager"),
          "건물 300kW+위험물 → 전기+위험물관리자 복합",     "건물 300kW+위험물 → 복합 미발동")
    check(has_appt(bf8, "safety_manager") and has_appt(bf8, "electric_safety_manager") and
          has_appt(bf8, "hazardous_material_manager") and has_appt(bf8, "gas_safety_manager"),
          "건물 100명+300kW+위험물+가스 → 4종 복합",       "건물 4종 복합 → 일부 미발동")

    sub("산업(MANUFACTURING) — 8건")
    mf1 = diagnose("MANUFACTURING", {"worker_count": 100})
    mf2 = diagnose("MANUFACTURING", {"worker_count": 300})
    mf3 = diagnose("MANUFACTURING", {"worker_count": 30,  "has_high_pressure_gas": True,  "has_hazardous_material": False})
    mf4 = diagnose("MANUFACTURING", {"worker_count": 30,  "has_high_pressure_gas": False, "has_hazardous_material": True})
    mf5 = diagnose("MANUFACTURING", {"worker_count": 50,  "has_high_pressure_gas": True})
    mf6 = diagnose("MANUFACTURING", {"worker_count": 5,   "has_hazardous_material": True})
    mf7 = diagnose("MANUFACTURING", {"worker_count": 100, "has_hazardous_material": True})
    mf8 = diagnose("MANUFACTURING", {"worker_count": 10,  "has_boiler": True})

    check(has_appt(mf1, "safety_manager"),             "산업 100명 → 안전관리자",              "산업 100명 → 안전관리자 미발동")
    check(has_appt(mf2, "safety_manager"),             "산업 300명 → 안전관리자",              "산업 300명 → 안전관리자 미발동")
    check(has_appt(mf3, "gas_safety_manager"),         "산업 가스만 → 가스안전관리자",          "산업 가스만 → 가스안전관리자 미발동")
    check(has_appt(mf4, "hazardous_material_manager"), "산업 위험물만 → 위험물관리자",          "산업 위험물만 → 위험물관리자 미발동")
    check(has_appt(mf5, "safety_manager") and has_appt(mf5, "gas_safety_manager"),
          "산업 50명+가스 → 안전관리자+가스안전관리자",    "산업 50명+가스 → 복합 미발동")
    check(has_appt(mf6, "hazardous_material_manager") and not has_appt(mf6, "safety_manager"),
          "산업 5명+위험물 → 위험물관리자만(안전관리자없음)", "산업 5명+위험물 → 안전관리자 오발동",
          str([r.get("appointment_target") for r in mf6.get("appointment_required", [])]))
    check(has_appt(mf7, "safety_manager") and has_appt(mf7, "hazardous_material_manager"),
          "산업 100명+위험물 → 안전관리자+위험물관리자",   "산업 100명+위험물 → 복합 미발동")
    check(has_appt(mf8, "energy_manager"),             "산업 보일러있음 → 에너지관리자",        "산업 보일러있음 → 에너지관리자 미발동")

    sub("건설(CONSTRUCTION) — 10건")
    cf1  = diagnose("CONSTRUCTION", {"contract_amount_eok": 200,  "construction_type": "건축", "direct_workers": 5,   "subcon_workers": 5})
    cf2  = diagnose("CONSTRUCTION", {"contract_amount_eok": 500,  "construction_type": "건축", "direct_workers": 5,   "subcon_workers": 5})
    cf3  = diagnose("CONSTRUCTION", {"contract_amount_eok": 200,  "construction_type": "토목", "direct_workers": 5,   "subcon_workers": 5})
    cf4  = diagnose("CONSTRUCTION", {"contract_amount_eok": 500,  "construction_type": "토목", "direct_workers": 5,   "subcon_workers": 5})
    cf5  = diagnose("CONSTRUCTION", {"contract_amount_eok": 30,   "construction_type": "건축", "direct_workers": 60,  "subcon_workers": 40})
    cf6  = diagnose("CONSTRUCTION", {"contract_amount_eok": 30,   "construction_type": "건축", "direct_workers": 200, "subcon_workers": 100})
    cf7  = diagnose("CONSTRUCTION", {"contract_amount_eok": 100,  "construction_type": "건축", "direct_workers": 5})
    cf8  = diagnose("CONSTRUCTION", {"contract_amount_eok": 200,  "construction_type": "건축", "direct_workers": 5})
    cf9  = diagnose("CONSTRUCTION", {"contract_amount_eok": 1000, "construction_type": "건축", "direct_workers": 5})
    cf10 = diagnose("CONSTRUCTION", {"contract_amount_eok": 10,   "construction_type": "건축", "direct_workers": 0})

    check(sm(cf1) is True,  "건설 건축200억 → 안전관리자 필요",    "건설 건축200억 → 안전관리자 미발동")
    check(sm(cf2) is True,  "건설 건축500억 → 안전관리자 필요",    "건설 건축500억 → 안전관리자 미발동")
    check(sm(cf3) is True,  "건설 토목200억 → 안전관리자 필요",    "건설 토목200억 → 안전관리자 미발동")
    check(sm(cf4) is True,  "건설 토목500억 → 안전관리자 필요",    "건설 토목500억 → 안전관리자 미발동")
    check(sm(cf5) is True,  "건설 합계100명(직60+하40) → 안전관리자 필요", "건설 합계100명 → 안전관리자 미발동")
    check(sm(cf6) is True and th(cf6, "300명이상_안전관리자선임") is True,
          "건설 합계300명 → 안전관리자+300명이상 임계값", "건설 합계300명 → 임계값 미달")
    check(th(cf7, "100억_안전관리계획서") is True,  "건설 100억 → 안전관리계획서",     "건설 100억 → 안전관리계획서 미발동")
    check(th(cf8, "200억_안전보건관리책임자") is True, "건설 200억 → 안전보건관리책임자", "건설 200억 → 안전보건관리책임자 미발동")
    check(th(cf9, "1000억_건설안전판정사") is True, "건설 1000억 → 건설안전판정사",    "건설 1000억 → 건설안전판정사 미발동")
    check(th(cf10, "1억_산업안전보건관리비") is True and sm(cf10) is False,
          "건설 10억 → 산안관리비O + 안전관리자X",     "건설 10억 → 조합 오류")


# ══════════════════════════════════════════════
# 역방향 26건 — 기존과 다른 수치로 소멸 확인
# ══════════════════════════════════════════════

def test_reverse_52():
    head("역방향 26건 — 기존과 다른 수치로 의무 소멸 확인")

    sub("건물(BUILDING) — 8건")
    br1 = diagnose("BUILDING", {"total_floor_area": 5000, "worker_count": 0,   "electric_capacity": 50})
    br2 = diagnose("BUILDING", {"total_floor_area": 5000, "worker_count": 1,   "electric_capacity": 50})
    br3 = diagnose("BUILDING", {"total_floor_area": 5000, "worker_count": 10,  "electric_capacity": 0})
    br4 = diagnose("BUILDING", {"total_floor_area": 5000, "worker_count": 10,  "electric_capacity": 50})
    br5 = diagnose("BUILDING", {"total_floor_area": 5000, "worker_count": 10,  "has_high_pressure_gas": False, "has_hazardous_material": True})
    br6 = diagnose("BUILDING", {"total_floor_area": 5000, "worker_count": 10,  "has_high_pressure_gas": True,  "has_hazardous_material": False})
    br7 = diagnose("BUILDING", {"total_floor_area": 5000, "worker_count": 48,  "electric_capacity": 74})
    br8 = diagnose("BUILDING", {"total_floor_area": 5000, "worker_count": 100, "has_hazardous_material": False})

    check(not has_appt(br1, "safety_manager"),             "건물 0명 → 안전관리자 없음",           "건물 0명에서 안전관리자 오발동")
    check(not has_appt(br2, "safety_manager"),             "건물 1명 → 안전관리자 없음",           "건물 1명에서 안전관리자 오발동")
    check(not has_appt(br3, "electric_safety_manager"),    "건물 0kW → 전기안전관리자 없음",       "건물 0kW에서 전기안전관리자 오발동")
    check(not has_appt(br4, "electric_safety_manager"),    "건물 50kW → 전기안전관리자 없음",      "건물 50kW에서 전기안전관리자 오발동")
    check(not has_appt(br5, "gas_safety_manager"),         "건물 가스없음+위험물 → 가스관리자없음", "건물 가스없음인데 가스관리자 오발동")
    check(not has_appt(br6, "hazardous_material_manager"), "건물 가스+위험물없음 → 위험물관리자없음","건물 위험물없음인데 위험물관리자 오발동")
    check(not has_appt(br7, "safety_manager") and not has_appt(br7, "electric_safety_manager"),
          "건물 48명+74kW → 안전관리자+전기 둘다없음",   "건물 48명+74kW에서 오발동")
    check(has_appt(br8, "safety_manager") and not has_appt(br8, "hazardous_material_manager"),
          "건물 100명+위험물없음 → 안전관리자만(위험물관리자없음)", "건물 100명+위험물없음 → 선택적 소멸 실패")

    sub("산업(MANUFACTURING) — 8건")
    mr1 = diagnose("MANUFACTURING", {"worker_count": 0})
    mr2 = diagnose("MANUFACTURING", {"worker_count": 1})
    mr3 = diagnose("MANUFACTURING", {"worker_count": 10, "has_high_pressure_gas": False, "has_hazardous_material": True})
    mr4 = diagnose("MANUFACTURING", {"worker_count": 10, "has_high_pressure_gas": True,  "has_hazardous_material": False})
    mr5 = diagnose("MANUFACTURING", {"worker_count": 50, "has_high_pressure_gas": False})
    mr6 = diagnose("MANUFACTURING", {"worker_count": 1,  "has_hazardous_material": False, "has_high_pressure_gas": False})
    mr7 = diagnose("MANUFACTURING", {"worker_count": 100,"has_hazardous_material": False})
    mr8 = diagnose("MANUFACTURING", {"worker_count": 10, "has_boiler": False})

    check(not has_appt(mr1, "safety_manager"),             "산업 0명 → 안전관리자 없음",           "산업 0명에서 안전관리자 오발동")
    check(not has_appt(mr2, "safety_manager"),             "산업 1명 → 안전관리자 없음",           "산업 1명에서 안전관리자 오발동")
    check(not has_appt(mr3, "gas_safety_manager"),         "산업 가스없음+위험물 → 가스관리자없음", "산업 가스없음인데 가스관리자 오발동")
    check(not has_appt(mr4, "hazardous_material_manager"), "산업 가스+위험물없음 → 위험물관리자없음","산업 위험물없음인데 위험물관리자 오발동")
    check(has_appt(mr5, "safety_manager") and not has_appt(mr5, "gas_safety_manager"),
          "산업 50명+가스없음 → 안전관리자만(가스관리자없음)","산업 50명+가스없음 → 선택적 소멸 실패")
    check(mr6.get("summary", {}).get("appointment", 0) == 0,
          "산업 1명+조건없음 → 선임의무 0건",              "산업 1명+조건없음인데 선임의무 발동")
    check(has_appt(mr7, "safety_manager") and not has_appt(mr7, "hazardous_material_manager"),
          "산업 100명+위험물없음 → 안전관리자만(위험물없음)","산업 100명+위험물없음 → 선택적 소멸 실패")
    check(not has_appt(mr8, "energy_manager"),             "산업 보일러없음 → 에너지관리자없음",   "산업 보일러없음인데 에너지관리자 오발동")

    sub("건설(CONSTRUCTION) — 10건")
    cr1  = diagnose("CONSTRUCTION", {"contract_amount_eok": 100,  "construction_type": "건축", "direct_workers": 5,  "subcon_workers": 5})
    cr2  = diagnose("CONSTRUCTION", {"contract_amount_eok": 130,  "construction_type": "건축", "direct_workers": 5,  "subcon_workers": 5})
    cr3  = diagnose("CONSTRUCTION", {"contract_amount_eok": 100,  "construction_type": "토목", "direct_workers": 5,  "subcon_workers": 5})
    cr4  = diagnose("CONSTRUCTION", {"contract_amount_eok": 30,   "construction_type": "건축", "direct_workers": 24, "subcon_workers": 24})
    cr5  = diagnose("CONSTRUCTION", {"contract_amount_eok": 0.5,  "construction_type": "건축", "direct_workers": 3})
    cr6  = diagnose("CONSTRUCTION", {"contract_amount_eok": 0,    "construction_type": "건축", "direct_workers": 0})
    cr7  = diagnose("CONSTRUCTION", {"contract_amount_eok": 99,   "construction_type": "건축", "direct_workers": 5})
    cr8  = diagnose("CONSTRUCTION", {"contract_amount_eok": 199,  "construction_type": "건축", "direct_workers": 5})
    cr9  = diagnose("CONSTRUCTION", {"contract_amount_eok": 999,  "construction_type": "건축", "direct_workers": 5})
    cr10 = diagnose("CONSTRUCTION", {"contract_amount_eok": 49,   "construction_type": "건축", "direct_workers": 5})

    check(sm(cr1)  is False, "건설 건축100억(150억미만) → 안전관리자없음", "건설 건축100억인데 안전관리자 오발동")
    check(sm(cr2)  is False, "건설 건축130억(150억미만) → 안전관리자없음", "건설 건축130억인데 안전관리자 오발동")
    check(sm(cr3)  is False, "건설 토목100억(120억미만) → 안전관리자없음", "건설 토목100억인데 안전관리자 오발동")
    check(sm(cr4)  is False, "건설 합계48명(직24+하24) → 안전관리자없음", "건설 48명인데 안전관리자 오발동")
    check(th(cr5,  "1억_산업안전보건관리비") is False, "건설 5000만 → 산안관리비없음",  "건설 5000만인데 산안관리비 오발동")
    check(sm(cr6)  is False and th(cr6, "1억_산업안전보건관리비") is False,
          "건설 0억0명 → 전부없음",                                     "건설 0억0명 → 오발동 존재")
    check(th(cr7,  "100억_안전관리계획서")   is False, "건설 99억 → 안전관리계획서없음",   "건설 99억인데 안전관리계획서 오발동")
    check(th(cr8,  "200억_안전보건관리책임자") is False, "건설 199억 → 안전보건관리책임자없음","건설 199억인데 안전보건관리책임자 오발동")
    check(th(cr9,  "1000억_건설안전판정사") is False,   "건설 999억 → 건설안전판정사없음",  "건설 999억인데 건설안전판정사 오발동")
    check(th(cr10, "50억_유해위험방지계획서") is False,  "건설 49억 → 유해위험방지계획서없음","건설 49억인데 유해위험방지계획서 오발동")


# ══════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="TAI 법령엔진 52건 무결성 검증")
    parser.add_argument("--url", default="https://api.taieng.co.kr")
    args = parser.parse_args()
    BASE_URL = args.url.rstrip("/")

    print(f"{BOLD}")
    print(f"{'═'*60}")
    print(f"  TAI 법령엔진 무결성 검증 52건 v1.0")
    print(f"  대상: {BASE_URL}")
    print(f"  기준: 정방향26 + 역방향26 = 52건")
    print(f"{'═'*60}{RESET}")

    try:
        r = requests.get(f"{BASE_URL}/", timeout=10).json()
        info(f"API 버전: {r.get('version', '?')}")
        test_forward_52()
        test_reverse_52()
    except requests.exceptions.ConnectionError:
        print(f"{RED}❌ API 연결 실패: {BASE_URL}{RESET}")
        sys.exit(1)
    except Exception as e:
        print(f"{RED}❌ 예외: {e}{RESET}")
        import traceback; traceback.print_exc()
        sys.exit(1)

    total = passed + failed
    print(f"\n{BOLD}{'═'*60}")
    print(f"  결과: {passed}통과 / {failed}실패 / {total}전체")
    print(f"{'═'*60}{RESET}")

    if failed > 0:
        print(f"{RED}{BOLD}  ❌ 실패 {failed}건 — 데이터 또는 엔진 버그{RESET}")
        sys.exit(1)
    else:
        print(f"{GREEN}{BOLD}  ✅ 52건 전체 통과{RESET}")
