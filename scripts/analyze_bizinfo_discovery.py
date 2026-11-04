"""WO-TAI-BIZINFO-SAFETY-DISCOVERY-001 — 기존 DB 전수 재분석.

사용법:
  railway run python3 scripts/analyze_bizinfo_discovery.py [--verbose] [--keys KEY1 KEY2 ...]

기능:
  - bizinfo_source_records 전체 조회 (DB 미변경)
  - 새 selector 기준으로 재분류 (IN_SCOPE / REVIEW_REQUIRED / OUT_OF_SCOPE)
  - 기존 판정 대비 변화 집계
  - 분류 기반(basis) 집계 — tech_adoption 후보 목록 출력
  - 특정 키(--keys) 상세 출력

의존 환경변수:
  SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_KEY)
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TABLE    = "bizinfo_source_records"
_PAGE     = 200  # records per page
_MAX_SHOW = 30   # max items per category in verbose output

_PRIORITY_KEYS = {
    "PBLN_000000000127340",  # 구미 스마트 안전솔루션 (필수 검증)
    "PBLN_000000000127589",  # 2027 스마트 제조혁신
    "PBLN_000000000127587",  # 충남 AI 팩토리
    "PBLN_000000000124841",  # DX·AX 컨설팅
    "PBLN_000000000127610",  # 성남 제조AX 솔루션 매칭 (R1 검증: 제조ax 키워드)
    "PBLN_000000000127680",  # AX R&D 과제 (R1 검증: R&D vs 도입비 구분)
    "EVEN_000000000069655",  # 스마트공장 교육
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_supabase():
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        or os.environ.get("SUPABASE_KEY", "").strip()
    )
    if not url or not key:
        raise EnvironmentError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY 미설정")
    from supabase import create_client
    return create_client(url, key)


def _fetch_all(sb) -> list[dict]:
    rows: list[dict] = []
    offset = 0
    cols = "source_kind,source_key,title,summary,support_target,relevance_verdict"
    while True:
        resp = (
            sb.table(_TABLE)
            .select(cols)
            .order("source_key")
            .range(offset, offset + _PAGE - 1)
            .execute()
        )
        batch = resp.data or []
        rows.extend(batch)
        if len(batch) < _PAGE:
            break
        offset += _PAGE
    return rows


def _make_record(row: dict):
    from services.bizinfo.normalizer import NormalizedSourceRecord
    return NormalizedSourceRecord(
        source_kind=row["source_kind"],
        source_id="BIZINFO_PROGRAM" if row["source_kind"] == "PROGRAM" else "BIZINFO_EVENT",
        source_key=row["source_key"],
        title=row.get("title") or "",
        source_org=None,
        origin_url=None,
        bizinfo_url=None,
        retrieved_at=datetime.now(timezone.utc),
        summary=row.get("summary"),
        support_target=row.get("support_target"),
    )


def _basis_category(basis: tuple[str, ...]) -> str:
    for b in basis:
        if b.startswith("tech_adoption:"):   return "TECH_ADOPTION"
        if b.startswith("eligibility:"):     return "ELIGIBILITY_ONLY"
        if "title:" in b or "summary:" in b:  return "DIRECT_SAFETY_TECH_OR_DIRECT"
        if b.startswith("signal:"):           return "SINGLE_DIRECT"
        if b.startswith("adjacent:"):         return "ADJACENT"
        if b.startswith("non_safety:"):       return "NON_SAFETY"
        if b.startswith("purpose_conflict:"): return "CONFLICT"
        if b.startswith("safety_negated:"):   return "NEGATED"
        if b.startswith("tech_signal:"):      return "TECH_SIGNAL"
    if "no_confirming_evidence" in basis:  return "NO_EVIDENCE"
    if "no_content_available" in basis:    return "NO_CONTENT"
    return "OTHER"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Bizinfo DISCOVERY-001 전수 분석")
    parser.add_argument("--verbose", action="store_true", help="후보 목록 상세 출력")
    parser.add_argument("--keys", nargs="*", default=[], help="특정 키 상세 분석")
    args = parser.parse_args()

    from services.bizinfo.selector import review_relevance

    print(f"[{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}] DB 연결 중 ...")
    sb = _get_supabase()

    print("전체 레코드 조회 중 ...")
    rows = _fetch_all(sb)
    total = len(rows)
    print(f"  {total}건 조회 완료\n")

    # -- analysis --
    old_counts: dict[str, int]  = defaultdict(int)
    new_counts: dict[str, int]  = defaultdict(int)
    basis_counts: dict[str, int] = defaultdict(int)
    changes: list[dict] = []
    tech_adoption_records: list[dict] = []
    eligibility_records: list[dict] = []
    direct_safety_tech_records: list[dict] = []
    priority_results: list[dict] = []
    specific_keys: set[str] = set(args.keys)

    for row in rows:
        old_verdict = row.get("relevance_verdict") or "UNKNOWN"
        old_counts[old_verdict] += 1

        record = _make_record(row)
        decision = review_relevance(record)
        new_verdict = decision.verdict
        new_counts[new_verdict] += 1

        cat = _basis_category(decision.basis)
        basis_counts[cat] += 1

        item = {
            "key":        row["source_key"],
            "kind":       row["source_kind"],
            "title":      (row.get("title") or "")[:60],
            "old":        old_verdict,
            "new":        new_verdict,
            "basis":      decision.basis[:3],
            "category":   cat,
        }

        if old_verdict != new_verdict:
            changes.append(item)

        if cat == "TECH_ADOPTION":
            tech_adoption_records.append(item)

        if cat == "ELIGIBILITY_ONLY":
            eligibility_records.append(item)

        # direct safety tech = IN_SCOPE and basis has compact tech term
        if new_verdict == "IN_SCOPE" and any(
            kw in b
            for b in decision.basis
            for kw in ("스마트안전", "안전솔루션", "안전관리시스템",
                       "안전모니터링", "재해예방시스템", "안전관리소프트웨어",
                       "산업안전솔루션")
        ):
            direct_safety_tech_records.append(item)

        if row["source_key"] in _PRIORITY_KEYS or row["source_key"] in specific_keys:
            priority_results.append(item)

    # -- report --
    _print_summary(total, old_counts, new_counts, basis_counts,
                   changes, tech_adoption_records, eligibility_records,
                   direct_safety_tech_records, priority_results, args.verbose)


def _print_summary(
    total, old_counts, new_counts, basis_counts,
    changes, tech_adoption, eligibility_only,
    direct_safety_tech, priority_results, verbose
) -> None:
    sep = "─" * 60

    print(sep)
    print("WO-TAI-BIZINFO-SAFETY-DISCOVERY-002  전수 분석 결과")
    print(sep)
    print(f"  분석 대상: {total}건")
    print()

    print("── 판정 분포 비교 ───────────────────────────────")
    print(f"  {'분류':<20} {'기존':>8} {'신규':>8}  {'Δ':>6}")
    print(f"  {'─'*20} {'─'*8} {'─'*8}  {'─'*6}")
    for v in ("IN_SCOPE", "REVIEW_REQUIRED", "OUT_OF_SCOPE", "UNKNOWN"):
        o = old_counts.get(v, 0)
        n = new_counts.get(v, 0)
        delta = f"+{n-o}" if n > o else (str(n-o) if n != o else "0")
        mark = " ◀" if n != o else ""
        print(f"  {v:<20} {o:>8} {n:>8}  {delta:>6}{mark}")
    print()

    print("── 판정 근거 분류 (신규 기준) — REVIEW_REQUIRED 세부 ─")
    ordered_cats = [
        "DIRECT_SAFETY_TECH_OR_DIRECT", "SINGLE_DIRECT",
        "ADJACENT", "TECH_ADOPTION", "ELIGIBILITY_ONLY",
        "NO_EVIDENCE", "NO_CONTENT",
        "NON_SAFETY", "CONFLICT", "NEGATED", "OTHER",
    ]
    for cat in ordered_cats:
        cnt = basis_counts.get(cat, 0)
        if cnt:
            marker = " ★" if cat in ("TECH_ADOPTION", "ELIGIBILITY_ONLY") else ""
            print(f"  {cat:<35} {cnt:>5}건{marker}")
    print()

    print("── 판정 변경 건수 ───────────────────────────────")
    if changes:
        for c in changes:
            print(f"  {c['old']}→{c['new']}  {c['key']}  {c['title']}")
            print(f"      basis={c['basis']}")
    else:
        print("  (변경 없음)")
    print()

    print(f"── DIRECT_SAFETY_TECH (안전기술 IN_SCOPE) {len(direct_safety_tech)}건 ─")
    _show_items(direct_safety_tech, verbose)
    print()

    print(f"── TECH_ADOPTION_POTENTIAL (스마트공장·AI·DX) {len(tech_adoption)}건 ─")
    print("   [★ 기술 도입 잠재 후보 — 안전 용도 미확인, 인간 검토 필요]")
    _show_items(tech_adoption, verbose)
    print()

    print(f"── ELIGIBILITY_ONLY (창업기업 등 자격조건 REVIEW) {len(eligibility_only)}건 ─")
    print("   [★ 창업·초기기업 자격조건 — 기술 도입 신호 없음, TECH_ADOPTION 집단과 별도 처리]")
    _show_items(eligibility_only, verbose)
    print()

    if priority_results:
        print("── 필수 검증 대상 ───────────────────────────────")
        for item in priority_results:
            flag = "✓" if item["new"] == "IN_SCOPE" else ("○" if item["new"] == "OUT_OF_SCOPE" else "△")
            changed = f" [{item['old']}→{item['new']}]" if item["old"] != item["new"] else f" [{item['new']}]"
            print(f"  {flag} {item['key']}{changed}")
            print(f"    {item['title']}")
            print(f"    basis={item['basis']}")
        print()

    print(sep)
    print("DB 미변경. 이 결과를 GPT 검증 후 판정 반영 여부 별도 승인.")
    print(sep)


def _show_items(items: list[dict], verbose: bool) -> None:
    if not items:
        print("  (없음)")
        return
    show = items if verbose else items[:_MAX_SHOW]
    for item in show:
        flag = {"IN_SCOPE": "●", "OUT_OF_SCOPE": "○"}.get(item["new"], "△")
        print(f"  {flag} {item['key']}  {item['title']}")
        print(f"      basis={item['basis']}")
    if not verbose and len(items) > _MAX_SHOW:
        print(f"  ... 외 {len(items) - _MAX_SHOW}건 (--verbose로 전체 표시)")


if __name__ == "__main__":
    main()
