"""WO-D-DOMAIN-001: Actor x Sector Domain Filter

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

from typing import Dict, List, Optional, Tuple

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

# 조문 단위 MISMATCH 예외 규칙
# {법령명 키워드: [조문번호, ...]} — 해당 조문은 INDUSTRIAL 제외
_ARTICLE_MISMATCH_RULES: Dict[str, List[int]] = {
    "소방시설 설치 및 관리에 관한 법률": [10],           # 주택소방시설 — 주택 전용
    "소방시설 설치 및 관리에 관한 법률 시행규칙": [23],    # 소방시설관리업자 의무
    "수도법": [38],                                     # 위탁심의위원회 — 수도사업자
    "수도법 시행령": [38],
    "승강기산업 진흥법": [16],                          # 협회 설립인가
    "산업안전보건기준에 관한 규칙": [547],            # 잠수작업 — 제조업 280명 공장 해당 없음
}


def _check_article_mismatch(law_name: str, article_no) -> Optional[str]:
    """조문 단위 MISMATCH 여부 확인. 해당하면 reason 반환, 없으면 None."""
    if not article_no or not law_name:
        return None
    try:
        art_int = int(str(article_no))
    except (ValueError, TypeError):
        return None

    for law_keyword, articles in _ARTICLE_MISMATCH_RULES.items():
        if law_keyword in law_name and art_int in articles:
            return (
                f"{law_name} 제{article_no}조: "
                "조문 단위 INDUSTRIAL 제외 (법령 레벨 sector_mapping 한계)"
            )
    return None


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
    law_name: str = "",
    article_no=None,
) -> Tuple[str, str]:
    """(domain_verdict, mismatch_reason) 반환."""

    if facility_sector != "INDUSTRIAL":
        return "DOMAIN_REVIEW", "비-INDUSTRIAL sector 판단 미적용"

    # AUTHORITY → MISMATCH
    if actor_group == "AUTHORITY":
        return "DOMAIN_MISMATCH", "AUTHORITY actor: 행정청 의무는 사업주 의무 아님"

    # FRAGMENT → MISMATCH
    if actor_group == "FRAGMENT":
        return "DOMAIN_MISMATCH", "FRAGMENT: 주체 토큰 아님"

    # CONSTRUCTOR → MISMATCH
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

        if not law_sectors:
            return "DOMAIN_REVIEW", "law_sector_mapping 미매핑: pass-through 오염 검토 필요"

        if "INDUSTRIAL" in law_sectors:
            # 조문 단위 예외 규칙 체크
            article_reason = _check_article_mismatch(law_name, article_no)
            if article_reason:
                return "DOMAIN_MISMATCH", article_reason
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
    estimated_clean: int
    top_mismatches: List[dict]
    top_keeps: List[dict]
    article_mismatch_applied: int  # 조문 단위 예외규칙 적용 건수


@router.get("/stats", response_model=DomainFilterStats)
def get_domain_filter_stats(
    facility_id: str = Query(...),
):
    """K-06~09: Domain Filter 적용 후 감소량 측정."""
    supabase = get_supabase()

    fac_res = (
        supabase.table("factories")
        .select("id, sector")
        .eq("id", facility_id)
        .single()
        .execute()
    )
    facility_sector = str((fac_res.data or {}).get("sector") or "")

    check_results = load_track_a_results(
        supabase, facility_id=facility_id,
        status_filter=_DEFAULT_STATUS_FILTER,
    )
    traces = run_reverse_check_batch(check_results)

    draft_ids = [
        t.full_trace.get("stage_check", {}).get("draft_id")
        for t in traces
    ]
    draft_ids_clean = [d for d in draft_ids if d]
    actor_map = _build_actor_map_chunked(supabase, draft_ids_clean)

    # draft_id → law_id + law_name + article_no
    draft_to_law: Dict[str, str] = {}
    draft_to_law_name: Dict[str, str] = {}
    draft_to_article_no: Dict[str, object] = {}

    for i in range(0, len(draft_ids_clean), 50):
        chunk = draft_ids_clean[i: i + 50]
        try:
            dr = (
                supabase.table("executable_draft")
                .select("id, article_id")
                .in_("id", chunk)
                .execute()
            )
            article_id_pairs = [
                (str(d["id"]), str(d["article_id"]))
                for d in (dr.data or []) if d.get("article_id")
            ]
            if not article_id_pairs:
                continue

            art_ids = [a[1] for a in article_id_pairs]
            ar = (
                supabase.table("law_article")
                .select("id, law_id, article_no")
                .in_("id", art_ids)
                .execute()
            )
            art_map = {
                str(a["id"]): (str(a["law_id"]), a.get("article_no"))
                for a in (ar.data or [])
            }

            law_ids_chunk = list({v[0] for v in art_map.values()})
            lm_res = (
                supabase.table("law_master")
                .select("id, law_name")
                .in_("id", law_ids_chunk)
                .execute()
            )
            law_name_map = {
                str(lm["id"]): str(lm["law_name"])
                for lm in (lm_res.data or [])
            }

            for did, aid in article_id_pairs:
                if aid in art_map:
                    lid, art_no = art_map[aid]
                    draft_to_law[did] = lid
                    draft_to_article_no[did] = art_no
                    draft_to_law_name[did] = law_name_map.get(lid, "")
        except Exception:
            continue

    law_ids = list(set(draft_to_law.values()))
    law_sector_map = _get_law_sector_map(supabase, law_ids)

    counts = {"DOMAIN_KEEP": 0, "DOMAIN_MISMATCH": 0, "DOMAIN_REVIEW": 0}
    mismatches: List[dict] = []
    keeps: List[dict] = []
    article_mismatch_count = 0

    for t in traces:
        draft_id = t.full_trace.get("stage_check", {}).get("draft_id")
        actor_info = actor_map.get(str(draft_id), {}) if draft_id else {}
        did_str = str(draft_id) if draft_id else ""
        law_id = draft_to_law.get(did_str, "")
        law_sectors = law_sector_map.get(law_id, []) if law_id else []
        law_name = draft_to_law_name.get(did_str, "") or (t.law_name or "")
        article_no = draft_to_article_no.get(did_str) or t.article_no

        verdict, reason = _compute_domain_verdict(
            facility_sector=facility_sector,
            actor_group=actor_info.get("actor_group", "UNKNOWN"),
            actor_code=actor_info.get("actor_code"),
            law_sectors=law_sectors,
            law_name=law_name,
            article_no=article_no,
        )
        counts[verdict] += 1

        if "조문 단위" in reason:
            article_mismatch_count += 1

        if verdict == "DOMAIN_MISMATCH" and len(mismatches) < 20:
            mismatches.append({
                "law_name": law_name or t.law_name,
                "article_no": str(article_no) if article_no else t.article_no,
                "actor_group": actor_info.get("actor_group"),
                "actor_code": actor_info.get("actor_code"),
                "law_sectors": law_sectors,
                "reason": reason,
            })

        if verdict == "DOMAIN_KEEP" and len(keeps) < 30:
            keeps.append({
                "law_name": law_name or t.law_name,
                "article_no": str(article_no) if article_no else t.article_no,
                "actor_code": actor_info.get("actor_code"),
                "applicability_status": t.applicability_status,
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
        top_keeps=keeps,
        article_mismatch_applied=article_mismatch_count,
    )
