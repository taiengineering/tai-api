"""
diagram_proxy.py v1.0.1
Supabase Storage 한글 파일명 CDN 503 문제 우회
Python supabase-py로 직접 다운로드 후 SVG 반환
GET /api/v1/diagrams/{number}  -> SVG 스트림
GET /api/v1/diagrams/          -> 전체 목록 JSON
v1.0.1: dict[int,str] -> Dict[int,str] (Python 3.8 호환)
"""

import os
from typing import Dict
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from supabase import create_client

router = APIRouter(prefix="/diagrams", tags=["diagrams"])

# 1-25 번호 -> 한글 파일명 매핑
DIAGRAM_FILES: Dict[int, str] = {
    1:  "01-중대재해처벌법-적용-흐름도.svg",
    2:  "02-산업안전보건법-의무-계층도.svg",
    3:  "03-건축물관리법-적용-범위.svg",
    4:  "04-건설현장-3법-비교표.svg",
    5:  "05-확대적용-타임라인.svg",
    6:  "06-과태료-벌칙-구조.svg",
    7:  "07-경영책임자-9대의무.svg",
    8:  "08-안전관리자-선임기준.svg",
    9:  "09-관리책임자-체계도.svg",
    10: "10-안전보건관리체제-구축요건.svg",
    11: "11-업무분산-비포애프터.svg",
    12: "12-전문기관위탁-vs-자체선임.svg",
    13: "13-설비-정기검사-주기.svg",
    14: "14-PTW-발급-프로세스.svg",
    15: "15-TBM-진행-플로우.svg",
    16: "16-위험성평가-5단계.svg",
    17: "17-작업중지-판단기준.svg",
    18: "18-특수특별교육-매트릭스.svg",
    19: "19-건물-노후도별-점검의무.svg",
    20: "20-소방시설-자체점검-일정.svg",
    21: "21-석면조사-대상판정.svg",
    22: "22-승강기-보일러-압력용기-검사주기.svg",
    23: "23-TAI-ROI-비교.svg",
    24: "24-TAI-도입-4단계.svg",
    25: "25-안전관리-분산구조도.svg",
}


def _get_supabase():
    url = os.environ["SUPABASE_URL"]
    key = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ["SUPABASE_KEY"]
    return create_client(url, key)


@router.get("/", summary="다이어그램 목록")
async def list_diagrams():
    """diagram_templates 테이블 전체 목록 반환"""
    sb = _get_supabase()
    res = (
        sb.table("diagram_templates")
        .select("diagram_number,title_ko,diagram_type,sector_filter,is_default,usage_locations")
        .order("diagram_number")
        .execute()
    )
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
