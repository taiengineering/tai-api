"""
미매핑 법령 12개 수집 스크립트
법제처 API → law_master / law_version / law_article / law_paragraph 적재

실행:
  railway run python3 scripts/collect_missing_laws.py
  export $(cat .env | grep -v '#' | xargs) && python3 scripts/collect_missing_laws.py
"""

import os, requests, time, xml.etree.ElementTree as ET
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except Exception:
    pass

from supabase import create_client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_ANON_KEY")
LAW_API_KEY  = os.environ.get("LAW_API_KEY", "")  # 법제처 API 키

sb = create_client(SUPABASE_URL, SUPABASE_KEY)

BASE_URL = "https://www.law.go.kr/DRF"

# 수집 대상 법령 목록
TARGET_LAWS = [
    # BUILDING 섹터 미수집
    "근로기준법",
    "소음·진동관리법",
    "악취방지법",
    "토양환경보전법",
    "하수도법",
    "소방기본법",
    "소방시설공사업법",
    "수도법",
    "주차장법",
    "환경기술 및 환경산업 지원법",
    "장애인·노인·임산부 등의 편의증진 보장에 관한 법률",
    # SPECIAL_FACILITY 섹터 미수집
    "의료기기법",
]

def search_law(law_name: str):
    """법령명으로 법령 기본정보 검색"""
    params = {
        "OC": LAW_API_KEY,
        "target": "law",
        "type": "XML",
        "query": law_name,
        "display": 5,
    }
    try:
        resp = requests.get(f"{BASE_URL}/lawSearch.do", params=params, timeout=20)
        root = ET.fromstring(resp.text)
        for item in root.findall(".//law"):
            name = item.findtext("법령명한글", "").strip()
            if name == law_name or law_name in name:
                return {
                    "law_id":   item.findtext("법령ID", ""),
                    "mst":      item.findtext("법령일련번호", ""),
                    "law_name": name,
                    "law_type": item.findtext("법령구분명", ""),
                }
    except Exception as e:
        print(f"  검색 오류({law_name}): {e}")
    return None

def fetch_law_detail(mst: str):
    """법령 전문 조회 (조문 포함)"""
    params = {"OC": LAW_API_KEY, "target": "law", "type": "XML", "MST": mst}
    try:
        resp = requests.get(f"{BASE_URL}/lawService.do", params=params, timeout=30)
        return ET.fromstring(resp.text)
    except Exception as e:
        print(f"  전문 조회 오류({mst}): {e}")
        return None

def get_or_create_law_master(law_name: str, law_type: str):
    """law_master upsert → id 반환"""
    type_code_map = {
        "법률": "LAW",
        "대통령령": "ENFORCEMENT_DECREE",
        "부령": "ENFORCEMENT_RULE",
        "총리령": "ENFORCEMENT_RULE",
    }
    type_code = type_code_map.get(law_type, "LAW")

    existing = sb.table("law_master").select("id").eq("law_name", law_name).execute()
    if existing.data:
        return existing.data[0]["id"]

    res = sb.table("law_master").insert({
        "law_name": law_name,
        "law_type_code": type_code,
        "is_active": True,
    }).execute()
    return res.data[0]["id"] if res.data else None

def get_or_create_version(law_id: str, law_master_id: str, proclamation_no: str = ""):
    """law_version upsert → id 반환"""
    existing = sb.table("law_version").select("id")\
        .eq("law_id", law_master_id).eq("is_current", True).execute()
    if existing.data:
        return existing.data[0]["id"]

    res = sb.table("law_version").insert({
        "law_id":          law_master_id,
        "external_law_id": law_id,
        "proclamation_no": proclamation_no,
        "is_current":      True,
    }).execute()
    return res.data[0]["id"] if res.data else None

