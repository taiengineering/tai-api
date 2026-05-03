#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
judge_orphan_rules.py v2 — 매핑 의심 룰 살림/죽임 판정 (read-only)

v2 변경 (2026-05-03):
    - DUTY_STRONG 사전 보강:
        '할 것', '받아야 (한다|할)', '두어야 한다', '갖추어야 (한다|할)',
        '마련하여야 한다', '아니 된다', '안 된다', '받지 아니하고는',
        '의무가 있다', '책임이 있다', '명사+하여야' 등
    - 중대재해처벌법 시행령 제5조('...할 것' 의무)가 v1 에서 KILL 오판된 것이 계기.
    - KILL 후보 본문 미리보기 600자로 확장 (사용자 spot-check 강화).

사용자 기준:
    하나라도 놓치면 수백 현장이 해야 할 일을 안 하게 되고,
    하나를 잘못 넣으면 수백 현장이 안 해도 될 일을 하게 됨.
    살릴지 죽일지 본문 기준으로 판단.

판정 로직:
    1. DUTY_STRONG 매칭 -> KEEP
    2. (DUTY 부재) AND DEFINITION_TITLE OR DEFINITION 패턴 -> KILL
    3. (DUTY 부재) AND PERMISSION 만 -> REVIEW
    4. 그 외 -> REVIEW

실행:
    cd ~/dev/tai-api
    git pull origin main
    railway run python3 scripts/judge_orphan_rules.py [--include-all]
