"""
소방청 국가 위험물 정보 조회 라우터 — v1.0.0
prefix: /fire-hazmat

대상 외부 API: apis.data.go.kr/1661000/materialInfoSvc
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import os
import asyncio
import json

from services.kr_public_api import kr_get

router = APIRouter(prefix="/fire-hazmat", tags=["소방청위험물"])

VERSION = "1.0.0"
SERVICE_KEY = os.getenv(
    "FIRE_SERVICE_KEY",
    os.getenv("BUILDING_API_KEY", "da4e826323c2c9fef9f325bd4e39a3765d06ac1b582695bcbc475bc0a076255b")
)
FIRE_BASE = "https://apis.data.go.kr/1661000/materialInfoSvc"


async def _fire_get(path: str, params: dict) -> dict:
    params["serviceKey"] = SERVICE_KEY
    params.setdefault("type", "json")
    try:
        _st, _tx = await asyncio.to_thread(kr_get, f"{FIRE_BASE}/{path}", params=params, timeout=15)
        if _st >= 400:
            raise HTTPException(status_code=502, detail=f"소방청 위험물 API HTTP {_st}")
        try:
            return json.loads(_tx)
        except Exception:
            return {"raw": _tx[:3000]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"소방청 API 연결 실패: {str(e)}")


# ─────────────────────────────────────────────────────
# GET /fire-hazmat/materials  위험물 리스트
# ─────────────────────────────────────────────────────
@router.get("/materials")
async def list_hazmat_materials(
    material_nm:  Optional[str] = Query(None, description="위험물명 검색"),
    category:     Optional[str] = Query(None, description="위험물 유형 (제1류~제6류)"),
    page_no:      int = Query(1,  ge=1),
    num_of_rows:  int = Query(10, ge=1, le=100),
):
    """
    소방청 국가 위험물 정보 목록 조회.
    위험물명, 유형, CAS번호, 세부 정보 제공.
    """
    params: dict = {"pageNo": page_no, "numOfRows": num_of_rows}
    if material_nm: params["materialNm"] = material_nm
    if category:    params["category"]   = category

    result = await _fire_get("getMaterialList", params)
    return {"status": "success", "data": result}


# ─────────────────────────────────────────────────────
# GET /fire-hazmat/materials/{material_id}  위험물 상세
# ─────────────────────────────────────────────────────
@router.get("/materials/{material_id}")
async def get_hazmat_material(material_id: str):
    """
    위험물 ID로 상세 정보 조회.
    장미도명스트리등, 연소범위, 비등점, 안전대리방법 등 제공.
    """
    result = await _fire_get("getMaterialInfo", {"materialId": material_id})
    return {"status": "success", "data": result}
