"""
TAI 법령엔진 무결성 검증 스크립트 — v2.0.0 (FROZEN BASELINE)
=============================================================

이 테스트는 법령엔진의 정방향/역방향 무결성 기준점입니다.
법령 데이터 추가·수정·엔진 코드 변경 후 반드시 이 테스트를 먼저 통과해야 합니다.
실패 시 즉시 롤백하고 원인을 수정한 후 재실행합니다.

고정 기준일: 2026-04-06
엔진 버전:   v5.5.5 이상
API 대상:    https://api.taieng.co.kr

실행:
  python tests/test_legal_engine.py
  python tests/test_legal_engine.py --url https://api.taieng.co.kr

테스트 구성 (26건):
  - 정방향 11건: 조건 충족 시 의무 발동 확인
  - 역방향 11건: 조건 해제 시 의무 소멸 확인 (핵심 무결성)
  - 규모비교  2건: 소규모→대규모 의무 증가 확인
  - 섹터격리  2건: 건설 법령이 건물/산업에 노출되지 않음 확인

실패 = 데이터 오류 또는 엔진 버그
모든 26건이 PASS 되어야만 법령엔진이 정상 상태입니다.
"""
import requests
import sys
from typing import Optional

BASE_URL = "https://api.taieng.co.kr"

# ── 색상 ──
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BLUE   = "\033[94m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

def ok(msg):   print(f"{GREEN}  ✅ {msg}{RESET}")
def fail(msg): print(f"{RED}  ❌ {msg}{RESET}")
def info(msg): print(f"{BLUE}  ℹ️  {msg}{RESET}")
def head(msg): print(f"\n{BOLD}{'═'*60}\n  {msg}\n{'═'*60}{RESET}")
def sub(msg):  print(f"\n{BOLD}── {msg} ──{RESET}")

passed = 0
failed = 0


def check(condition: bool, msg_ok: str, msg_fail: str):
    global passed, failed
    if condition:
        ok(msg_ok)
        passed += 1
    else:
        fail(msg_fail)
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
    """appointment_required 목록에서 정확히 일치하는 target 존재 여부"""
    return any(
        r.get("appointment_target") == target_code
        for r in data.get("appointment_required", [])
    )


def cons_summary(data: dict) -> dict:
    return data.get("construction_summary") or {}


def thresholds(data: dict) -> dict:
    return cons_summary(data).get("key_thresholds_met") or {}


def sm_required(data: dict) -> Optional[bool]:
    return cons_summary(data).get("safety_manager_required")


# ══════════════════════════════════════════════
# 정방향 테스트 (11건)
# ══════════════════════════════════════════════

def test_forward():
    head("정방향 테스트 — 조건 충족 시 의무 발동")

    sub("건물(BUILDING)")
    b50  = diagnose("BUILDING", {"total_floor_area": 5000, "worker_count": 50, "electric_capacity": 100})
    e75  = diagnose("BUILDING", {"total_floor_area": 3000, "worker_count": 10, "electric_capacity": 75})
    hz1  = diagnose("BUILDING", {"total_floor_area": 3000, "worker_count": 10, "has_hazardous_material": True})
    check(has_appt(b50, "safety_manager"),             "건물 50명 → 안전관리자 발동",         "건물 50명 → 안전관리자 미발동")
    check(has_appt(e75, "electric_safety_manager"),    "건물 75kW → 전기안전관리자 발동",      "건물 75kW → 전기안전관리자 미발동")
    check(has_appt(hz1, "hazardous_material_manager"), "건물 위험물 있음 → 위험물관리자 발동", "건물 위험물 있음 → 위험물관리자 미발동")

    sub("산업(MANUFACTURING)")
    m50   = diagnose("MANUFACTURING", {"worker_count": 50})
    mhz1  = diagnose("MANUFACTURING", {"worker_count": 30, "has_hazardous_material": True})
    mgas1 = diagnose("MANUFACTURING", {"worker_count": 30, "has_high_pressure_gas": True})
    check(has_appt(m50,   "safety_manager"),             "산업 50명 → 안전관리자 발동",         "산업 50명 → 안전관리자 미발동")
    check(has_appt(mhz1,  "hazardous_material_manager"), "산업 위험물 있음 → 위험물관리자 발동","산업 위험물 있음 → 위험물관리자 미발동")
    check(has_appt(mgas1, "gas_safety_manager"),         "산업 가스 있음 → 가스안전관리자 발동","산업 가스 있음 → 가스안전관리자 미발동")

    sub("건설(CONSTRUCTION)")
    c150  = diagnose("CONSTRUCTION", {"contract_amount_eok": 150, "construction_type": "건축", "direct_workers": 5, "subcon_workers": 5})
    t120  = diagnose("CONSTRUCTION", {"contract_amount_eok": 120, "construction_type": "토목", "direct_workers": 5, "subcon_workers": 5})
    w50   = diagnose("CONSTRUCTION", {"contract_amount_eok": 30,  "construction_type": "건축", "direct_workers": 25, "subcon_workers": 25})
    h50   = diagnose("CONSTRUCTION", {"contract_amount_eok": 50,  "construction_type": "건축", "direct_workers": 5})
    fee10 = diagnose("CONSTRUCTION", {"contract_amount_eok": 1,   "construction_type": "건축", "direct_workers": 3})
    check(sm_required(c150) is True,                         "건설 건축 150억 → 안전관리자 필요",          "건설 건축 150억 → 안전관리자 미발동")
    check(sm_required(t120) is True,                         "건설 토목 120억 → 안전관리자 필요",          "건설 토목 120억 → 안전관리자 미발동")
    check(sm_required(w50)  is True,                         "건설 합계 50명(직25+하25) → 안전관리자 필요", "건설 합계 50명 → 안전관리자 미발동")
    check(thresholds(h50).get("50억_유해위험방지계획서") is True,  "건설 50억 → 유해위험방지계획서 발동",        "건설 50억 → 유해위험방지계획서 미발동")
    check(thresholds(fee10).get("1억_산업안전보건관리비") is True, "건설 1억 → 산안관리비 계상 발동",           "건설 1억 → 산안관리비 미발동")


