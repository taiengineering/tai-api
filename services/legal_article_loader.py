"""services/legal_article_loader.py

rule_id 리스트를 받아서 rule_article_mapping을 통해 law_article 본문을
배치로 조회하는 헬퍼. N+1 쿼리 방지를 위해 2회 쿼리로 처리.

사용:
    from services.legal_article_loader import fetch_article_contexts
    
    rule_ids = [r['rule_id'] for r in matched_rules]
    article_ctx = fetch_article_contexts(supabase, rule_ids)
    
    for rule in matched_rules:
        formatted = format_rule_result_db(rule, article_ctx.get(rule['rule_id']))

반환 형식:
    {
        "rule_id_1": {
            "article_id": "uuid",
            "article_internal_key": "0050001" | "nfpc-art-038" | "nftc-sec-1.7.1.11",
            "article_title": "...",
            "article_text": "...",
            "confidence": 0.95,
            "law_system": "LEGAL" | "NFPC" | "NFTC" | "OTHER"
        },
        ...
    }
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

_IN_CHUNK = 80
_MAX_CITATION_RULES = 100


def _chunked_in_query(supabase, table: str, select: str, column: str, ids: List[str]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    clean = [x for x in ids if x]
    for i in range(0, len(clean), _IN_CHUNK):
        chunk = clean[i : i + _IN_CHUNK]
        if not chunk:
            continue
        res = supabase.table(table).select(select).in_(column, chunk).execute()
        rows.extend(res.data or [])
    return rows


def classify_law_system(article_internal_key: str) -> str:
    """article_internal_key로 법령 체계 분류."""
    if not article_internal_key:
        return "UNKNOWN"
    key = article_internal_key.strip()
    # 체계 A: 법제처 공식 7자리 숫자 (예: 0050001)
    if len(key) == 7 and key.isdigit():
        return "LEGAL"
    if key.startswith("nfpc-"):
        return "NFPC"
    if key.startswith("nftc-"):
        return "NFTC"
    if key.startswith("admrul-"):
        return "ADMRUL_FALLBACK"
    return "OTHER"


def _article_no_digits(law_article: str) -> str:
    s = (law_article or "").strip()
    if not s:
        return ""
    digits = re.sub(r"[^\d]", "", s)
    return digits


def _lookup_articles_by_citation(
    supabase,
    rules: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """rule_article_mapping 없을 때 law_name + 조문번호로 law_article 조회."""
    out: Dict[str, Dict[str, Any]] = {}
    pairs: List[tuple[str, str, str]] = []
    for rule in rules[:_MAX_CITATION_RULES]:
        rid = str(rule.get("rule_id") or "")
        law = (rule.get("law_name") or "").strip()
        art_digits = _article_no_digits(rule.get("law_article") or "")
        if rid and law and art_digits:
            pairs.append((rid, law, art_digits))

    seen_laws = list({p[1] for p in pairs})
    for law_name in seen_laws[:50]:
        try:
            res = (
                supabase.table("law_article")
                .select(
                    "id, law_name, article_no, article_internal_key, article_type, "
                    "article_title, article_text, article_status_code, law_id"
                )
                .eq("article_status_code", "ACTIVE")
                .ilike("law_name", f"%{law_name}%")
                .limit(500)
                .execute()
            )
        except Exception:
            continue
        articles = res.data or []
        by_digits: Dict[str, Dict[str, Any]] = {}
        for a in articles:
            d = _article_no_digits(str(a.get("article_no") or ""))
            if d and d not in by_digits:
                by_digits[d] = a
        for rid, ln, digits in pairs:
            if ln != law_name or rid in out:
                continue
            article = by_digits.get(digits)
            if not article:
                continue
            internal_key = article.get("article_internal_key") or ""
            out[rid] = {
                "article_id": article["id"],
                "article_internal_key": internal_key,
                "article_no": article.get("article_no"),
                "article_sub_no": article.get("article_sub_no"),
                "article_type": article.get("article_type", ""),
                "article_title": article.get("article_title", ""),
                "article_text": article.get("article_text", ""),
                "law_id": article.get("law_id"),
                "confidence": 0.5,
                "law_system": classify_law_system(internal_key),
            }
    return out


def fetch_article_contexts(
    supabase,
    rule_ids: List[str],
    rules: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    rule_id 리스트 → {rule_id: article_info} 매핑 반환.
    
    내부 구현:
      1) rule_article_mapping에서 rule_id → article_id 조회 (in_ 배치)
      2) law_article에서 article_id → 본문 조회 (in_ 배치)
      3) dict 합쳐서 반환
    
    rule_id가 매핑 안 된 경우 해당 rule_id는 결과 dict에 없음.
    호출자는 result.get(rule_id)로 접근.
    """
    if not rule_ids:
        return {}
    
    # 중복 제거
    unique_rule_ids = list(set(filter(None, rule_ids)))
    if not unique_rule_ids:
        return {}
    
    try:
        mappings: List[Dict[str, Any]] = _chunked_in_query(
            supabase,
            "rule_article_mapping",
            "rule_id, article_id, article_internal_key, confidence_score",
            "rule_id",
            unique_rule_ids,
        )
    except Exception as e:
        print(f"[LEGAL_ARTICLE_LOADER] rule_article_mapping 조회 실패: {e}")
        mappings = []
    
    result: Dict[str, Dict[str, Any]] = {}

    if mappings:
        article_ids = list({m["article_id"] for m in mappings if m.get("article_id")})
        if article_ids:
            try:
                articles = _chunked_in_query(
                    supabase,
                    "law_article",
                    "id, article_internal_key, article_no, article_sub_no, "
                    "article_type, article_title, article_text, "
                    "article_status_code, law_id",
                    "id",
                    article_ids,
                )
                articles = [a for a in articles if (a.get("article_status_code") or "") == "ACTIVE"]
            except Exception as e:
                print(f"[LEGAL_ARTICLE_LOADER] law_article 조회 실패: {e}")
                articles = []
        else:
            articles = []

        article_by_id = {a["id"]: a for a in articles}

        for m in mappings:
            rid = m.get("rule_id")
            aid = m.get("article_id")
            if not rid or not aid or aid not in article_by_id:
                continue

            article = article_by_id[aid]
            confidence = float(m.get("confidence_score") or 0)

            existing = result.get(rid)
            if existing and existing.get("confidence", 0) >= confidence:
                continue

            internal_key = article.get("article_internal_key") or ""

            result[rid] = {
                "article_id": article["id"],
                "article_internal_key": internal_key,
                "article_no": article.get("article_no"),
                "article_sub_no": article.get("article_sub_no"),
                "article_type": article.get("article_type", ""),
                "article_title": article.get("article_title", ""),
                "article_text": article.get("article_text", ""),
                "law_id": article.get("law_id"),
                "confidence": confidence,
                "law_system": classify_law_system(internal_key),
            }
    
    if rules:
        try:
            citation_ctx = _lookup_articles_by_citation(supabase, rules)
            for rid, info in citation_ctx.items():
                if rid not in result:
                    result[rid] = info
        except Exception as e:
            print(f"[LEGAL_ARTICLE_LOADER] citation fallback 실패 (무시): {e}")

    return result


def fetch_single_article_context(supabase, rule_id: str) -> Optional[Dict[str, Any]]:
    """단일 rule_id 조회 (편의 함수)."""
    ctx_map = fetch_article_contexts(supabase, [rule_id])
    return ctx_map.get(rule_id)
