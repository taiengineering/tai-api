#!/usr/bin/env python3
"""
collect_phase4_full.py — S9 Phase 4 통합 본문 수집 (v3.1)
====================================================
v3.1 수정 (2026-05-03):
  - lm_data에 law_key NOT NULL 컬럼 추가 ({api_id}_{mst_no} 패턴)
"""

import os, sys, json, time, argparse, traceback
from datetime import datetime, timezone
from typing import Optional

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import requests
    from supabase import create_client, Client
except ImportError:
    print("[ERROR] 필요 패키지 설치: pip install supabase python-dotenv requests")
    sys.exit(1)

try:
    from routers.law_collector_admrul import fetch_admrul_content, parse_admrul_content_xml
except Exception as e:
    print(f"[FATAL] routers/law_collector_admrul.py import 실패: {e}")
    sys.exit(1)

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY", "")
LAW_OC = "taieng"

if not SUPABASE_URL or not SUPABASE_KEY:
    print("[FATAL] SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY 필요")
    sys.exit(1)

sb: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

PHASE_A_LAWS = [
    "소방기본법",
    "건축물의 에너지원단위 목표관리 등에 관한 고시",
    "고압가스 및 액화석유가스 ISO 탱크 컨테이너의 제조, 충전·운반, 저장·사용에 관한 기준",
    "기존 건축물의 에너지성능 개선기준",
]

STATS = {
    "phase_a_inserted": 0, "phase_a_skipped": 0, "phase_a_failed": 0,
    "phase_b_collected": 0, "phase_b_skipped": 0, "phase_b_failed": 0,
    "phase_b_articles": 0,
}

DEBUG_DIR = "scripts/_phase4_debug"


def log(msg: str, level: str = "INFO"):
    icons = {"INFO": "ℹ️", "OK": "✓", "WARN": "⚠️", "ERR": "❌", "PHASE": "▶"}
    print(f"  {icons.get(level, '·')} {msg}")


def save_debug(name: str, data):
    os.makedirs(DEBUG_DIR, exist_ok=True)
    if isinstance(data, str):
        path = f"{DEBUG_DIR}/{name}.xml"
        with open(path, "w", encoding="utf-8") as f:
            f.write(data)
        return path
    path = f"{DEBUG_DIR}/{name}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def law_search(query: str, target: str = "law", display: int = 5):
    url = "https://www.law.go.kr/DRF/lawSearch.do"
    params = {"OC": LAW_OC, "target": target, "type": "JSON", "query": query, "display": display}
    try:
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
        if target == "law":
            items = data.get("LawSearch", {}).get("law", [])
        else:
            items = data.get("AdmRulSearch", {}).get("admrul", [])
        if isinstance(items, dict):
            items = [items]
        return items
    except Exception as e:
        log(f"검색 실패 ({query}, target={target}): {e}", "WARN")
        return []


def detect_target_from_type(law_type_code: str) -> str:
    if law_type_code in ("LAW", "ENFORCEMENT_DECREE", "ENFORCEMENT_RULE"):
        return "law"
    return "admrul"


def detect_type_from_meta(meta: dict, law_name: str) -> str:
    sort_name = meta.get("법령구분명", "") or meta.get("행정규칙종류", "")
    if "시행령" in sort_name or "시행령" in law_name:
        return "ENFORCEMENT_DECREE"
    if "시행규칙" in sort_name or "시행규칙" in law_name:
        return "ENFORCEMENT_RULE"
    if "고시" in sort_name or "고시" in law_name:
        return "NOTICE"
    if "법" in sort_name and "시행" not in sort_name:
        return "LAW"
    if "기준" in sort_name or "기준" in law_name:
        return "NOTICE"
    return "LAW"


