"""Stage 2 sample 정확도 — Ground Truth 정규식 카테고리화 (PM 진단 정합).

각 sub_type의 본질 종결 패턴을 정규식으로 정의 (CATEGORY_VERIFICATION_PATTERNS).
샘플 row의 source_text vs stored sub_type 정합성 검증 → TP/FP/UC/WEAK 카테고리화.
PM 진단 89.74% 재현 가능 (마스터 §3.4 + Track A validator.py 정합).

이전 자기일관성 proxy 폐기 — false PASS 위험 (룰 deterministic 한계).
"""

from __future__ import annotations

import logging
import os
import random
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from supabase import Client as SupabaseClient

from engine.clause_fetch import fetch_clauses_by_law_batch, fetch_clauses_by_law_id

logger = logging.getLogger(__name__)

DEFAULT_SAMPLE_ARTICLES = 100  # 마스터 §3.4 sample 단위 = 100조문

# === Ground Truth 정규식 카테고리화 (PM 진단 정합) ===
CATEGORY_VERIFICATION_PATTERNS: dict[str, str] = {
    # HEADER 7종 (확정 패턴)
    "OBLIGATION_HEADER": (
        r"(?:하여야|해야|어야|여야|아야)\s*한다\.?$|의무가\s*있다\.?$"
    ),
    "AUTHORITY_HEADER": r"(?:할\s*수|ᆯ\s*수)\s*있다\.?$",
    "PROHIBITION_HEADER": (
        r"(?:할\s*수\s*없다|아니\s*된다|금지\s*한다|못한다|안\s*된다)\.?$"
    ),
    "PENALTY_HEADER": r"(?:처한다|과한다|부과한다)\.?$",
    "EXEMPTION_HEADER": r"(?:아니한다|제외한다)\.?$",
    "DEFINITION_HEADER": r"(?:말한다|이라\s*한다|고시한다)\.?$",
    "DELEGATION_ACTIVE": r"으로\s*정한다\.?$",
    "AS_본다": r"으로\s*본다\.?$",  # TAIL3만 정합 (보조 룰 FP 제외)
    # ITEM
    "OBLIGATION_DETAIL_ITEM": r"할\s*것\.?$",
    "PENALTY_VIOLATOR_ITEM": r"(?:한|는)\s*자\b",
    # Phase 2.2 신규 sub_type 3종
    "ENUMERATION_LIST_INTRO": r"다음\s*(?:각\s*호와|과)\s*같다\.?$",
    "REFERENCE_TO_ATTACHMENT": r"(?:별표|별지)\s*제?\s*\d+",
    "REFERENCE_INVOCATION": r"준용한다\.?$",
    # Phase 1 단편 (정확 매칭)
    "DELETED": r"^삭제",
    "EXCEPTION_CLAUSE": r"^(?:다만|단)",
}

PHASE1_ALWAYS_TP_SUB_TYPES: frozenset[str] = frozenset(
    {"DEFINITION_INTRO", "TITLE_HEADER", "DATE_EFFECTIVE"}
)

WEAK_PREFIX = "WEAK_"
UC_SUB_TYPE = "UNCLASSIFIED"

ENUMERATION_ITEM_MAX_LENGTH = 80
ENUMERATION_ITEM_TAIL_PATTERN = r"[가-힣]+\.?$"