def insert_articles(version_id: str, root: ET.Element):
    """조문 + 항 삽입"""
    articles_inserted = 0
    paras_inserted = 0

    # 기존 조문 삭제 (재수집)
    old_arts = sb.table("law_article").select("id").eq("law_version_id", version_id).execute()
    for art in (old_arts.data or []):
        sb.table("law_paragraph").delete().eq("article_id", art["id"]).execute()
    sb.table("law_article").delete().eq("law_version_id", version_id).execute()

    sort_idx = 0
    for cond in root.findall(".//조문단위"):
        art_no_raw = cond.findtext("조번호", "").strip()
        art_title  = cond.findtext("조제목", "").strip()
        art_text   = cond.findtext("조문내용", "").strip()

        try:
            art_no_int = int(art_no_raw) if art_no_raw.isdigit() else 0
        except Exception:
            art_no_int = 0

        sort_idx += 1
        art_res = sb.table("law_article").insert({
            "law_version_id":    version_id,
            "article_no":        art_no_int,
            "article_no_sort":   sort_idx,
            "article_title":     art_title[:200] if art_title else None,
            "article_text":      art_text[:2000] if art_text else None,
            "article_type":      "ARTICLE",
            "article_status_code": "ACTIVE",
        }).execute()

        if not art_res.data:
            continue
        art_id = art_res.data[0]["id"]
        articles_inserted += 1

        # 항 삽입
        para_sort = 0
        for para in cond.findall(".//항"):
            para_no   = para.findtext("항번호", "").strip()
            para_text = para.findtext("항내용", "").strip()
            if not para_text:
                continue
            para_sort += 1
            try:
                sb.table("law_paragraph").insert({
                    "article_id":    art_id,
                    "paragraph_no":  para_no,
                    "paragraph_no_sort": para_sort,
                    "paragraph_text": para_text[:2000],
                    "paragraph_status_code": "ACTIVE",
                }).execute()
                paras_inserted += 1
            except Exception:
                pass

    return articles_inserted, paras_inserted

def collect_law(law_name: str):
    print(f"\n  [{law_name}] 수집 시작...")

    # 1. 검색
    info = search_law(law_name)
    if not info:
        print(f"  → 검색 실패: {law_name}")
        return False

    print(f"  → 발견: {info['law_name']} ({info['law_type']})")
    time.sleep(0.5)

    # 2. 전문 조회
    root = fetch_law_detail(info["mst"])
    if root is None:
        print(f"  → 전문 조회 실패")
        return False
    time.sleep(0.5)

    # 3. law_master
    master_id = get_or_create_law_master(info["law_name"], info["law_type"])
    if not master_id:
        print(f"  → law_master 생성 실패")
        return False

    # 4. law_version
    version_id = get_or_create_version(info["law_id"], master_id, info["mst"])
    if not version_id:
        print(f"  → law_version 생성 실패")
        return False

    # 5. 조문 + 항 삽입
    arts, paras = insert_articles(version_id, root)
    print(f"  → 조문 {arts}개 / 항 {paras}개 적재 완료")
    return True

def main():
    print("=" * 60)
    print("미매핑 법령 12개 수집 시작")
    print("=" * 60)

    success = 0
    fail    = 0
    for law_name in TARGET_LAWS:
        ok = collect_law(law_name)
        if ok:
            success += 1
        else:
            fail += 1
        time.sleep(0.3)

    print(f"\n{'='*60}")
    print(f"완료: 성공 {success}개 / 실패 {fail}개")
    print(f"{'='*60}")

    # 최종 매핑 확인
    print("\n미매핑 잔여 확인:")
    res = sb.rpc("query", {"sql": """
        SELECT COUNT(*) as cnt
        FROM master_building_legal_rules r
        LEFT JOIN law_master lm ON lm.law_name = r.law_name
        WHERE r.is_active = true AND lm.id IS NULL
    """}).execute()

    # 직접 쿼리
    from supabase import create_client
    result = sb.table("law_master").select("law_name").in_(
        "law_name", TARGET_LAWS
    ).execute()
    collected = [r["law_name"] for r in (result.data or [])]
    missing   = [n for n in TARGET_LAWS if n not in collected]
    print(f"  수집됨: {len(collected)}개")
    if missing:
        print(f"  미수집: {missing}")
    else:
        print(f"  전체 수집 완료!")

if __name__ == "__main__":
    main()
