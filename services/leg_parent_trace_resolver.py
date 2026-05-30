"""
services/leg_parent_trace_resolver.py — LEG Parent Trace Resolver v1

역할:
- runtime_metadata_resolution의 (law_name, article_no) 쌍에서
  law_master → law_article → rule_candidate 역추적
- rule_candidate.has_numeric 플래그 반환
- 조건 데이터 보강 후보 제공

원칙:
- DB 조회만 수행 (조건 생성 금지)
- 하드코딩 금지
- 추론 금지
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple


def _extract_article_num(article_str: str) -> Optional[int]:
    """'제17조' → 17, '제36조의2' → 36"""
    m = re.search(r"(\d+)", article_str)
    return int(m.group(1)) if m else None


def batch_resolve_numeric_flags(
    supabase,
    law_article_pairs: List[Tuple[str, str]],
) -> Dict[Tuple[str, str], Optional[bool]]:
    """
    (law_name, law_article) 쌍 목록에서 rule_candidate.has_numeric 플래그 배치 조회.

    Returns:
        {
            ("산업안전보건법", "제17조"): True,   # 수치 조건 있음
            ("산업안전보건법", "제36조"): False,  # 수치 조건 없음
            ("알수없는법", "제1조"): None,        # 역추적 실패
        }
    """
    if not law_article_pairs:
        return {}

    # 유니크 (law_name, article_num) 추출
    unique_pairs: Dict[Tuple[str, int], Set[str]] = {}
    for law_name, law_article in law_article_pairs:
        art_num = _extract_article_num(law_article)
        if not law_name or art_num is None:
            continue
        key = (law_name, art_num)
        if key not in unique_pairs:
            unique_pairs[key] = set()
        unique_pairs[key].add(law_article)

    if not unique_pairs:
        return {}

    # 유니크 law_name 목록
    law_names = list({k[0] for k in unique_pairs})

    # Step 1: law_master에서 law_name → id 매핑
    law_id_map: Dict[str, str] = {}
    for i in range(0, len(law_names), 50):
        chunk = law_names[i:i + 50]
        try:
            res = (
                supabase.table("law_master")
                .select("id, law_name")
                .in_("law_name", chunk)
                .execute()
            )
            for row in (res.data or []):
                law_id_map[row["law_name"]] = str(row["id"])
        except Exception:
            continue

    if not law_id_map:
        return {(ln, la): None for ln, la in law_article_pairs}

    # Step 2: law_article에서 (law_id, article_no) → article_id 매핑
    # + rule_candidate join으로 has_numeric 조회
    article_numeric_map: Dict[Tuple[str, int], bool] = {}

    # law_id별로 그룹핑
    lawid_to_name: Dict[str, str] = {v: k for k, v in law_id_map.items()}
    law_ids = list(law_id_map.values())

    for i in range(0, len(law_ids), 20):
        chunk_ids = law_ids[i:i + 20]
        try:
            # law_article 조회
            res = (
                supabase.table("law_article")
                .select("id, law_id, article_no")
                .in_("law_id", chunk_ids)
                .execute()
            )
            articles = res.data or []
        except Exception:
            continue

        if not articles:
            continue

        # article_id → (law_name, article_no) 매핑
        article_id_to_key: Dict[str, Tuple[str, int]] = {}
        article_ids: List[str] = []
        for art in articles:
            law_id = str(art.get("law_id", ""))
            art_no = art.get("article_no")
            law_name = lawid_to_name.get(law_id, "")
            if law_name and art_no is not None:
                key = (law_name, int(art_no))
                if key in unique_pairs:
                    aid = str(art["id"])
                    article_id_to_key[aid] = key
                    article_ids.append(aid)

        if not article_ids:
            continue

        # rule_candidate에서 has_numeric 조회
        for j in range(0, len(article_ids), 100):
            chunk_aids = article_ids[j:j + 100]
            try:
                rc_res = (
                    supabase.table("rule_candidate")
                    .select("article_id, has_numeric")
                    .in_("article_id", chunk_aids)
                    .execute()
                )
                for rc in (rc_res.data or []):
                    aid = str(rc.get("article_id", ""))
                    key = article_id_to_key.get(aid)
                    if key is None:
                        continue
                    hn = rc.get("has_numeric", False)
                    # 하나라도 has_numeric=true이면 True
                    if hn:
                        article_numeric_map[key] = True
                    elif key not in article_numeric_map:
                        article_numeric_map[key] = False
            except Exception:
                continue

    # Step 3: 원본 (law_name, law_article) 쌍으로 결과 매핑
    result: Dict[Tuple[str, str], Optional[bool]] = {}
    for law_name, law_article in law_article_pairs:
        art_num = _extract_article_num(law_article)
        if art_num is None:
            result[(law_name, law_article)] = None
            continue
        key = (law_name, art_num)
        result[(law_name, law_article)] = article_numeric_map.get(key)

    return result
