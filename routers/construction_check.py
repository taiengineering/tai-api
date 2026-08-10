"""
건설 공정별 점검항목 조회 API — v1.0.0

/app/construction_inspect.html 에 하드코딩되어 있던 PROCESS_DATA(22건)를
construction_check_templates 테이블로 이관하고, 그 조회 경로를 제공한다.

API:
  GET /construction/check-templates            전 공정
  GET /construction/check-templates?process_key=temp&lang=vi

다국어는 테이블에 jsonb(name_i18n·desc_i18n·risk_i18n)로 담겨 있다.
서버가 lang 에 맞는 문자열을 골라 평탄화해서 내려준다. 프론트가 jsonb 를 직접
다루지 않아도 되고, 기존 PROCESS_DATA 구조(id·name·desc·risk)와 호환되어
프론트 수정 범위가 작다.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Query

from db.supabase_client import get_supabase

log = logging.getLogger(__name__)
router = APIRouter(tags=["ConstructionCheck"])

# 프론트 PROC_KEYS 와 동일한 순서. 화면 칩 배열에 쓰인다.
PROCESS_ORDER = ["temp", "earth", "struct", "finish", "mep"]

FALLBACK_LANG = "ko"


def _pick(i18n: Optional[dict], lang: str) -> str:
    """요청 언어 → ko 폴백 → 아무 값 순으로 고른다.

    번역이 아직 없는 언어라도 한국어라도 보여주는 편이 빈 화면보다 낫다.
    점검 항목이 비어 있으면 작업 전 점검 자체를 진행할 수 없기 때문이다.
    """
    if not i18n:
        return ""
    v = i18n.get(lang)
    if v:
        return v
    v = i18n.get(FALLBACK_LANG)
    if v:
        return v
    for val in i18n.values():
        if val:
            return val
    return ""


@router.get("/construction/check-templates")
def list_construction_check_templates(
    process_key: Optional[str] = Query(None, description="temp|earth|struct|finish|mep"),
    lang: str = Query("ko", description="ko|en|zh|vi|ne|km|tl"),
):
    """건설 공정별 점검항목 조회.

    반환 구조 — 프론트 PROCESS_DATA 와 호환:
    {
      "lang": "vi",
      "processes": [
        {"key":"temp","items":[{"id":"g1","name":"...","desc":"...","risk":"..."}, ...]},
        ...
      ]
    }
    """
    supabase = get_supabase()

    q = supabase.table("construction_check_templates").select("*").eq("is_active", True)
    if process_key:
        q = q.eq("process_key", process_key)
    res = q.order("process_key").order("item_seq").execute()
    rows = res.data or []

    grouped: dict = {}
    for r in rows:
        key = r["process_key"]
        grouped.setdefault(key, []).append({
            # 프론트는 item_code 를 결과 키로 쓴다. 이관 전 id(g1·t1…)와 동일하다.
            "id": r["item_code"],
            "name": _pick(r.get("name_i18n"), lang),
            "desc": _pick(r.get("desc_i18n"), lang),
            "risk": _pick(r.get("risk_i18n"), lang),
            "law_name": r.get("law_name"),
            "law_article": r.get("law_article"),
        })

    # 요청한 공정만 조회했더라도 PROCESS_ORDER 순서를 유지한다.
    order = [process_key] if process_key else PROCESS_ORDER
    processes = [{"key": k, "items": grouped.get(k, [])} for k in order if k in grouped]

    return {
        "status": "success",
        "data": {
            "lang": lang,
            "processes": processes,
            "total": sum(len(p["items"]) for p in processes),
        },
    }