# ══════════════════════════════════════════════
# 역방향 테스트 (11건) — 핵심 무결성
# ══════════════════════════════════════════════

def test_reverse():
    head("역방향 테스트 — 조건 해제 시 의무 소멸 (무결성 핵심)")

    sub("건물(BUILDING)")
    b49  = diagnose("BUILDING", {"total_floor_area": 5000, "worker_count": 49, "electric_capacity": 100})
    e74  = diagnose("BUILDING", {"total_floor_area": 3000, "worker_count": 10, "electric_capacity": 74})
    hz0  = diagnose("BUILDING", {"total_floor_area": 3000, "worker_count": 10, "has_hazardous_material": False})
    check(not has_appt(b49, "safety_manager"),             "건물 49명 → 안전관리자 소멸",           "건물 49명에서 안전관리자 오발동")
    check(not has_appt(e74, "electric_safety_manager"),    "건물 74kW → 전기안전관리자 소멸",        "건물 74kW에서 전기안전관리자 오발동")
    check(not has_appt(hz0, "hazardous_material_manager"), "건물 위험물 없음 → 위험물관리자 소멸",   "건물 위험물 없음인데 위험물관리자 오발동")

    sub("산업(MANUFACTURING)")
    m49   = diagnose("MANUFACTURING", {"worker_count": 49})
    mhz0  = diagnose("MANUFACTURING", {"worker_count": 30, "has_hazardous_material": False})
    mgas0 = diagnose("MANUFACTURING", {"worker_count": 30, "has_high_pressure_gas": False})
    check(not has_appt(m49,   "safety_manager"),             "산업 49명 → 안전관리자 소멸",           "산업 49명에서 안전관리자 오발동")
    check(not has_appt(mhz0,  "hazardous_material_manager"), "산업 위험물 없음 → 위험물관리자 소멸",  "산업 위험물 없음인데 위험물관리자 오발동")
    check(not has_appt(mgas0, "gas_safety_manager"),         "산업 가스 없음 → 가스안전관리자 소멸",  "산업 가스 없음인데 가스안전관리자 오발동")

    sub("건설(CONSTRUCTION)")
    c149  = diagnose("CONSTRUCTION", {"contract_amount_eok": 149, "construction_type": "건축", "direct_workers": 5, "subcon_workers": 5})
    t119  = diagnose("CONSTRUCTION", {"contract_amount_eok": 119, "construction_type": "토목", "direct_workers": 5, "subcon_workers": 5})
    w49   = diagnose("CONSTRUCTION", {"contract_amount_eok": 30,  "construction_type": "건축", "direct_workers": 25, "subcon_workers": 24})
    h49   = diagnose("CONSTRUCTION", {"contract_amount_eok": 49,  "construction_type": "건축", "direct_workers": 5})
    fee09 = diagnose("CONSTRUCTION", {"contract_amount_eok": 0.9, "construction_type": "건축", "direct_workers": 3})
    check(sm_required(c149) is False,                            "건설 건축 149억 → 안전관리자 소멸",        "건설 149억인데 안전관리자 오발동")
    check(sm_required(t119) is False,                            "건설 토목 119억 → 안전관리자 소멸",        "건설 토목 119억인데 안전관리자 오발동")
    check(sm_required(w49)  is False,                            "건설 합계 49명(직25+하24) → 안전관리자 소멸","건설 49명인데 안전관리자 오발동")
    check(thresholds(h49).get("50억_유해위험방지계획서") is False,    "건설 49억 → 유해위험방지계획서 소멸",      "건설 49억인데 유해위험방지계획서 오발동")
    check(thresholds(fee09).get("1억_산업안전보건관리비") is False,   "건설 9000만 → 산안관리비 소멸",           "건설 9000만인데 산안관리비 오발동")


