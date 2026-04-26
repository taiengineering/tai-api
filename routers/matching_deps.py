"""매칭 라우터 공통 Depends (서비스 계층으로 옮기지 않음)."""
from __future__ import annotations

from fastapi import Depends, HTTPException

from routers.auth import get_current_user


def _require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("role_code") != "001":
        raise HTTPException(status_code=403, detail="어드민만 접근 가능합니다.")
    return current_user
