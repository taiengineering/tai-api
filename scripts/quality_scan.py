#!/usr/bin/env python3
"""
법령 수집 품질 스캔 (collect_v2.py 동반 도구).

목적:
  collection_status=SUCCESS 라도 실제 데이터 품질이 부실한 케이스를 식별.

L1 (수집 성공): collect_v2.py 자체에서 처리
L2 (데이터 형태): article 갯수, paragraph 분해, raw_xml 존재 — v1.0~1.1
L3 (데이터 내용): 본문 실제로 의미있는지 — v1.2 신규
  - 행정규칙 raw_xml의 <조문내용> CDATA가 비어있는지 (첨부파일이 본체)
  - article_text 합산 길이 < 100자 (외형만 있고 알맹이 없음)
  - 첨부파일만 있고 본문 없는 행정규칙 별도 마킹

v1.2 (2026-05-03 S7):
  - L3 검증 추가: 본문 내용 실재 검사
  - 행정규칙 raw_xml 직접 분석으로 빈 CDATA / 첨부파일 본체 감지
  - issue_l3 컬럼 (HOLLOW_CDATA / ATTACHMENT_ONLY / SHORT_BODY)
  - CSV에 raw_text_len, attachment_count 추가

v1.1 (2026-05-03 S6):
  - 행정규칙(AdmRul) 분기 추가 — NO_PARAGRAPHS 면제
  - expected_article_count = 0 BELOW_EXPECTED 면제

실행:
  cd ~/dev/tai-api
  railway run python3 scripts/quality_scan.py
  railway run python3 scripts/quality_scan.py --domain FIRE
  railway run python3 scripts/quality_scan.py --csv /tmp/quality_report.csv
  railway run python3 scripts/quality_scan.py --phase PHASE_3   # 신규: phase 필터
"""
from __future__ import annotations

import argparse
import csv
import os
import re
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

ARTICLE_RATIO_THRESHOLD = 0.5    # expected 대비 50% 미만이면 의심
VALID_PCT_THRESHOLD     = 30.0   # article_text 유효 비율 30% 미만이면 의심
MIN_ARTICLE_COUNT       = 3      # 절대 최소: 조문 3개 미만
MIN_TOTAL_TEXT_LENGTH   = 100    # L3: 전체 본문 합산이 100자 미만이면 알맹이 부재

_ADMRUL_TYPE_CODES = {"STANDARD", "NOTICE"}
_ADMRUL_NAME_TOKENS = ("NFTC", "NFPC", "NFSC")

# L3 패턴
_RX_EMPTY_CDATA = re.compile(r"<조문내용>\s*(?:<!\[CDATA\[\s*\]\]>|)\s*</조문내용>")
_RX_ATTACHMENT  = re.compile(r"<첨부파일명>")


def _is_admrul(target: dict) -> bool:
    code = (target.get("law_type_code") or "").upper()
    if code in _ADMRUL_TYPE_CODES:
        return True
    name = target.get("law_name") or ""
    return any(tok in name for tok in _ADMRUL_NAME_TOKENS)


def _analyze_l3_content(raw_xml: str, articles: list[dict], is_admrul: bool) -> dict:
    """L3 본문 내용 분석.
    
    Returns:
      issue_l3: HOLLOW_CDATA / ATTACHMENT_ONLY / SHORT_BODY / OK
      raw_text_len: 모든 article_text 합산 길이
      attachment_count: raw_xml의 <첨부파일명> 태그 개수
      empty_cdata_count: 빈 <조문내용><![CDATA[]]></조문내용> 개수 (행정규칙만)
    """
    raw_text_len = sum(len(a.get("article_text") or "") for a in articles)
    
    # 첨부파일 마킹 카운트 (raw_xml)
    attachment_count = len(_RX_ATTACHMENT.findall(raw_xml or ""))
    
    # 빈 CDATA 카운트 (행정규칙 패턴)
    empty_cdata_count = 0
    if is_admrul and raw_xml:
        empty_cdata_count = len(_RX_EMPTY_CDATA.findall(raw_xml))
    
    # 이슈 판정 우선순위
    issue_l3 = "OK"
    if is_admrul and empty_cdata_count > 0 and attachment_count > 0:
        # 첨부파일이 본체인 행정규칙 — 진짜 부실 아니지만 본문 추출 별도 트랙 필요
        issue_l3 = "ATTACHMENT_ONLY"
    elif is_admrul and empty_cdata_count > 0:
        # 빈 CDATA만 있고 첨부파일도 없음 — 진짜 빈 행정규칙
        issue_l3 = "HOLLOW_CDATA"
    elif raw_text_len < MIN_TOTAL_TEXT_LENGTH:
        # 본문 합산 100자 미만 — 외형만 있고 알맹이 부재
        issue_l3 = "SHORT_BODY"
    
    return {
        "issue_l3": issue_l3,
        "raw_text_len": raw_text_len,
        "attachment_count": attachment_count,
        "empty_cdata_count": empty_cdata_count,
    }