# ══════════════════════════════════════════════
# 규모 비교 (2건)
# ══════════════════════════════════════════════

def test_scale():
    head("규모 비교 — 조건 많을수록 의무 증가")
    bSm = diagnose("BUILDING",      {"total_floor_area": 300,  "worker_count": 10, "electric_capacity": 30})
    bBg = diagnose("BUILDING",      {"total_floor_area": 5000, "worker_count": 60, "electric_capacity": 300, "has_hazardous_material": True})
    mSm = diagnose("MANUFACTURING", {"worker_count": 20})
    mBg = diagnose("MANUFACTURING", {"worker_count": 200, "has_hazardous_material": True, "has_high_pressure_gas": True})
    bSm_n = bSm.get("summary", {}).get("appointment", 0)
    bBg_n = bBg.get("summary", {}).get("appointment", 0)
    mSm_n = mSm.get("summary", {}).get("total", 0)
    mBg_n = mBg.get("summary", {}).get("total", 0)
    check(bBg_n > bSm_n, f"건물 소→대 선임 증가 (소:{bSm_n} 대:{bBg_n})",  f"건물 대형이 소형보다 선임 적음 (소:{bSm_n} 대:{bBg_n})")
    check(mBg_n > mSm_n, f"산업 소→대 총의무 증가 (소:{mSm_n} 대:{mBg_n})",f"산업 대형이 소형보다 의무 적음 (소:{mSm_n} 대:{mBg_n})")


# ══════════════════════════════════════════════
# 섹터 격리 (2건)
# ══════════════════════════════════════════════

def test_isolation():
    head("섹터 격리 — 건설 법령이 비건설 섹터에 노출 안 됨")
    ILLEGAL = ["건설기계", "건설기술 진흥", "건설산업", "건설공사"]
    b50 = diagnose("BUILDING",      {"total_floor_area": 5000, "worker_count": 60, "electric_capacity": 300})
    m50 = diagnose("MANUFACTURING", {"worker_count": 60})
    bad_bld = [l for l in b50.get("law_badges", []) if any(k in l for k in ILLEGAL)]
    bad_mfg = [l for l in m50.get("law_badges", []) if any(k in l for k in ILLEGAL)]
    check(len(bad_bld) == 0, "건물에 건설전용 법령 미노출",  f"건물에 건설법령 노출: {bad_bld}")
    check(len(bad_mfg) == 0, "산업에 건설전용 법령 미노출",  f"산업에 건설법령 노출: {bad_mfg}")


# ══════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="TAI 법령엔진 무결성 검증")
    parser.add_argument("--url", default="https://api.taieng.co.kr")
    args = parser.parse_args()
    BASE_URL = args.url.rstrip("/")

    print(f"{BOLD}")
    print(f"{'═'*60}")
    print(f"  TAI 법령엔진 무결성 검증 v2.0 (FROZEN BASELINE)")
    print(f"  대상: {BASE_URL}")
    print(f"  기준: 정방향11 + 역방향11 + 비교2 + 격리2 = 26건")
    print(f"{'═'*60}{RESET}")

    try:
        r = requests.get(f"{BASE_URL}/", timeout=10).json()
        info(f"API 버전: {r.get('version', '?')}")
        test_forward()
        test_reverse()
        test_scale()
        test_isolation()
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
        print(f"{RED}{BOLD}  ❌ 실패 {failed}건 — 롤백 후 원인 수정 필요{RESET}")
        sys.exit(1)
    else:
        print(f"{GREEN}{BOLD}  ✅ 26건 전체 통과 — 법령엔진 무결성 확인됨{RESET}")
