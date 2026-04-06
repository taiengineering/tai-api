"""
TAI 법령엔진 단계별(Layer) 무결성 검증 — v1.1
================================================

시설/설비/공정/복합 단계별로 엔진이 올바르게 동작하는지 검증합니다.

검증 계층:
  L1. 시설단위 (step1) — 설비 수치 직접 입력
      - 승강기 대수, 전기 용량, 가스/보일러 불리언 등
      - 정방향: 설비 있으면 발동 / 역방향: 설비 없으면 소멸
      - 복합: 두 설비 동시 입력 시 둘다 / 하나 제거 시 해당만 소멸

  L2. 공정단위 (step2) — 건설 공종별 법령
      - 공종 미지정: 전체 룰 (최대)
      - 공종 지정: 공통(NULL)+해당 공종 룰만 (필터)
      - 공종 추가할수록 룰 증가

  L3. 복합 시나리오
      - 공정2개+설비100개급: 모든 조건 동시 입력 → 선임 5종 이상
      - 부분 미입력: worker만, 빈 객체 → 오류없이 처리 (엔진 견고성)
      - 역방향: 복합 조건에서 하나씩 제거 → 해당 관리자만 소멸

엔진 설계 참고:
  - gas/boiler 조건은 has_high_pressure_gas/has_boiler 불리언 사용
  - elevator_count는 v5.6.1+ 부터 step1 BUILDING에서 지원
  - step2 공종 필터: 공종 없음=전체, 공종 지정=공통+해당공종만

고정 기준일: 2026-04-06 (v1.1 — Job4 CI 통합)
엔진 버전:   v5.6.1 이상 (elevator_count step1 BUILDING 지원)

실행:
  python tests/test_legal_engine_layer.py
  python tests/test_legal_engine_layer.py --url https://api.taieng.co.kr
"""
import requests
import sys
from typing import Optional

BASE_URL = "https://api.taieng.co.kr"

GREEN = "\033[92m"
RED   = "\033[91m"
YELLOW= "\033[93m"
BLUE  = "\033[94m"
RESET = "\033[0m"
BOLD  = "\033[1m"

def ok(msg):   print(f"{GREEN}  ✅ {msg}{RESET}")
def fail(msg): print(f"{RED}  ❌ {msg}{RESET}")
def warn(msg): print(f"{YELLOW}  ⚠️  {msg}{RESET}")
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


def diagnose_step1(sector: str, inp: dict) -> dict:
    r = requests.post(
        f"{BASE_URL}/legal-engine/diagnose/step1",
        json={"sector": sector, "input": inp},
        timeout=30
    )
    r.raise_for_status()
    return r.json().get("data", {})


def diagnose_step2(body: dict) -> dict:
    r = requests.post(
        f"{BASE_URL}/legal-engine/diagnose/step2",
        json=body,
        timeout=30
    )
    r.raise_for_status()
    return r.json()


def has_appt(data: dict, target_code: str) -> bool:
    return any(
        r.get("appointment_target") == target_code
        for r in data.get("appointment_required", [])
    )


def sm(data: dict) -> Optional[bool]:
    return (data.get("construction_summary") or {}).get("safety_manager_required")


def appt_targets(data: dict) -> list:
    return [r.get("appointment_target") for r in data.get("appointment_required", [])]


def appt_n(data: dict) -> int:
    return data.get("summary", {}).get("appointment", 0)


def total_n(data: dict) -> int:
    return data.get("summary", {}).get("total", 0)


# ══════════════════════════════════════════════
# L1: 시설단위 — 설비 수치 직접 입력 (정방향)
# 건물·산업·건설 × 시설,공사장 × 설비,작업
# ══════════════════════════════════════════════