def phase_a(dry_run: bool = False):
    print("\n" + "=" * 60)
    print("[PHASE A] catalog 미등록 4건 등록")
    print("=" * 60)

    for law_name in PHASE_A_LAWS:
        log(f"검색 중: {law_name}", "PHASE")
        existing = sb.table("law_external_catalog").select("id").eq("law_name", law_name).execute()
        if existing.data:
            log("이미 catalog에 있음, skip", "WARN")
            STATS["phase_a_skipped"] += 1
            continue

        items = law_search(law_name, target="law", display=10)
        meta = None
        target = "law"
        for it in items:
            it_name = (it.get("법령명한글") or "").strip()
            if it_name == law_name:
                meta = it
                break

        if not meta:
            items = law_search(law_name, target="admrul", display=10)
            for it in items:
                it_name = (it.get("행정규칙명") or "").strip()
                if it_name == law_name:
                    meta = it
                    target = "admrul"
                    break
            if not meta and items:
                meta = items[0]
                target = "admrul"

        if not meta:
            log("law.go.kr에서 찾을 수 없음", "ERR")
            STATS["phase_a_failed"] += 1
            continue

        law_type_code = detect_type_from_meta(meta, law_name)
        if target == "law":
            law_api_id = meta.get("법령일련번호", "")
            law_mst_no = meta.get("법령ID") or meta.get("법령일련번호", "")
        else:
            law_api_id = meta.get("행정규칙일련번호", "")
            law_mst_no = meta.get("행정규칙ID") or meta.get("행정규칙일련번호", "")
            law_type_code = "NOTICE"

        ministry_name = meta.get("소관부처명", "") or meta.get("소관부처", "")
        log(f"발견: api_id={law_api_id}, type={law_type_code}, ministry={ministry_name}", "INFO")

        if dry_run:
            log("[DRY-RUN] INSERT 스킵", "INFO")
            continue

        try:
            sb.table("law_external_catalog").insert({
                "law_name": law_name,
                "law_api_id": str(law_api_id),
                "law_mst_no": str(law_mst_no) if law_mst_no else None,
                "law_type_code": law_type_code,
                "ministry_name": ministry_name,
                "saas_relevance": "CORE",
                "is_in_collection_target": True,
                "is_in_law_master": False,
                "collected_at": datetime.now(timezone.utc).isoformat(),
                "api_target": target,
                "search_keyword": "S9_phase4_manual",
            }).execute()
            log("catalog 등록 완료", "OK")
            STATS["phase_a_inserted"] += 1
        except Exception as e:
            log(f"INSERT 실패: {e}", "ERR")
            STATS["phase_a_failed"] += 1

        time.sleep(0.5)

    print(f"\n[PHASE A 결과] 등록 {STATS['phase_a_inserted']} / 스킵 {STATS['phase_a_skipped']} / 실패 {STATS['phase_a_failed']}")


def fetch_collection_targets():
    targets = sb.table("law_external_catalog") \
        .select("id,law_name,law_api_id,law_mst_no,law_type_code,ministry_name") \
        .eq("is_in_collection_target", True) \
        .execute()
    target_rows = targets.data or []
    existing = sb.table("law_master").select("law_name").execute()
    existing_names = {r["law_name"] for r in (existing.data or [])}
    return [r for r in target_rows if r["law_name"] not in existing_names]


