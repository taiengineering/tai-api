"""
엔진 법규 마스터 화면용 API — v1.0.0

GET /engine-legal/stats
GET /engine-legal/laws
GET /engine-legal/laws/{law_id}
GET /engine-legal/rules
GET /engine-legal/rules/{rule_id}
GET /engine-legal/appendix
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from db.supabase_client import get_supabase

router = APIRouter(prefix="/engine-legal", tags=["엔진법규"])
VERSION = "1.0.0"

LAW_TYPE_LABEL = {
    "LAW": "법률",
    "ENFORCEMENT_DECREE": "시행령",
    "ENFORCEMENT_RULE": "시행규칙",
    "NOTICE": "고시·훈령",
    "STANDARD": "기술기준",
    "OTHER": "기타",
}

APPENDIX_DOMAIN_ALIASES: Dict[str, str] = {
    "safety_cert": "SAFETY_CERT",
    "hazmat": "HAZMAT",
    "appointment": "APPOINTMENT",
    "legal_inspection": "STATUTORY_INSPECTION",
}


def _chunked(ids: List[str], size: int = 400) -> List[List[str]]:
    return [ids[i : i + size] for i in range(0, len(ids), size)]


@router.get("/stats")
async def engine_legal_stats():
    """전체 법령수 / 조문수 / 판정룰수 / 미매핑룰수"""
    supabase = get_supabase()
    try:
        lm = (
            supabase.table("law_master")
            .select("id", count="exact")
            .eq("is_active", True)
            .execute()
        )
        la = supabase.table("law_article").select("id", count="exact").execute()
        ru = (
            supabase.table("master_building_legal_rules")
            .select("id", count="exact")
            .eq("is_active", True)
            .execute()
        )

        masters = supabase.table("law_master").select("law_name").eq("is_active", True).execute()
        name_set = {r["law_name"] for r in (masters.data or []) if r.get("law_name")}

        rules_rows = (
            supabase.table("master_building_legal_rules")
            .select("law_name,sector,obligation_type,form_code")
            .eq("is_active", True)
            .execute()
        )
        unmapped = 0
        sector_cnt: dict = {}
        type_cnt: dict = {}
        form_unmapped = 0
        for r in rules_rows.data or []:
            ln = (r.get("law_name") or "").strip()
            if ln and ln not in name_set:
                unmapped += 1
            s = r.get("sector") or "UNKNOWN"
            sector_cnt[s] = sector_cnt.get(s, 0) + 1
            ot = r.get("obligation_type") or "OTHER"
            type_cnt[ot] = type_cnt.get(ot, 0) + 1
            if ot in ("REPORT", "NOTIFY") and not (r.get("form_code") or "").strip():
                form_unmapped += 1

        return {
            "status": "success",
            "data": {
                "total_laws": lm.count or 0,
                "total_articles": la.count or 0,
                "total_rules": ru.count or 0,
                "unmapped_rules": unmapped,
                "rules_by_sector": sector_cnt,
                "rules_by_type": type_cnt,
                "form_unmapped": form_unmapped,
                "version": VERSION,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/laws")
async def engine_legal_laws(
    law_type: Optional[str] = Query(None, description="LAW | ENFORCEMENT_DECREE | ENFORCEMENT_RULE ..."),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    supabase = get_supabase()
    offset = (page - 1) * page_size
    try:
        q = (
            supabase.table("law_master")
            .select(
                "id, law_name, law_name_short, law_type_code, ministry_name, "
                "current_version_id, announcement_date, enforcement_date",
                count="exact",
            )
            .eq("is_active", True)
        )
        if law_type:
            q = q.eq("law_type_code", law_type)
        if search:
            q = q.ilike("law_name", f"%{search.strip()}%")
        q = q.order("law_name").range(offset, offset + page_size - 1)
        res = q.execute()
        rows = res.data or []
        total = res.count or 0

        version_ids = [r["current_version_id"] for r in rows if r.get("current_version_id")]
        article_counts: Dict[str, int] = defaultdict(int)
        hang_counts: Dict[str, int] = defaultdict(int)

        if version_ids:
            all_arts: List[Dict[str, Any]] = []
            for part in _chunked([str(v) for v in version_ids]):
                ar = (
                    supabase.table("law_article")
                    .select("id, law_version_id")
                    .in_("law_version_id", part)
                    .execute()
                )
                all_arts.extend(ar.data or [])

            for a in all_arts:
                vid = str(a.get("law_version_id") or "")
                article_counts[vid] += 1

            art_ids = [a["id"] for a in all_arts if a.get("id")]
            para_cnt_by_article: Dict[str, int] = defaultdict(int)
            for chunk in _chunked(art_ids):
                pr = (
                    supabase.table("law_paragraph")
                    .select("article_id")
                    .in_("article_id", chunk)
                    .execute()
                )
                for p in pr.data or []:
                    aid = str(p.get("article_id") or "")
                    para_cnt_by_article[aid] += 1

            art_by_version: Dict[str, List[str]] = defaultdict(list)
            for a in all_arts:
                vid = str(a.get("law_version_id") or "")
                if a.get("id"):
                    art_by_version[vid].append(str(a["id"]))

            for vid, aids in art_by_version.items():
                hang_counts[vid] = sum(para_cnt_by_article.get(aid, 0) for aid in aids)

        items = []
        for r in rows:
            vid = r.get("current_version_id")
            vs = str(vid) if vid else ""
            lt = r.get("law_type_code") or ""
            items.append(
                {
                    **r,
                    "law_type_label": LAW_TYPE_LABEL.get(lt, lt or "-"),
                    "article_count": article_counts.get(vs, 0),
                    "hang_count": hang_counts.get(vs, 0),
                }
            )

        return {
            "status": "success",
            "data": {"items": items, "total": total, "page": page, "page_size": page_size},
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/laws/{law_id}")
async def engine_legal_law_detail(law_id: str):
    supabase = get_supabase()
    try:
        res = (
            supabase.table("law_master")
            .select("*")
            .eq("id", law_id)
            .single()
            .execute()
        )
        if not res.data:
            raise HTTPException(status_code=404, detail="법령을 찾을 수 없습니다.")
        row = res.data
        lt = row.get("law_type_code") or ""
        row["law_type_label"] = LAW_TYPE_LABEL.get(lt, lt or "-")
        vid = row.get("current_version_id")
        if vid:
            ac = (
                supabase.table("law_article")
                .select("id", count="exact")
                .eq("law_version_id", str(vid))
                .execute()
            )
            row["article_count"] = ac.count or 0
            arts = (
                supabase.table("law_article")
                .select("id")
                .eq("law_version_id", str(vid))
                .execute()
            )
            aids = [a["id"] for a in (arts.data or [])]
            hang = 0
            for chunk in _chunked(aids):
                pc = (
                    supabase.table("law_paragraph")
                    .select("id", count="exact")
                    .in_("article_id", chunk)
                    .execute()
                )
                hang += pc.count or 0
            row["hang_count"] = hang
        else:
            row["article_count"] = 0
            row["hang_count"] = 0
        return {"status": "success", "data": row}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rules")
async def engine_legal_rules(
    sector: Optional[str] = Query(None),
    obligation_type: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=200),
):
    supabase = get_supabase()
    offset = (page - 1) * page_size
    try:
        q = (
            supabase.table("master_building_legal_rules")
            .select(
                "id, rule_id, law_name, law_article, sector, diagnosis_stage, "
                "obligation_summary, obligation_type, report_required, "
                "appointment_required, inspection_required, action_required, is_active",
                count="exact",
            )
            .eq("is_active", True)
        )
        if sector:
            q = q.eq("sector", sector.strip().upper())
        if obligation_type:
            q = q.eq("obligation_type", obligation_type.strip().upper())
        if search:
            pat = f"%{search.strip()}%"
            q = q.or_(f"law_name.ilike.{pat},rule_id.ilike.{pat},obligation_summary.ilike.{pat}")
        q = q.order("sector").order("rule_id").range(offset, offset + page_size - 1)
        res = q.execute()
        return {
            "status": "success",
            "data": {
                "items": res.data or [],
                "total": res.count or 0,
                "page": page,
                "page_size": page_size,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rules/by-code/{rule_code}")
async def engine_legal_rule_by_code(rule_code: str):
    """rule_id(코드)로 판정룰 상세"""
    supabase = get_supabase()
    try:
        res = (
            supabase.table("master_building_legal_rules")
            .select("*")
            .eq("rule_id", rule_code)
            .limit(1)
            .execute()
        )
        rows = res.data or []
        if not rows:
            raise HTTPException(status_code=404, detail="판정룰을 찾을 수 없습니다.")
        return {"status": "success", "data": rows[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rules/row/{row_id}")
async def engine_legal_rule_by_row_id(row_id: str):
    """master_building_legal_rules.id(UUID)로 상세"""
    supabase = get_supabase()
    try:
        res = (
            supabase.table("master_building_legal_rules")
            .select("*")
            .eq("id", row_id)
            .single()
            .execute()
        )
        if not res.data:
            raise HTTPException(status_code=404, detail="판정룰을 찾을 수 없습니다.")
        return {"status": "success", "data": res.data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/appendix")
async def engine_legal_appendix(
    domain_key: Optional[str] = Query(
        None,
        description="safety_cert | hazmat | appointment | legal_inspection 또는 legal_obligations.domain",
    ),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    """legal_obligations 기반 별표·의무 현황 (도메인별)"""
    supabase = get_supabase()
    offset = (page - 1) * page_size
    try:
        q = supabase.table("legal_obligations").select("*", count="exact")
        if domain_key:
            dk = APPENDIX_DOMAIN_ALIASES.get(domain_key.strip().lower(), domain_key.strip())
            q = q.eq("domain", dk)
        if search:
            pat = f"%{search.strip()}%"
            q = q.or_(f"obligation_name.ilike.{pat},legal_basis.ilike.{pat},category_code.ilike.{pat}")
        q = q.order("category_code").range(offset, offset + page_size - 1)
        res = q.execute()
        return {
            "status": "success",
            "data": {
                "items": res.data or [],
                "total": res.count or 0,
                "page": page,
                "page_size": page_size,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/appendix/{item_id}")
async def engine_legal_appendix_detail(item_id: str):
    supabase = get_supabase()
    try:
        res = (
            supabase.table("legal_obligations")
            .select("*")
            .eq("id", item_id)
            .single()
            .execute()
        )
        if not res.data:
            raise HTTPException(status_code=404, detail="항목을 찾을 수 없습니다.")
        return {"status": "success", "data": res.data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
