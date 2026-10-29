from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from db.supabase_client import get_supabase

log = logging.getLogger(__name__)


def list_document_forms(
    *,
    sector: Optional[str] = None,
    category: Optional[str] = None,
    tai_grade: Optional[str] = None,
    tab_type: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
) -> Dict[str, Any]:
    supabase = get_supabase()
    query = supabase.table("document_forms").select("*", count="exact").eq("is_active", True)

    if sector:
        query = query.eq("sector", sector)
    if category:
        query = query.eq("category", category)
    if tai_grade:
        query = query.eq("tai_grade", tai_grade.upper())
    if tab_type:
        query = query.eq("tab_type", tab_type)
    if search:
        q = search.replace(",", " ").strip()
        if q:
            query = query.or_(f"doc_name.ilike.%{q}%,law_ref.ilike.%{q}%,doc_id.ilike.%{q}%")

    page = max(1, int(page))
    per_page = max(1, min(200, int(per_page)))
    start = (page - 1) * per_page
    end = start + per_page - 1

    res = query.order("doc_id").range(start, end).execute()
    items = res.data or []
    _enrich_with_availability(supabase, items)
    return {
        "items": items,
        "total": int(res.count or 0),
        "page": page,
        "per_page": per_page,
    }


_APPROVED = "APPROVED_FOR_RUNTIME_USE"
_CANDIDATE = "CANDIDATE"


def _enrich_with_availability(supabase: Any, items: list[dict]) -> None:
    """Batch-enriches items with schema_availability. Mutates in place.

    Availability contract (mirrors catalog_resolver.py):
      APPROVED_FOR_RUNTIME_USE == 1  → READY_FOR_EDIT
      APPROVED_FOR_RUNTIME_USE > 1   → SCHEMA_ERROR (integrity violation, same policy as catalog_resolver)
      only CANDIDATE                 → PREPARING
      neither                        → NO_SCHEMA
      DB query failure               → NO_SCHEMA (fail-closed; never silently READY)
    """
    if not items:
        return

    catalog_ids = [item["id"] for item in items if item.get("id")]
    if not catalog_ids:
        for item in items:
            item["schema_availability"] = "NO_SCHEMA"
        return

    try:
        schema_rows = (
            supabase.table("runtime_form_schema")
            .select("catalog_document_id,status")
            .in_("catalog_document_id", catalog_ids)
            .in_("status", [_APPROVED, _CANDIDATE])
            .execute()
        ).data or []
    except Exception as exc:
        # DB query failure: distinct from "schema not yet created" — use SCHEMA_ERROR
        # so the frontend shows "상태 확인 불가" rather than "서식 미준비"
        log.warning("runtime_form_schema batch query failed — marking all as SCHEMA_ERROR: %s", exc)
        for item in items:
            item["schema_availability"] = "SCHEMA_ERROR"
        return

    approved_map: dict[str, int] = {}
    candidate_count_map: dict[str, int] = {}
    for s in schema_rows:
        cid = s["catalog_document_id"]
        if s["status"] == _APPROVED:
            approved_map[cid] = approved_map.get(cid, 0) + 1
        elif s["status"] == _CANDIDATE:
            candidate_count_map[cid] = candidate_count_map.get(cid, 0) + 1

    for item in items:
        cid = item.get("id")
        acount = approved_map.get(cid, 0)
        ccount = candidate_count_map.get(cid, 0)
        if acount > 1:
            item["schema_availability"] = "SCHEMA_ERROR"
        elif acount == 1:
            item["schema_availability"] = "READY_FOR_EDIT"
        elif ccount > 0:
            item["schema_availability"] = "PREPARING"
        else:
            item["schema_availability"] = "NO_SCHEMA"


def get_document_form(doc_id: str) -> Dict[str, Any]:
    supabase = get_supabase()
    res = (
        supabase.table("document_forms")
        .select("*")
        .eq("doc_id", doc_id)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail=f"document form not found: {doc_id}")
    return res.data[0]


def get_document_forms_stats() -> Dict[str, Any]:
    supabase = get_supabase()
    res = (
        supabase.table("document_forms")
        .select("sector,tai_grade,tab_type")
        .eq("is_active", True)
        .execute()
    )
    rows = res.data or []

    by_sector: Dict[str, int] = {}
    by_grade: Dict[str, int] = {}
    by_tab: Dict[str, int] = {}
    for r in rows:
        s = (r.get("sector") or "").strip() or "UNKNOWN"
        g = (r.get("tai_grade") or "").strip().upper() or "X"
        t = (r.get("tab_type") or "").strip() or "UNKNOWN"
        by_sector[s] = by_sector.get(s, 0) + 1
        by_grade[g] = by_grade.get(g, 0) + 1
        by_tab[t] = by_tab.get(t, 0) + 1

    return {
        "total": len(rows),
        "by_sector": by_sector,
        "by_grade": by_grade,
        "by_tab": by_tab,
    }


# ---------------------------------------------------------------------------
# WO-DOC260-SHARED-ARTICLE-READ-019  (R1 보정: 운영 DB 스키마 정합)
# ---------------------------------------------------------------------------

# field_rule_mapping.review_status 값 중 법적 확정으로 인정되는 상태.
# ACTIVE/CONFIRMED 임의 포함 금지 — 실제 PRJ 승인 계약 기준만 인정.
_CONFIRMED_STATUSES = frozenset({"APPROVED"})


