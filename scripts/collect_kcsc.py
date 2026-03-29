"""
KCSC(국가건설기준센터) API → 건설공종·작업 수집
DB: kcsc_process_master, kcsc_work_master

실행:
  python3 scripts/collect_kcsc.py
  또는
  railway run python3 scripts/collect_kcsc.py

API 인증키: BHunaeOUSfy0qKRhE7106HEQFbql_8Ew4z1ub9ccjpk
유효기간: 2027-03-29까지
"""

import os, requests, time
from pathlib import Path
from supabase import create_client

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except Exception:
    pass

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_ANON_KEY")
KCSC_API_KEY = "BHunaeOUSfy0qKRhE7106HEQFbql_8Ew4z1ub9ccjpk"
KCSC_BASE    = "https://kcsc.re.kr/OpenApi"

sb = create_client(SUPABASE_URL, SUPABASE_KEY)

# ══════════════════════════════════════════
# 건축/토목 판별 (fullCode 앞자리 기준)
# KCS 분류체계:
#   11 = 건축공사
#   14 = 토목공사
#   21 = 설비공사 (건축부속)
#   기타 = 공통
# ══════════════════════════════════════════
def classify_construction_type(full_code: str, parent_name: str = "") -> str:
    if not full_code:
        return "COMMON"
    prefix = str(full_code)[:2]
    if prefix in ("11", "21"):
        return "BUILDING"
    if prefix in ("14", "12", "13", "15", "17"):
        return "CIVIL"
    if "건축" in parent_name:
        return "BUILDING"
    if "토목" in parent_name or "도로" in parent_name or "교량" in parent_name or "터널" in parent_name:
        return "CIVIL"
    return "COMMON"


# 위험작업 키워드 분류
HAZARD_KEYWORDS = {
    "굴착":     "굴착작업",
    "굴토":     "굴착작업",
    "터파기":   "굴착작업",
    "발파":     "발파작업",
    "고소":     "고소작업",
    "비계":     "고소작업",
    "거푸집":   "거푸집작업",
    "동바리":   "거푸집작업",
    "철골":     "철골작업",
    "크레인":   "중장비작업",
    "항타":     "중장비작업",
    "화기":     "화기작업",
    "용접":     "화기작업",
    "밀폐":     "밀폐공간",
    "콘크리트 타설": "콘크리트작업",
    "터널":     "터널작업",
    "수중":     "수중작업",
}

def detect_hazard(title: str):
    for kw, htype in HAZARD_KEYWORDS.items():
        if kw in title:
            return True, htype
    return False, None


# ══════════════════════════════════════════
# STEP 1: 전체 KCS 코드 목록 수집
# ══════════════════════════════════════════
def fetch_code_list():
    print("전체 KCS/KDS 코드 목록 수집 중...")
    try:
        resp = requests.get(f"{KCSC_BASE}/CodeList", params={"key": KCSC_API_KEY}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        kcs_list = [d for d in data if d.get("codeType") == "KCS"]
        print(f"  전체: {len(data)}개 / KCS(표준시방서): {len(kcs_list)}개")
        return kcs_list
    except Exception as e:
        print(f"  코드목록 수집 실패: {e}")
        return []


# ══════════════════════════════════════════
# STEP 2: 개별 KCS 코드 상세 (공종 + 작업목차) 수집
# ══════════════════════════════════════════
def fetch_code_detail(kcs_code: str):
    try:
        resp = requests.get(
            f"{KCSC_BASE}/CodeViewer/KCS/{kcs_code}",
            params={"key": KCSC_API_KEY},
            timeout=20
        )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list) and data:
            return data[0]
        return data if isinstance(data, dict) else None
    except Exception as e:
        print(f"    상세 수집 실패({kcs_code}): {e}")
        return None


# ══════════════════════════════════════════
# STEP 3: DB 적재
# ══════════════════════════════════════════
def upsert_process(item: dict, kcs_code: str):
    parent_codes = item.get("listParentCodes") or []
    level1 = parent_codes[1].get("name", "") if len(parent_codes) > 1 else ""
    level2 = parent_codes[2].get("name", "") if len(parent_codes) > 2 else ""
    full_code = item.get("fullCode", "")
    c_type = classify_construction_type(full_code, level1)

    row = {
        "kcs_code":         kcs_code,
        "full_code":        full_code,
        "process_name":     item.get("name", ""),
        "construction_type": c_type,
        "level1_name":      level1,
        "level2_name":      level2,
        "version":          item.get("version", ""),
        "updated_at_kcsc":  item.get("updateDate"),
        "is_active":        True,
    }
    try:
        res = sb.table("kcsc_process_master").upsert(
            row, on_conflict="kcs_code"
        ).execute()
        return res.data[0]["id"] if res.data else None
    except Exception as e:
        print(f"    공종 적재 실패({kcs_code}): {e}")
        return None