# ═══════════════════════════════════════════════════════════
# 메인 스캔 로직
# ═══════════════════════════════════════════════════════════

def scan_one(target: dict, supabase: Any) -> dict:
    """타겟 1개에 대한 품질 진단 1행 생성."""
    law_name = target["law_name"]
    domain = target.get("domain_code") or "?"
    expected = target.get("expected_article_count") or 0
    is_admrul = _is_admrul(target)
    phase = target.get("added_in_phase") or "?"

    master_q = supabase.table("law_master") \
        .select("id,law_name,current_version_id,law_mst_no,updated_at") \
        .eq("law_name", law_name).limit(1).execute()
    if not master_q.data:
        master_q = supabase.table("law_master") \
            .select("id,law_name,current_version_id,law_mst_no,updated_at") \
            .ilike("law_name", f"%{law_name}%").limit(1).execute()

    if not master_q.data:
        return {
            "domain": domain, "phase": phase, "law_name": law_name,
            "expected": expected, "is_admrul": is_admrul,
            "issue_l2": "MASTER_MISSING", "issue_l3": "N/A",
            "article_total": 0, "article_active": 0,
            "valid_pct": 0.0, "paragraph_total": 0, "raw_xml_size": 0,
            "raw_text_len": 0, "attachment_count": 0, "empty_cdata_count": 0,
            "current_version_id": None, "updated_at": None,
        }

    master = master_q.data[0]
    law_id = master["id"]
    version_id = master.get("current_version_id")

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

    para_q = supabase.table("law_paragraph") \
        .select("id", count="exact").eq("law_id", law_id).execute()
    paragraph_total = para_q.count or 0

    raw_xml = ""
    raw_xml_size = 0
    if version_id:
        raw_q = supabase.table("law_content_raw") \
            .select("raw_xml").eq("law_version_id", version_id).limit(1).execute()
        if raw_q.data:
            raw_xml = raw_q.data[0].get("raw_xml") or ""
            raw_xml_size = len(raw_xml)

    # ── L2 이슈 (외형) ───────────────────────────────────
    issues_l2 = []
    if article_total < MIN_ARTICLE_COUNT:
        issues_l2.append(f"TOO_FEW_ARTICLES({article_total})")
    if expected > 0 and article_active < expected * ARTICLE_RATIO_THRESHOLD:
        issues_l2.append(f"BELOW_EXPECTED({article_active}/{expected})")
    if article_active > 0 and valid_pct < VALID_PCT_THRESHOLD:
        issues_l2.append(f"LOW_VALID_PCT({valid_pct}%)")
    if raw_xml_size == 0:
        issues_l2.append("RAW_XML_MISSING")
    if not is_admrul and article_active > 0 and paragraph_total == 0:
        issues_l2.append("NO_PARAGRAPHS")
    issue_l2 = ",".join(issues_l2) if issues_l2 else "OK"

    # ── L3 이슈 (내용) ───────────────────────────────────
    l3_result = _analyze_l3_content(raw_xml, arts, is_admrul)

    return {
        "domain": domain, "phase": phase, "law_name": law_name,
        "expected": expected, "is_admrul": is_admrul,
        "issue_l2": issue_l2, "issue_l3": l3_result["issue_l3"],
        "article_total": article_total, "article_active": article_active,
        "valid_pct": valid_pct, "paragraph_total": paragraph_total,
        "raw_xml_size": raw_xml_size,
        "raw_text_len": l3_result["raw_text_len"],
        "attachment_count": l3_result["attachment_count"],
        "empty_cdata_count": l3_result["empty_cdata_count"],
        "current_version_id": version_id,
        "updated_at": master.get("updated_at"),
    }