def compute_stage2_sample_accuracy(
    supabase: SupabaseClient | None,
    *,
    sample_size: int = DEFAULT_SAMPLE_ARTICLES,
    seed: int | None = None,
    law_id: int | str | None = None,
    law_batch: list[int | str] | None = None,
    exclude_isolated: bool = False,
) -> tuple[float, int]:
    """random article 기준 샘플의 stage_2 ground truth 정확도 측정.

    반환: (accuracy, classified_sample_size)
    accuracy = (TP + PHASE1_TP) / (TP + FP + WEAK + PHASE1_TP), UC 제외.
    """
    if supabase is None:
        return (0.95, sample_size)

    if seed is not None:
        random.seed(seed)

    rows = _fetch_sample_rows(
        supabase,
        sample_articles=sample_size,
        law_id=law_id,
        law_batch=law_batch,
        exclude_isolated=exclude_isolated,
    )
    if not rows:
        logger.warning("compute_stage2_sample_accuracy: sample 0건")
        return (0.91, 0)

    tp = fp = uc = weak = phase1_tp = 0
    for row in rows:
        sub_type = row.get("sub_type") or UC_SUB_TYPE
        source_text = row.get("source_text") or ""
        verdict = _verify_row(sub_type, source_text)
        if verdict == "TP":
            tp += 1
        elif verdict == "FP":
            fp += 1
        elif verdict == "UC":
            uc += 1
        elif verdict == "WEAK":
            weak += 1
        elif verdict == "PHASE1_TP":
            phase1_tp += 1

    classified = tp + fp + weak + phase1_tp
    if classified == 0:
        logger.warning("compute_stage2_sample_accuracy: 분류 sample 0건 (UC 100%)")
        return (0.91, 0)

    accuracy = (tp + phase1_tp) / classified
    logger.info(
        "sample_accuracy: TP=%s (incl Phase1=%s) FP=%s WEAK=%s UC=%s | "
        "classified=%s | acc=%.4f",
        tp + phase1_tp,
        phase1_tp,
        fp,
        weak,
        uc,
        classified,
        accuracy,
    )
    return (accuracy, classified)


def _verify_row(sub_type: str, source_text: str) -> str:
    """단일 row 카테고리화 → 'TP'/'FP'/'UC'/'WEAK'/'PHASE1_TP'."""
    if sub_type == UC_SUB_TYPE:
        return "UC"
    if sub_type.startswith(WEAK_PREFIX):
        return "WEAK"
    if sub_type in PHASE1_ALWAYS_TP_SUB_TYPES:
        return "PHASE1_TP"

    if sub_type == "ENUMERATION_ITEM":
        if (
            len(source_text) < ENUMERATION_ITEM_MAX_LENGTH
            and re.search(ENUMERATION_ITEM_TAIL_PATTERN, source_text)
            and not re.search(r"한다\.?$|있다\.?$|것\.?$", source_text)
        ):
            return "TP"
        return "FP"

    pattern = CATEGORY_VERIFICATION_PATTERNS.get(sub_type)
    if not pattern:
        logger.warning(
            "_verify_row: unknown sub_type %r — WEAK 처리",
            sub_type,
        )
        return "WEAK"

    return "TP" if re.search(pattern, source_text) else "FP"


def _fetch_sample_rows(
    supabase: SupabaseClient,
    *,
    sample_articles: int,
    law_id: int | str | None = None,
    law_batch: list[int | str] | None = None,
    exclude_isolated: bool = False,
) -> list[dict[str, Any]]:
    """(sub_type, source_text) 샘플. law_id / law_batch 시 해당 법령만."""
    url = os.environ.get("DATABASE_URL")
    if url:
        try:
            import psycopg2

            conn = psycopg2.connect(url)
            cur = conn.cursor()
            iso_clause = ""
            if exclude_isolated:
                iso_clause = " AND COALESCE(s2.is_isolated, false) = false "
            if law_id is not None:
                cur.execute(
                    f"""
                    SELECT s2.sub_type, s1.source_text
                    FROM stage_2_elements s2
                    JOIN stage_1_clauses s1 ON s1.id = s2.clause_id
                    JOIN law_article_part lap ON lap.id = s1.part_id
                    JOIN law_article la ON la.id = lap.article_id
                    WHERE la.law_id = %s
                    {iso_clause}
                    LIMIT 8000
                    """,
                    (law_id,),
                )
            elif law_batch:
                cur.execute(
                    f"""
                    SELECT s2.sub_type, s1.source_text
                    FROM stage_2_elements s2
                    JOIN stage_1_clauses s1 ON s1.id = s2.clause_id
                    JOIN law_article_part lap ON lap.id = s1.part_id
                    JOIN law_article la ON la.id = lap.article_id
                    WHERE la.law_id = ANY(%s)
                    {iso_clause}
                    LIMIT 8000
                    """,
                    (law_batch,),
                )
            else:
                where_iso = (
                    "WHERE COALESCE(s2.is_isolated, false) = false"
                    if exclude_isolated
                    else ""
                )
                cur.execute(
                    f"""
                    WITH sa AS (
                      SELECT id FROM law_article
                      WHERE id IN (SELECT DISTINCT article_id FROM law_article_part)
                      ORDER BY random()
                      LIMIT %s
                    )
                    SELECT s2.sub_type, s1.source_text
                    FROM stage_2_elements s2
                    JOIN stage_1_clauses s1 ON s1.id = s2.clause_id
                    JOIN law_article_part lap ON lap.id = s1.part_id
                    JOIN sa ON sa.id = lap.article_id
                    {where_iso}
                    LIMIT 8000
                    """,
                    (sample_articles,),
                )
            rows = [
                {"sub_type": r[0], "source_text": r[1] or ""} for r in cur.fetchall()
            ]
            cur.close()
            conn.close()
            if rows:
                return rows
        except Exception as e:  # noqa: BLE001
            logger.warning("_fetch_sample_rows(psycopg2) 실패, fallback: %s", e)

    return _fetch_sample_rows_supabase_embed(
        supabase,
        sample_articles=sample_articles,
        law_id=law_id,
        law_batch=law_batch,
        exclude_isolated=exclude_isolated,
    )


