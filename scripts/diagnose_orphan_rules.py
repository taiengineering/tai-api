#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
diagnose_orphan_rules.py — 매핑 의심 룰 진단 (read-only)

S9 § 3.3 처리 항목 #1 (KEC 숫자 8) + #2 (보일러플레이트 198) 통합 트랙.

목적:
    master_building_legal_rules 의 의심 룰을 본문(law_master/law_version/law_article)
    과 대조하여 자동 판정 가능한 분류를 산출. 결과 CSV를 사용자가 검토 후 처리
    방향(삭제/재파싱/비활성)을 결정한다. 본 스크립트는 절대 DB를 수정하지 않는다.

대상 패턴:
    1) obligation_summary 가 '<동사> 의무 (<설명>)' 형태로 끝나는 짧은 보일러플레이트
    2) law_article 이 KEC 점번호 형태 ('^[0-9]+$', '^[0-9]+\\.[0-9]+$')

자동 분류:
    A. ORPHAN_NO_LAW     : law_master 에 해당 법령 자체가 없음
    B. ATTACHMENT_BODY   : 법령 있으나 article < 5 (첨부파일 본체 의심, S8 § 5.1)
    C. ORPHAN_NO_ARTICLE : 법령 있으나 해당 article_no 없음
    C2. PARSE_FAIL       : law_article 에서 article_no 추출 자체 실패
    D. MAPPED            : article 매칭됨 → obligation_summary 정합성은 사용자/AI 검토

출력:
    /tmp/orphan_rules_diagnosis.csv  (UTF-8 BOM, Excel 호환)
    콘솔 요약 + 분류별 카운트 + source_api 분포

실행:
    cd ~/dev/tai-api
    git pull origin main
    railway run python3 scripts/diagnose_orphan_rules.py

원칙 (S9):
    - read-only 만. DB 변경 금지.
    - 핸드오프 의존 금지 — DB가 진실.
    - 분류는 자동 판정 가능한 것만. D 케이스의 의무 정합성은 사용자가 결정.
