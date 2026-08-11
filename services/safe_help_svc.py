# -*- coding: utf-8 -*-
"""safe 헬프센터 검색/색인 서비스 (Path B). 설계: DESIGN-SAFE-HELP-CENTER v3 §9. DB: tai-db.

- safe_help_content 테이블 upsert(doc_id 기준) + kiwi 토큰 색인(reindex_help RPC).
- search_help / search_help_count RPC 질의(type/page_slug/게이팅 필터).
"""
from typing import Optional, List, Dict, Any

from db.supabase_client import get_supabase
from services.safe_help_kiwi import strip_html, index_text, query_text

_TABLE = "safe_help_content"


def _doc_index_text(row: Dict[str, Any]) -> str:
    """행에서 검색 색인 대상 텍스트를 모아 kiwi 토큰 문자열로 변환."""
    parts: List[Optional[str]] = [
        row.get("title"),
        row.get("question"),
        row.get("answer_short"),
        row.get("menu_group"),
        row.get("task_group"),
        strip_html(row.get("body") or ""),
    ]
    steps = row.get("steps") or []
    if isinstance(steps, list):
        for s in steps:
            if isinstance(s, dict) and s.get("text"):
                parts.append(s.get("text"))
    laws = row.get("related_laws") or []
    if isinstance(laws, list):
        parts.extend([x for x in laws if x])
    return index_text(*[p for p in parts if p])


def upsert_help(doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """doc_id 기준 upsert 후 kiwi 토큰으로 색인. 반환: 저장된 행."""
    for k in ("doc_id", "type", "title", "slug"):
        if not doc.get(k):
            raise ValueError("doc_id, type, title, slug 는 필수입니다.")
    sb = get_supabase()
    res = sb.table(_TABLE).upsert(doc, on_conflict="doc_id").execute()
    saved = (res.data or [None])[0]
    if saved and saved.get("id"):
        sb.rpc("reindex_help", {"p_id": saved["id"], "p_txt": _doc_index_text(saved)}).execute()
    return saved


def reindex(doc_id: str) -> bool:
    """단일 문서 재색인(원문 무변경, search_tsv 만 갱신)."""
    sb = get_supabase()
    res = sb.table(_TABLE).select("*").eq("doc_id", doc_id).limit(1).execute()
    row = (res.data or [None])[0]
    if not row:
        return False
    sb.rpc("reindex_help", {"p_id": row["id"], "p_txt": _doc_index_text(row)}).execute()
    return True


def search(
    q: str,
    types: Optional[List[str]] = None,
    page_slug: Optional[str] = None,
    sector: Optional[str] = None,
    level: Optional[int] = None,
    addons: Optional[List[str]] = None,
    role: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> Dict[str, Any]:
    """kiwi 질의 토큰 → search_help/search_help_count RPC. 반환: {items, total}."""
    tsq = query_text(q or "")
    if not tsq.strip():
        return {"items": [], "total": 0}
    sb = get_supabase()
    items = sb.rpc("search_help", {
        "p_tsq": tsq, "p_types": types, "p_page_slug": page_slug,
        "p_sector": sector, "p_level": level, "p_addons": addons, "p_role": role,
        "p_limit": limit, "p_offset": offset,
    }).execute().data or []
    total = sb.rpc("search_help_count", {
        "p_tsq": tsq, "p_types": types, "p_sector": sector,
        "p_level": level, "p_addons": addons, "p_role": role,
    }).execute().data
    if isinstance(total, list):
        total = total[0] if total else 0
    return {"items": items, "total": int(total or 0)}


def get_by_slug(slug: str) -> Optional[Dict[str, Any]]:
    sb = get_supabase()
    res = sb.table(_TABLE).select("*").eq("slug", slug).limit(1).execute()
    return (res.data or [None])[0]