def fetch_and_parse_law_json(api_id: str) -> dict:
    url = "https://www.law.go.kr/DRF/lawService.do"
    params = {"OC": LAW_OC, "target": "law", "type": "JSON", "ID": api_id}
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()

    block = data.get("법령", {})
    if not block:
        if "Law" in data and isinstance(data["Law"], str):
            raise Exception(f"법령 fetch 거부: {data['Law'][:100]}")
        raise Exception(f"법령 응답 키 없음. keys={list(data.keys())}")

    basic_raw = block.get("기본정보", {})
    articles_raw = block.get("조문", {}).get("조문단위", [])
    if isinstance(articles_raw, dict):
        articles_raw = [articles_raw]

    unified_articles = []
    for idx, art in enumerate(articles_raw, start=1):
        if not isinstance(art, dict):
            continue
        art_no_raw = art.get("조문번호", "") or art.get("조번호", "")
        art_sub_raw = art.get("조문가지번호", "") or art.get("조문가지", "")
        art_title = art.get("조문제목", "") or art.get("조제목", "") or ""
        content_list = art.get("조문내용", []) or art.get("내용", "")
        if isinstance(content_list, dict):
            content_list = [content_list]
        if isinstance(content_list, list):
            text_parts = []
            for c in content_list:
                if isinstance(c, dict):
                    text_parts.append(c.get("조문내용텍스트", "") or c.get("내용", "") or str(c))
                else:
                    text_parts.append(str(c))
            article_text = "\n".join(text_parts)
        else:
            article_text = str(content_list or "")

        art_no_int = None
        try:
            s = str(art_no_raw).strip().lstrip("0") or "0"
            if s.isdigit():
                art_no_int = int(s)
        except Exception:
            pass
        art_sub_int = None
        try:
            if str(art_sub_raw).strip().isdigit():
                art_sub_int = int(art_sub_raw)
        except Exception:
            pass

        if art_sub_int:
            internal_key = f"law-art-{art_no_int:03d}-of-{art_sub_int:02d}" if art_no_int else f"law-art-idx-{idx:03d}"
        else:
            internal_key = f"law-art-{art_no_int:03d}" if art_no_int else f"law-art-idx-{idx:03d}"

        unified_articles.append({
            "article_internal_key": internal_key,
            "article_no": art_no_int,
            "article_sub_no": art_sub_int,
            "article_type": "본칙",
            "article_title": (art_title or "")[:200],
            "article_text": (article_text or "")[:30000],
            "enforcement_date": None,
            "is_changed": False,
        })

    basic = {
        "announcement_date": basic_raw.get("공포일자", "") or "",
        "enforcement_date": basic_raw.get("시행일자", "") or "",
        "law_number": basic_raw.get("공포번호", "") or "",
    }
    return {"basic": basic, "articles": unified_articles, "format": "law_json"}


def fetch_and_parse_admrul(api_id: str) -> dict:
    result = fetch_admrul_content(api_id)
    if not result["ok"]:
        raise Exception(f"admrul fetch HTTP 실패: status={result['status']}")
    parsed = parse_admrul_content_xml(result["xml"])

    return {
        "basic": {
            "announcement_date": parsed["info"].get("announcement_date") or "",
            "enforcement_date": parsed["info"].get("enforcement_date") or "",
            "law_number": parsed["info"].get("law_number", "") or "",
            "_parse_mode": parsed["info"].get("_parse_mode", "?"),
        },
        "articles": parsed["articles"],
        "format": "admrul_xml",
    }