def test_L1_forward():
    head("L1 시설단위 설비 정방향 — 설비 있으면 관리자 발동")

    sub("건물(BUILDING) — 승강기 (elevator_count)")
    elev1 = diagnose_step1("BUILDING", {"total_floor_area": 3000, "worker_count": 10, "elevator_count": 1})
    elev0 = diagnose_step1("BUILDING", {"total_floor_area": 3000, "worker_count": 10, "elevator_count": 0})
    check(has_appt(elev1, "elevator_safety_manager"),
          "건물 승강기 1대 → 승강기안전관리자 발동",  "건물 승강기 1대 → 승강기안전관리자 미발동",
          str(appt_targets(elev1)))
    check(not has_appt(elev0, "elevator_safety_manager"),
          "건물 승강기 0대 → 승강기안전관리자 없음",  "건물 승강기 0대인데 오발동")

    sub("건물(BUILDING) — 전기 (electric_capacity)")
    e500 = diagnose_step1("BUILDING", {"total_floor_area": 3000, "worker_count": 10, "electric_capacity": 500})
    e0   = diagnose_step1("BUILDING", {"total_floor_area": 3000, "worker_count": 10, "electric_capacity": 0})
    check(has_appt(e500, "electric_safety_manager"),   "건물 전기 500kW → 전기안전관리자 발동", "건물 전기 500kW → 전기안전관리자 미발동")
    check(not has_appt(e0, "electric_safety_manager"), "건물 전기 0kW → 전기안전관리자 없음",  "건물 전기 0kW인데 오발동")

    sub("산업(MANUFACTURING) — 가스/보일러 (불리언)")
    gas_t  = diagnose_step1("MANUFACTURING", {"worker_count": 30, "has_high_pressure_gas": True})
    gas_f  = diagnose_step1("MANUFACTURING", {"worker_count": 30, "has_high_pressure_gas": False})
    boil_t = diagnose_step1("MANUFACTURING", {"worker_count": 30, "has_boiler": True})
    boil_f = diagnose_step1("MANUFACTURING", {"worker_count": 30, "has_boiler": False})
    check(has_appt(gas_t,  "gas_safety_manager"),     "산업 가스있음 → 가스안전관리자 발동",  "산업 가스있음 → 가스안전관리자 미발동")
    check(not has_appt(gas_f, "gas_safety_manager"),  "산업 가스없음 → 가스안전관리자 없음",  "산업 가스없음인데 오발동")
    check(has_appt(boil_t, "energy_manager"),          "산업 보일러있음 → 에너지관리자 발동",  "산업 보일러있음 → 에너지관리자 미발동")
    check(not has_appt(boil_f, "energy_manager"),      "산업 보일러없음 → 에너지관리자 없음",  "산업 보일러없음인데 오발동")


# ══════════════════════════════════════════════
# L1: 시설단위 — 역방향 (선택적 소멸)
# ══════════════════════════════════════════════

def test_L1_reverse():
    head("L1 시설단위 설비 역방향 — 하나 제거 시 해당만 소멸")

    sub("건물(BUILDING) — 승강기+전기 복합 역방향")
    both  = diagnose_step1("BUILDING", {"total_floor_area": 3000, "worker_count": 10, "elevator_count": 1, "electric_capacity": 300})
    no_e  = diagnose_step1("BUILDING", {"total_floor_area": 3000, "worker_count": 10, "elevator_count": 0, "electric_capacity": 300})
    no_ec = diagnose_step1("BUILDING", {"total_floor_area": 3000, "worker_count": 10, "elevator_count": 1, "electric_capacity": 0})
    check(has_appt(both, "elevator_safety_manager") and has_appt(both, "electric_safety_manager"),
          "건물 승강기+전기 → 둘다 발동",         "건물 승강기+전기 복합 → 일부 미발동")
    check(not has_appt(no_e, "elevator_safety_manager") and has_appt(no_e, "electric_safety_manager"),
          "건물 승강기제거 → 전기만 남음",         "건물 승강기제거 → 선택적 소멸 실패")
    check(has_appt(no_ec, "elevator_safety_manager") and not has_appt(no_ec, "electric_safety_manager"),
          "건물 전기제거 → 승강기만 남음",         "건물 전기제거 → 선택적 소멸 실패")

    sub("산업(MANUFACTURING) — 가스+위험물 복합 역방향")
    m_both  = diagnose_step1("MANUFACTURING", {"worker_count": 30, "has_high_pressure_gas": True,  "has_hazardous_material": True})
    m_nogas = diagnose_step1("MANUFACTURING", {"worker_count": 30, "has_high_pressure_gas": False, "has_hazardous_material": True})
    m_nohzm = diagnose_step1("MANUFACTURING", {"worker_count": 30, "has_high_pressure_gas": True,  "has_hazardous_material": False})
    check(has_appt(m_both, "gas_safety_manager") and has_appt(m_both, "hazardous_material_manager"),
          "산업 가스+위험물 → 둘다 발동",          "산업 가스+위험물 복합 → 일부 미발동")
    check(not has_appt(m_nogas, "gas_safety_manager") and has_appt(m_nogas, "hazardous_material_manager"),
          "산업 가스제거 → 위험물관리자만 남음",    "산업 가스제거 → 선택적 소멸 실패")
    check(has_appt(m_nohzm, "gas_safety_manager") and not has_appt(m_nohzm, "hazardous_material_manager"),
          "산업 위험물제거 → 가스안전관리자만 남음", "산업 위험물제거 → 선택적 소멸 실패")


