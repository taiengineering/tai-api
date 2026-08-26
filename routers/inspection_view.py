"""WP-PERSISTENCE-03 STEP-2 — 점검 결과 Web View read endpoint.

canonical runtime:
    authenticated caller
    → ownership/scope guard (_ensure_inspection_own)
    → READ-ONLY Composer (compose_inspection_view)
    → GENERAL View Model
    → HTTP response

invariant:
    - AUTH BEFORE COMPOSE: get_current_user → ownership guard → composer (순서 고정).
    - GET side effect = 0 (write/문서생성/PDF/storage 없음).
    - Composer domain 예외만 명시적 HTTP 변환; ownership guard 의 HTTPException 은 그대로 전파.
    - 내부 detail(UUID/schema 상태/table 이름 등) 을 public response 로 노출하지 않는다.
    - Composer(services/inspection_view_composer.py) 는 SEALED — 이 라우터는 조회 결과를 그대로 반환.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from routers.inspection_checklist import _ensure_inspection_own
from services.inspection_view_composer import (
    InspectionViewComposeError,
    compose_inspection_view,
)

router = APIRouter(
    prefix="/inspection",
    tags=["점검 결과 Web View"],
)

# Composer domain error → HTTP status.
# INSPECTION_NOT_FOUND 만 404; 그 외 domain-state 오류는 409(요청 형식이 아니라
# 현재 source/config/state 로 Web View 를 안전하게 구성할 수 없는 상태).
_NOT_FOUND_CODE = "INSPECTION_NOT_FOUND"


@router.get("/{inspection_id}/view")
async def get_inspection_view(
    inspection_id: str,
    current: dict = Depends(get_current_user),
):
    """점검 1건의 GENERAL presentation View Model 을 반환 (READ-ONLY).

    AUTH BEFORE COMPOSE. ownership guard 통과 후에만 Composer 를 호출한다.
    """
    sb = get_supabase()

    # 1) AUTH BEFORE COMPOSE — 미소유/미해소 row 는 여기서 404 로 은닉된다.
    _ensure_inspection_own(sb, inspection_id, current)

    # 2) READ-ONLY compose (동일 sb instance 재사용)
    try:
        return compose_inspection_view(inspection_id, supabase=sb)
    except InspectionViewComposeError as exc:
        if exc.code == _NOT_FOUND_CODE:
            raise HTTPException(
                status_code=404,
                detail={"code": _NOT_FOUND_CODE, "message": "점검 레코드를 찾을 수 없습니다."},
            )
        # 내부 exc.detail 은 노출하지 않는다 (code 만 전달).
        raise HTTPException(
            status_code=409,
            detail={"code": exc.code, "message": "점검 결과 화면을 구성할 수 없습니다."},
        )