def insert_law_master_and_articles(meta: dict, parsed: dict):
    law_name = meta["law_name"]
    law_type_code = meta.get("law_type_code", "LAW")
    basic = parsed["basic"]

    def norm_date(s) -> Optional[str]:
        if not s:
            return None
        s = str(s).replace(".", "").replace("-", "").strip()
        if len(s) == 8 and s.isdigit():
            return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
        return None

    announcement_date = norm_date(basic.get("announcement_date"))
    enforcement_date = norm_date(basic.get("enforcement_date"))
    law_number = basic.get("law_number") or ""

    api_id = meta.get("law_api_id") or ""
    mst_no = meta.get("law_mst_no") or api_id
    # ★ law_key NOT NULL — 기존 패턴: "{api_id}_{mst_no}"
    law_key = f"{api_id}_{mst_no}"

    lm_data = {
        "law_key": law_key,                                # ★ 추가
        "law_name": law_name,
        "law_api_id": api_id,
        "law_mst_no": mst_no,
        "law_type_code": law_type_code,
        "ministry_name": meta.get("ministry_name", ""),
        "law_number": str(law_number) if law_number else None,
        "announcement_date": announcement_date,
        "enforcement_date": enforcement_date,
        "law_status_code": "EFFECTIVE",
        "is_active": True,
        "source_system": "law.go.kr",
        "source_url": f"https://www.law.go.kr/lsInfoP.do?lsiSeq={api_id}",
    }
    lm_resp = sb.table("law_master").insert(lm_data).execute()
    if not lm_resp.data:
        raise Exception("law_master INSERT 응답 비어있음")
    law_master_id = lm_resp.data[0]["id"]

    lv_data = {
        "law_id": law_master_id,
        "version_no": "1",
        "announcement_date": announcement_date,
        "enforcement_date": enforcement_date,
        "law_status_code": "EFFECTIVE",
        "is_current": True,
    }
    lv_resp = sb.table("law_version").insert(lv_data).execute()
    if not lv_resp.data:
        raise Exception("law_version INSERT 응답 비어있음")
    law_version_id = lv_resp.data[0]["id"]

    sb.table("law_master").update({"current_version_id": law_version_id}).eq("id", law_master_id).execute()

    article_count = 0
    for idx, art in enumerate(parsed["articles"], start=1):
        try:
            sb.table("law_article").insert({
                "law_version_id": law_version_id,
                "law_id": law_master_id,
                "article_no": art.get("article_no"),
                "article_sub_no": art.get("article_sub_no"),
                "article_no_sort": idx,
                "article_type": art.get("article_type", "본칙"),
                "article_title": (art.get("article_title") or "")[:200],
                "article_text": (art.get("article_text") or "")[:30000],
                "article_internal_key": art.get("article_internal_key") or f"{law_master_id}-idx-{idx}",
                "article_status_code": "EFFECTIVE",
                "is_changed": art.get("is_changed", False),
                "is_deleted_in_version": False,
            }).execute()
            article_count += 1
        except Exception as e:
            log(f"  article INSERT 실패 (조문 {art.get('article_no')}): {e}", "WARN")

    return law_master_id, article_count


def phase_b(dry_run: bool = False, debug_first: bool = False):
    print("\n" + "=" * 60)
    print("[PHASE B] 본문 수집 (v3.1 — law_key 추가)")
    print("=" * 60)

    targets = fetch_collection_targets()
    log(f"수집 대상: {len(targets)}건", "PHASE")

    if dry_run:
        print("\n[DRY-RUN] 다음 항목들이 수집됩니다:")
        for i, t in enumerate(targets, 1):
            print(f"  [{i:>3}] [{t['law_type_code']}] {t['law_name']} (api_id={t['law_api_id']})")
        return

    if debug_first:
        if not targets:
            log("수집 대상 없음", "WARN")
            return
        t = targets[0]
        target_endpoint = detect_target_from_type(t["law_type_code"])
        log(f"[DEBUG] 첫 1건: {t['law_name']} (api_id={t['law_api_id']}, target={target_endpoint})", "PHASE")
        try:
            if target_endpoint == "law":
                parsed = fetch_and_parse_law_json(t["law_api_id"])
            else:
                parsed = fetch_and_parse_admrul(t["law_api_id"])
            log(f"파싱 OK: format={parsed['format']}, articles={len(parsed['articles'])}개", "OK")
            log(f"basic: {parsed['basic']}", "INFO")
            if parsed["articles"]:
                first_art = parsed["articles"][0]
                log(f"첫 article: no={first_art.get('article_no')}, title={first_art.get('article_title')[:50]}, text_len={len(first_art.get('article_text',''))}", "INFO")
        except Exception as e:
            log(f"파싱 실패: {e}", "ERR")
            traceback.print_exc()
        return

    for i, t in enumerate(targets, 1):
        log(f"[{i:>3}/{len(targets)}] [{t['law_type_code']}] {t['law_name'][:50]}...", "PHASE")
        if not t.get("law_api_id"):
            log("law_api_id 없음, skip", "WARN")
            STATS["phase_b_skipped"] += 1
            continue

        target_endpoint = detect_target_from_type(t["law_type_code"])
        try:
            if target_endpoint == "law":
                parsed = fetch_and_parse_law_json(t["law_api_id"])
            else:
                parsed = fetch_and_parse_admrul(t["law_api_id"])
            law_master_id, art_cnt = insert_law_master_and_articles(t, parsed)
            sb.table("law_external_catalog").update({"is_in_law_master": True}).eq("id", t["id"]).execute()
            log(f"수집 완료 (조문 {art_cnt}개, format={parsed['format']})", "OK")
            STATS["phase_b_collected"] += 1
            STATS["phase_b_articles"] += art_cnt
        except Exception as e:
            log(f"수집 실패: {e}", "ERR")
            if i <= 3:
                traceback.print_exc()
            STATS["phase_b_failed"] += 1

        time.sleep(1.0)

    print(f"\n[PHASE B 결과] 수집 {STATS['phase_b_collected']} / 스킵 {STATS['phase_b_skipped']} / 실패 {STATS['phase_b_failed']}")
    print(f"             조문 합계: {STATS['phase_b_articles']}개")


