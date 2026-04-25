"""
routers/law_viewer.py - v1.0.0

법령 조문 조회 + 관련 판례 API
  GET /law/article?law_name=산업안전보건법&article_no=17
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from db.supabase_client import get_supabase

log = logging.getLogger(__name__)

router = APIRouter(prefix="/law", tags=["법령조문"])


@router.get("/article")
def get_law_article(
    law_name: str = Query(..., description="법령명 (예: 산업안전보건법)"),
    article_no: int = Query(..., description="조문 번호 (예: 17)"),
    rule_id: Optional[str] = Query(None, description="rule_id (판례 매칭용, 선택)"),
):
    """법령 조문 원문 + 관련 판례 조회."""
    supabase = get_supabase()

    # 1) 조문 원문 조회
    master_res = (
        supabase.table("law_master")
        .select("id, law_name")
        .eq("law_name", law_name)
        .limit(1)
        .execute()
    )
    if not master_res.data:
        master_res = (
            supabase.table("law_master")
            .select("id, law_name")
            .ilike("law_name", f"%{law_name}%")
            .limit(1)
            .execute()
        )
    if not master_res.data:
        raise HTTPException(status_code=404, detail=f"법령을 찾을 수 없습니다: {law_name}")

    law_id = master_res.data[0]["id"]
    law_name_actual = master_res.data[0]["law_name"]

    article_res = (
        supabase.table("law_article")
        .select("article_no, article_title, article_text, enforcement_date")
        .eq("law_id", law_id)
        .eq("article_no", article_no)
        .neq("article_status_code", "DELETED")
        .order("enforcement_date", desc=True)
        .limit(1)
        .execute()
    )

    if not article_res.data:
        version_res = (
            supabase.table("law_version")
            .select("id")
            .eq("law_id", law_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if version_res.data:
            article_res = (
                supabase.table("law_article")
                .select("article_no, article_title, article_text, enforcement_date")
                .eq("law_version_id", version_res.data[0]["id"])
                .eq("article_no", article_no)
                .neq("article_status_code", "DELETED")
                .limit(1)
                .execute()
            )

    article = None
    if article_res.data:
        row = article_res.data[0]
        article = {
            "article_no": row.get("article_no"),
            "article_title": row.get("article_title") or "",
            "article_text": row.get("article_text") or "",
            "enforcement_date": str(row.get("enforcement_date") or ""),
        }

    # 2) 판례 조회 (graceful degradation: 실패 시 빈 배열)
    precedents = []
    if rule_id:
        try:
            link_res = (
                supabase.table("precedent_rule_links")
                .select("precedent_id, relevance_score, link_type")
                .eq("rule_id", rule_id)
                .order("relevance_score", desc=True)
                .limit(5)
                .execute()
            )
            if link_res.data:
                precedent_ids = [r["precedent_id"] for r in link_res.data]
                prec_res = (
                    supabase.table("industrial_accident_precedents")
                    .select(
                        "id, case_number, case_name, court_name, decision_date, "
                        "summary, sentence_type, sentence_detail, fine_amount, "
                        "corporate_fine, death_count, injury_count, accident_type, industry_name"
                    )
                    .in_("id", precedent_ids)
                    .eq("is_active", True)
                    .execute()
                )
                prec_map = {str(p["id"]): p for p in (prec_res.data or [])}
                for link in link_res.data:
                    p = prec_map.get(str(link["precedent_id"]))
                    if p:
                        precedents.append(
                            {
                                "case_number": p.get("case_number") or "",
                                "case_name": p.get("case_name") or "",
                                "court_name": p.get("court_name") or "",
                                "decision_date": str(p.get("decision_date") or ""),
                                "summary": p.get("summary") or "",
                                "sentence": p.get("sentence_detail") or p.get("sentence_type") or "",
                                "fine_amount": p.get("fine_amount") or 0,
                                "corporate_fine": p.get("corporate_fine") or 0,
                                "death_count": p.get("death_count") or 0,
                                "injury_count": p.get("injury_count") or 0,
                                "relevance_score": link.get("relevance_score") or 0,
                            }
                        )
        except Exception as e:
            log.warning("[LAW VIEWER] 판례 조회 실패 (무시): %s", e)

    return {
        "status": "success",
        "data": {
            "law_name": law_name_actual,
            "article": article,
            "precedents": precedents,
            "precedent_count": len(precedents),
        },
    }
