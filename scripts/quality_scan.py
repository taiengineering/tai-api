#!/usr/bin/env python3
"""
법령 수집 품질 스캔 (collect_v2.py 동반 도구).

목적:
  collection_status=SUCCESS 라도 실제 데이터 품질이 부실한 케이스를 식별.
  - 조문 수가 비정상적으로 적음 (expected_article_count 대비 < 50%)
  - valid_pct (article_text 길이 > 20자 비율)가 30% 미만
  - law_content_raw 누락 (XML 원본 미저장)
  - law_paragraph 0개 (조문은 있는데 항/호 분해 실패)

실행:
  cd ~/dev/tai-api
  railway run python3 scripts/quality_scan.py
  railway run python3 scripts/quality_scan.py --domain FIRE
  railway run python3 scripts/quality_scan.py --csv /tmp/quality_report.csv

출력:
  - 콘솔: 도메인별 부실 건수 + 의심 법령 상위 30건
  - --csv 옵션: 전체 결과 CSV 파일

부실 식별 후:
  python3 scripts/collect_v2.py test "<문제 법령명>"
  → force 재수집은 routers/law_collector.py POST /collect/{name}?force=true
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import datetime
from typing import Any, Optional

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    from dotenv import load_dotenv
    _ENV_PATH = os.path.join(_ROOT, ".env")
    if os.path.isfile(_ENV_PATH):
        load_dotenv(_ENV_PATH, override=False)
except ImportError:
    pass

from db.database import get_supabase


# ═══════════════════════════════════════════════════════════
# 진단 임계값
# ═══════════════════════════════════════════════════════════

ARTICLE_RATIO_THRESHOLD = 0.5    # expected_article_count 대비 50% 미만이면 의심
VALID_PCT_THRESHOLD     = 30.0   # article_text 유효 비율 30% 미만이면 의심
MIN_ARTICLE_COUNT       = 3      # 절대 최소: 조문 3개 미만이면 무조건 의심


# ═══════════════════════════════════════════════════════════
# 메인 스캔 로직
# ═══════════════════════════════════════════════════════════

def scan_one(target: dict, supabase: Any) -> dict:
    """타겟 1개에 대한 품질 진단 1행 생성."""
    law_name = target["law_name"]
    domain = target.get("domain_code") or "?"
    expected = target.get("expected_article_count") or 0

    # law_master 매칭 (law_name 완전일치 우선)
    master_q = supabase.table("law_master") \
        .select("id,law_name,current_version_id,law_mst_no,updated_at") \
        .eq("law_name", law_name).limit(1).execute()
    if not master_q.data:
        # ilike 폴백
        master_q = supabase.table("law_master") \
            .select("id,law_name,current_version_id,law_mst_no,updated_at") \
            .ilike("law_name", f"%{law_name}%").limit(1).execute()

    if not master_q.data:
        return {
            "domain": domain,
            "law_name": law_name,
            "expected": expected,
            "issue": "MASTER_MISSING",
            "article_total": 0,
            "article_active": 0,
            "valid_pct": 0.0,
            "paragraph_total": 0,
            "raw_xml_size": 0,
            "current_version_id": None,
            "updated_at": None,
        }

    master = master_q.data[0]
    law_id = master["id"]
    version_id = master.get("current_version_id")

    # 조문 카운트
    arts_q = supabase.table("law_article") \
        .select("id,article_text,article_status_code") \
        .eq("law_id", law_id).execute()
    arts = arts_q.data or []
    article_total = len(arts)
    article_active = sum(1 for a in arts if a.get("article_status_code") == "ACTIVE")
    valid_articles = sum(
        1 for a in arts
        if a.get("article_status_code") == "ACTIVE"
        and a.get("article_text") and len(a["article_text"]) > 20
    )
    valid_pct = round(valid_articles * 100.0 / article_active, 1) if article_active > 0 else 0.0

    # 항(paragraph) 카운트 — article 단위가 아닌 law_id 단위로 한 번에
    para_q = supabase.table("law_paragraph") \
        .select("id", count="exact").eq("law_id", law_id).execute()
    paragraph_total = para_q.count or 0

    # raw_xml 크기 확인 (현재 버전)
    raw_xml_size = 0
    if version_id:
        raw_q = supabase.table("law_content_raw") \
            .select("raw_xml") \
            .eq("law_version_id", version_id).limit(1).execute()
        if raw_q.data:
            raw_xml_size = len(raw_q.data[0].get("raw_xml") or "")

    # 이슈 판정
    issues = []
    if article_total < MIN_ARTICLE_COUNT:
        issues.append(f"TOO_FEW_ARTICLES({article_total})")
    if expected and expected > 0 and article_active < expected * ARTICLE_RATIO_THRESHOLD:
        issues.append(f"BELOW_EXPECTED({article_active}/{expected})")
    if article_active > 0 and valid_pct < VALID_PCT_THRESHOLD:
        issues.append(f"LOW_VALID_PCT({valid_pct}%)")
    if raw_xml_size == 0:
        issues.append("RAW_XML_MISSING")
    if article_active > 0 and paragraph_total == 0:
        # 조문은 있는데 항이 없는 건 STANDARD/NOTICE에서는 정상일 수 있음
        # 일단 표시만 (decision은 사용자)
        issues.append("NO_PARAGRAPHS")

    return {
        "domain": domain,
        "law_name": law_name,
        "expected": expected,
        "issue": ",".join(issues) if issues else "OK",
        "article_total": article_total,
        "article_active": article_active,
        "valid_pct": valid_pct,
        "paragraph_total": paragraph_total,
        "raw_xml_size": raw_xml_size,
        "current_version_id": version_id,
        "updated_at": master.get("updated_at"),
    }


def run_scan(domain_filter: Optional[str] = None, csv_path: Optional[str] = None) -> int:
    supabase = get_supabase()

    q = supabase.table("law_collection_target") \
        .select("law_name,domain_code,expected_article_count,collection_status") \
        .eq("is_active", True) \
        .eq("collection_status", "SUCCESS")
    if domain_filter:
        q = q.eq("domain_code", domain_filter.upper())
    targets = (q.order("domain_code").order("law_name").execute()).data or []

    if not targets:
        print("❌ SUCCESS 상태 타겟 없음")
        return 1

    print(f"\n{'=' * 78}")
    print(f"🔍 법령 수집 품질 스캔 ({datetime.now():%Y-%m-%d %H:%M:%S})")
    if domain_filter:
        print(f"   도메인 필터: {domain_filter.upper()}")
    print(f"   대상: {len(targets)}개 (collection_status=SUCCESS)")
    print(f"{'=' * 78}\n")

    rows = []
    for idx, t in enumerate(targets, 1):
        row = scan_one(t, supabase)
        rows.append(row)
        # 진행 표시 (50건마다)
        if idx % 50 == 0 or idx == len(targets):
            print(f"  진행 {idx}/{len(targets)} ...")

    # ─── 집계 출력 ────────────────────────────────────────────
    ok = [r for r in rows if r["issue"] == "OK"]
    bad = [r for r in rows if r["issue"] != "OK"]

    print(f"\n{'─' * 78}")
    print(f"📊 결과 요약")
    print(f"{'─' * 78}")
    print(f"  ✅ 정상         : {len(ok):4} / {len(rows)}")
    print(f"  ⚠️  부실/의심   : {len(bad):4} / {len(rows)}")

    # 도메인별 부실 카운트
    by_domain: dict[str, dict] = {}
    for r in rows:
        d = r["domain"]
        if d not in by_domain:
            by_domain[d] = {"total": 0, "ok": 0, "bad": 0}
        by_domain[d]["total"] += 1
        if r["issue"] == "OK":
            by_domain[d]["ok"] += 1
        else:
            by_domain[d]["bad"] += 1

    print(f"\n🏛️  도메인별:")
    print(f"  {'도메인':<22} {'전체':>5} {'정상':>5} {'부실':>5} {'정상률':>7}")
    print(f"  {'-' * 50}")
    for d in sorted(by_domain):
        s = by_domain[d]
        ok_pct = s["ok"] * 100.0 / s["total"] if s["total"] else 0
        print(f"  {d:<22} {s['total']:>5} {s['ok']:>5} {s['bad']:>5} {ok_pct:>6.1f}%")

    # 이슈 종류별 카운트
    issue_buckets: dict[str, int] = {}
    for r in bad:
        for tok in r["issue"].split(","):
            base = tok.split("(")[0]
            issue_buckets[base] = issue_buckets.get(base, 0) + 1
    if issue_buckets:
        print(f"\n🚨 이슈 종류:")
        for k, v in sorted(issue_buckets.items(), key=lambda x: -x[1]):
            print(f"  {k:<22} {v:>5}건")

    # 부실 상위 30건 (조문 수 적은 순)
    if bad:
        print(f"\n⚠️  부실/의심 상위 30건 (article_active 오름차순):")
        bad_sorted = sorted(bad, key=lambda r: (r["article_active"], r["law_name"]))
        print(f"  {'#':>3}  {'도메인':<14} {'법령명':<35} {'조문':>4} {'예상':>4} {'유효%':>6} {'XML':>8} {'이슈'}")
        print(f"  {'-' * 76}")
        for i, r in enumerate(bad_sorted[:30], 1):
            name = (r["law_name"] or "")[:34]
            xml_kb = f"{r['raw_xml_size']//1024}KB" if r['raw_xml_size'] else "0"
            print(f"  {i:>3}  {r['domain']:<14} {name:<35} "
                  f"{r['article_active']:>4} {r['expected']:>4} "
                  f"{r['valid_pct']:>5.1f}% {xml_kb:>8} {r['issue']}")

    # CSV 저장
    if csv_path:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=[
                "domain", "law_name", "expected", "article_total", "article_active",
                "valid_pct", "paragraph_total", "raw_xml_size",
                "current_version_id", "updated_at", "issue",
            ])
            w.writeheader()
            for r in rows:
                w.writerow(r)
        print(f"\n💾 CSV 저장: {csv_path}")

    print(f"\n{'=' * 78}")
    print(f"📌 완료: 정상 {len(ok)} / 부실 {len(bad)} / 전체 {len(rows)}")
    print(f"{'=' * 78}\n")

    if bad:
        print("재수집 명령 예시:")
        sample = bad[0]["law_name"]
        print(f'  railway run python3 scripts/collect_v2.py test "{sample}"')
        print()
    return 0 if not bad else 2


def main() -> int:
    ap = argparse.ArgumentParser(
        description="법령 수집 품질 스캔",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--domain", help="특정 도메인만 (예: FIRE, BUILDING)")
    ap.add_argument("--csv", help="CSV 출력 경로 (예: /tmp/quality_report.csv)")
    args = ap.parse_args()
    return run_scan(domain_filter=args.domain, csv_path=args.csv)


if __name__ == "__main__":
    raise SystemExit(main())
