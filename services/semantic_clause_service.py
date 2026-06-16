"""D-001: SemanticClause 서비스

semantic_clause_fix + law_article + law_master를 JOIN해
SemanticClause 객체를 생성하는 조회 서비스.

실측 확인된 컬럼명 (2026-06-16):
  - source_article_id (part_id 아님)
  - source_text (clause_text 대용)
  - sector (sector_hint 아님)
  - law_article_part 조회 불필요 — source_article_id로 law_article 직접 연결

금지:
  - semantic_clause_fix 테이블 수정/삭제
  - anonymous_diagnosis.py 수정
"""
from __future__ import annotations

import logging
from typing import List, Optional

from schemas.semantic_clause_schema import SemanticClause

log = logging.getLogger(__name__)

_PAGE_SIZE = 1000


def _build_clause(r: dict, article: dict, law: dict) -> SemanticClause:
    return SemanticClause(
        clause_id=str(r["id"]),
        part_id=str(r.get("source_part_id") or ""),
        article_id=str(article["id"]),
        law_id=str(law["id"]),
        law_name=str(law.get("law_name") or ""),
        article_no=str(article.get("article_no") or ""),
        article_title=str(article.get("article_title") or ""),
        executor_text=str(r["executor_text"]),
        clause_text=str(r.get("source_text") or ""),
        sector_hint=r.get("sector"),
        created_at=r.get("created_at"),
    )


def get_semantic_clauses(
    supabase,
    law_id: Optional[str] = None,
    sector_hint: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[SemanticClause]:
    """SemanticClause 목록 조회. 페이지네이션 필수.

    Args:
        law_id: 특정 법령 law_master.id 필터 (None = 전체).
        sector_hint: sector 필터 (INDUSTRIAL/BUILDING/CONSTRUCTION/COMMON 등).
        limit: 페이지 크기 (max 1000).
        offset: 시작 위치.
    """
    limit = min(limit, _PAGE_SIZE)

    try:
        # 1) semantic_clause_fix 조회
        q = (
            supabase.table("semantic_clause_fix")
            .select(
                "id, source_part_id, source_article_id, "
                "executor_text, source_text, sector, created_at"
            )
            .not_.is_("executor_text", "null")
            .neq("executor_text", "")
        )
        if sector_hint:
            q = q.eq("sector", sector_hint)
        res = q.range(offset, offset + limit - 1).execute()
        rows = res.data or []
        if not rows:
            return []

        # 2) source_article_id 목록으로 law_article 조회
        article_ids = list({
            str(r["source_article_id"])
            for r in rows
            if r.get("source_article_id")
        })
        if not article_ids:
            return []

        articles_res = (
            supabase.table("law_article")
            .select("id, law_id, article_no, article_title")
            .in_("id", article_ids)
            .execute()
        )
        article_map = {str(a["id"]): a for a in (articles_res.data or [])}

        # law_id 필터 적용
        if law_id:
            article_map = {
                k: v for k, v in article_map.items()
                if str(v.get("law_id") or "") == law_id
            }
        if not article_map:
            return []

        # 3) law_id 목록으로 law_master 조회
        law_ids = list({str(a["law_id"]) for a in article_map.values() if a.get("law_id")})
        laws_res = (
            supabase.table("law_master")
            .select("id, law_name")
            .in_("id", law_ids)
            .execute()
        )
        law_map = {str(lm["id"]): lm for lm in (laws_res.data or [])}

        # 4) 조립
        result: List[SemanticClause] = []
        for r in rows:
            art_id = str(r.get("source_article_id") or "")
            article = article_map.get(art_id)
            if not article:
                continue
            law = law_map.get(str(article.get("law_id") or ""))
            if not law:
                continue
            result.append(_build_clause(r, article, law))

        return result

    except Exception as exc:
        log.error("get_semantic_clauses 오류: %s", exc)
        return []


def get_semantic_clause_by_id(
    supabase,
    clause_id: str,
) -> Optional[SemanticClause]:
    """clause_id(semantic_clause_fix.id)로 단건 조회. 역추적용."""
    try:
        res = (
            supabase.table("semantic_clause_fix")
            .select(
                "id, source_part_id, source_article_id, "
                "executor_text, source_text, sector, created_at"
            )
            .eq("id", clause_id)
            .limit(1)
            .execute()
        )
        if not res.data:
            return None
        r = res.data[0]

        art_id = str(r.get("source_article_id") or "")
        if not art_id:
            return None

        art_res = (
            supabase.table("law_article")
            .select("id, law_id, article_no, article_title")
            .eq("id", art_id)
            .limit(1)
            .execute()
        )
        if not art_res.data:
            return None
        article = art_res.data[0]

        law_res = (
            supabase.table("law_master")
            .select("id, law_name")
            .eq("id", str(article.get("law_id") or ""))
            .limit(1)
            .execute()
        )
        if not law_res.data:
            return None
        law = law_res.data[0]

        return _build_clause(r, article, law)

    except Exception as exc:
        log.error("get_semantic_clause_by_id 오류: %s", exc)
        return None


def count_semantic_clauses(
    supabase,
    law_id: Optional[str] = None,
) -> int:
    """executor_text 있는 semantic_clause_fix 건수."""
    try:
        q = (
            supabase.table("semantic_clause_fix")
            .select("id", count="exact")
            .not_.is_("executor_text", "null")
            .neq("executor_text", "")
        )
        res = q.limit(1).execute()
        return res.count or 0
    except Exception as exc:
        log.error("count_semantic_clauses 오류: %s", exc)
        return 0
