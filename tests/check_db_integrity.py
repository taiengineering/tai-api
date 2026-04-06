"""
TAI DB 무결성 빠른 검증 — GitHub Actions Job 1
================================================
Supabase REST API 직접 호출 (배포 불필요, 약 3초)

검증 항목:
  1. 활성 룰 총수 1000건 이상
  2. APPOINT 룰 전부 target_code 있음
  3. target_code 영문 형식 (한글 잔존 0건)
  4. INSPECT 룰 전부 executor_type_code 있음
  5. BUILDING INSPECT 4완비율 80% 이상
  6. MANUFACTURING INSPECT condition 완비율 60% 이상
  7. sector 값이 허용 범위 내
  8. obligation_type 값이 허용 범위 내

실행:
  SUPABASE_URL=https://xxx.supabase.co \\
  SUPABASE_SERVICE_KEY=eyJhb... \\
  python tests/check_db_integrity.py
"""
import os
import sys
import re
import requests

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SERVICE_KEY  = os.environ["SUPABASE_SERVICE_KEY"]

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

passed = 0
failed = 0
warnings = 0


def fetch(table: str, select: str, filters: dict, limit: int = 2000) -> list:
    params = {"select": select, "limit": limit}
    for k, v in filters.items():
        params[k] = v
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers={
            "apikey":        SERVICE_KEY,
            "Authorization": f"Bearer {SERVICE_KEY}",
        },
        params=params,
        timeout=15,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Supabase 오류 {r.status_code}: {r.text[:200]}")
    return r.json()


def chk(label: str, condition: bool, detail: str = "", warn_only: bool = False):
    global passed, failed, warnings
    if condition:
        print(f"{GREEN}  ✅ {label}{RESET}")
        passed += 1
    elif warn_only:
        print(f"{YELLOW}  ⚠️  {label}" + (f" → {detail}" if detail else "") + RESET)
        warnings += 1
    else:
        print(f"{RED}  ❌ {label}" + (f" → {detail}" if detail else "") + RESET)
        failed += 1


def main():
    print(f"\n{BOLD}{'═'*58}")
    print("  TAI DB 무결성 빠른 검증")
    print(f"  대상: {SUPABASE_URL}")
    print(f"{'═'*58}{RESET}\n")

    # 전체 룰 한 번에 로드
    all_rules = fetch(
        "master_building_legal_rules",
        "rule_id,obligation_type,sector,appointment_target_code,"
        "condition_code,condition_value,inspection_cycle_unit_code,"
        "executor_type_code,law_article",
        {"is_active": "eq.true"},
        limit=2000,
    )
    total = len(all_rules)
    print(f"  → 활성 룰 {total}건 로드 완료\n")

    # 1. 총수
    chk(f"활성 룰 1000건 이상 ({total}건)", total >= 1000, f"실제: {total}건")

    # 2. APPOINT target
    appoint = [r for r in all_rules if r["obligation_type"] == "APPOINT"]
    no_target = [r for r in appoint if not r.get("appointment_target_code")]
    chk(
        f"APPOINT {len(appoint)}건 전부 target_code 있음",
        len(no_target) == 0,
        f"target 없는 {len(no_target)}건: {[r['rule_id'] for r in no_target[:5]]}",
    )

    # 3. 한글 target_code
    korean = [
        r for r in all_rules
        if r.get("appointment_target_code")
        and not re.match(r"^[a-z][a-z0-9_]*$", r["appointment_target_code"])
    ]
    chk(
        "한글/비표준 target_code 0건",
        len(korean) == 0,
        f"{len(korean)}건: {[r['appointment_target_code'] for r in korean[:5]]}",
    )

    # 4. INSPECT executor
    inspect = [r for r in all_rules if r["obligation_type"] == "INSPECT"]
    no_exec = [r for r in inspect if not r.get("executor_type_code")]
    chk(
        f"INSPECT {len(inspect)}건 전부 executor_type_code 있음",
        len(no_exec) == 0,
        f"executor 없는 {len(no_exec)}건: {[r['rule_id'] for r in no_exec[:5]]}",
    )

    # 5. BUILDING INSPECT 4완비율
    bi = [r for r in inspect if r["sector"] == "BUILDING"]
    bi_ok = [
        r for r in bi
        if r.get("condition_code") and r.get("inspection_cycle_unit_code")
        and r.get("executor_type_code") and r.get("law_article")
    ]
    ratio_bi = int(len(bi_ok) / len(bi) * 100) if bi else 0
    chk(
        f"BUILDING INSPECT 4완비율 80% 이상 ({ratio_bi}%, {len(bi_ok)}/{len(bi)}건)",
        ratio_bi >= 80,
        f"미완비 {len(bi)-len(bi_ok)}건",
    )

    # 6. MANUFACTURING INSPECT condition 완비율
    mi = [r for r in inspect if r["sector"] == "MANUFACTURING"]
    mi_ok = [r for r in mi if r.get("condition_code")]
    ratio_mi = int(len(mi_ok) / len(mi) * 100) if mi else 0
    chk(
        f"MANUFACTURING INSPECT condition 완비율 60% 이상 ({ratio_mi}%, {len(mi_ok)}/{len(mi)}건)",
        ratio_mi >= 60,
        f"미설정 {len(mi)-len(mi_ok)}건",
    )

    # 7. sector 범위
    allowed_sectors = {
        "BUILDING", "MANUFACTURING", "CONSTRUCTION", "COMMON",
        "BUILDING_MANUFACTURING", "BUILDING_CONSTRUCTION",
        "CONSTRUCTION_MANUFACTURING", "SPECIAL_FACILITY",
    }
    bad_sector = [r for r in all_rules if r["sector"] not in allowed_sectors]
    chk(
        "sector 값 전부 허용 범위 내",
        len(bad_sector) == 0,
        f"{len(bad_sector)}건: {list(set(r['sector'] for r in bad_sector[:5]))}",
    )

    # 8. obligation_type 범위
    allowed_types = {"APPOINT", "INSPECT", "ACTION", "REPORT", "NOTIFY", "DOCUMENT", "OTHER"}
    bad_type = [r for r in all_rules if r["obligation_type"] not in allowed_types]
    chk(
        "obligation_type 값 전부 허용 범위 내",
        len(bad_type) == 0,
        f"{len(bad_type)}건: {list(set(r['obligation_type'] for r in bad_type[:5]))}",
    )

    # 결과
    total_checks = passed + failed + warnings
    print(f"\n{BOLD}{'═'*58}")
    print(f"  결과: ✅{passed}통과 / ❌{failed}실패 / ⚠️{warnings}경고 / 전체{total_checks}건")
    print(f"{'═'*58}{RESET}")

    if failed > 0:
        print(f"\n{RED}{BOLD}  ❌ DB 무결성 검증 실패 — 파이프라인 중단{RESET}")
        sys.exit(1)
    else:
        print(f"\n{GREEN}{BOLD}  ✅ DB 무결성 검증 통과{RESET}")


if __name__ == "__main__":
    main()