# ══════════════════════════════════════════════
# L2: 공정단위 — step2 건설 공종별
# 공사장 × 공정 × 정방향/역방향
# ══════════════════════════════════════════════

def test_L2_process():
    head("L2 공정단위 (step2) — 건설 공종별 법령 필터 (정방향+역방향)")

    sub("정방향: 공종 추가할수록 룰 증가")
    s2_none  = diagnose_step2({"sector": "CONSTRUCTION", "construction_work_types": []})
    s2_crane = diagnose_step2({"sector": "CONSTRUCTION", "construction_work_types": ["CRANE"]})
    s2_two   = diagnose_step2({"sector": "CONSTRUCTION", "construction_work_types": ["CRANE", "EXCAVATION"]})
    s2_three = diagnose_step2({"sector": "CONSTRUCTION", "construction_work_types": ["CRANE", "EXCAVATION", "BLASTING"]})
    s2_five  = diagnose_step2({"sector": "CONSTRUCTION", "construction_work_types": ["CRANE", "EXCAVATION", "BLASTING", "CONFINED_SPACE", "HIGH_WORK"]})

    n0 = s2_none.get("rule_count", 0)
    n1 = s2_crane.get("rule_count", 0)
    n2 = s2_two.get("rule_count", 0)
    n3 = s2_three.get("rule_count", 0)
    n5 = s2_five.get("rule_count", 0)

    info(f"공종수별 룰 수: 없음={n0} / 1개={n1} / 2개={n2} / 3개={n3} / 5개={n5}")

    check(n0 >= n1, f"공종없음({n0}) ≥ 공종1개({n1}) — 미필터=전체",       f"공종없음이 공종1개보다 적음 (오류)")
    check(n2 >= n1, f"공종2개({n2}) ≥ 공종1개({n1}) — 공종추가시 증가",   f"공종2개가 1개보다 적음 (오류)")
    check(n3 >= n2, f"공종3개({n3}) ≥ 공종2개({n2}) — 공종추가시 증가",   f"공종3개가 2개보다 적음 (오류)")
    check(n5 >= n3, f"공종5개({n5}) ≥ 공종3개({n3}) — 공종추가시 증가",   f"공종5개가 3개보다 적음 (오류)")

    sub("역방향: 공종 제거 → 룰 감소 (공종없음이 최대)")
    check(n0 >= n5, f"공종없음({n0}) ≥ 공종5개({n5}) — 공종제거시 최대",  f"공종없음이 공종5개보다 적음 (오류)")


# ══════════════════════════════════════════════
# L3: 복합 시나리오 — 건물·산업·건설 전체
# ══════════════════════════════════════════════

