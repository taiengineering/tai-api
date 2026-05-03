#!/usr/bin/env python3
"""
collect_phase4_full.py — S9 Phase 4 (v5 — admrul dedupe 추가)
=========================================================================
v5 (2026-05-03):
  - admrul 결과에 _dedupe_articles_by_internal_key 적용
    (LAW는 parse_law_content_xml 내부에서 자동 dedupe됨,
     admrul은 parse_admrul_content_xml이 dedupe 없음 → 같은 internal_key 충돌)

실행:
  cd ~/dev/tai-api && git pull
  railway run python3 scripts/collect_phase4_full.py            # all
  railway run python3 scripts/collect_phase4_full.py --phase b
  railway run python3 scripts/collect_phase4_full.py --debug-first
"""

import os, sys, time, argparse, traceback
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ─── 파이프라인 본체 import ──────────────────────────────────────────
try:
    from routers.law_collector import (
        fetch_law_list, parse_law_list_xml,
        fetch_law_content, parse_law_content_xml,
        save_law_to_db,
        _dedupe_articles_by_internal_key,   # v5: admrul에도 적용
    )
    from routers.law_collector_admrul import (
        fetch_admrul_content, parse_admrul_content_xml,
    )
    from db.database import get_supabase
except Exception as e:
    print(f"[FATAL] 파이프라인 모듈 import 실패: {e}")
    sys.exit(1)

import requests

LAW_OC = os.environ.get("LAW_API_OC", "taieng")
sb = get_supabase()

PHASE_A_LAWS = [
    "소방기본법",
    "건축물의 에너지원단위 목표관리 등에 관한 고시",
    "고압가스 및 액화석유가스 ISO 탱크 컨테이너의 제조, 충전·운반, 저장·사용에 관한 기준",
    "기존 건축물의 에너지성능 개선기준",
]

STATS = {
    "phase_a_inserted": 0, "phase_a_skipped": 0, "phase_a_failed": 0,
    "phase_b_collected": 0, "phase_b_failed": 0, "phase_b_articles": 0,
}


def log(msg, level="INFO"):
    icons = {"INFO": "ℹ️", "OK": "✓", "WARN": "⚠️", "ERR": "❌", "PHASE": "▶"}
    print(f"  {icons.get(level, '·')} {msg}")


# ============================================================
# Phase A
# ============================================================
def _law_search_meta(query, target):
    url = "https://www.law.go.kr/DRF/lawSearch.do"
    params = {"OC": LAW_OC, "target": target, "type": "JSON", "query": query, "display": 10}
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
        name_key = "법령명한글" if target == "law" else "행정규칙명"
        for it in items:
            if (it.get(name_key) or "").strip() == query:
                return it
        return items[0] if items else None
    except Exception as e:
        log(f"검색 실패 ({query}, {target}): {e}", "WARN")
        return None


def phase_a(dry_run=False):
    print("\n" + "=" * 60)
    print("[PHASE A] catalog 미등록 4건 등록")
    print("=" * 60)

    for law_name in PHASE_A_LAWS:
        log(f"검색: {law_name}", "PHASE")
        existing = sb.table("law_external_catalog").select("id").eq("law_name", law_name).execute()
        if existing.data:
            log("이미 catalog에 있음, skip", "WARN")
            STATS["phase_a_skipped"] += 1
            continue

        meta = _law_search_meta(law_name, "law")
        target = "law"
        if not meta:
            meta = _law_search_meta(law_name, "admrul")
            target = "admrul"
        if not meta:
            log("law.go.kr에서 찾을 수 없음", "ERR")
            STATS["phase_a_failed"] += 1
            continue

        if target == "law":
            law_api_id = meta.get("법령ID", "") or meta.get("법령일련번호", "")
            law_mst_no = meta.get("법령일련번호", "")
            sort_name = meta.get("법령구분명", "")
            if "시행령" in sort_name or "시행령" in law_name:
                law_type_code = "ENFORCEMENT_DECREE"
            elif "시행규칙" in sort_name or "시행규칙" in law_name:
                law_type_code = "ENFORCEMENT_RULE"
            else:
                law_type_code = "LAW"
        else:
            law_api_id = meta.get("행정규칙ID", "") or meta.get("행정규칙일련번호", "")
            law_mst_no = meta.get("행정규칙일련번호", "")
            law_type_code = "NOTICE"

        ministry_name = meta.get("소관부처명", "") or meta.get("소관부처", "")
        log(f"발견: api_id={law_api_id}, mst={law_mst_no}, type={law_type_code}", "INFO")

        if dry_run:
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