"""

import csv
import os
import re
import sys
from collections import Counter
from pathlib import Path

# 1) .env 자동 로드 (S7 패턴)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# 2) 죽은 iwinv Squid 프록시 무력화 (S8 패턴)
for _k in ("OUTBOUND_PROXY", "HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(_k, None)

# 3) Supabase 연결
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = (
    os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    or os.environ.get("SUPABASE_KEY")
    or os.environ.get("SUPABASE_SERVICE_KEY")
)
if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: SUPABASE_URL / SUPABASE_(SERVICE_ROLE_)KEY 환경변수 누락", file=sys.stderr)
    print("       railway run 으로 실행하거나 .env 점검", file=sys.stderr)
    sys.exit(1)

from supabase import create_client  # noqa: E402
sb = create_client(SUPABASE_URL, SUPABASE_KEY)

# ────────────────────────────────────────────────────────────────
# 패턴
# ────────────────────────────────────────────────────────────────
BOILER_RE = re.compile(
    r'^\s*('
    r'조치|점검|이행|보고|기록|작성|선임|준수|관리|준비|확인|실시|신고|'
    r'등록|교육|배치|보존|비치|승인|평가|진단|측정|시험'
    r')\s*의무\s*\(.+\)\s*$'
)
KEC_RE = re.compile(r'^\s*[0-9]+(\.[0-9]+)?\s*$')
ARTICLE_RE = re.compile(r'제\s*(\d+)\s*조(?:의\s*(\d+))?')


# ────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────
def fetch_paged(table, columns, **eq_filters):
    """supabase-py .range()로 페이징 (.execute()는 1000건 한도)."""
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


def extract_article_no(law_article: str):
    """law_article 텍스트에서 (article_no, article_sub_no) 추출."""
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


# ────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────
def main():
    # Step 1: 대상 수집
    print("=" * 72)
    print("Step 1. 대상 룰 수집")
    print("=" * 72)
    rules = fetch_paged(
        "master_building_legal_rules",
        "id,law_name,law_article,obligation_summary,is_active,source_api,created_at",
    )
    print(f"전체 master 룰: {len(rules):,}건")

    target = []
    for r in rules:
        olaw = r.get("obligation_summary") or ""
        larticle = r.get("law_article") or ""
        if BOILER_RE.match(olaw) or KEC_RE.match(larticle):
            target.append(r)

    print(f"대상 룰 (보일러플레이트 + KEC 점번호): {len(target):,}건")
    src_cnt = Counter((r.get("source_api") or "?") for r in target)
    for src, n in src_cnt.most_common():
        print(f"  {src:32} {n:5}건")

    if not target:
        print("대상 0건 — 종료")
        return

    # Step 2: law_master + article 캐싱
    print()
    print("=" * 72)
    print("Step 2. law_master + current version article 캐싱")
    print("=" * 72)
    distinct_names = sorted({r.get("law_name") for r in target if r.get("law_name")})
    print(f"distinct 법령: {len(distinct_names)}개")

    cache = {}
    for i, ln in enumerate(distinct_names, 1):
        m_resp = (
            sb.table("law_master")
            .select("id,current_version_id")
            .eq("law_name", ln)
            .limit(1)
            .execute()
        )
        if not m_resp.data:
            cache[ln] = {"master_id": None, "article_count": 0, "articles_by_no": {}}
            if i % 10 == 0 or i == len(distinct_names):
                print(f"  {i}/{len(distinct_names)} 캐싱 진행 ({ln[:30]} → law_master 없음)")
            continue
        m = m_resp.data[0]
        cv = m.get("current_version_id")
        if not cv:
            cache[ln] = {"master_id": m["id"], "article_count": 0, "articles_by_no": {}}
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
        cache[ln] = {
            "master_id": m["id"],
            "version_id": cv,
            "article_count": len(arts),
            "articles_by_no": by_no,
        }
        if i % 10 == 0 or i == len(distinct_names):
            print(f"  {i}/{len(distinct_names)} 캐싱 진행")

    # Step 3: 분류
    print()
    print("=" * 72)
    print("Step 3. 분류")
    print("=" * 72)
    rows_out = []
    cls_cnt = Counter()
    for r in target:
        ln = r.get("law_name")
        larticle = r.get("law_article") or ""
        c = cache.get(ln) or {"master_id": None, "article_count": 0, "articles_by_no": {}}

        if c["master_id"] is None:
            cls = "A_ORPHAN_NO_LAW"
            article_no = None
            article_title = None
            article_text_preview = None
        elif c["article_count"] < 5:
            cls = "B_ATTACHMENT_BODY"
            article_no = None
            article_title = None
            article_text_preview = None
        else:
            ano, asub = extract_article_no(larticle)
            if ano is None:
                cls = "C2_PARSE_FAIL"
                article_no = None
                article_title = None
                article_text_preview = None
            else:
                a = c["articles_by_no"].get((ano, asub or 0)) or c["articles_by_no"].get((ano, 0))
                if a is None:
                    cls = "C_ORPHAN_NO_ARTICLE"
                    article_no = ano
                    article_title = None
                    article_text_preview = None
                else:
                    cls = "D_MAPPED"
                    article_no = ano
                    article_title = a.get("article_title")
                    article_text_preview = (a.get("article_text") or "")[:300].replace("\n", " ")

        cls_cnt[cls] += 1
        rows_out.append({
            "id": r.get("id"),
            "is_active": r.get("is_active"),
            "law_name": ln,
            "law_article_raw": larticle,
            "obligation_summary": (r.get("obligation_summary") or "")[:200].replace("\n", " "),
            "source_api": r.get("source_api"),
            "created_at": str(r.get("created_at") or "")[:10],
            "classification": cls,
            "extracted_article_no": article_no,
            "law_master_article_count": c["article_count"],
            "real_article_title": article_title,
            "real_article_text_preview": article_text_preview,
        })

    for cls, n in sorted(cls_cnt.items()):
        print(f"  {cls:25} {n:5}건")

    # Step 4: CSV 출력
    print()
    print("=" * 72)
    print("Step 4. CSV 출력")
    print("=" * 72)
    out_path = Path("/tmp/orphan_rules_diagnosis.csv")
    if rows_out:
        with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(rows_out[0].keys()))
            w.writeheader()
            for row in rows_out:
                w.writerow(row)
    print(f"✓ {out_path} ({len(rows_out)}건)")

    # 분류별 source_api 분포 (참고)
    print()
    print("Step 5. 분류 × source_api 교차표 (참고)")
    cross = Counter()
    for row in rows_out:
        cross[(row["classification"], row["source_api"] or "?")] += 1
    for (cls, src), n in sorted(cross.items()):
        print(f"  {cls:25} {src:30} {n:5}건")

    print()
    print("=" * 72)
    print("다음 단계 가이드")
    print("=" * 72)
    print("  A. ORPHAN_NO_LAW     : law_external_catalog 보완 후 수집 또는 비활성화")
    print("  B. ATTACHMENT_BODY   : 첨부파일 본체 트랙 (S8 § 5.1, 82건과 합산)")
    print("  C. ORPHAN_NO_ARTICLE : 매핑 깨짐 — 비활성화 / 삭제 검토")
    print("  C2. PARSE_FAIL       : law_article 형식 결함 — 정정 후 재분류")
    print("  D. MAPPED            : 본문 매칭됨 — 사용자/AI 의무 정합성 spot-check")
    print()
    print("CSV 검토 후 사용자 결정 → 처리 스크립트 별도 작성")


if __name__ == "__main__":
    main()
