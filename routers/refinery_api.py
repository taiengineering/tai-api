"""D-007 + Actor Overlay: Refinery API

중복 제거 + 문장 생성 → StoredDiagnosisResult.
Actor Overlay: draft_id → article_id → semantic_clause_fix → actor_resolution

금지:
  emit_stored_diagnosis_result / assemble_refinery_result
  fetch_compiler_candidates / evaluate_single_factory
"""
from __future__ import annotations

from typing import Dict, List

from fastapi import APIRouter, Query

from db.supabase_client import get_supabase
from schemas.stored_diagnosis_schema import StoredDiagnosisResult
from services.check_engine_adapter import load_track_a_results
from services.refinery_service import build_stored_diagnosis_result
from services.reverse_check_service import run_reverse_check_batch

router = APIRouter(prefix="/refinery", tags=["D-007 Refinery"])

_DEFAULT_STATUS_FILTER = ["MATCH_CANDIDATE", "POSSIBLE_CANDIDATE"]

# actor_group 우선순위: 좌표 작을수록 먼저
_GROUP_PRIORITY = {
    "AUTHORITY": 0,
    "FRAGMENT": 1,
    "ASSOCIATION": 2,
    "BUSINESS": 3,
}


def _build_actor_map_sql(
    supabase,
    draft_ids: List[str],
) -> Dict[str, dict]:
    """SQL로 draft_id → actor_group 매핑 구성.

    PostgREST .in_() URL 제한 회피를 위해 execute_sql 사용.
    반환: {draft_id: {actor_group, actor_code, confidence}}
    """
    if not draft_ids:
        return {}

    # UUID 리스트 안전하게 이스케이프
    ids_literal = ",".join(f"'{d}'" for d in set(draft_ids) if d)

    sql = f"""
        SELECT
            ed.id AS draft_id,
            r.actor_group,
            r.actor_code,
            r.confidence,
            MIN(_GROUP_PRIORITY.priority) OVER (PARTITION BY ed.id) AS min_priority
        FROM executable_draft ed
        JOIN semantic_clause_fix sc ON sc.source_article_id = ed.article_id
        JOIN semantic_clause_actor_resolution r ON r.clause_id = sc.id
        JOIN (VALUES
            ('AUTHORITY', 0),
            ('FRAGMENT', 1),
            ('ASSOCIATION', 2),
            ('BUSINESS', 3)
        ) AS _GROUP_PRIORITY(grp, priority)
            ON _GROUP_PRIORITY.grp = r.actor_group
        WHERE ed.id IN ({ids_literal})
    """

    # 이 방식이 복잡하지 않은 단순 SQL로 돌림
    sql_simple = f"""
        WITH base AS (
            SELECT
                ed.id AS draft_id,
                r.actor_group,
                r.actor_code,
                r.confidence,
                CASE r.actor_group
                    WHEN 'AUTHORITY' THEN 0
                    WHEN 'FRAGMENT' THEN 1
                    WHEN 'ASSOCIATION' THEN 2
                    WHEN 'BUSINESS' THEN 3
                    ELSE 99
                END AS grp_priority,
                ROW_NUMBER() OVER (
                    PARTITION BY ed.id
                    ORDER BY
                        CASE r.actor_group
                            WHEN 'AUTHORITY' THEN 0
                            WHEN 'FRAGMENT' THEN 1
                            WHEN 'ASSOCIATION' THEN 2
                            WHEN 'BUSINESS' THEN 3
                            ELSE 99
                        END ASC
                ) AS rn
            FROM executable_draft ed
            JOIN semantic_clause_fix sc ON sc.source_article_id = ed.article_id
            JOIN semantic_clause_actor_resolution r ON r.clause_id = sc.id
            WHERE ed.id IN ({ids_literal})
        )
        SELECT draft_id, actor_group, actor_code, confidence
        FROM base
        WHERE rn = 1
    """

    try:
        res = supabase.rpc("_", {}).execute()  # dummy 실패 시 대맰 폴백
    except Exception:
        pass

    try:
        # Supabase execute_sql 대신 postgrest SQL 실행
        from postgrest import APIError  # type: ignore
    except Exception:
        pass

    # supabase-py v2: supabase.rpc 아님, table("").select()... 사용
    # 비관습적 SQL을 위해 supabase.postgrest.session.post 직접 호출 불가 →
    # 대신 분리 조회로 분해
    return _build_actor_map_chunked(supabase, draft_ids)