# ============================================================
# Phase B
# ============================================================
def fetch_collection_targets():
    targets = sb.table("law_external_catalog") \
        .select("id,law_name,law_api_id,law_mst_no,law_type_code,ministry_name,api_target") \
        .eq("is_in_collection_target", True) \
        .execute().data or []
    masters = sb.table("law_master").select("law_name").execute().data or []
    master_names = {r["law_name"] for r in masters}
    return [r for r in targets if r["law_name"] not in master_names]


def collect_one_law(catalog_row):
    """LAW: parse_law_content_xml이 자동 dedupe.
    admrul: parse_admrul_content_xml은 dedupe 없음 → 여기서 _dedupe 호출.
    """
    law_name = catalog_row["law_name"]
    api_id = catalog_row["law_api_id"]
    mst_no = catalog_row["law_mst_no"]
    type_code = catalog_row["law_type_code"]

    if type_code in ("LAW", "ENFORCEMENT_DECREE", "ENFORCEMENT_RULE"):
        list_result = fetch_law_list(query=law_name, display=10)
        if not list_result["ok"]:
            raise Exception(f"법령 검색 HTTP {list_result['status']}")
        laws = parse_law_list_xml(list_result["xml"])
        if not laws:
            raise Exception("법령 검색 결과 없음")
        matched = next((l for l in laws if l["law_name"] == law_name), None)
        if not matched:
            matched = next((l for l in laws if law_name in l["law_name"]), laws[0])

        content_result = fetch_law_content(matched["law_mst_no"])
        if not content_result["ok"]:
            raise Exception(f"법령 본문 HTTP {content_result['status']}")
        parsed = parse_law_content_xml(content_result["xml"])  # 내부에서 자동 dedupe됨
        law_info = {
            **parsed["info"],
            "law_mst_no": matched["law_mst_no"],
            "law_name_short": matched.get("law_name_short", ""),
            "revision_type": matched.get("revision_type", ""),
        }
        return save_law_to_db(law_info, content_result["xml"], parsed["articles"], sb)

    else:
        content_result = fetch_admrul_content(api_id)
        if not content_result["ok"]:
            raise Exception(f"admrul 본문 HTTP {content_result['status']}")
        parsed = parse_admrul_content_xml(content_result["xml"])

        # ★ v5: admrul도 dedupe 적용 (LAW와 동일 방식)
        articles = _dedupe_articles_by_internal_key(parsed["articles"])

        law_info = {
            **parsed["info"],
            "law_mst_no": mst_no or api_id,
        }
        if not law_info.get("law_name"):
            law_info["law_name"] = law_name
        if not law_info.get("law_type_name"):
            law_info["law_type_name"] = "고시"
        if not law_info.get("law_name_short"):
            law_info["law_name_short"] = ""
        return save_law_to_db(law_info, content_result["xml"], articles, sb)