def phase_c():
    print("\n" + "=" * 60)
    print("[PHASE C] L1+L2+L3 무결성 검증")
    print("=" * 60)

    targets = sb.table("law_external_catalog").select("law_name").eq("is_in_collection_target", True).execute()
    target_names = [r["law_name"] for r in (targets.data or [])]
    masters = sb.table("law_master").select("law_name").execute()
    master_names = {r["law_name"] for r in (masters.data or [])}
    missing = [n for n in target_names if n not in master_names]
    if missing:
        log(f"L1 FAIL: {len(missing)}건 미수집", "ERR")
        for n in missing[:10]:
            print(f"     - {n}")
        if len(missing) > 10:
            print(f"     ... +{len(missing) - 10}건")
    else:
        log(f"L1 OK: catalog target {len(target_names)}건 모두 law_master에 존재", "OK")

    masters_full = sb.table("law_master").select("id,law_name,current_version_id").execute()
    no_version = [m for m in (masters_full.data or []) if not m.get("current_version_id")]
    if no_version:
        log(f"L2 FAIL: {len(no_version)}건이 current_version_id 없음", "ERR")
        for m in no_version[:5]:
            print(f"     - {m['law_name']}")
    else:
        log(f"L2 OK: 모든 law_master({len(masters_full.data or [])})에 current_version 존재", "OK")

    versions = sb.table("law_version").select("id,law_id").execute()
    no_articles = []
    for v in (versions.data or [])[:50]:
        arts = sb.table("law_article").select("id", count="exact").eq("law_version_id", v["id"]).limit(1).execute()
        if arts.count == 0:
            no_articles.append(v["id"])
    if no_articles:
        log(f"L3 FAIL: {len(no_articles)}건 (샘플 50개 중)이 article 0개", "ERR")
    else:
        log(f"L3 OK: 검사한 version 모두 article >= 1", "OK")
    print()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--phase", choices=["a", "b", "c", "all"], default="all")
    p.add_argument("--debug-first", action="store_true")
    args = p.parse_args()

    print(f"\n{'=' * 60}")
    print(f"  S9 Phase 4 통합 수집 v3.1 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  dry_run={args.dry_run} / phase={args.phase} / debug_first={args.debug_first}")
    print(f"{'=' * 60}")

    if args.debug_first:
        phase_b(dry_run=False, debug_first=True)
        return

    if args.phase in ("a", "all"):
        phase_a(dry_run=args.dry_run)
    if args.phase in ("b", "all"):
        phase_b(dry_run=args.dry_run)
    if args.phase in ("c", "all"):
        phase_c()

    print("\n" + "=" * 60)
    print(f"  완료 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Phase A: 등록 {STATS['phase_a_inserted']} / 스킵 {STATS['phase_a_skipped']} / 실패 {STATS['phase_a_failed']}")
    print(f"  Phase B: 수집 {STATS['phase_b_collected']} / 스킵 {STATS['phase_b_skipped']} / 실패 {STATS['phase_b_failed']} / 조문 {STATS['phase_b_articles']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
