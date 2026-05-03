#!/usr/bin/env python3
"""
collect_phase4_full.py — S9 Phase 4 통합 본문 수집
====================================================
목표:
  1. catalog 미등록 4건 등록 (소방기본법 등 — master_building_legal_rules에서 사용 중)
  2. catalog.is_in_collection_target=TRUE && law_master에 미수집인 항목 모두 본문 수집
  3. L1+L2+L3 무결성 검증

실행:
  cd ~/dev/tai-api
  python scripts/collect_phase4_full.py            # 정상 실행
  python scripts/collect_phase4_full.py --dry-run  # DB 변경 없이 대상만 출력
  python scripts/collect_phase4_full.py --phase a  # Phase A만 (catalog 등록만)
  python scripts/collect_phase4_full.py --phase b  # Phase B만 (본문 수집만)
  python scripts/collect_phase4_full.py --phase c  # Phase C만 (검증만)

환경(.env):
  SUPABASE_URL=https://vwlahtguyggrhvslabax.supabase.co
  SUPABASE_SERVICE_ROLE_KEY=eyJ...

법제처 API: OC=taieng (인증키 불필요, S5에서 검증된 패턴)
작성: 2026-05-03 (S9)
"""

import os, sys, json, time, argparse, traceback
from datetime import datetime, timezone
from typing import Optional

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

# ============================================================
# 설정
# ============================================================
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY", "")
LAW_OC = "taieng"  # 법제처 Open API ID

if not SUPABASE_URL or not SUPABASE_KEY:
    print("[FATAL] .env에 SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY 설정 필요")
    sys.exit(1)

sb: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Phase A: 사용 중이지만 catalog에도 없는 4건
PHASE_A_LAWS = [
    "소방기본법",
    "건축물의 에너지원단위 목표관리 등에 관한 고시",
    "고압가스 및 액화석유가스 ISO 탱크 컨테이너의 제조, 충전·운반, 저장·사용에 관한 기준",
    "기존 건축물의 에너지성능 개선기준",
]

# 통계
STATS = {
    "phase_a_inserted": 0, "phase_a_skipped": 0, "phase_a_failed": 0,
    "phase_b_collected": 0, "phase_b_skipped": 0, "phase_b_failed": 0,
    "phase_b_articles": 0,
}


# ============================================================
# 공통 유틸
# ============================================================
def log(msg: str, level: str = "INFO"):
    icons = {"INFO": "ℹ️", "OK": "✓", "WARN": "⚠️", "ERR": "❌", "PHASE": "▶"}
    print(f"  {icons.get(level, '·')} {msg}")


def law_search(query: str, target: str = "law", display: int = 5):
    """law.go.kr DRF lawSearch.do — target=law (본법/시행령/시행규칙) or admrul (고시)"""
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


def law_service_fetch(api_id: str, target: str = "law"):
    """law.go.kr DRF lawService.do — 본문 + 조문 가져오기"""
    url = "https://www.law.go.kr/DRF/lawService.do"
    if target == "law":
        params = {"OC": LAW_OC, "target": "law", "type": "JSON", "ID": api_id}
    else:  # admrul
        params = {"OC": LAW_OC, "target": "admrul", "type": "JSON", "ID": api_id}
    try:
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log(f"본문 fetch 실패 (ID={api_id}, target={target}): {e}", "WARN")
        return None


def detect_target_from_type(law_type_code: str) -> str:
    """law_type_code → DRF target 매핑"""
    if law_type_code in ("LAW", "ENFORCEMENT_DECREE", "ENFORCEMENT_RULE"):
        return "law"
    return "admrul"  # NOTICE, OTHER, STANDARD


def detect_type_from_meta(meta: dict, law_name: str) -> str:
    """검색 결과 메타에서 law_type_code 추정"""
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


# ============================================================
# Phase A: catalog 미등록 4건 등록
# ============================================================
def phase_a(dry_run: bool = False):
    print("\n" + "=" * 60)
    print("[PHASE A] catalog 미등록 4건 등록")
    print("=" * 60)

    for law_name in PHASE_A_LAWS:
        log(f"검색 중: {law_name}", "PHASE")

        # 이미 catalog에 있는지 확인
        existing = sb.table("law_external_catalog").select("id").eq("law_name", law_name).execute()
        if existing.data:
            log(f"이미 catalog에 있음, skip", "WARN")
            STATS["phase_a_skipped"] += 1
            continue

        # 1차: target=law 검색
        items = law_search(law_name, target="law", display=10)
        meta = None
        target = "law"
        for it in items:
            it_name = (it.get("법령명한글") or "").strip()
            if it_name == law_name:
                meta = it
                break

        # 2차: target=admrul 검색 (고시/기준)
        if not meta:
            items = law_search(law_name, target="admrul", display=10)
            for it in items:
                it_name = (it.get("행정규칙명") or "").strip()
                if it_name == law_name:
                    meta = it
                    target = "admrul"
                    break
            # 정확 매칭 없으면 첫 결과
            if not meta and items:
                meta = items[0]
                target = "admrul"

        if not meta:
            log(f"law.go.kr에서 찾을 수 없음", "ERR")
            STATS["phase_a_failed"] += 1
            continue

        # 메타 추출
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

        # INSERT
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
            }).execute()
            log(f"catalog 등록 완료", "OK")
            STATS["phase_a_inserted"] += 1
        except Exception as e:
            log(f"INSERT 실패: {e}", "ERR")
            STATS["phase_a_failed"] += 1

        time.sleep(0.5)  # rate limit 보호

    print(f"\n[PHASE A 결과] 등록 {STATS['phase_a_inserted']} / 스킵 {STATS['phase_a_skipped']} / 실패 {STATS['phase_a_failed']}")