def phase_b(dry_run=False, debug_first=False):
    print("\n" + "=" * 60)
    print("[PHASE B] 본문 수집 (v5 — admrul dedupe 추가)")
    print("=" * 60)

    targets = fetch_collection_targets()
    log(f"수집 대상: {len(targets)}건", "PHASE")

    if dry_run:
        for i, t in enumerate(targets, 1):
            print(f"  [{i:>3}] [{t['law_type_code']}] {t['law_name']} (api_id={t['law_api_id']})")
        return

    if debug_first:
        if not targets:
            return
        t = targets[0]
        log(f"[DEBUG] {t['law_name']} (api_id={t['law_api_id']}, type={t['law_type_code']})", "PHASE")
        try:
            result = collect_one_law(t)
            log(f"수집 완료: {result}", "OK")
            sb.table("law_external_catalog").update({"is_in_law_master": True}).eq("id", t["id"]).execute()
        except Exception as e:
            log(f"실패: {e}", "ERR")
            traceback.print_exc()
        return

    for i, t in enumerate(targets, 1):
        log(f"[{i:>3}/{len(targets)}] [{t['law_type_code']}] {t['law_name'][:50]}...", "PHASE")
        try:
            result = collect_one_law(t)
            sb.table("law_external_catalog").update({"is_in_law_master": True}).eq("id", t["id"]).execute()
            log(f"수집 완료 (조문 {result['article_count']}개, new={result['is_new_version']})", "OK")
            STATS["phase_b_collected"] += 1
            STATS["phase_b_articles"] += result["article_count"]
        except Exception as e:
            log(f"실패: {e}", "ERR")
            if i <= 3:
                traceback.print_exc()
            STATS["phase_b_failed"] += 1
        time.sleep(1.0)

    print(f"\n[PHASE B] 수집 {STATS['phase_b_collected']} / 실패 {STATS['phase_b_failed']} / 조문 {STATS['phase_b_articles']}")


def phase_c():
    print("\n" + "=" * 60)
    print("[PHASE C] L1+L2+L3 무결성 검증")
    print("=" * 60)

    targets = sb.table("law_external_catalog").select("law_name").eq("is_in_collection_target", True).execute().data or []
    target_names = [r["law_name"] for r in targets]
    masters = sb.table("law_master").select("law_name").execute().data or []
    master_names = {r["law_name"] for r in masters}
    missing = [n for n in target_names if n not in master_names]
    if missing:
        log(f"L1 FAIL: {len(missing)}건 미수집", "ERR")
        for n in missing[:10]:
            print(f"     - {n}")
        if len(missing) > 10:
            print(f"     ... +{len(missing) - 10}건")
    else:
        log(f"L1 OK: catalog target {len(target_names)}건 모두 law_master에 존재", "OK")

    masters_full = sb.table("law_master").select("id,law_name,current_version_id").execute().data or []
    no_version = [m for m in masters_full if not m.get("current_version_id")]
    if no_version:
        log(f"L2 FAIL: {len(no_version)}건이 current_version_id 없음", "ERR")
    else:
        log(f"L2 OK: {len(masters_full)}건 모두 current_version 존재", "OK")

    versions = sb.table("law_version").select("id").execute().data or []
    no_articles = []
    for v in versions[:50]:
        arts = sb.table("law_article").select("id", count="exact").eq("law_version_id", v["id"]).limit(1).execute()
        if arts.count == 0:
            no_articles.append(v["id"])
    if no_articles:
        log(f"L3 FAIL: {len(no_articles)}건 article 0개 (샘플 50)", "ERR")
    else:
        log("L3 OK: 검사 version 모두 article >= 1", "OK")
    print()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--phase", choices=["a", "b", "c", "all"], default="all")
    p.add_argument("--debug-first", action="store_true")
    args = p.parse_args()

    print(f"\n{'=' * 60}")
    print(f"  S9 Phase 4 v5 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
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
    print(f"  Phase A: {STATS['phase_a_inserted']}/{STATS['phase_a_skipped']}/{STATS['phase_a_failed']}")
    print(f"  Phase B: 수집 {STATS['phase_b_collected']} / 실패 {STATS['phase_b_failed']} / 조문 {STATS['phase_b_articles']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
