"""
안전정보 게시판 라우터 — v1.0.0
prefix: /posts

엔드포인트:
  GET  /posts                목록 조회 (category/page/size/sort/search 필터)
  GET  /posts/latest         최신글 (limit, 인증 불필요)
  GET  /posts/stats/today    오늘 통계 (위젯용)
  GET  /posts/{id}           상세 조회 + view_count +1 + 이전/다음글
  POST /posts                게시글 작성
  PATCH /posts/{id}          게시글 수정
  DELETE /posts/{id}         게시글 삭제
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, date
import json

from db.supabase_client import get_supabase

router = APIRouter(prefix="/posts", tags=["posts"])

VERSION = "1.0.0"

# 카테고리 코드 목록
VALID_CATEGORIES = {
    "notice", "safety_news", "law_update", "accident_case",
    "kosha_guide", "msds", "hazmat", "general"
}


class PostCreate(BaseModel):
    category:     str
    title:        str
    content:      Optional[str]  = None
    summary:      Optional[str]  = None
    subcategory:  Optional[str]  = None
    thumbnail_url: Optional[str] = None
    external_url: Optional[str]  = None
    source:       Optional[str]  = None
    source_id:    Optional[str]  = None
    tags:         Optional[List[str]] = None
    attachments:  Optional[list] = None
    status:       Optional[str]  = "published"
    is_pinned:    Optional[bool] = False
    is_featured:  Optional[bool] = False
    author_name:  Optional[str]  = None
    published_at: Optional[str]  = None


class PostUpdate(BaseModel):
    category:     Optional[str]  = None
    title:        Optional[str]  = None
    content:      Optional[str]  = None
    summary:      Optional[str]  = None
    subcategory:  Optional[str]  = None
    thumbnail_url: Optional[str] = None
    external_url: Optional[str]  = None
    source:       Optional[str]  = None
    tags:         Optional[List[str]] = None
    attachments:  Optional[list] = None
    status:       Optional[str]  = None
    is_pinned:    Optional[bool] = None
    is_featured:  Optional[bool] = None
    author_name:  Optional[str]  = None


# ─────────────────────────────────────────────────────
# GET /posts/latest  최신글 (인증 불필요, 메인 노출용)
# ─────────────────────────────────────────────────────
@router.get("/latest")
def get_latest_posts(
    limit:    int = Query(3, ge=1, le=20),
    category: Optional[str] = Query(None),
    featured: Optional[bool] = Query(None, description="is_featured=true 필터"),
):
    """
    최신 게시글 목록. 인증 불필요.
    메인 페이지/대시보드 노출용.
    """
    supabase = get_supabase()
    query = supabase.table("posts") \
        .select("id, category, title, summary, thumbnail_url, source, published_at, view_count, is_featured") \
        .eq("status", "published")

    if category:
        query = query.eq("category", category)
    if featured is True:
        query = query.eq("is_featured", True)

    res = query.order("published_at", desc=True).limit(limit).execute()
    return {"status": "success", "data": {"items": res.data, "count": len(res.data)}}


# ─────────────────────────────────────────────────────
# GET /posts/stats/today  오늘 통계 (위젯용)
# ─────────────────────────────────────────────────────
@router.get("/stats/today")
def get_today_stats():
    """
    오늘 통계: 오늘 등록게수, 전체 게시게수, 카테고리별 수.
    대시보드 위젯용.
    """
    from datetime import date
    supabase = get_supabase()
    today_str = date.today().isoformat()

    # 오늘 등록긴 게시글
    today_res = supabase.table("posts") \
        .select("id", count="exact") \
        .gte("created_at", f"{today_str}T00:00:00") \
        .lt("created_at",  f"{today_str}T23:59:59") \
        .execute()

    # 전체 published 게시글 수
    total_res = supabase.table("posts") \
        .select("id", count="exact") \
        .eq("status", "published") \
        .execute()

    # 카테고리별 수 (파이썬에서 간단하게 집계)
    cat_res = supabase.table("posts") \
        .select("category") \
        .eq("status", "published") \
        .execute()

    cat_counts: dict = {}
    for row in (cat_res.data or []):
        c = row.get("category", "unknown")
        cat_counts[c] = cat_counts.get(c, 0) + 1

    return {
        "status": "success",
        "data": {
            "today_count":  today_res.count  or 0,
            "total_count":  total_res.count  or 0,
            "by_category":  cat_counts,
            "date":         today_str,
        }
    }


# ─────────────────────────────────────────────────────
# GET /posts  목록 조회
# ─────────────────────────────────────────────────────
@router.get("")
def get_posts(
    page:        int  = Query(1,  ge=1),
    size:        int  = Query(20, ge=1, le=100),
    category:    Optional[str]  = Query(None, description="카테고리 필터"),
    search:      Optional[str]  = Query(None, description="제목 검색"),
    source:      Optional[str]  = Query(None, description="출심 필터"),
    is_pinned:   Optional[bool] = Query(None, description="고정글 필터"),
    is_featured: Optional[bool] = Query(None, description="메인노출 필터"),
    status:      Optional[str]  = Query("published", description="상태 필터"),
    sort:        Optional[str]  = Query("latest", description="latest|views|pinned"),
):
    """
    안전정보 게시판 목록.
    sort: latest(최신순) | views(조회순) | pinned(고정우선)
    """
    supabase = get_supabase()
    query = supabase.table("posts") \
        .select(
            "id, category, subcategory, title, summary, thumbnail_url, "
            "source, published_at, view_count, is_pinned, is_featured, tags",
            count="exact"
        )

    if status:      query = query.eq("status", status)
    if category:    query = query.eq("category", category)
    if source:      query = query.eq("source", source)
    if search:      query = query.ilike("title", f"%{search}%")
    if is_pinned is not None:   query = query.eq("is_pinned",   is_pinned)
    if is_featured is not None: query = query.eq("is_featured", is_featured)

    # 정렬
    if sort == "views":
        query = query.order("view_count",   desc=True)
    elif sort == "pinned":
        query = query.order("is_pinned",    desc=True).order("published_at", desc=True)
    else:  # latest
        query = query.order("is_pinned",    desc=True).order("published_at", desc=True)

    offset = (page - 1) * size
    res = query.range(offset, offset + size - 1).execute()

    return {
        "status": "success",
        "data": {
            "items":       res.data,
            "total":       res.count,
            "page":        page,
            "size":        size,
            "total_pages": -(-res.count // size) if res.count else 0,
        }
    }


# ─────────────────────────────────────────────────────
# GET /posts/{id}  상세 조회 + view_count +1 + 이전/다음글
# ─────────────────────────────────────────────────────
@router.get("/{post_id}")
def get_post(post_id: str):
    """
    게시글 상세 + view_count +1 + 이전글/다음글.
    """
    supabase = get_supabase()

    # 상세 조회
    res = supabase.table("posts") \
        .select("*") \
        .eq("id", post_id) \
        .eq("status", "published") \
        .single().execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="게시글을 찾을 수 없습니다")

    post = res.data

    # view_count +1 (RPC 없이 단순 업데이트)
    supabase.table("posts") \
        .update({"view_count": post["view_count"] + 1}) \
        .eq("id", post_id).execute()
    post["view_count"] += 1

    # 이전글 (동일 카테고리, 더 오래된 것)
    prev_res = supabase.table("posts") \
        .select("id, title, published_at") \
        .eq("status",   "published") \
        .eq("category", post["category"]) \
        .lt("published_at", post["published_at"]) \
        .order("published_at", desc=True) \
        .limit(1).execute()

    # 다음글 (동일 카테고리, 더 최신인 것)
    next_res = supabase.table("posts") \
        .select("id, title, published_at") \
        .eq("status",   "published") \
        .eq("category", post["category"]) \
        .gt("published_at", post["published_at"]) \
        .order("published_at", desc=False) \
        .limit(1).execute()

    return {
        "status": "success",
        "data": {
            **post,
            "prev_post": prev_res.data[0] if prev_res.data else None,
            "next_post": next_res.data[0] if next_res.data else None,
        }
    }


# ─────────────────────────────────────────────────────
# POST /posts  게시글 작성
# ─────────────────────────────────────────────────────
@router.post("")
def create_post(req: PostCreate):
    supabase = get_supabase()

    now = datetime.now().isoformat()
    data = {
        k: v for k, v in req.dict().items()
        if v is not None
    }
    data["created_at"] = now
    data["updated_at"] = now
    if not data.get("published_at"):
        data["published_at"] = now
    if data.get("attachments"):
        data["attachments"] = json.dumps(data["attachments"])

    res = supabase.table("posts").insert(data).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="게시글 작성 실패")

    return {"status": "success", "message": "게시글이 등록됩니다", "data": res.data[0]}


# ─────────────────────────────────────────────────────
# PATCH /posts/{id}  수정
# ─────────────────────────────────────────────────────
@router.patch("/{post_id}")
def update_post(post_id: str, req: PostUpdate):
    supabase = get_supabase()

    existing = supabase.table("posts").select("id").eq("id", post_id).single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="게시글을 찾을 수 없습니다")

    update_data = {k: v for k, v in req.dict().items() if v is not None}
    update_data["updated_at"] = datetime.now().isoformat()

    res = supabase.table("posts").update(update_data).eq("id", post_id).execute()
    return {"status": "success", "message": "게시글이 수정됩니다", "data": res.data[0] if res.data else {}}


# ─────────────────────────────────────────────────────
# DELETE /posts/{id}  삭제 (soft delete)
# ─────────────────────────────────────────────────────
@router.delete("/{post_id}")
def delete_post(post_id: str):
    supabase = get_supabase()

    existing = supabase.table("posts").select("id").eq("id", post_id).single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="게시글을 찾을 수 없습니다")

    supabase.table("posts").update({
        "status":     "hidden",
        "updated_at": datetime.now().isoformat(),
    }).eq("id", post_id).execute()

    return {"status": "success", "message": "게시글이 삭제됩니다"}