# ============================================================
# Phase B: 본문 수집 (catalog target=true && 미수집)
# ============================================================
def fetch_collection_targets():
    """수집 대상 catalog 항목 조회 (collection_target=TRUE && law_master에 없음)"""
    # 단계 1: catalog의 target=true 항목
    targets = sb.table("law_external_catalog") \
        .select("id,law_name,law_api_id,law_mst_no,law_type_code,ministry_name") \
        .eq("is_in_collection_target", True) \
        .execute()
    target_rows = targets.data or []

    # 단계 2: 이미 law_master에 있는 것 제외
    existing = sb.table("law_master").select("law_name").execute()
    existing_names = {r["law_name"] for r in (existing.data or [])}

    return [r for r in target_rows if r["law_name"] not in existing_names]


def insert_law_master_and_articles(meta: dict, fetch_data: dict, target: str):
    """law_master + law_version + law_article INSERT"""
    law_name = meta["law_name"]
    law_type_code = meta.get("law_type_code", "LAW")

    if target == "law":
        # 본법/시행령/시행규칙
        law_block = fetch_data.get("법령", {})
        if not law_block:
            return None, 0
        basic = law_block.get("기본정보", {})
        announcement_date = basic.get("공포일자", "") or ""
        enforcement_date = basic.get("시행일자", "") or ""
        law_number = basic.get("공포번호", "")
        articles_raw = law_block.get("조문", {}).get("조문단위", [])
    else:
        # 고시/행정규칙
        admrul_block = fetch_data.get("AdmRulService", {}) or fetch_data.get("행정규칙", {})
        if not admrul_block:
            return None, 0
        basic = admrul_block.get("기본정보", admrul_block)
        announcement_date = basic.get("발령일자", "") or ""
        enforcement_date = basic.get("시행일자", "") or ""
        law_number = basic.get("발령번호", "")
        articles_raw = admrul_block.get("조문", {}).get("조문단위", []) \
            or admrul_block.get("조항", []) \
            or admrul_block.get("조문내용", [])

    if isinstance(articles_raw, dict):
        articles_raw = [articles_raw]

    def norm_date(s: str) -> Optional[str]:
        s = (s or "").replace(".", "").replace("-", "").strip()
        if len(s) == 8 and s.isdigit():
            return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
        return None

    # law_master INSERT
    lm_data = {
        "law_name": law_name,
        "law_api_id": meta.get("law_api_id"),
        "law_mst_no": meta.get("law_mst_no"),
        "law_type_code": law_type_code,
        "ministry_name": meta.get("ministry_name", ""),
        "law_number": str(law_number) if law_number else None,
        "announcement_date": norm_date(announcement_date),
        "enforcement_date": norm_date(enforcement_date),
        "law_status_code": "EFFECTIVE",
        "is_active": True,
        "source_system": "law.go.kr",
        "source_url": f"https://www.law.go.kr/lsInfoP.do?lsiSeq={meta.get('law_api_id')}",
    }
    lm_resp = sb.table("law_master").insert(lm_data).execute()
    if not lm_resp.data:
        return None, 0
    law_master_id = lm_resp.data[0]["id"]

    # law_version INSERT
    lv_data = {
        "law_id": law_master_id,
        "version_no": "1",
        "announcement_date": norm_date(announcement_date),
        "enforcement_date": norm_date(enforcement_date),
        "law_status_code": "EFFECTIVE",
        "is_current": True,
    }
    lv_resp = sb.table("law_version").insert(lv_data).execute()
    if not lv_resp.data:
        return law_master_id, 0
    law_version_id = lv_resp.data[0]["id"]

    # law_master.current_version_id 업데이트
    sb.table("law_master").update({"current_version_id": law_version_id}).eq("id", law_master_id).execute()

    # 조문 INSERT
    article_count = 0
    for idx, art in enumerate(articles_raw):
        if not isinstance(art, dict):
            continue
        art_no_raw = art.get("조문번호", "") or art.get("조번호", "")
        art_sub = art.get("조문가지번호", "") or art.get("조문가지", "")
        art_title = art.get("조문제목", "") or art.get("조제목", "") or ""
        # 조문내용
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

        # article_no는 integer (NULL 허용)
        art_no_int = None
        try:
            art_no_int = int(str(art_no_raw).lstrip("0") or "0") if str(art_no_raw).strip().isdigit() or str(art_no_raw).lstrip("0").isdigit() else None
        except Exception:
            art_no_int = None

        try:
            sb.table("law_article").insert({
                "law_version_id": law_version_id,
                "law_id": law_master_id,
                "article_no": art_no_int,
                "article_sub_no": int(art_sub) if str(art_sub).isdigit() else None,
                "article_no_sort": idx + 1,
                "article_type": "본칙",
                "article_title": art_title,
                "article_text": article_text,
                "article_internal_key": f"{law_master_id}-{art_no_int or idx}-{art_sub or ''}",
                "article_status_code": "EFFECTIVE",
                "is_changed": False,
                "is_deleted_in_version": False,
            }).execute()
            article_count += 1
        except Exception as e:
            log(f"  article INSERT 실패 (조문 {art_no_raw}): {e}", "WARN")

    return law_master_id, article_count


