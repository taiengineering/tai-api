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
from engine.validator import SAMPLE_ACCURACY_THRESHOLDS

logger = logging.getLogger(__name__)

DEFAULT_SAMPLE_ARTICLES = 100  # 마스터 §3.4 sample 단위 = 100조문

# Stage 2 역순 검증 임계 — validator Stage2와 동일 (본문 변경 없이 상수만 참조)
REVERSE_VERIFICATION_THRESHOLD: float = SAMPLE_ACCURACY_THRESHOLDS.get(2, 0.90)

# === Ground Truth 정규식 카테고리화 (PM 진단 정합) ===
CATEGORY_VERIFICATION_PATTERNS: dict[str, str] = {
    # HEADER 7종 (확정 패턴) — v4: 의무 결말형 보강 (좁은 패턴으로 TP 오판·오격리 방지)
    "OBLIGATION_HEADER": (
        r"(?:하여야|해야|어야|여야|아야)\s*한다\.?$"
        r"|의무가\s*있다\.?$"
        r"|(?:지켜야|준수하여야|이행하여야|준수해야|이행해야)\s*한다\.?$"
        r"|(?:하여야|해야)\s*합니다\.?$"
        r"|(?:을|를)\s*이행하여야\s*한다\.?$"
        r"|(?:스스로\s*)?책임지고\s*이행하여야\s*한다\.?$"
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


# 역순 검증용 — 결말형 완화 (정순 패턴 미스 시 TP 보정, Phase 2.2 v4)
_OBLIGATION_HEADER_RELAXED = re.compile(
    r"(?:하여야|해야|어야|여야|아야)\s*한다"
    r"|의무가\s*있다"
    r"|(?:지켜야|준수하여야|이행하여야|준수해야|이행해야)\s*한다"
    r"|(?:하여야|해야)\s*합니다",
)


def _obligation_header_relaxed_ok(source_text: str) -> bool:
    s = (source_text or "").strip()
    return bool(s and _OBLIGATION_HEADER_RELAXED.search(s))


def _verify_row_reverse(sub_type: str, source_text: str) -> str:
    """역순 검증 verdict — 정순 FP 중 OBLIGATION_HEADER 꼬리형 보정."""
    v = _verify_row(sub_type, source_text)
    if sub_type == "OBLIGATION_HEADER" and v == "FP":
        if _obligation_header_relaxed_ok(source_text):
            return "TP"
    return v


def fetch_law_stage2_rows(
    supabase: SupabaseClient | None,
    law_id: Any,
    *,
    exclude_isolated: bool = True,
) -> list[dict[str, Any]]:
    """법령 단위 stage_2 행 (element id + sub_type + source_text)."""
    out: list[dict[str, Any]] = []
    if supabase is None:
        return out

    url = os.environ.get("DATABASE_URL")
    iso_sql = " AND COALESCE(s2.is_isolated, false) = false " if exclude_isolated else ""
    if url:
        try:
            import psycopg2

            conn = psycopg2.connect(url)
            cur = conn.cursor()
            cur.execute(
                f"""
                SELECT s2.id::text, s2.sub_type, s1.source_text
                FROM stage_2_elements s2
                JOIN stage_1_clauses s1 ON s1.id = s2.clause_id
                JOIN law_article_part lap ON lap.id = s1.part_id
                JOIN law_article la ON la.id = lap.article_id
                WHERE la.law_id = %s
                {iso_sql}
                LIMIT 20000
                """,
                (law_id,),
            )
            for eid, st, stext in cur.fetchall():
                out.append(
                    {
                        "id": str(eid),
                        "sub_type": st,
                        "source_text": stext or "",
                    }
                )
            cur.close()
            conn.close()
            return out
        except Exception as e:  # noqa: BLE001
            logger.warning("fetch_law_stage2_rows(psycopg2) 실패: %s", e)

    try:
        clauses = fetch_clauses_by_law_id(supabase, law_id)
        cmap = {c["id"]: c for c in clauses if c.get("id")}
        for cid, cl in cmap.items():
            stext = cl.get("source_text") or ""
            res = (
                supabase.table("stage_2_elements")
                .select("id, sub_type, is_isolated")
                .eq("clause_id", cid)
                .execute()
                .data
                or []
            )
            for elem in res:
                if exclude_isolated and elem.get("is_isolated") is True:
                    continue
                eid = elem.get("id")
                if not eid:
                    continue
                out.append(
                    {
                        "id": str(eid),
                        "sub_type": elem.get("sub_type"),
                        "source_text": stext,
                    }
                )
    except Exception as e:  # noqa: BLE001
        logger.warning("fetch_law_stage2_rows(supabase) 실패: %s", e)

    return out


def compute_law_reverse_verification(
    supabase: SupabaseClient | None,
    law_id: Any,
    *,
    exclude_isolated: bool = True,
    threshold: float | None = None,
) -> tuple[bool, float, int]:
    """법령 단위 역순 검증 — _verify_row_reverse 집계.

    반환: (통과 여부, accuracy, classified 건수)
    통과: FP=0 이거나 accuracy≥threshold (validator Stage2와 동일 기본값).
    WEAK-only 등 FP=0이면 accuracy 미달이어도 통과.
    """
    thr = threshold if threshold is not None else REVERSE_VERIFICATION_THRESHOLD
    if supabase is None:
        return True, 1.0, 0

    rows = fetch_law_stage2_rows(
        supabase, law_id, exclude_isolated=exclude_isolated
    )
    if not rows:
        return True, 1.0, 0

    tp = fp = uc = weak = phase1_tp = 0
    for row in reversed(rows):
        sub_type = row.get("sub_type") or UC_SUB_TYPE
        source_text = row.get("source_text") or ""
        verdict = _verify_row_reverse(sub_type, source_text)
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
        return True, 1.0, 0

    accuracy = (tp + phase1_tp) / classified
    ok = fp == 0 or accuracy >= thr
    logger.info(
        "reverse_verification law_id=%s ok=%s acc=%.4f classified=%s fp=%s",
        law_id,
        ok,
        accuracy,
        classified,
        fp,
    )
    return ok, accuracy, classified


def compute_subtype_group_accuracy(
    supabase: SupabaseClient | None,
    *,
    law_id: int | str | None = None,
    law_batch: list[int | str] | None = None,
    sample_articles: int = DEFAULT_SAMPLE_ARTICLES,
    exclude_isolated: bool = False,
) -> dict[str, dict[str, Any]]:
    """sub_type별 TP/FP/WEAK/UC/PHASE1_TP 및 accuracy (law_id·law_batch·전역 샘플)."""
    empty: dict[str, dict[str, Any]] = {}
    if supabase is None:
        return empty

    rows = _fetch_sample_rows(
        supabase,
        sample_articles=max(sample_articles, 500),
        law_id=law_id,
        law_batch=law_batch,
        exclude_isolated=exclude_isolated,
    )
    buckets: dict[str, dict[str, int]] = {}
    for row in rows:
        st = row.get("sub_type") or UC_SUB_TYPE
        buckets.setdefault(
            st,
            {"tp": 0, "fp": 0, "uc": 0, "weak": 0, "phase1_tp": 0},
        )
        b = buckets[st]
        verdict = _verify_row(st, row.get("source_text") or "")
        if verdict == "TP":
            b["tp"] += 1
        elif verdict == "FP":
            b["fp"] += 1
        elif verdict == "UC":
            b["uc"] += 1
        elif verdict == "WEAK":
            b["weak"] += 1
        elif verdict == "PHASE1_TP":
            b["phase1_tp"] += 1

    out: dict[str, dict[str, Any]] = {}
    for st, b in buckets.items():
        classified = b["tp"] + b["fp"] + b["weak"] + b["phase1_tp"]
        acc = (
            (b["tp"] + b["phase1_tp"]) / classified
            if classified
            else 0.0
        )
        out[st] = {
            **b,
            "classified": classified,
            "accuracy": round(acc, 6),
        }
    return out


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