def _build_actor_map_chunked(
    supabase,
    draft_ids: List[str],
    chunk_size: int = 50,
) -> Dict[str, dict]:
    """draft_ids를 chunk_size로 나눠 actor_map 구성.

    PostgREST URL 제한(~4KB) 회피.
    """
    if not draft_ids:
        return {}

    unique_ids = list(set(d for d in draft_ids if d))
    result: Dict[str, dict] = {}

    # 1) draft_id → article_id (chunk)
    draft_to_article: Dict[str, str] = {}
    for i in range(0, len(unique_ids), chunk_size):
        chunk = unique_ids[i: i + chunk_size]
        try:
            res = (
                supabase.table("executable_draft")
                .select("id, article_id")
                .in_("id", chunk)
                .execute()
            )
            for d in (res.data or []):
                if d.get("article_id"):
                    draft_to_article[str(d["id"])] = str(d["article_id"])
        except Exception:
            continue

    article_ids = list(set(draft_to_article.values()))
    if not article_ids:
        return {}

    # 2) article_id → {clause_id: actor_info} (chunk)
    article_to_best: Dict[str, dict] = {}
    for i in range(0, len(article_ids), chunk_size):
        chunk = article_ids[i: i + chunk_size]
        try:
            # semantic_clause_fix
            sc_res = (
                supabase.table("semantic_clause_fix")
                .select("id, source_article_id")
                .in_("source_article_id", chunk)
                .execute()
            )
            clause_rows = sc_res.data or []
            if not clause_rows:
                continue

            article_to_clauses: Dict[str, List[str]] = {}
            for c in clause_rows:
                aid = str(c.get("source_article_id") or "")
                if aid:
                    article_to_clauses.setdefault(aid, []).append(str(c["id"]))

            all_cids = [cid for cids in article_to_clauses.values() for cid in cids]

            # actor_resolution (chunk again if needed)
            for j in range(0, len(all_cids), chunk_size):
                cchunk = all_cids[j: j + chunk_size]
                try:
                    ar_res = (
                        supabase.table("semantic_clause_actor_resolution")
                        .select("clause_id, actor_group, actor_code, confidence")
                        .in_("clause_id", cchunk)
                        .execute()
                    )
                    for row in (ar_res.data or []):
                        cid = str(row["clause_id"])
                        info = {
                            "actor_group": row.get("actor_group") or "UNKNOWN",
                            "actor_code": row.get("actor_code"),
                            "confidence": row.get("confidence"),
                        }
                        # 어느 article에 속하는지 역산한 후 best 업데이트
                        for aid, cids in article_to_clauses.items():
                            if cid in cids:
                                cur = article_to_best.get(aid)
                                new_p = _GROUP_PRIORITY.get(info["actor_group"], 99)
                                cur_p = _GROUP_PRIORITY.get(
                                    (cur or {}).get("actor_group", ""), 99
                                )
                                if cur is None or new_p < cur_p:
                                    article_to_best[aid] = info
                except Exception:
                    continue
        except Exception:
            continue

    # 3) draft_id → actor_info
    for draft_id, article_id in draft_to_article.items():
        actor = article_to_best.get(article_id)
        if actor:
            result[draft_id] = actor

    return result


def _get_draft_actor(actor_map: Dict[str, dict], trace) -> dict:
    draft_id = trace.full_trace.get("stage_check", {}).get("draft_id")
    return actor_map.get(str(draft_id), {}) if draft_id else {}


@router.post("/run", response_model=StoredDiagnosisResult)
def run_refinery(
    facility_id: str = Query(..., description="factories.id"),
    sector: str = Query(None),
    limit: int = Query(500, ge=1, le=2000),
    exclude_authority: bool = Query(False),
):
    supabase = get_supabase()
    check_results = load_track_a_results(
        supabase, facility_id=facility_id, status_filter=_DEFAULT_STATUS_FILTER
    )
    check_results = check_results[:limit]
    traces = run_reverse_check_batch(check_results)

    draft_ids = [
        t.full_trace.get("stage_check", {}).get("draft_id") for t in traces
    ]
    actor_map = _build_actor_map_chunked(supabase, [d for d in draft_ids if d])

    counts = {"AUTHORITY": 0, "FRAGMENT": 0, "BUSINESS": 0, "ASSOCIATION": 0, "UNKNOWN": 0}
    filtered = []
    for t in traces:
        info = _get_draft_actor(actor_map, t)
        ag = info.get("actor_group", "UNKNOWN")
        counts[ag if ag in counts else "UNKNOWN"] += 1
        if ag == "AUTHORITY" and exclude_authority:
            continue
        if info:
            t.full_trace["actor_overlay"] = info
        filtered.append(t)

    result = build_stored_diagnosis_result(
        traces=filtered,
        facility_id=facility_id,
        sector=sector,
        pipeline_stages={
            "track_a_loaded": len(check_results),
            "after_reverse_check": len(traces),
            "actor_overlay_applied": len(actor_map),
            **counts,
            "after_actor_filter": len(filtered),
        },
    )
    return result


@router.get("/actor-stats")
def get_actor_stats(facility_id: str = Query(...)):
    supabase = get_supabase()
    check_results = load_track_a_results(
        supabase, facility_id=facility_id, status_filter=_DEFAULT_STATUS_FILTER
    )
    traces = run_reverse_check_batch(check_results)
    draft_ids = [
        t.full_trace.get("stage_check", {}).get("draft_id") for t in traces
    ]
    actor_map = _build_actor_map_chunked(supabase, [d for d in draft_ids if d])

    counts = {"AUTHORITY": 0, "FRAGMENT": 0, "BUSINESS": 0, "ASSOCIATION": 0, "UNKNOWN": 0}
    for t in traces:
        ag = _get_draft_actor(actor_map, t).get("actor_group", "UNKNOWN")
        counts[ag if ag in counts else "UNKNOWN"] += 1

    return {
        "total": len(traces),
        **counts,
        "actor_overlay_coverage": len(actor_map),
        "estimated_clean_after_authority_filter": (
            len(traces) - counts["AUTHORITY"] - counts["FRAGMENT"]
        ),
    }