def get_document_form_articles(
    doc_id: str,
    include_pending: bool = False,
) -> Dict[str, Any]:
    """서식별 연결 조문 조회 (field_rule_mapping → law_article).

    field_rule_mapping 실제 컬럼: doc_id / field_key / article_id / review_status.
    동일 article_id 중복 제거. PENDING → is_confirmed=False.
    is_confirmed=True 조건: 해당 article_id의 모든 매핑이 APPROVED인 경우만.
    고시 제6조 자동 추론 금지.
    """
    supabase = get_supabase()

    # 1. doc_id 유효성 확인
    form_res = (
        supabase.table("document_forms")
        .select("id, doc_id, doc_name")
        .eq("doc_id", doc_id)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )
    if not form_res.data:
        raise HTTPException(status_code=404, detail=f"document form not found: {doc_id}")
    form_row = form_res.data[0]

    # 2. field_rule_mapping 조회 (doc_id 기반 단일 경로, UUID fallback 없음)
    r = (
        supabase.table("field_rule_mapping")
        .select("field_key, article_id, review_status")
        .eq("doc_id", doc_id)
        .execute()
    )
    all_raw_rows: List[Dict[str, Any]] = r.data or []

    # 3. PENDING 필터 전 raw 상태 보존 (gap 판정용)
    if not include_pending:
        frm_rows = [m for m in all_raw_rows if m.get("review_status") in _CONFIRMED_STATUSES]
    else:
        frm_rows = all_raw_rows

    # 4. article_id → field_keys / statuses 수집 (중복 제거)
    article_id_to_fields: Dict[str, List[str]] = {}
    article_id_to_statuses: Dict[str, List[str]] = {}
    for m in frm_rows:
        aid = m.get("article_id")
        if not aid:
            continue
        fk = m.get("field_key") or ""
        status = m.get("review_status") or "UNKNOWN"
        article_id_to_fields.setdefault(aid, [])
        if fk and fk not in article_id_to_fields[aid]:
            article_id_to_fields[aid].append(fk)
        article_id_to_statuses.setdefault(aid, []).append(status)

    # 5. law_article 조회 (DELETED + is_deleted_in_version 제외)
    articles_out: List[Dict[str, Any]] = []
    mapping_gaps: List[str] = []

    unique_article_ids = list(article_id_to_fields.keys())

    if unique_article_ids:
        art_res = (
            supabase.table("law_article")
            .select(
                "id, law_id, article_no, article_title, article_text, "
                "article_internal_key, enforcement_date, article_status_code, "
                "is_deleted_in_version"
            )
            .in_("id", unique_article_ids)
            .neq("article_status_code", "DELETED")
            .eq("is_deleted_in_version", False)
            .execute()
        )
        fetched = {a["id"]: a for a in (art_res.data or [])}

        # 6. law_master 조회
        law_ids = list({a["law_id"] for a in fetched.values() if a.get("law_id")})
        law_map: Dict[str, Dict] = {}
        if law_ids:
            lm_res = (
                supabase.table("law_master")
                .select("id, law_name, law_number, enforcement_date")
                .in_("id", law_ids)
                .execute()
            )
            law_map = {lm["id"]: lm for lm in (lm_res.data or [])}

        for aid in unique_article_ids:
            art = fetched.get(aid)
            if not art:
                continue
            lm = law_map.get(art.get("law_id") or "")
            statuses = article_id_to_statuses.get(aid, [])
            # 보수적 확정 판정: 모든 매핑이 APPROVED인 경우만 True
            is_confirmed = bool(statuses) and all(s in _CONFIRMED_STATUSES for s in statuses)
            mapping_status = "APPROVED" if is_confirmed else (statuses[0] if statuses else "UNKNOWN")
            articles_out.append({
                "law_article_id":           aid,
                "field_keys":               article_id_to_fields.get(aid, []),
                "mapping_status":           mapping_status,
                "is_confirmed":             is_confirmed,
                "law_name":                 (lm or {}).get("law_name") or "",
                "law_number":               (lm or {}).get("law_number") or "",
                "law_enforcement_date":     str((lm or {}).get("enforcement_date") or ""),
                "article_no":               art.get("article_no"),
                "article_internal_key":     art.get("article_internal_key") or "",
                "article_title":            art.get("article_title") or "",
                "article_text":             art.get("article_text") or "",
                "article_enforcement_date": str(art.get("enforcement_date") or ""),
            })

    # 7. MAPPING_GAP 감지: raw 매핑이 있으나 articles_out에 포함되지 않은 경우
    # 하드코딩 금지 — 실제 매핑 데이터 기반으로만 판정
    confirmed_ids = {a["law_article_id"] for a in articles_out}
    raw_excluded: Dict[str, List[str]] = {}
    for m in all_raw_rows:
        aid = m.get("article_id")
        if aid and aid not in confirmed_ids:
            raw_excluded.setdefault(aid, []).append(m.get("review_status") or "UNKNOWN")

    for aid, statuses in raw_excluded.items():
        if all(s == "PENDING" for s in statuses):
            fks = sorted({m.get("field_key") for m in all_raw_rows if m.get("article_id") == aid})
            mapping_gaps.append(
                f"article_id={aid} field_keys={fks}: "
                f"PENDING 매핑만 존재 — 법적 미확정 (UNCONFIRMED_MAPPING)"
            )

    return {
        "doc_id": doc_id,
        "doc_name": form_row.get("doc_name") or "",
        "articles": articles_out,
        "article_count": len(articles_out),
        "mapping_gaps": mapping_gaps,
        "include_pending": include_pending,
    }