"""

import argparse
import csv
import os
import re
import sys
from collections import Counter

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
for _k in ("OUTBOUND_PROXY", "HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(_k, None)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = (
    os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    or os.environ.get("SUPABASE_KEY")
    or os.environ.get("SUPABASE_SERVICE_KEY")
)
if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: SUPABASE_URL / SUPABASE_(SERVICE_ROLE_)KEY env required", file=sys.stderr)
    sys.exit(1)

from supabase import create_client  # noqa: E402
sb = create_client(SUPABASE_URL, SUPABASE_KEY)

BOILER_RE = re.compile(
    r'^\s*('
    r'조치|점검|이행|보고|기록|작성|선임|준수|관리|준비|확인|실시|신고|'
    r'등록|교육|배치|보존|비치|승인|평가|진단|측정|시험'
    r')\s*의무\s*\(.+\)\s*$'
)
KEC_RE = re.compile(r'^\s*[0-9]+(\.[0-9]+)?\s*$')
ARTICLE_RE = re.compile(r'제\s*(\d+)\s*조(?:의\s*(\d+))?')

# v2: 의무 동사 사전 보강
DUTY_STRONG = [
    # v1 기존
    re.compile(r'하여야\s*한다'),
    re.compile(r'해야\s*한다'),
    re.compile(r'하여야\s*하며'),
    re.compile(r'해야\s*하며'),
    re.compile(r'하도록\s*한다'),
    re.compile(r'하지\s*아니하여야'),
    re.compile(r'하지\s*않아야'),
    re.compile(r'하지\s*못한다'),
    re.compile(r'할\s*수\s*없다'),
    re.compile(r'금지(?:한다|된다|되어\s*있다)'),
    # v2 추가
    re.compile(r'[\.\s]\s*할\s*것\s*[\.。]?'),       # 시행령/시행규칙 핵심 의무 (중대재해법 시행령 제5조)
    re.compile(r'받아야\s*한다'),                    # 검사·승인 수동 의무
    re.compile(r'받아야\s*할'),
    re.compile(r'두어야\s*한다'),                    # 비치/배치
    re.compile(r'갖추어야\s*한다'),                  # 갖춤 의무
    re.compile(r'갖추어야\s*할'),
    re.compile(r'마련하여야\s*한다'),                # 절차/체계 마련
    re.compile(r'아니\s*된다'),                     # 강한 금지
    re.compile(r'안\s*된다'),
    re.compile(r'받지\s*아니하고는'),                # 조건부 금지
    re.compile(r'의무가\s*있다'),                   # 명시적 의무
    re.compile(r'책임이\s*있다'),                   # 명시적 책임
    re.compile(r'필요한\s*조치를\s*하'),             # 필요한 조치를 한다/하여야
    re.compile(r'취하여야\s*한다'),                  # 조치 취해야
    re.compile(r'(?:실시|점검|검사|측정|평가|기록|작성|보존|비치|보고|신고|선임|배치|이행)하여야'),
    re.compile(r'(?:받|두|놓|갖추)게\s*하여야'),     # 사역형 의무
]

PERMISSION = re.compile(r'할\s*수\s*있다')

DEFINITION = [
    re.compile(r'(?:이|라)\s*(?:란|함은)'),
    re.compile(r'을\s*말한다'),
    re.compile(r'를\s*말한다'),
]

DEFINITION_TITLE = re.compile(r'\((?:정의|목적|용어\s*정리|적용\s*범위)\)')


def fetch_paged(table, columns, **eq_filters):
    out, offset, page = [], 0, 1000
    while True:
        q = sb.table(table).select(columns)
        for k, v in eq_filters.items():
            q = q.eq(k, v)
        resp = q.range(offset, offset + page - 1).execute()
        rows = resp.data or []
        out.extend(rows)
        if len(rows) < page:
            break
        offset += page
    return out


def extract_article_no(law_article):
    if not law_article:
        return None, None
    s = law_article.strip()
    m = ARTICLE_RE.search(s)
    if m:
        return int(m.group(1)), int(m.group(2) or 0)
    m2 = re.match(r'^(\d+)(?:\.(\d+))?$', s)
    if m2:
        return int(m2.group(1)), 0
    return None, None


def judge(article_text, article_title):
    if not article_text:
        return "REVIEW", "본문 비어있음"

    duty_hits = [p.pattern for p in DUTY_STRONG if p.search(article_text)]
    is_def_title = bool(article_title and DEFINITION_TITLE.search(article_title))
    def_hits = sum(1 for p in DEFINITION if p.search(article_text))
    permission = bool(PERMISSION.search(article_text))

    if duty_hits:
        return "KEEP", "duty: " + duty_hits[0][:30] + (f" +{len(duty_hits)-1}" if len(duty_hits) > 1 else "")

    if is_def_title and def_hits >= 1:
        return "KILL", f"def-title: {article_title}"

    if def_hits >= 2 and not duty_hits:
        return "KILL", f"def-pattern x{def_hits}"

    if permission and not duty_hits:
        return "REVIEW", "permission only"

    return "REVIEW", "no duty/no def"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--include-all", action="store_true",
                    help="B/C/C2 도 포함 (기본: D_MAPPED 만)")
    ap.add_argument("--out", default="/tmp/orphan_rules_judgment.csv")
    args = ap.parse_args()

    print("=" * 72)
    print("Step 1. 대상 룰 + 본문 수집  (judge v2)")
    print("=" * 72)
    rules = fetch_paged(
        "master_building_legal_rules",
        "id,law_name,law_article,obligation_summary,is_active,source_api,created_at",
    )
    target = []
    for r in rules:
        olaw = r.get("obligation_summary") or ""
        larticle = r.get("law_article") or ""
        if BOILER_RE.match(olaw) or KEC_RE.match(larticle):
            target.append(r)
    print(f"전체 master 룰: {len(rules):,} / 의심 패턴: {len(target):,}")

    distinct_names = sorted({r.get("law_name") for r in target if r.get("law_name")})
    print(f"distinct 법령: {len(distinct_names)}개 캐싱 중...")
    cache = {}
    for i, ln in enumerate(distinct_names, 1):
        m_resp = (
            sb.table("law_master").select("id,current_version_id")
            .eq("law_name", ln).limit(1).execute()
        )
        if not m_resp.data:
            cache[ln] = {"master_id": None, "article_count": 0, "by_no": {}}
            continue
        m = m_resp.data[0]
        cv = m.get("current_version_id")
        if not cv:
            cache[ln] = {"master_id": m["id"], "article_count": 0, "by_no": {}}
            continue
        arts = fetch_paged(
            "law_article",
            "article_no,article_sub_no,article_title,article_text",
            law_version_id=cv,
        )
        by_no = {}
        for a in arts:
            ano = a.get("article_no")
            asub = a.get("article_sub_no") or 0
            if ano is not None:
                by_no[(ano, asub)] = a
        cache[ln] = {"master_id": m["id"], "article_count": len(arts), "by_no": by_no}
        if i % 10 == 0 or i == len(distinct_names):
            print(f"  {i}/{len(distinct_names)}")

    print()
    print("=" * 72)
    print("Step 3. 본문 의무 동사 검사 + 판정 (v2 사전)")
    print("=" * 72)
    rows_out = []
    cls_cnt = Counter()
    verdict_cnt = Counter()

    for r in target:
        ln = r.get("law_name")
        larticle = r.get("law_article") or ""
        c = cache.get(ln) or {"master_id": None, "article_count": 0, "by_no": {}}

        article_obj = None
        if c["master_id"] is None:
            cls = "A_ORPHAN_NO_LAW"
        elif c["article_count"] < 5:
            cls = "B_ATTACHMENT_BODY"
        else:
            ano, asub = extract_article_no(larticle)
            if ano is None:
                cls = "C2_PARSE_FAIL"
            else:
                a = c["by_no"].get((ano, asub or 0)) or c["by_no"].get((ano, 0))
                if a is None:
                    cls = "C_ORPHAN_NO_ARTICLE"
                else:
                    cls = "D_MAPPED"
                    article_obj = a

        cls_cnt[cls] += 1

        if cls == "D_MAPPED":
            verdict, reason = judge(
                article_obj.get("article_text") or "",
                article_obj.get("article_title"),
            )
        elif cls == "B_ATTACHMENT_BODY":
            verdict, reason = "KEEP", "attachment body track"
        elif cls == "C_ORPHAN_NO_ARTICLE":
            verdict, reason = "REVIEW", "no article in master (law_name typo possible)"
        elif cls == "C2_PARSE_FAIL":
            verdict, reason = "REVIEW", "law_article parse fail"
        else:
            verdict, reason = "REVIEW", "law_master missing"

        verdict_cnt[verdict] += 1

        if not args.include_all and cls != "D_MAPPED":
            continue

        article_text_preview = ""
        article_title = ""
        if article_obj:
            article_title = article_obj.get("article_title") or ""
            # v2: KILL 후보 검증 위해 본문 600자로 확장
            preview_len = 600 if verdict == "KILL" else 300
            article_text_preview = (article_obj.get("article_text") or "")[:preview_len].replace("\n", " ")

        rows_out.append({
            "id": r.get("id"),
            "is_active": r.get("is_active"),
            "law_name": ln,
            "law_article_raw": larticle,
            "obligation_summary": (r.get("obligation_summary") or "")[:200].replace("\n", " "),
            "source_api": r.get("source_api"),
            "created_at": str(r.get("created_at") or "")[:10],
            "classification": cls,
            "verdict": verdict,
            "reason": reason,
            "real_article_title": article_title,
            "real_article_text_preview": article_text_preview,
        })

    print()
    print("분류 카운트:")
    for cls, n in sorted(cls_cnt.items()):
        print(f"  {cls:25} {n:5}")
    print()
    print("판정 카운트 (전체 193건 기준):")
    for v in ("KEEP", "KILL", "REVIEW"):
        print(f"  {v:10} {verdict_cnt[v]:5}")

    print()
    print(f"Step 4. CSV 출력 -> {args.out}")
    if rows_out:
        with open(args.out, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(rows_out[0].keys()))
            w.writeheader()
            for row in rows_out:
                w.writerow(row)
    print(f"OK {args.out} ({len(rows_out)} rows)")

    print()
    print("판정 x source_api 교차표 (출력 대상만):")
    cross = Counter()
    for row in rows_out:
        cross[(row["verdict"], row["source_api"] or "?")] += 1
    for (v, src), n in sorted(cross.items()):
        print(f"  {v:10} {src:30} {n:5}")

    kill_rows = [r for r in rows_out if r["verdict"] == "KILL"]
    if kill_rows:
        print()
        print(f"KILL 후보 {len(kill_rows)}건 (사용자 spot-check 필수, 본문 600자 미리보기는 CSV 참조):")
        for r in kill_rows[:30]:
            print(f"  [{r['source_api']:25}] {r['law_name'][:30]:30} {r['law_article_raw']:18} title={r['real_article_title'][:40]}")
        if len(kill_rows) > 30:
            print(f"  ... 그 외 {len(kill_rows)-30}건")

    print()
    print("=" * 72)
    print("다음 단계")
    print("=" * 72)
    print("  1) KILL 후보 본문 직접 대조 (CSV real_article_text_preview 600자)")
    print("  2) KEEP 분: is_active 유지. 본 미션 4단계(의무 추출)에서 본문 기반 자연 대체")
    print("  3) KILL 확정 분: 처리 스크립트로 DELETE/비활성화")
    print("  4) REVIEW: 사용자 spot-check 후 KEEP/KILL 재분류")


if __name__ == "__main__":
    main()
