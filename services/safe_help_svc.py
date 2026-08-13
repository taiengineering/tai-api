# -*- coding: utf-8 -*-
"""safe 헬프센터 검색/색인 서비스 (Path B). 설계: DESIGN-SAFE-HELP-CENTER v3 §9. DB: tai-db.

- safe_help_content 테이블 upsert(doc_id 기준) + kiwi 토큰 색인(reindex_help RPC).
- search_help / search_help_count RPC 질의(type/page_slug/게이팅 필터).
- 관리자(admin) CRUD: 목록/단건/상태토글/삭제/그룹목록 (매뉴얼 관리 화면용).
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


# ─────────────────────────────────────────────────────────────────────────
# 관리자(admin) CRUD — safe.taieng.co.kr 헬프센터(매뉴얼) 관리 화면용.
# 설계: admin-vue3 '서비스 운영 > 매뉴얼'. 목록/상태토글/삭제. 등록·수정은 upsert_help 재사용.
# ─────────────────────────────────────────────────────────────────────────

_ADMIN_COLS = (
    "id, doc_id, type, title, slug, status, menu_group, task_group, page_slug, "
    "question, answer_short, body, steps, sectors, min_level, related_pages, "
    "related_laws, created_at, updated_at"
)


def list_admin(
    q: Optional[str] = None,
    type: Optional[str] = None,
    menu_group: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """관리자 목록 — 전체 행(게이팅/색인 무관, status 포함) 조회. 반환: {items, total}.

    kiwi 검색이 아니라 관리 목적의 단순 필터(제목/doc_id/질문 ILIKE + type/menu_group/status).
    """
    sb = get_supabase()
    query = sb.table(_TABLE).select(_ADMIN_COLS, count="exact")
    if type:
        query = query.eq("type", type)
    if menu_group:
        query = query.eq("menu_group", menu_group)
    if status:
        query = query.eq("status", status)
    if q and q.strip():
        term = q.strip().replace(",", " ")
        query = query.or_(
            f"title.ilike.%{term}%,doc_id.ilike.%{term}%,question.ilike.%{term}%"
        )
    query = query.order("menu_group", desc=False).order("type", desc=False).order("doc_id", desc=False)
    res = query.range(offset, offset + limit - 1).execute()
    total = res.count if res.count is not None else len(res.data or [])
    return {"items": res.data or [], "total": int(total)}


def get_admin(doc_id: str) -> Optional[Dict[str, Any]]:
    """관리자 단건(doc_id 기준, 전체 필드)."""
    sb = get_supabase()
    res = sb.table(_TABLE).select("*").eq("doc_id", doc_id).limit(1).execute()
    return (res.data or [None])[0]


def set_status(doc_id: str, status: str) -> Optional[Dict[str, Any]]:
    """상태 온오프 — PUBLISHED / DRAFT 등 status 값만 변경(색인 무변경)."""
    if not status:
        raise ValueError("status 는 필수입니다.")
    sb = get_supabase()
    res = sb.table(_TABLE).update({"status": status}).eq("doc_id", doc_id).execute()
    return (res.data or [None])[0]


def delete_help(doc_id: str) -> bool:
    """단일 문서 삭제(doc_id 기준). 반환: 삭제 성공 여부."""
    sb = get_supabase()
    res = sb.table(_TABLE).delete().eq("doc_id", doc_id).execute()
    return bool(res.data)


def list_menu_groups() -> List[str]:
    """등록된 menu_group 목록(중복 제거, 정렬) — 관리 화면 필터/셀렉트용."""
    sb = get_supabase()
    res = sb.table(_TABLE).select("menu_group").not_.is_("menu_group", "null").execute()
    groups = sorted({r["menu_group"] for r in (res.data or []) if r.get("menu_group")})
    return groups