def test_L3_complex():
    head("L3 복합 시나리오 — 전체조건 정방향 + 부분미입력 + 역방향")

    sub("L3-정방향: 산업 모든 설비 동시 입력")
    full = diagnose_step1("MANUFACTURING", {
        "worker_count": 200, "electric_capacity": 2000,
        "has_high_pressure_gas": True, "has_boiler": True,
        "has_hazardous_material": True, "has_chemical_substance": True,
        "elevator_count": 5, "annual_energy_toe": 2000, "ksic_major": "C20"
    })
    info(f"복합최대 선임 {appt_n(full)}건: {appt_targets(full)}")
    check(appt_n(full) >= 5,
          f"복합최대 → 선임 5종 이상 ({appt_n(full)}건)",
          f"복합최대 → 선임 미달 ({appt_n(full)}건)")
    check(has_appt(full, "safety_manager") and has_appt(full, "gas_safety_manager") and
          has_appt(full, "energy_manager") and has_appt(full, "hazardous_material_manager"),
          "복합최대 → 안전+가스+에너지+위험물 4종 포함",
          "복합최대 → 4종 중 일부 미발동", str(appt_targets(full)))

    sub("L3-견고성: 부분/전체 미입력")
    w_only    = diagnose_step1("MANUFACTURING", {"worker_count": 100})
    empty_mfg = diagnose_step1("MANUFACTURING", {})
    empty_bld = diagnose_step1("BUILDING", {})
    check(total_n(w_only) > 0,
          f"worker만 입력 → 의무 존재 ({total_n(w_only)}건)", "worker만 입력 → 의무 0건 (오류)")
    check(isinstance(empty_mfg, dict) and "summary" in empty_mfg,
          "빈입력(산업) → 오류없이 처리", "빈입력(산업) → 예외 발생")
    check(isinstance(empty_bld, dict) and "summary" in empty_bld,
          "빈입력(건물) → 오류없이 처리", "빈입력(건물) → 예외 발생")

    sub("L3-역방향: 산업 복합조건에서 설비 하나씩 제거")
    r_all    = diagnose_step1("MANUFACTURING", {"worker_count": 200, "has_high_pressure_gas": True,  "has_boiler": True, "has_hazardous_material": True})
    r_nogas  = diagnose_step1("MANUFACTURING", {"worker_count": 200, "has_high_pressure_gas": False, "has_boiler": True, "has_hazardous_material": True})
    r_noboil = diagnose_step1("MANUFACTURING", {"worker_count": 200, "has_high_pressure_gas": True,  "has_boiler": False,"has_hazardous_material": True})
    r_nohzm  = diagnose_step1("MANUFACTURING", {"worker_count": 200, "has_high_pressure_gas": True,  "has_boiler": True, "has_hazardous_material": False})
    r_none   = diagnose_step1("MANUFACTURING", {"worker_count": 200})

    check(has_appt(r_all, "gas_safety_manager") and has_appt(r_all, "energy_manager") and
          has_appt(r_all, "hazardous_material_manager") and has_appt(r_all, "safety_manager"),
          "전체조건 → 가스+에너지+위험물+안전관리자 발동",
          "전체조건 → 일부 미발동", str(appt_targets(r_all)))
    check(not has_appt(r_nogas, "gas_safety_manager") and
          has_appt(r_nogas, "energy_manager") and has_appt(r_nogas, "hazardous_material_manager"),
          "가스만제거 → 가스안전관리자 소멸, 나머지 유지",
          "가스만제거 → 선택적 소멸 실패", str(appt_targets(r_nogas)))
    check(not has_appt(r_noboil, "energy_manager") and
          has_appt(r_noboil, "gas_safety_manager") and has_appt(r_noboil, "hazardous_material_manager"),
          "보일러만제거 → 에너지관리자 소멸, 나머지 유지",
          "보일러만제거 → 선택적 소멸 실패", str(appt_targets(r_noboil)))
    check(not has_appt(r_nohzm, "hazardous_material_manager") and
          has_appt(r_nohzm, "gas_safety_manager") and has_appt(r_nohzm, "energy_manager"),
          "위험물만제거 → 위험물관리자 소멸, 나머지 유지",
          "위험물만제거 → 선택적 소멸 실패", str(appt_targets(r_nohzm)))
    check(not has_appt(r_none, "gas_safety_manager") and
          not has_appt(r_none, "energy_manager") and
          not has_appt(r_none, "hazardous_material_manager") and
          has_appt(r_none, "safety_manager"),
          "전부제거(근로자만) → 설비 관리자 소멸, 안전관리자만 남음",
          "전부제거 → 소멸 실패", str(appt_targets(r_none)))


# ══════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="TAI 법령엔진 단계별 무결성 검증")
    parser.add_argument("--url", default="https://api.taieng.co.kr")
    args = parser.parse_args()
    BASE_URL = args.url.rstrip("/")

    print(f"{BOLD}")
    print(f"{'═'*60}")
    print(f"  TAI 법령엔진 단계별(Layer) 무결성 검증 v1.1")
    print(f"  대상: {BASE_URL}")
    print(f"  L1(건물·산업 설비 정/역방향) + L2(건설 공정) + L3(복합)")
    print(f"{'═'*60}{RESET}")

    try:
        r = requests.get(f"{BASE_URL}/", timeout=10).json()
        v = r.get("version", "?")
        info(f"API 버전: {v}")
        if v < "5.6.1":
            warn(f"v5.6.1 미만({v}) — elevator_count step1 테스트는 실패할 수 있음")

        test_L1_forward()
        test_L1_reverse()
        test_L2_process()
        test_L3_complex()

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
        print(f"{RED}{BOLD}  ❌ 실패 {failed}건 — 엔진 또는 데이터 버그{RESET}")
        sys.exit(1)
    else:
        print(f"{GREEN}{BOLD}  ✅ 전체 통과 — 단계별 무결성 확인됨{RESET}")
