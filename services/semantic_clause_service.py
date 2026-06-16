"""D-001: SemanticClause 서비스

semantic_clause_fix + law_article_part + law_article + law_master를 JOIN해
SemanticClause 객체를 생성하는 조회 서비스.

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

_QUERY = """
SELECT
    scf.id          AS clause_id,
    scf.part_id,
    la.id           AS article_id,
    lm.id           AS law_id,
    lm.law_name,
    la.article_no::text AS article_no,
    la.article_title,
    scf.executor_text,
    lap.part_text   AS clause_text,
    scf.sector_hint,
    scf.created_at
FROM semantic_clause_fix scf
JOIN law_article_part lap ON scf.part_id = lap.id
JOIN law_article      la  ON lap.article_id = la.id
JOIN law_master       lm  ON la.law_id = lm.id
WHERE scf.executor_text IS NOT NULL
  AND scf.executor_text <> ''
"""


def _row_to_clause(row: dict) -> SemanticClause:
    return SemanticClause(
        clause_id=str(row["clause_id"]),
        part_id=str(row["part_id"]),
        article_id=str(row["article_id"]),
        law_id=str(row["law_id"]),
        law_name=str(row["law_name"] or ""),
        article_no=str(row["article_no"] or ""),
        article_title=str(row["article_title"] or ""),
        executor_text=str(row["executor_text"]),
        clause_text=str(row["clause_text"] or ""),
        sector_hint=row.get("sector_hint"),
        created_at=row.get("created_at"),
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
        sector_hint: 섹터 힌트 필터 (None = 전체).
        limit: 페이지 크기 (max 1000).
        offset: 시작 위치.
    """
    limit = min(limit, _PAGE_SIZE)

    # Supabase PostgREST 는 복잡한 JOIN SQL을 직접 지원하지 않으므로
    # 단계별 조회 후 Python에서 조인
    try:
        # 1) semantic_clause_fix 조회
        q = (
            supabase.table("semantic_clause_fix")
            .select("id, part_id, executor_text, sector_hint, created_at")
            .not_.is_("executor_text", "null")
            .neq("executor_text", "")
        )
        if sector_hint:
            q = q.eq("sector_hint", sector_hint)
        res = q.range(offset, offset + limit - 1).execute()
        rows = res.data or []
        if not rows:
            return []

        # 2) part_id 목록로 law_article_part 조회
        part_ids = [r["part_id"] for r in rows if r.get("part_id")]
        parts_res = (
            supabase.table("law_article_part")
            .select("id, article_id, part_text")
            .in_("id", part_ids)
            .execute()
        )
        part_map = {p["id"]: p for p in (parts_res.data or [])}

        # 3) article_id 목록로 law_article 조회
        article_ids = list({p["article_id"] for p in part_map.values() if p.get("article_id")})
        articles_res = (
            supabase.table("law_article")
            .select("id, law_id, article_no, article_title")
            .in_("id", article_ids)
            .execute()
        )
        article_map = {a["id"]: a for a in (articles_res.data or [])}

        # law_id 필터 적용
        if law_id:
            article_map = {k: v for k, v in article_map.items() if str(v.get("law_id") or "") == law_id}

        # 4) law_id 목록로 law_master 조회
        law_ids = list({a["law_id"] for a in article_map.values() if a.get("law_id")})
        laws_res = (
            supabase.table("law_master")
            .select("id, law_name")
            .in_("id", law_ids)
            .execute()
        )
        law_map = {lm["id"]: lm for lm in (laws_res.data or [])}

        # 5) 조립
        result: List[SemanticClause] = []
        for r in rows:
            part = part_map.get(r.get("part_id") or "")
            if not part:
                continue
            article = article_map.get(part.get("article_id") or "")
            if not article:
                continue
            law = law_map.get(article.get("law_id") or "")
            if not law:
                continue
            result.append(
                SemanticClause(
                    clause_id=str(r["id"]),
                    part_id=str(r["part_id"]),
                    article_id=str(article["id"]),
                    law_id=str(law["id"]),
                    law_name=str(law.get("law_name") or ""),
                    article_no=str(article.get("article_no") or ""),
                    article_title=str(article.get("article_title") or ""),
                    executor_text=str(r["executor_text"]),
                    clause_text=str(part.get("part_text") or ""),
                    sector_hint=r.get("sector_hint"),
                    created_at=r.get("created_at"),
                )
            )
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
            .select("id, part_id, executor_text, sector_hint, created_at")
            .eq("id", clause_id)
            .limit(1)
            .execute()
        )
        if not res.data:
            return None
        r = res.data[0]
        # 한 건이면 목록에서 재사용
        items = get_semantic_clauses(supabase, limit=1, offset=0)
        # 단건 정확 조회는 위 목록과 다른 경로 사용
        part_res = (
            supabase.table("law_article_part")
            .select("id, article_id, part_text")
            .eq("id", r["part_id"])
            .limit(1)
            .execute()
        )
        if not part_res.data:
            return None
        part = part_res.data[0]
        art_res = (
            supabase.table("law_article")
            .select("id, law_id, article_no, article_title")
            .eq("id", part["article_id"])
            .limit(1)
            .execute()
        )
        if not art_res.data:
            return None
        article = art_res.data[0]
        law_res = (
            supabase.table("law_master")
            .select("id, law_name")
            .eq("id", article["law_id"])
            .limit(1)
            .execute()
        )
        if not law_res.data:
            return None
        law = law_res.data[0]
        return SemanticClause(
            clause_id=str(r["id"]),
            part_id=str(r["part_id"]),
            article_id=str(article["id"]),
            law_id=str(law["id"]),
            law_name=str(law.get("law_name") or ""),
            article_no=str(article.get("article_no") or ""),
            article_title=str(article.get("article_title") or ""),
            executor_text=str(r["executor_text"]),
            clause_text=str(part.get("part_text") or ""),
            sector_hint=r.get("sector_hint"),
            created_at=r.get("created_at"),
        )
    except Exception as exc:
        log.error("get_semantic_clause_by_id 오류: %s", exc)
        return None


def count_semantic_clauses(
    supabase,
    law_id: Optional[str] = None,
) -> int:
    """executor_text 있는 semantic_clause_fix 건수. 건수 확인용."""
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