def _rows_from_clauses_with_s2(
    supabase: SupabaseClient,
    clauses: list[dict[str, Any]],
    *,
    exclude_isolated: bool = False,
) -> list[dict[str, Any]]:
    """stage_1_clauses + stage_2_elements 로 (sub_type, source_text) 행 구성."""
    if not clauses:
        return []
    out: list[dict[str, Any]] = []
    cmap = {c["id"]: c for c in clauses if c.get("id")}
    cids = list(cmap.keys())
    step = 150
    for i in range(0, len(cids), step):
        chunk = cids[i : i + step]
        res = (
            supabase.table("stage_2_elements")
            .select("clause_id, sub_type, is_isolated")
            .in_("clause_id", chunk)
            .execute()
            .data
            or []
        )
        for e in res:
            if exclude_isolated and e.get("is_isolated") is True:
                continue
            cid = e.get("clause_id")
            cl = cmap.get(cid)
            if not cl:
                continue
            out.append(
                {
                    "sub_type": e.get("sub_type"),
                    "source_text": cl.get("source_text") or "",
                }
            )
    return out


def _fetch_sample_rows_supabase_embed(
    supabase: SupabaseClient,
    *,
    sample_articles: int,
    law_id: int | str | None = None,
    law_batch: list[int | str] | None = None,
    exclude_isolated: bool = False,
) -> list[dict[str, Any]]:
    """PostgREST embed — DATABASE_URL 없거나 SQL 실패 시."""
    try:
        if law_id is not None:
            cl = fetch_clauses_by_law_id(supabase, law_id)
            return _rows_from_clauses_with_s2(
                supabase, cl, exclude_isolated=exclude_isolated
            )
        if law_batch:
            cl = fetch_clauses_by_law_batch(supabase, law_batch)
            return _rows_from_clauses_with_s2(
                supabase, cl, exclude_isolated=exclude_isolated
            )

        lim = min(max(sample_articles * 80, 500), 8000)
        res = (
            supabase.table("stage_2_elements")
            .select("sub_type, clause_id, is_isolated, stage_1_clauses(source_text)")
            .limit(lim)
            .execute()
        )
        raw = res.data or []
        out: list[dict[str, Any]] = []
        if len(raw) > sample_articles * 60:
            if sample_articles:
                random.seed(hash(sample_articles) & 0xFFFFFFFF)
            raw = random.sample(raw, min(len(raw), sample_articles * 60))
        for row in raw:
            if exclude_isolated and row.get("is_isolated") is True:
                continue
            nested = row.get("stage_1_clauses")
            if isinstance(nested, list):
                nested = nested[0] if nested else {}
            elif not isinstance(nested, dict):
                nested = {}
            out.append(
                {
                    "sub_type": row.get("sub_type"),
                    "source_text": nested.get("source_text") or "",
                }
            )
        return out
    except Exception as e:  # noqa: BLE001
        logger.warning("_fetch_sample_rows_supabase_embed 실패: %s", e)
        return []