def phase_b(dry_run: bool = False):
    print("\n" + "=" * 60)
    print("[PHASE B] 본문 수집")
    print("=" * 60)

    targets = fetch_collection_targets()
    log(f"수집 대상: {len(targets)}건", "PHASE")

    if dry_run:
        print("\n[DRY-RUN] 다음 항목들이 수집됩니다:")
        for i, t in enumerate(targets, 1):
            print(f"  [{i:>3}] [{t['law_type_code']}] {t['law_name']} (api_id={t['law_api_id']})")
        return

    for i, t in enumerate(targets, 1):
        log(f"[{i:>3}/{len(targets)}] {t['law_name'][:50]}...", "PHASE")
        if not t.get("law_api_id"):
            log("law_api_id 없음, skip", "WARN")
            STATS["phase_b_skipped"] += 1
            continue

        target_endpoint = detect_target_from_type(t["law_type_code"])
        data = law_service_fetch(t["law_api_id"], target=target_endpoint)
        if not data:
            STATS["phase_b_failed"] += 1
            continue

        try:
            law_master_id, art_cnt = insert_law_master_and_articles(t, data, target_endpoint)
            if law_master_id:
                # catalog의 is_in_law_master 업데이트
                sb.table("law_external_catalog").update({"is_in_law_master": True}) \
                    .eq("id", t["id"]).execute()
                log(f"수집 완료 (조문 {art_cnt}개)", "OK")
                STATS["phase_b_collected"] += 1
                STATS["phase_b_articles"] += art_cnt
            else:
                log("INSERT 실패", "ERR")
                STATS["phase_b_failed"] += 1
        except Exception as e:
            log(f"수집 실패: {e}", "ERR")
            traceback.print_exc()
            STATS["phase_b_failed"] += 1

        time.sleep(1.0)  # rate limit (1 req/sec)

    print(f"\n[PHASE B 결과] 수집 {STATS['phase_b_collected']} / 스킵 {STATS['phase_b_skipped']} / 실패 {STATS['phase_b_failed']}")
    print(f"             조문 합계: {STATS['phase_b_articles']}개")


# ============================================================
# Phase C: L1+L2+L3 무결성 검증 (S8 패턴)
# ============================================================
def phase_c():
    print("\n" + "=" * 60)
    print("[PHASE C] L1+L2+L3 무결성 검증")
    print("=" * 60)

    # L1: catalog target=true 항목이 모두 law_master에 있는가
    targets = sb.table("law_external_catalog") \
        .select("law_name") \
        .eq("is_in_collection_target", True) \
        .execute()
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

    # L2: 각 law_master에 law_version이 있는가
    masters_full = sb.table("law_master").select("id,law_name,current_version_id").execute()
    no_version = [m for m in (masters_full.data or []) if not m.get("current_version_id")]
    if no_version:
        log(f"L2 FAIL: {len(no_version)}건이 current_version_id 없음", "ERR")
        for m in no_version[:5]:
            print(f"     - {m['law_name']}")
    else:
        log(f"L2 OK: 모든 law_master({len(masters_full.data or [])})에 current_version 존재", "OK")

    # L3: 각 law_version에 law_article >= 1
    versions = sb.table("law_version").select("id,law_id").execute()
    no_articles = []
    for v in (versions.data or [])[:50]:  # 최대 50개만 (시간 단축)
        arts = sb.table("law_article").select("id", count="exact").eq("law_version_id", v["id"]).limit(1).execute()
        if arts.count == 0:
            no_articles.append(v["id"])
    if no_articles:
        log(f"L3 FAIL: {len(no_articles)}건 (샘플 50개 중)이 article 0개", "ERR")
    else:
        log(f"L3 OK: 검사한 version 모두 article >= 1", "OK")

    print()


# ============================================================
# main
# ============================================================
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", help="DB 변경 없이 대상만 출력")
    p.add_argument("--phase", choices=["a", "b", "c", "all"], default="all", help="실행할 phase")
    args = p.parse_args()

    print(f"\n{'=' * 60}")
    print(f"  S9 Phase 4 통합 수집 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  dry_run={args.dry_run} / phase={args.phase}")
    print(f"{'=' * 60}")

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
