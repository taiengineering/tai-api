"""WO-D-DOMAIN-001: Actor × Sector Domain Filter

Track A 결과에 actor_resolution + law_sector_mapping을 조합하여
domain_verdict를 생성한다.

목적 = 오염 알굴리즈 측정. DROP 어부 저장 금지.

금지:
  facility_applicability_eval 수정 금지
  compatibility_validation 수정 금지
  law_sector_mapping 수정 금지
  domain_filter_result에 DROP 컨럼 추가 금지
"""
from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from db.supabase_client import get_supabase
from services.check_engine_adapter import load_track_a_results
from services.reverse_check_service import run_reverse_check_batch
from routers.refinery_api import _build_actor_map_chunked

router = APIRouter(
    prefix="/domain-filter",
    tags=["D-DOMAIN-001 Domain Filter"],
)

_DEFAULT_STATUS_FILTER = ["MATCH_CANDIDATE", "POSSIBLE_CANDIDATE"]


def _get_law_sector_map(supabase, law_ids: List[str]) -> Dict[str, List[str]]:
    """law_id → sectors 매핑 로드 (chunk 50)."""
    if not law_ids:
        return {}
    result: Dict[str, List[str]] = {}
    unique = list(set(law_ids))
    for i in range(0, len(unique), 50):
        chunk = unique[i: i + 50]
        try:
            res = (
                supabase.table("law_sector_mapping")
                .select("law_id, sectors")
                .in_("law_id", chunk)
                .execute()
            )
            for row in (res.data or []):
                result[str(row["law_id"])] = row.get("sectors") or []
        except Exception:
            continue
    return result


def _compute_domain_verdict(
    facility_sector: str,
    actor_group: str,
    actor_code: Optional[str],
    law_sectors: List[str],
) -> tuple[str, str]:
    """(domain_verdict, mismatch_reason) 반환."""

    if facility_sector != "INDUSTRIAL":
        # INDUSTRIAL 외 섹터는 현단계 파일럿 범위 밖
        return "DOMAIN_REVIEW", "비-INDUSTRIAL sector 판단 미적용"

    # AUTHORITY → MISMATCH
    if actor_group == "AUTHORITY":
        return "DOMAIN_MISMATCH", "AUTHORITY actor: 행정청 의무는 사업주 의무 아님"

    # FRAGMENT → MISMATCH
    if actor_group == "FRAGMENT":
        return "DOMAIN_MISMATCH", "FRAGMENT: 주체 토큰 아님"

    # CONSTRUCTOR → MISMATCH (sector 무관하게)
    if actor_code == "ACTOR:CONSTRUCTOR":
        return "DOMAIN_MISMATCH", "ACTOR:CONSTRUCTOR: 제조업 사업장에 공사업자 의무 적용 불가"

    # ASSOCIATION → REVIEW
    if actor_group == "ASSOCIATION":
        return "DOMAIN_REVIEW", "ASSOCIATION: 협회 자체 vs 회원 사업자 의무 확인 필요"

    # UNKNOWN → REVIEW
    if actor_group == "UNKNOWN" or not actor_group:
        return "DOMAIN_REVIEW", "UNKNOWN actor: 분류 불가"

    # BUSINESS 계열
    if actor_group == "BUSINESS":
        if actor_code == "ACTOR:MANAGER":
            if law_sectors and "INDUSTRIAL" not in law_sectors:
                return "DOMAIN_MISMATCH", (
                    f"ACTOR:MANAGER + law_sectors={law_sectors}: "
                    "건물/주택 관리의무는 INDUSTRIAL 적용 불가"
                )
            return "DOMAIN_KEEP", "사업장 내 관리의무"

        if not law_sectors:
            # 미매핑 pass-through
            return "DOMAIN_REVIEW", "law_sector_mapping 미매핑: pass-through 오염 검토 필요"

        if "INDUSTRIAL" in law_sectors:
            return "DOMAIN_KEEP", f"BUSINESS + law_sectors={law_sectors}: 업종 일치"
        else:
            return "DOMAIN_REVIEW", (
                f"BUSINESS + law_sectors={law_sectors}: "
                "INDUSTRIAL 제외 업종 확인 필요"
            )

    return "DOMAIN_REVIEW", f"actor_group={actor_group}: 판단 규칙 미정의"


