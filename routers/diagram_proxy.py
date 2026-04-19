"""
diagram_proxy.py v1.0.0
Supabase Storage 한글 파일명 CDN 503 문제 우회
Python supabase-py로 직접 다운로드 후 SVG 반환
GET /api/v1/diagrams/{number}  -> SVG 스트림
GET /api/v1/diagrams/          -> 전체 목록 JSON
"""

import os
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from supabase import create_client, Client

router = APIRouter(prefix="/diagrams", tags=["diagrams"])

# 1-25 번호 -> 한글 파일명 매핑
DIAGRAM_FILES: dict[int, str] = {
    1:  "01-\uc911\ub300\uc7ac\ud574\ucc98\ubc8c\ubc95-\uc801\uc6a9-\ud750\ub984\ub3c4.svg",
    2:  "02-\uc0b0\uc5c5\uc548\uc804\ubcf4\uac74\ubc95-\uc758\ubb34-\uacc4\uce35\ub3c4.svg",
    3:  "03-\uac74\ucd95\ubb3c\uad00\ub9ac\ubc95-\uc801\uc6a9-\ubc94\uc704.svg",
    4:  "04-\uac74\uc124\ud604\uc7a5-3\ubc95-\ube44\uad50\ud45c.svg",
    5:  "05-\ud655\ub300\uc801\uc6a9-\ud0c0\uc784\ub77c\uc778.svg",
    6:  "06-\uacfc\ud0dc\ub8cc-\ubc8c\uce59-\uad6c\uc870.svg",
    7:  "07-\uacbd\uc601\ucc45\uc784\uc790-9\ub300\uc758\ubb34.svg",
    8:  "08-\uc548\uc804\uad00\ub9ac\uc790-\uc120\uc784\uae30\uc900.svg",
    9:  "09-\uad00\ub9ac\ucc45\uc784\uc790-\uccb4\uacc4\ub3c4.svg",
    10: "10-\uc548\uc804\ubcf4\uac74\uad00\ub9ac\uccb4\uc81c-\uad6c\ucd95\uc694\uac74.svg",
    11: "11-\uc5c5\ubb34\ubd84\uc0b0-\ube44\ud3ec\uc560\ud504\ud130.svg",
    12: "12-\uc804\ubb38\uae30\uad00\uc704\ud0c1-vs-\uc790\uccb4\uc120\uc784.svg",
    13: "13-\uc124\ube44-\uc815\uae30\uac80\uc0ac-\uc8fc\uae30.svg",
    14: "14-PTW-\ubc1c\uae09-\ud504\ub85c\uc138\uc2a4.svg",
    15: "15-TBM-\uc9c4\ud589-\ud50c\ub85c\uc6b0.svg",
    16: "16-\uc704\ud5d8\uc131\ud3c9\uac00-5\ub2e8\uacc4.svg",
    17: "17-\uc791\uc5c5\uc911\uc9c0-\ud310\ub2e8\uae30\uc900.svg",
    18: "18-\ud2b9\uc218\ud2b9\ubcc4\uad50\uc721-\ub9e4\ud2b8\ub9ad\uc2a4.svg",
    19: "19-\uac74\ubb3c-\ub178\ud6c4\ub3c4\ubcc4-\uc810\uac80\uc758\ubb34.svg",
    20: "20-\uc18c\ubc29\uc2dc\uc124-\uc790\uccb4\uc810\uac80-\uc77c\uc815.svg",
    21: "21-\uc11d\uba74\uc870\uc0ac-\ub300\uc0c1\ud310\uc815.svg",
    22: "22-\uc2b9\uac15\uae30-\ubcf4\uc77c\ub7ec-\uc555\ub825\uc6a9\uae30-\uac80\uc0ac\uc8fc\uae30.svg",
    23: "23-TAI-ROI-\ube44\uad50.svg",
    24: "24-TAI-\ub3c4\uc785-4\ub2e8\uacc4.svg",
    25: "25-\uc548\uc804\uad00\ub9ac-\ubd84\uc0b0\uad6c\uc870\ub3c4.svg",
}


def _get_supabase() -> Client:
    url = os.environ["SUPABASE_URL"]
    key = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ["SUPABASE_KEY"]
    return create_client(url, key)


@router.get("/", summary="다이어그램 목록")
async def list_diagrams():
    """diagram_templates 테이블 전체 목록 반환"""
    sb = _get_supabase()
    res = sb.table("diagram_templates").select(
        "diagram_number,title_ko,diagram_type,sector_filter,is_default,usage_locations"
    ).order("diagram_number").execute()
    return {"diagrams": res.data}


@router.get("/{number}", summary="SVG 다이어그램 스트림")
async def get_diagram_svg(number: int):
    """
    다이어그램 번호(1-25)로 SVG 파일 직접 반환.
    Supabase Storage 한글 파일명 CDN 503 우회.
    """
    filename = DIAGRAM_FILES.get(number)
    if not filename:
        raise HTTPException(status_code=404, detail=f"diagram {number} not found")

    try:
        sb = _get_supabase()
        data: bytes = sb.storage.from_("diagrams").download(filename)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Storage error: {str(e)}")

    return Response(
        content=data,
        media_type="image/svg+xml",
        headers={
            "Cache-Control": "public, max-age=86400",
            "Access-Control-Allow-Origin": "*",
            "Content-Disposition": "inline",
        },
    )