def run_scan(domain_filter: Optional[str] = None,
             phase_filter: Optional[str] = None,
             csv_path: Optional[str] = None) -> int:
    supabase = get_supabase()

    q = supabase.table("law_collection_target") \
        .select("law_name,domain_code,expected_article_count,collection_status,"
                "law_type_code,added_in_phase") \
        .eq("is_active", True) \
        .eq("collection_status", "SUCCESS")
    if domain_filter:
        q = q.eq("domain_code", domain_filter.upper())
    if phase_filter:
        q = q.eq("added_in_phase", phase_filter.upper())
    targets = (q.order("added_in_phase").order("domain_code")
               .order("law_name").execute()).data or []

    if not targets:
        print("❌ SUCCESS 상태 타겟 없음")
        return 1

    print(f"\n{'=' * 80}")
    print(f"🔍 법령 수집 품질 스캔 v1.2 ({datetime.now():%Y-%m-%d %H:%M:%S})")
    if domain_filter: print(f"   도메인: {domain_filter.upper()}")
    if phase_filter:  print(f"   phase: {phase_filter.upper()}")
    print(f"   대상: {len(targets)}개")
    print(f"   L2: 조문<{MIN_ARTICLE_COUNT} | expected 대비 <{int(ARTICLE_RATIO_THRESHOLD*100)}% | "
          f"valid_pct <{VALID_PCT_THRESHOLD}%")
    print(f"   L3: 본문 합산 <{MIN_TOTAL_TEXT_LENGTH}자 | 빈 CDATA | 첨부파일 본체 감지")
    print(f"{'=' * 80}\n")

    rows = []
    for idx, t in enumerate(targets, 1):
        rows.append(scan_one(t, supabase))
        if idx % 50 == 0 or idx == len(targets):
            print(f"  진행 {idx}/{len(targets)} ...")

    # 결과 분리
    l2_ok = [r for r in rows if r["issue_l2"] == "OK"]
    l2_bad = [r for r in rows if r["issue_l2"] != "OK"]
    l3_ok = [r for r in rows if r["issue_l3"] == "OK"]
    l3_attach = [r for r in rows if r["issue_l3"] == "ATTACHMENT_ONLY"]
    l3_hollow = [r for r in rows if r["issue_l3"] == "HOLLOW_CDATA"]
    l3_short = [r for r in rows if r["issue_l3"] == "SHORT_BODY"]

    # 진짜 부실 = L2 또는 L3 둘 다 문제 (단, ATTACHMENT_ONLY는 별도 트랙이라 부실 아님)
    truly_bad = [r for r in rows
                 if r["issue_l2"] != "OK" and r["issue_l3"] != "ATTACHMENT_ONLY"]

    print(f"\n{'─' * 80}")
    print(f"📊 결과 요약")
    print(f"{'─' * 80}")
    print(f"  ✅ L2 통과            : {len(l2_ok):4} / {len(rows)}")
    print(f"  ⚠️  L2 의심           : {len(l2_bad):4} / {len(rows)}")
    print(f"")
    print(f"  ✅ L3 통과            : {len(l3_ok):4} / {len(rows)}")
    print(f"  📎 L3 첨부파일 본체   : {len(l3_attach):4}  (별도 트랙 — 부실 아님)")
    print(f"  ⚠️  L3 빈 CDATA       : {len(l3_hollow):4}")
    print(f"  ⚠️  L3 본문 < 100자   : {len(l3_short):4}")
    print(f"")
    print(f"  🚨 진짜 부실 (L2 의심 - 첨부파일 제외): {len(truly_bad)}")

    # 도메인 × phase 통계
    by_phase: dict[str, dict] = {}
    for r in rows:
        p = r["phase"]
        if p not in by_phase:
            by_phase[p] = {"total": 0, "l2_ok": 0, "l3_ok": 0,
                           "attach": 0, "truly_bad": 0}
        by_phase[p]["total"] += 1
        if r["issue_l2"] == "OK": by_phase[p]["l2_ok"] += 1
        if r["issue_l3"] == "OK": by_phase[p]["l3_ok"] += 1
        if r["issue_l3"] == "ATTACHMENT_ONLY": by_phase[p]["attach"] += 1
        if r["issue_l2"] != "OK" and r["issue_l3"] != "ATTACHMENT_ONLY":
            by_phase[p]["truly_bad"] += 1

    print(f"\n📋 Phase별 분포:")
    print(f"  {'phase':<10} {'전체':>5} {'L2 OK':>6} {'L3 OK':>6} "
          f"{'첨부':>5} {'진짜부실':>8}")
    print(f"  {'-' * 50}")
    for p in sorted(by_phase):
        s = by_phase[p]
        print(f"  {p:<10} {s['total']:>5} {s['l2_ok']:>6} {s['l3_ok']:>6} "
              f"{s['attach']:>5} {s['truly_bad']:>8}")

    # 진짜 부실 상위 30건
    if truly_bad:
        print(f"\n🚨 진짜 부실/의심 상위 30건 (article_active 오름차순):")
        bad_sorted = sorted(truly_bad,
                            key=lambda r: (r["article_active"], r["law_name"]))
        print(f"  {'#':>3}  {'phase':<8} {'도메인':<14} {'법령명':<32} "
              f"{'타입':<6} {'조문':>4} {'본문':>6} {'XML':>7} {'L2 이슈'}")
        print(f"  {'-' * 90}")
        for i, r in enumerate(bad_sorted[:30], 1):
            name = (r["law_name"] or "")[:31]
            xml_kb = f"{r['raw_xml_size']//1024}KB" if r['raw_xml_size'] else "0"
            tp = "AdmRul" if r["is_admrul"] else "Law"
            print(f"  {i:>3}  {r['phase']:<8} {r['domain']:<14} {name:<32} "
                  f"{tp:<6} {r['article_active']:>4} {r['raw_text_len']:>6} "
                  f"{xml_kb:>7} {r['issue_l2'][:35]}")

    # 첨부파일 본체 행정규칙 카운트만 (다음 트랙 — 별표/서식 + 첨부파일 PDF/HWP 추출)
    if l3_attach:
        print(f"\n📎 첨부파일 본체 행정규칙 ({len(l3_attach)}건) — "
              f"다음 트랙(첨부파일 본문 추출) 필요:")
        attach_sorted = sorted(l3_attach,
                               key=lambda r: (r["domain"], r["law_name"]))
        for r in attach_sorted[:15]:
            print(f"  - [{r['domain']}] {r['law_name']} "
                  f"(첨부 {r['attachment_count']}개)")
        if len(l3_attach) > 15:
            print(f"  ... 외 {len(l3_attach) - 15}건 (전체는 CSV 참고)")

    if csv_path:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=[
                "phase", "domain", "law_name", "is_admrul", "expected",
                "article_total", "article_active", "valid_pct",
                "paragraph_total", "raw_xml_size", "raw_text_len",
                "attachment_count", "empty_cdata_count",
                "issue_l2", "issue_l3",
                "current_version_id", "updated_at",
            ])
            w.writeheader()
            for r in rows:
                w.writerow(r)
        print(f"\n💾 CSV 저장: {csv_path}")

    print(f"\n{'=' * 80}")
    print(f"📌 완료: 정상 {len(rows) - len(truly_bad)} / 진짜부실 {len(truly_bad)} "
          f"/ 첨부본체(별도) {len(l3_attach)} / 전체 {len(rows)}")
    print(f"{'=' * 80}\n")

    return 0 if not truly_bad else 2


def main() -> int:
    ap = argparse.ArgumentParser(
        description="법령 수집 품질 스캔 v1.2 (L2 외형 + L3 내용)",
    )
    ap.add_argument("--domain", help="특정 도메인만 (예: FIRE, BUILDING)")
    ap.add_argument("--phase", help="특정 phase만 (PHASE_1/PHASE_2/PHASE_3)")
    ap.add_argument("--csv", help="CSV 출력 경로")
    args = ap.parse_args()
    return run_scan(domain_filter=args.domain,
                    phase_filter=args.phase,
                    csv_path=args.csv)


if __name__ == "__main__":
    raise SystemExit(main())
