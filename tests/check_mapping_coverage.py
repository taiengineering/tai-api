"""
TAI 정적 매핑 커버리지 검증 — GitHub Actions Job 2
====================================================
DB에 실제 사용 중인 condition_code가 엔진의
_input_to_facility_context() 에 처리 코드가 있는지 확인합니다.

문제: 새 condition_code를 DB에 추가하고 엔진 코드에 처리를 빠뜨리면
     룰이 발동 안 되는 버그가 발생하지만 눈에 안 띔.

이 스크립트는 그 격차를 자동으로 탐지합니다.

실행:
  SUPABASE_URL=https://xxx.supabase.co \\
  SUPABASE_SERVICE_KEY=eyJhb... \\
  python tests/check_mapping_coverage.py
"""
import os
import sys
import requests

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SERVICE_KEY  = os.environ["SUPABASE_SERVICE_KEY"]

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

# ── 엔진이 처리할 수 있는 context key 전체 목록 ──
# routers/legal_engine.py 의 CONDITION_CODE_TO_CONTEXT_KEY 및
# _input_to_facility_context() 에서 세팅하는 키와 동기화 유지
# ※ 새 condition_code를 DB에 추가하면 반드시 이 목록에도 추가할 것
ENGINE_CONTEXT_KEYS = {
    # 공통 수치
    "worker_count", "employee_count",
    "total_floor_area", "building_area", "floor_area",
    "floor_count",
    "electric_capacity", "electrical_capacity_kw",
    "transformer_capacity_kva",
    "annual_energy_toe",
    "contractor_count",
    # 설비 수치 (직접 입력 — v5.6.3)
    "elevator_count",
    "gas_capacity_kg", "gas_capacity_m3",
    "boiler_capacity_kw", "boiler_capacity_th",
    # 설비 불리언 (boolean → 수치 변환)
    "has_high_pressure_gas", "has_boiler",
    "has_hazardous_material", "has_chemical_substance",
    "has_tunnel_bridge", "has_blasting", "has_crane",
    "has_high_work",      # 고소작업(2m 이상) 여부 — DB: OSHSRULE-333-006-CST
    # 상태 플래그
    "is_hazardous_material", "is_multi_use", "is_factory_registered",
    # 건설 전용
    "construction_amount", "contract_amount",
    "construction_type", "building_use_code",
    "safety_manager_threshold",
    "is_building", "is_civil",
    "direct_workers", "subcon_workers", "subcontractor_worker_count",
    # 건물 전용
    "hospital_beds", "student_count",
    # 기타
    "ksic_code",
}


def fetch_db_codes() -> set:
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/master_building_legal_rules",
        headers={
            "apikey":        SERVICE_KEY,
            "Authorization": f"Bearer {SERVICE_KEY}",
        },
        params={
            "select": "condition_code",
            "is_active": "eq.true",
            "condition_code": "not.is.null",
            "limit": 2000,
        },
        timeout=15,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Supabase 오류 {r.status_code}: {r.text[:200]}")
    return {row["condition_code"] for row in r.json() if row.get("condition_code")}


def main():
    print(f"\n{BOLD}{'═'*58}")
    print("  TAI 정적 매핑 커버리지 검증")
    print(f"{'═'*58}{RESET}\n")

    db_codes = fetch_db_codes()
    print(f"  DB condition_code 종류:      {len(db_codes)}개")
    print(f"  엔진 처리 가능 key 종류:     {len(ENGINE_CONTEXT_KEYS)}개\n")

    # DB에 있는데 엔진에 없음 → 룰 발동 안 됨 (버그)
    missing = db_codes - ENGINE_CONTEXT_KEYS

    # 엔진에 있는데 DB에 없음 → 미사용 매핑 (경고만)
    unused = ENGINE_CONTEXT_KEYS - db_codes

    if missing:
        print(f"{RED}{BOLD}  ❌ 엔진 매핑 누락 — 이 condition_code는 DB에 있지만 엔진이 처리 못 함:{RESET}")
        for code in sorted(missing):
            print(f"{RED}     • {code}{RESET}")
        print()
        print(f"{RED}  → routers/legal_engine.py 의 CONDITION_CODE_TO_CONTEXT_KEY 또는")
        print(f"  → _input_to_facility_context() 에 추가하세요.{RESET}")
    else:
        print(f"{GREEN}  ✅ 모든 DB condition_code가 엔진에 매핑되어 있음{RESET}")

    if unused:
        print(f"\n{YELLOW}  ⚠️  엔진에 정의됐지만 DB에서 미사용 ({len(unused)}개) — 경고만:{RESET}")
        for code in sorted(unused):
            print(f"{YELLOW}     • {code}{RESET}")

    # 결과
    print(f"\n{BOLD}{'═'*58}")
    if missing:
        print(f"  ❌ 매핑 커버리지 검증 실패 ({len(missing)}개 누락)")
        print(f"{'═'*58}{RESET}")
        sys.exit(1)
    else:
        print(f"  ✅ 매핑 커버리지 검증 통과")
        print(f"{'═'*58}{RESET}")


if __name__ == "__main__":
    main()