def upsert_works(process_id: str, kcs_code: str, work_list: list):
    if not work_list:
        return 0

    # 기존 작업 삭제 후 재삽입 (멱등성)
    sb.table("kcsc_work_master").delete().eq("process_id", process_id).execute()

    rows = []
    in_construction = False  # "시공" 섹션 여부

    for item in work_list:
        title   = item.get("title", "")
        level   = item.get("level", 1)
        sort    = item.get("sort", 0)
        contents = item.get("contents", "") or ""

        # "3. 시공" 섹션 감지 → 이 이후가 실제 작업
        if level == 1 and "시공" in title:
            in_construction = True
        elif level == 1 and "시공" not in title:
            in_construction = False

        is_hazardous, hazard_type = detect_hazard(title)

        rows.append({
            "process_id":   process_id,
            "kcs_code":     kcs_code,
            "sort_order":   sort,
            "level":        level,
            "title":        title[:300],
            "contents":     contents[:2000] if contents else None,
            "is_work_item": in_construction and level >= 2,
            "is_hazardous": is_hazardous,
            "hazard_type":  hazard_type,
            "is_active":    True,
        })

    if not rows:
        return 0

    # 50개씩 배치 삽입
    inserted = 0
    for i in range(0, len(rows), 50):
        try:
            res = sb.table("kcsc_work_master").insert(rows[i:i+50]).execute()
            inserted += len(res.data or [])
        except Exception as e:
            print(f"    작업 적재 실패: {e}")
    return inserted


# ══════════════════════════════════════════
# 메인
# ══════════════════════════════════════════
def main():
    print("=" * 60)
    print("KCSC 건설공종·작업 수집 시작")
    print("=" * 60)

    # 전체 KCS 목록
    kcs_list = fetch_code_list()
    if not kcs_list:
        print("수집 실패")
        return

    total_process = 0
    total_works   = 0
    errors        = []

    for idx, item in enumerate(kcs_list):
        kcs_code = item.get("code", "")
        name     = item.get("name", "")
        if not kcs_code:
            continue

        print(f"\n[{idx+1}/{len(kcs_list)}] {kcs_code} — {name}")

        # 상세 수집
        detail = fetch_code_detail(kcs_code)
        if not detail:
            errors.append(kcs_code)
            time.sleep(0.3)
            continue

        # 공종 적재
        process_id = upsert_process(detail, kcs_code)
        if not process_id:
            errors.append(kcs_code)
            continue
        total_process += 1

        # 작업 목차 적재
        work_list = detail.get("list") or []
        n = upsert_works(process_id, kcs_code, work_list)
        total_works += n
        print(f"  → 작업 {n}개 적재")

        time.sleep(0.2)  # API 부하 방지

    print("\n" + "=" * 60)
    print(f"수집 완료")
    print(f"  공종: {total_process}개")
    print(f"  작업: {total_works}개")
    print(f"  오류: {len(errors)}개 ({', '.join(errors[:10])})")
    print("=" * 60)

    # 최종 현황
    print("\nDB 현황:")
    p = sb.table("kcsc_process_master").select("id", count="exact").execute()
    w = sb.table("kcsc_work_master").select("id", count="exact").execute()
    h = sb.table("kcsc_work_master").select("id", count="exact").eq("is_hazardous", True).execute()
    b = sb.table("kcsc_process_master").select("id", count="exact").eq("construction_type", "BUILDING").execute()
    c = sb.table("kcsc_process_master").select("id", count="exact").eq("construction_type", "CIVIL").execute()
    print(f"  공종 전체: {p.count}개")
    print(f"    건축(BUILDING): {b.count}개")
    print(f"    토목(CIVIL):    {c.count}개")
    print(f"  작업 전체: {w.count}개")
    print(f"    위험작업:       {h.count}개")


if __name__ == "__main__":
    main()
