# -*- coding: utf-8 -*-
"""헬프센터 공개 조회 API (help.taieng.co.kr) — v1.0.0

경로
  GET  /helpcenter/tree                 트리(축 전체 또는 root_key 하나) + 축별 문서 수
  GET  /helpcenter/doc/{slug}           문서 단건 + 브레드크럼 + 관련·짝 문서
  GET  /helpcenter/search               검색 (ctx 우선 정렬, 0건이면 대체 질문)
  GET  /helpcenter/context/{page_slug}  화면 하나의 도움말 묶음 — 앱·어드민 '?' 진입
  POST /helpcenter/feedback             문서 도움됨/안됨

게이팅 (P13)
  role·sector·level 은 **전부 서버가 토큰에서 도출한다.** 이 라우터는 그 세 값을 쿼리
  파라미터로 선언하지 않으며, 클라이언트가 보내더라도 읽지 않는다. 값을 조작해도 응답이
  바뀌지 않는다. routers/leader_scope.py 의 '클라이언트 값 불신' 관례를 따른 것이고,
  기존 routers/safe_help.py 가 sector·level·addons·role 을 쿼리로 받는 구조는 승계하지 않는다.

  비로그인도 열람 가능하다(P9). 토큰이 없으면 익명 viewer 로 PUBLIC 문서만 보인다.
  토큰이 있는데 유효하지 않으면 401 로 끊는다 — 조용히 익명으로 낮추지 않는다.

등급 (P14)
  계약 plan_code 가 매핑에 없으면 level 은 None 이고, min_level 이 걸린 문서는 보이지 않는다.
  추측해서 등급을 채우지 않는다. services/help_plan_level.py 참조.

구자산 safe_help_content 및 /help/* 라우터와는 무관하다 — 읽지도 쓰지도 않는다.
"""
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel

from db.supabase_client import get_supabase
from services import help_plan_level, helpcenter_svc
from services import helpcenter_visibility as vis

log = logging.getLogger(__name__)
router = APIRouter(prefix="/helpcenter", tags=["HelpCenter"])

_MAX_LIMIT = 50


# ─────────────────────────────────────────────────────────────────────────
# 인증 — 있으면 검증, 없으면 익명. routers/worker_check.py 의 _optional_auth 와 같은 형태다.
# ─────────────────────────────────────────────────────────────────────────

def _optional_auth(authorization: Optional[str] = Header(None)) -> Optional[Dict[str, Any]]:
    """Authorization 이 있으면 검증하고 users 행을 돌려준다. 없으면 None.

    토큰이 붙어 있는데 만료·위조면 401 이다. 익명으로 강등하면 사용자가 로그인한 줄 알고
    안 보이는 문서를 계속 찾게 된다.
    """
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.replace("Bearer ", "")
    supabase = get_supabase()
    try:
        ur = supabase.auth.get_user(token)
        if not ur or not ur.user:
            raise HTTPException(status_code=401, detail={"error": "AUTH_EXPIRED"})
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail={"error": "AUTH_EXPIRED"})

    res = supabase.table("users").select("*").eq("auth_id", str(ur.user.id)).limit(1).execute()
    if not res.data:
        # 인증은 됐으나 업무 사용자 행이 없다 — 게이팅 근거가 없으므로 익명으로 본다.
        log.info("[helpcenter] users 행 없음 auth_id=%s — 익명 판정", ur.user.id)
        return None
    return res.data[0]


def get_viewer(user: Optional[Dict[str, Any]] = Depends(_optional_auth)) -> Dict[str, Any]:
    """노출 판정용 viewer — 토큰에서 도출한 값만 담는다."""
    if not user:
        return dict(vis.ANONYMOUS)
    contract = help_plan_level.resolve_for_company(user.get("company_id"))
    return vis.build_viewer(user, contract)


def _ok(data: Any) -> Dict[str, Any]:
    return {"status": "success", "data": data}


# ─────────────────────────────────────────────────────────────────────────
# O8 트리
# ─────────────────────────────────────────────────────────────────────────