class DomainFilterStats(BaseModel):
    facility_id: str
    facility_sector: str
    total: int
    DOMAIN_KEEP: int
    DOMAIN_MISMATCH: int
    DOMAIN_REVIEW: int
    actor_overlay_coverage: int
    estimated_clean: int   # DOMAIN_KEEP만
    top_mismatches: List[dict]


@router.get("/stats", response_model=DomainFilterStats)
def get_domain_filter_stats(
    facility_id: str = Query(...),
):
    """K-06~09: Domain Filter 적용 후 감소량 측정."""
    supabase = get_supabase()

    # 1) 사업장 sector 로드
    fac_res = (
        supabase.table("factories")
        .select("id, sector")
        .eq("id", facility_id)
        .single()
        .execute()
    )
    facility_sector = str((fac_res.data or {}).get("sector") or "")

    # 2) Track A 로드
    check_results = load_track_a_results(
        supabase, facility_id=facility_id,
        status_filter=_DEFAULT_STATUS_FILTER,
    )
    traces = run_reverse_check_batch(check_results)

    # 3) Actor Overlay
    draft_ids = [
        t.full_trace.get("stage_check", {}).get("draft_id")
        for t in traces
    ]
    draft_ids_clean = [d for d in draft_ids if d]
    actor_map = _build_actor_map_chunked(supabase, draft_ids_clean)

    # 4) draft_id → law_id 매핑
    draft_to_law: Dict[str, str] = {}
    for i in range(0, len(draft_ids_clean), 50):
        chunk = draft_ids_clean[i: i + 50]
        try:
            dr = (
                supabase.table("executable_draft")
                .select("id, article_id")
                .in_("id", chunk)
                .execute()
            )
            article_ids = [
                (str(d["id"]), str(d["article_id"]))
                for d in (dr.data or []) if d.get("article_id")
            ]
            if article_ids:
                art_ids = [a[1] for a in article_ids]
                ar = (
                    supabase.table("law_article")
                    .select("id, law_id")
                    .in_("id", art_ids)
                    .execute()
                )
                art_to_law = {str(a["id"]): str(a["law_id"]) for a in (ar.data or [])}
                for did, aid in article_ids:
                    if aid in art_to_law:
                        draft_to_law[did] = art_to_law[aid]
        except Exception:
            continue

    # 5) law_id → sectors 매핑
    law_ids = list(set(draft_to_law.values()))
    law_sector_map = _get_law_sector_map(supabase, law_ids)

    # 6) domain_verdict 산정
    counts = {"DOMAIN_KEEP": 0, "DOMAIN_MISMATCH": 0, "DOMAIN_REVIEW": 0}
    mismatches: List[dict] = []

    for t in traces:
        draft_id = t.full_trace.get("stage_check", {}).get("draft_id")
        actor_info = actor_map.get(str(draft_id), {}) if draft_id else {}
        law_id = draft_to_law.get(str(draft_id) if draft_id else "", "")
        law_sectors = law_sector_map.get(law_id, []) if law_id else []

        verdict, reason = _compute_domain_verdict(
            facility_sector=facility_sector,
            actor_group=actor_info.get("actor_group", "UNKNOWN"),
            actor_code=actor_info.get("actor_code"),
            law_sectors=law_sectors,
        )
        counts[verdict] += 1

        if verdict == "DOMAIN_MISMATCH" and len(mismatches) < 20:
            mismatches.append({
                "law_name": t.law_name,
                "article_no": t.article_no,
                "actor_group": actor_info.get("actor_group"),
                "actor_code": actor_info.get("actor_code"),
                "law_sectors": law_sectors,
                "reason": reason,
            })

    return DomainFilterStats(
        facility_id=facility_id,
        facility_sector=facility_sector,
        total=len(traces),
        DOMAIN_KEEP=counts["DOMAIN_KEEP"],
        DOMAIN_MISMATCH=counts["DOMAIN_MISMATCH"],
        DOMAIN_REVIEW=counts["DOMAIN_REVIEW"],
        actor_overlay_coverage=len(actor_map),
        estimated_clean=counts["DOMAIN_KEEP"],
        top_mismatches=mismatches,
    )