@router.get("/tree")
def get_tree(
    root_key: Optional[str] = Query(None, description="축 키. 생략하면 전체 축"),
    viewer: Dict[str, Any] = Depends(get_viewer),
):
    """축 트리. 감춰진 부모 아래는 통째로 빠진다(고아 없음)."""
    tree = helpcenter_svc.get_tree(root_key, viewer)
    payload: Dict[str, Any] = {"root_key": root_key, "tree": tree}
    if not root_key:
        payload["counts"] = helpcenter_svc.count_by_root(viewer)
    return _ok(payload)


# ─────────────────────────────────────────────────────────────────────────
# O9 문서
# ─────────────────────────────────────────────────────────────────────────

@router.get("/doc/{slug}")
def get_doc(
    slug: str,
    lang: str = Query("ko"),
    viewer: Dict[str, Any] = Depends(get_viewer),
):
    """문서 단건. 안 보이는 문서는 404 다 — 403 으로 존재를 알리지 않는다."""
    doc = helpcenter_svc.get_doc(slug, viewer, lang=lang)
    if not doc:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다")
    return _ok(doc)


# ─────────────────────────────────────────────────────────────────────────
# O10 검색
# ─────────────────────────────────────────────────────────────────────────

@router.get("/search")
def search(
    q: str = Query(..., min_length=1, description="검색어"),
    ctx: Optional[str] = Query(None, description="현재 화면 page_slug — 결과 상단 고정에 쓴다"),
    types: Optional[str] = Query(None, description="문서 유형 쉼표 구분 (GUIDE,TROUBLE,FAQ,TASK,CONCEPT,POLICY)"),
    lang: str = Query("ko"),
    limit: int = Query(20, ge=1, le=_MAX_LIMIT),
    offset: int = Query(0, ge=0),
    viewer: Dict[str, Any] = Depends(get_viewer),
):
    """검색. role·sector·level 은 받지 않는다 — 서버가 토큰에서 도출한 값으로만 거른다."""
    type_list: Optional[List[str]] = None
    if types:
        type_list = [t.strip().upper() for t in types.split(",") if t.strip()]

    result = helpcenter_svc.search(
        q, viewer, ctx=ctx, types=type_list, lang=lang, limit=limit, offset=offset
    )
    helpcenter_svc.record_search(q, result.get("total", 0), ctx, viewer)
    return _ok(result)


# ─────────────────────────────────────────────────────────────────────────
# O11 화면 컨텍스트
# ─────────────────────────────────────────────────────────────────────────

@router.get("/context/{page_slug}")
def get_context(
    page_slug: str,
    lang: str = Query("ko"),
    viewer: Dict[str, Any] = Depends(get_viewer),
):
    """화면 하나의 도움말 묶음. 매핑이 없는 화면도 200 이며 found=false 로 알린다."""
    return _ok(helpcenter_svc.get_context(page_slug, viewer, lang=lang))


# ─────────────────────────────────────────────────────────────────────────
# O12 피드백
# ─────────────────────────────────────────────────────────────────────────

class FeedbackBody(BaseModel):
    doc_id: str
    verdict: str                      # UP | DOWN
    session_hash: str                 # 개인 식별자 대신 쓰는 익명 키
    block_id: Optional[str] = None
    reason_code: Optional[str] = None
    reason_text: Optional[str] = None
    ctx: Optional[str] = None
    referrer: Optional[str] = None


@router.post("/feedback")
def post_feedback(
    body: FeedbackBody,
    viewer: Dict[str, Any] = Depends(get_viewer),
):
    """도움됨/안됨 1건. 안 보이는 문서에는 남길 수 없다."""
    doc = helpcenter_svc.get_doc_by_id_for_viewer(body.doc_id, viewer)
    if not doc:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다")
    try:
        saved = helpcenter_svc.record_feedback(body.dict())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _ok({"recorded": saved.get("recorded", True), "doc_id": body.doc_id})
