#!/usr/bin/env python3
"""
Track E Stage 1/2 Phase 2 / Phase 2.1 — Kiwi 메타 보강 + sub_type 정밀 분류 + 6하원칙.

Phase 2: Cursor_Stage_1_2_Phase_2_Spec.md
Phase 2.1: Cursor_Phase_2_1_Rule_Redesign_Spec.md
Phase 2.2: Cursor_Phase_2_2_Accuracy_Spec.md

실행:
  cd tai-api && railway run python3 scripts/track_e_phase2_run.py [--phase21|--phase22] [--only ...] [--limit N]

  Phase 2.2 (v1.2 Pipeline): --phase22 [--only checks|backup|rules|pipeline|all]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    import psycopg2
    from psycopg2.extras import Json, execute_batch
except ImportError as e:
    raise SystemExit("psycopg2 required: pip install psycopg2-binary") from e

from db.database import get_supabase
from engine.morpheme import MorphemeEngine
from engine.phase_21_rule_payload import RULE_INSERTS as PHASE21_INSERTS
from engine.phase_21_rule_payload import RULE_PATTERN_UPDATES as PHASE21_UPDATES
from engine.phase_22_apply import apply_phase_22_rule_changes
from engine.phase_22_apply import apply_phase_22_schema
from engine.six_w_heuristic import extract_six_w
from engine.subtype_rule_match import pick_first_matching_subtype_rule
from engine.pipeline import PipelineHaltError, TAIExtractionPipeline, halt_exit
from engine.schemas.stage_2 import Stage2Input
from engine.stages import Stage2Decomposer, StageContext
from engine.validator import Validator

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BACKUP_S1 = "stage_1_clauses_backup_20260510_pre_phase2"
BACKUP_S2 = "stage_2_elements_backup_20260510_pre_phase2"

BACKUP_RULES_P21 = "rule_classify_subtype_backup_20260510_pre_phase2_1"
BACKUP_S2_P21 = "stage_2_elements_backup_20260510_pre_phase2_1"

BACKUP_RULES_P22 = "rule_classify_subtype_backup_20260511_pre_phase22"
BACKUP_S2_P22 = "stage_2_elements_backup_20260511_pre_phase22"

# Phase 2.2 진입 (Phase 2.1 완료 직후 DB)
EXPECTED_PHASE22_UNCLASSIFIED = 68130
# Phase 2.2 명세 §2.1 진입 점검 — rule INSERT/비활성 반영 후 활성 룰 수 (배포 스냅샷 기준)
EXPECTED_PHASE22_RULES_SUB = 34

EXPECTED_TOTAL = 151751
EXPECTED_UNCLASSIFIED = 143542
EXPECTED_RULES_SUB = 23
EXPECTED_RULES_IF = 8

# Phase 2.1 진입 (Phase 2.0 직후 DB)
EXPECTED_PHASE21_UNCLASSIFIED = 143220
EXPECTED_PHASE21_TARGET_ROWS = 143542  # 151751 - 8209 (Phase 1 고정)

PHASE1_LOCKED_SUBTYPES = (
    "DELETED",
    "EXCEPTION_CLAUSE",
    "DEFINITION_INTRO",
    "TITLE_HEADER",
    "DATE_EFFECTIVE",
)


def _chunks(xs: list, n: int):
    for i in range(0, len(xs), n):
        yield xs[i : i + n]


def run_entry_checks(sb) -> dict[str, Any]:
    """§2 진입 점검 (Phase 2.0 기준)."""
    s1 = sb.table("stage_1_clauses").select("id", count="exact", head=True).execute().count
    s2 = sb.table("stage_2_elements").select("id", count="exact", head=True).execute().count
    rs = (
        sb.table("rule_classify_subtype")
        .select("id", count="exact", head=True)
        .eq("enabled", True)
        .execute()
        .count
    )
    rif = (
        sb.table("rule_classify_if_pattern")
        .select("id", count="exact", head=True)
        .eq("enabled", True)
        .execute()
        .count
    )
    uc = (
        sb.table("stage_2_elements")
        .select("id", count="exact", head=True)
        .eq("sub_type", "UNCLASSIFIED")
        .execute()
        .count
    )
    out = {
        "stage_1_clauses": s1,
        "stage_2_elements": s2,
        "rule_classify_subtype_enabled": rs,
        "rule_classify_if_pattern_enabled": rif,
        "UNCLASSIFIED": uc,
    }
    logger.info("진입 점검: %s", out)
    if s1 != EXPECTED_TOTAL or s2 != EXPECTED_TOTAL:
        raise SystemExit(f"진입 점검 실패: row 수 불일치 (예상 {EXPECTED_TOTAL})")
    if rs != EXPECTED_RULES_SUB or rif != EXPECTED_RULES_IF:
        raise SystemExit("진입 점검 실패: 룰 수 불일치")
    if uc != EXPECTED_UNCLASSIFIED:
        raise SystemExit(f"진입 점검 실패: UNCLASSIFIED {uc} != {EXPECTED_UNCLASSIFIED}")
    return out


def run_entry_checks_phase21(sb) -> dict[str, Any]:
    """§2.1 Phase 2.1 진입 점검."""
    s1 = sb.table("stage_1_clauses").select("id", count="exact", head=True).execute().count
    s2 = sb.table("stage_2_elements").select("id", count="exact", head=True).execute().count
    rs = (
        sb.table("rule_classify_subtype")
        .select("id", count="exact", head=True)
        .eq("enabled", True)
        .execute()
        .count
    )
    rif = (
        sb.table("rule_classify_if_pattern")
        .select("id", count="exact", head=True)
        .eq("enabled", True)
        .execute()
        .count
    )
    uc = (
        sb.table("stage_2_elements")
        .select("id", count="exact", head=True)
        .eq("sub_type", "UNCLASSIFIED")
        .execute()
        .count
    )
    c = pg_conn()
    cur = c.cursor()
    cur.execute(
        "SELECT 100.0 * COUNT(*) FILTER (WHERE tokenization_json IS NULL) / COUNT(*) FROM stage_1_clauses"
    )
    tok_null = float(cur.fetchone()[0] or 0)
    cur.close()
    c.close()

    out = {
        "stage_1_clauses": s1,
        "stage_2_elements": s2,
        "rule_classify_subtype_enabled": rs,
        "rule_classify_if_pattern_enabled": rif,
        "UNCLASSIFIED": uc,
        "tokenization_null_pct": tok_null,
    }
    logger.info("Phase2.1 진입 점검: %s", out)
    if s1 != EXPECTED_TOTAL or s2 != EXPECTED_TOTAL:
        raise SystemExit(f"진입 점검 실패: row 수 불일치 ({EXPECTED_TOTAL})")
    if rs != EXPECTED_RULES_SUB or rif != EXPECTED_RULES_IF:
        raise SystemExit("진입 점검 실패: subtype/if_pattern 룰 수 불일치")
    if uc != EXPECTED_PHASE21_UNCLASSIFIED:
        raise SystemExit(f"진입 점검 실패: UNCLASSIFIED {uc} != {EXPECTED_PHASE21_UNCLASSIFIED}")
    if tok_null > 0.1:
        raise SystemExit(f"tokenization_json NULL {tok_null}% > 0.1% — 정지")
    return out


def pg_conn():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL 없음")
    return psycopg2.connect(url)


def run_backup(conn) -> None:
    """§3 백업 (Phase 2.0)."""
    cur = conn.cursor()
    for name, src in ((BACKUP_S1, "stage_1_clauses"), (BACKUP_S2, "stage_2_elements")):
        cur.execute(
            """
            SELECT EXISTS (
              SELECT FROM pg_tables WHERE schemaname='public' AND tablename=%s
            )
            """,
            (name,),
        )
        exists = cur.fetchone()[0]
        if exists:
            logger.warning("백업 테이블 이미 존재 — 스킵: %s", name)
            continue
        cur.execute(f"CREATE TABLE {name} AS TABLE {src}")
        logger.info("CREATE TABLE %s AS SELECT * FROM %s", name, src)
    conn.commit()
    cur.execute(f"SELECT COUNT(*) FROM {BACKUP_S1}")
    c1 = cur.fetchone()[0]
    cur.execute(f"SELECT COUNT(*) FROM {BACKUP_S2}")
    c2 = cur.fetchone()[0]
    cur.close()
    logger.info("백업 검증: %s=%s %s=%s", BACKUP_S1, c1, BACKUP_S2, c2)
    if c1 != EXPECTED_TOTAL or c2 != EXPECTED_TOTAL:
        raise SystemExit("백업 row 수 불일치 — 정지")


def run_entry_checks_phase22(sb) -> dict[str, Any]:
    """Phase 2.2 진입 점검 (명세 Cursor_Phase_2_2_Pipeline_Engine_Spec_v1_2 §2.1)."""
    s2 = (
        sb.table("stage_2_elements")
        .select("id", count="exact", head=True)
        .execute()
        .count
    )
    rs = (
        sb.table("rule_classify_subtype")
        .select("id", count="exact", head=True)
        .eq("enabled", True)
        .execute()
        .count
    )
    uc = (
        sb.table("stage_2_elements")
        .select("id", count="exact", head=True)
        .eq("sub_type", "UNCLASSIFIED")
        .execute()
        .count
    )
    out: dict[str, Any] = {
        "stage_2_elements": s2,
        "UNCLASSIFIED": uc,
        "rule_classify_subtype_enabled": rs,
    }
    logger.info("Phase2.2 진입 점검: %s", out)
    if s2 != EXPECTED_TOTAL:
        raise SystemExit(f"진입 점검 실패: stage_2_elements {s2} != {EXPECTED_TOTAL}")
    if uc != EXPECTED_PHASE22_UNCLASSIFIED:
        raise SystemExit(
            f"진입 점검 실패: UNCLASSIFIED {uc} != {EXPECTED_PHASE22_UNCLASSIFIED}"
        )
    if rs != EXPECTED_PHASE22_RULES_SUB:
        raise SystemExit(
            f"진입 점검 실패: 활성 sub_type 룰 {rs} != {EXPECTED_PHASE22_RULES_SUB} "
            "(Phase2.2 룰 반영 전/후 스냅샷이 다르면 상수 조정)"
        )
    return out


def run_backup_phase22(conn) -> None:
    """Phase 2.2 백업 (rule_classify_subtype + stage_2_elements)."""
    cur = conn.cursor()
    for name, src in (
        (BACKUP_RULES_P22, "rule_classify_subtype"),
        (BACKUP_S2_P22, "stage_2_elements"),
    ):
        cur.execute(
            """
            SELECT EXISTS (
              SELECT FROM pg_tables WHERE schemaname='public' AND tablename=%s
            )
            """,
            (name,),
        )
        if cur.fetchone()[0]:
            logger.warning("Phase2.2 백업 이미 존재 — 스킵: %s", name)
            continue
        cur.execute(f"CREATE TABLE {name} AS TABLE {src}")
        logger.info("CREATE TABLE %s AS TABLE %s", name, src)
    conn.commit()
    cur.execute(f"SELECT COUNT(*) FROM {BACKUP_RULES_P22}")
    cr = cur.fetchone()[0]
    cur.execute(f"SELECT COUNT(*) FROM {BACKUP_S2_P22}")
    ce = cur.fetchone()[0]
    cur.close()
    logger.info("Phase2.2 백업 검증: rules=%s elems=%s", cr, ce)
    if cr < 1 or ce != EXPECTED_TOTAL:
        raise SystemExit("Phase2.2 백업 row 수 불일치 — 정지")


def run_phase22_pipeline(sb) -> Any:
    """Pipeline 내장 검증 hook만 실행 (Stage2 샘플 정확도). 실패 시 SystemExit."""
    pipeline = TAIExtractionPipeline(
        stages=[Stage2Decomposer()],
        validator=Validator(supabase=sb),
        ctx=StageContext(supabase=sb),
        halt_on_warning=True,
    )
    try:
        inp = Stage2Input(clauses=[]).model_dump()
        return pipeline.run(inp, only_stages=[2])
    except PipelineHaltError as e:
        halt_exit(e)
        return None


def run_backup_phase21(conn) -> None:
    """§5 Phase 2.1 백업."""
    cur = conn.cursor()
    for name, src in ((BACKUP_RULES_P21, "rule_classify_subtype"), (BACKUP_S2_P21, "stage_2_elements")):
        cur.execute(
            """
            SELECT EXISTS (
              SELECT FROM pg_tables WHERE schemaname='public' AND tablename=%s
            )
            """,
            (name,),
        )
        if cur.fetchone()[0]:
            logger.warning("Phase2.1 백업 이미 존재 — 스킵: %s", name)
            continue
        cur.execute(f"CREATE TABLE {name} AS TABLE {src}")
        logger.info("CREATE TABLE %s AS SELECT * FROM %s", name, src)
    conn.commit()
    cur.execute(f"SELECT COUNT(*) FROM {BACKUP_RULES_P21}")
    cr = cur.fetchone()[0]
    cur.execute(f"SELECT COUNT(*) FROM {BACKUP_S2_P21}")
    ce = cur.fetchone()[0]
    cur.close()
    logger.info("Phase2.1 백업 검증: rules=%s elems=%s", cr, ce)
    if cr != EXPECTED_RULES_SUB or ce != EXPECTED_TOTAL:
        raise SystemExit("Phase2.1 백업 row 수 불일치 — 정지")


def apply_phase_21_rule_changes(conn) -> dict[str, Any]:
    """§4 룰 패턴 UPDATE + 신규 INSERT (idempotent)."""
    cur = conn.cursor()
    updated = 0
    for rn, pat in PHASE21_UPDATES.items():
        cur.execute(
            """
            UPDATE rule_classify_subtype
            SET pattern = %s, updated_at = NOW()
            WHERE rule_name = %s
            """,
            (pat, rn),
        )
        updated += cur.rowcount
    inserted = 0
    for rule_name, sub_type, pattern, pos, pri, desc in PHASE21_INSERTS:
        cur.execute("SELECT 1 FROM rule_classify_subtype WHERE rule_name = %s", (rule_name,))
        if cur.fetchone():
            continue
        cur.execute(
            """
            INSERT INTO rule_classify_subtype
              (rule_name, sub_type, match_strategy, pattern, pattern_position, priority, enabled, description)
            VALUES (%s, %s, 'TAIL_POS', %s, %s, %s, true, %s)
            """,
            (rule_name, sub_type, pattern, pos, pri, desc),
        )
        inserted += 1
    conn.commit()
    cur.close()
    logger.info("Phase2.1 룰 변경: updated_rows=%s inserted_rules=%s", updated, inserted)
    return {"updated_rows": updated, "inserted_rules": inserted}


def load_split_rules(sb) -> list[dict[str, Any]]:
    return (
        sb.table("rule_clause_split")
        .select("id, priority, pattern")
        .eq("enabled", True)
        .order("priority", desc=False)
        .execute()
        .data
        or []
    )


def match_split_rule_id(source_text: str, rules: list[dict[str, Any]]) -> str | None:
    if not source_text:
        return None
    for r in rules:
        pat = r.get("pattern") or ""
        try:
            if re.search(pat, source_text):
                return r["id"]
        except re.error:
            continue
    return None


def fetch_parts_map(sb, part_ids: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for chunk in _chunks(part_ids, 150):
        res = sb.table("law_article_part").select("id, part_text").in_("id", chunk).execute()
        for row in res.data or []:
            out[row["id"]] = row.get("part_text") or ""
    return out


def run_stage1(sb, conn, *, batch_size: int, limit: int | None) -> dict[str, Any]:
    """§4 Stage 1 메타데이터 보강."""
    engine = MorphemeEngine(supabase=sb)
    split_rules = load_split_rules(sb)
    logger.info("split rules loaded: %d user_dict_size=%s", len(split_rules), engine.user_dict_size)

    cur = conn.cursor()
    processed = 0
    tok_fail = 0
    total_target = limit or EXPECTED_TOTAL

    offset = 0
    while offset < total_target:
        lim = min(batch_size, total_target - offset)
        res = (
            sb.table("stage_1_clauses")
            .select("id, source_text, part_id")
            .order("id")
            .range(offset, offset + lim - 1)
            .execute()
        )
        rows = res.data or []
        if not rows:
            break
        part_ids = list({r["part_id"] for r in rows})
        pmap = fetch_parts_map(sb, part_ids)

        updates: list[tuple[Any, ...]] = []
        for row in rows:
            sid = row["id"]
            stext = row["source_text"] or ""
            pid = row["part_id"]
            try:
                toks = engine.tokenize(stext)
                tok_json = [{"form": t.form, "tag": t.tag, "start": t.start, "len": t.len} for t in toks]
            except Exception:
                tok_fail += 1
                tok_json = None

            split_id = match_split_rule_id(stext, split_rules)
            part_text = pmap.get(pid) or ""
            cs: int | None = None
            ce: int | None = None
            if part_text and stext:
                idx = part_text.find(stext)
                if idx >= 0:
                    cs = idx
                    ce = idx + len(stext)

            updates.append((Json(tok_json) if tok_json is not None else None, split_id, cs, ce, sid))

        execute_batch(
            cur,
            """
            UPDATE stage_1_clauses SET
              tokenization_json = %s,
              split_rule_id = %s::uuid,
              char_start = %s,
              char_end = %s
            WHERE id = %s::uuid
            """,
            updates,
            page_size=len(updates),
        )
        conn.commit()
        processed += len(rows)
        offset += lim
        logger.info("stage1 progress %s/%s tok_fail=%s", processed, total_target, tok_fail)

    cur.close()
    fail_pct = 100.0 * tok_fail / max(processed, 1)
    if fail_pct > 1.0:
        raise SystemExit(f"Kiwi 토큰화 실패율 {fail_pct:.2f}% > 1% — 정지")
    return {"processed": processed, "tok_fail": tok_fail, "tok_fail_pct": fail_pct}


def load_subtype_rules(sb, *, phase21: bool = False) -> list[dict[str, Any]]:
    rules = (
        sb.table("rule_classify_subtype")
        .select("*")
        .eq("enabled", True)
        .order("priority", desc=False)
        .execute()
        .data
        or []
    )
    rules.sort(key=lambda r: (r.get("priority") or 0, str(r.get("id") or "")))
    if not phase21 and len(rules) != EXPECTED_RULES_SUB:
        raise SystemExit(f"subtype rules {len(rules)} != {EXPECTED_RULES_SUB}")
    if phase21 and len(rules) < EXPECTED_RULES_SUB:
        raise SystemExit(f"Phase2.1: subtype rules {len(rules)} < {EXPECTED_RULES_SUB}")
    return rules


def run_stage2(sb, conn, rules: list[dict[str, Any]], *, batch_size: int, limit: int | None) -> dict[str, Any]:
    """§5 UNCLASSIFIED만 sub_type 업데이트."""
    cur = conn.cursor()
    processed = 0
    matched = 0
    total_loop = limit or EXPECTED_UNCLASSIFIED

    while processed < total_loop:
        lim = min(batch_size, total_loop - processed)
        batch = (
            sb.table("stage_2_elements")
            .select("id, clause_id, sub_type")
            .eq("sub_type", "UNCLASSIFIED")
            .order("id")
            .limit(lim)
            .execute()
            .data
            or []
        )
        if not batch:
            break

        cids = [b["clause_id"] for b in batch]
        clauses = (
            sb.table("stage_1_clauses")
            .select("id, source_text, tokenization_json")
            .in_("id", cids)
            .execute()
            .data
            or []
        )
        cmap = {c["id"]: c for c in clauses}

        ups: list[tuple[Any, ...]] = []
        for elem in batch:
            cl = cmap.get(elem["clause_id"])
            if not cl:
                continue
            tj = cl.get("tokenization_json")
            if not tj:
                continue
            if isinstance(tj, str):
                try:
                    tj = json.loads(tj)
                except json.JSONDecodeError:
                    continue
            stext = cl.get("source_text") or ""
            rule = pick_first_matching_subtype_rule(rules, tj, stext)
            if not rule:
                continue
            ar = {
                "phase": "phase_2",
                "method": "kiwi_subtype_rules",
                "sub_type_rule_id": rule["id"],
                "sub_type_rule_name": rule["rule_name"],
            }
            ups.append(
                (
                    rule["sub_type"],
                    Json(ar),
                    0.85,
                    elem["id"],
                )
            )
            matched += 1

        if ups:
            execute_batch(
                cur,
                """
                UPDATE stage_2_elements SET
                  sub_type = %s,
                  applied_rules = COALESCE(applied_rules, '{}'::jsonb) || %s::jsonb,
                  confidence_score = %s
                WHERE id = %s::uuid AND sub_type = 'UNCLASSIFIED'
                """,
                ups,
                page_size=len(ups),
            )
            conn.commit()

        processed += len(batch)
        logger.info("stage2 scanned=%s matched_total=%s batch=%s", processed, matched, len(batch))

    cur.close()
    return {"processed_u": processed, "matched": matched}


def run_stage2_phase21(
    conn, rules: list[dict[str, Any]], *, batch_size: int, limit: int | None
) -> dict[str, Any]:
    """§6.5 Phase 2.1 — Phase 1 제외 전 행 재분류 (매칭 없으면 UNCLASSIFIED)."""
    cur = conn.cursor()
    last_id: str | None = None
    scanned = 0
    matched = 0
    cap = limit or 10**12

    merge_sql = """
        UPDATE stage_2_elements SET
          sub_type = %s,
          applied_rules = COALESCE(applied_rules, '{}'::jsonb) || %s::jsonb,
          confidence_score = %s
        WHERE id = %s::uuid
        """
    nom_sql = """
        UPDATE stage_2_elements SET
          sub_type = 'UNCLASSIFIED',
          applied_rules = COALESCE(applied_rules, '{}'::jsonb) || %s::jsonb,
          confidence_score = 0
        WHERE id = %s::uuid
        """

    while scanned < cap:
        lim = min(batch_size, cap - scanned)
        if last_id is None:
            cur.execute(
                f"""
                SELECT e.id, e.clause_id, s1.source_text, s1.tokenization_json
                FROM stage_2_elements e
                INNER JOIN stage_1_clauses s1 ON s1.id = e.clause_id
                WHERE e.sub_type NOT IN %s
                ORDER BY e.id
                LIMIT %s
                """,
                (PHASE1_LOCKED_SUBTYPES, lim),
            )
        else:
            cur.execute(
                f"""
                SELECT e.id, e.clause_id, s1.source_text, s1.tokenization_json
                FROM stage_2_elements e
                INNER JOIN stage_1_clauses s1 ON s1.id = e.clause_id
                WHERE e.sub_type NOT IN %s AND e.id > %s::uuid
                ORDER BY e.id
                LIMIT %s
                """,
                (PHASE1_LOCKED_SUBTYPES, last_id, lim),
            )
        rows = cur.fetchall()
        if not rows:
            break
        last_id = rows[-1][0]

        ups_m: list[tuple[Any, ...]] = []
        ups_u: list[tuple[Any, ...]] = []
        for eid, _cid, stext, tj in rows:
            if not tj:
                nom = {"phase": "phase_2_1", "method": "kiwi_subtype_rules_no_token"}
                ups_u.append((Json(nom), eid))
                continue
            if isinstance(tj, str):
                try:
                    tj = json.loads(tj)
                except json.JSONDecodeError:
                    nom = {"phase": "phase_2_1", "method": "kiwi_subtype_rules_bad_json"}
                    ups_u.append((Json(nom), eid))
                    continue
            rule = pick_first_matching_subtype_rule(rules, tj, stext or "")
            if rule:
                ar = {
                    "phase": "phase_2_1",
                    "method": "kiwi_subtype_rules",
                    "sub_type_rule_id": rule["id"],
                    "sub_type_rule_name": rule["rule_name"],
                }
                ups_m.append((rule["sub_type"], Json(ar), 0.85, eid))
                matched += 1
            else:
                nom = {"phase": "phase_2_1", "method": "kiwi_subtype_rules_no_match"}
                ups_u.append((Json(nom), eid))

        if ups_m:
            execute_batch(cur, merge_sql, ups_m, page_size=len(ups_m))
        if ups_u:
            execute_batch(cur, nom_sql, ups_u, page_size=len(ups_u))
        conn.commit()
        scanned += len(rows)
        logger.info("phase21 stage2 scanned=%s matched_total=%s batch=%s", scanned, matched, len(rows))

    cur.close()
    return {"scanned_reclass": scanned, "matched": matched}


def verify_phase1_preserved(sb) -> int:
    """Phase 2.0 백업 대비 분류 행 덮어쓰기 검출."""
    conn = pg_conn()
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT COUNT(*) FROM stage_2_elements e
        INNER JOIN {BACKUP_S2} b ON e.id = b.id
        WHERE b.sub_type <> 'UNCLASSIFIED'
          AND e.sub_type IS DISTINCT FROM b.sub_type
        """
    )
    n = cur.fetchone()[0]
    cur.close()
    conn.close()
    return n


def verify_phase1_preserved_phase21(conn) -> int:
    """Phase 1 (5종) 절대 보전 — Phase2.1 시작 백업 대비."""
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT COUNT(*) FROM stage_2_elements e
        INNER JOIN {BACKUP_S2_P21} b ON e.id = b.id
        WHERE b.sub_type IN %s
          AND e.sub_type IS DISTINCT FROM b.sub_type
        """,
        (PHASE1_LOCKED_SUBTYPES,),
    )
    n = cur.fetchone()[0]
    cur.close()
    return n


def count_zero_match_rules(conn) -> tuple[list[str], int]:
    """활성 룰 중 매칭 row 0건인 rule_name 목록."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT r.rule_name
        FROM rule_classify_subtype r
        WHERE r.enabled = true
          AND (
            SELECT COUNT(*) FROM stage_2_elements e
            WHERE e.applied_rules->>'sub_type_rule_id' = r.id::text
               OR e.applied_rules->>'sub_type_rule' = r.rule_name
          ) = 0
        ORDER BY r.priority, r.rule_name
        """
    )
    names = [r[0] for r in cur.fetchall()]
    cur.close()
    return names, len(names)


def run_six_w(sb, conn, *, batch_size: int, limit: int | None) -> dict[str, Any]:
    """§5.6 — sub_type <> UNCLASSIFIED 인 행만, NULL 컬럼만 채움."""
    cur = conn.cursor()
    processed = 0
    filled = 0
    total_cap = limit or 10**9
    last_id: str | None = None

    fields = ("executor", "recipient", "what", "when_value", "where_value", "how", "condition")

    while processed < total_cap:
        lim = min(batch_size, total_cap - processed)
        q = (
            sb.table("stage_2_elements")
            .select(
                "id, clause_id, executor, recipient, what, when_value, where_value, how, condition, sub_type"
            )
            .neq("sub_type", "UNCLASSIFIED")
            .order("id")
            .limit(lim)
        )
        if last_id:
            q = q.gt("id", last_id)
        rows = q.execute().data or []
        if not rows:
            break
        last_id = rows[-1]["id"]

        cids = [r["clause_id"] for r in rows]
        clauses = (
            sb.table("stage_1_clauses")
            .select("id, source_text, tokenization_json")
            .in_("id", cids)
            .execute()
            .data
            or []
        )
        cmap = {c["id"]: c for c in clauses}

        ups: list[tuple[Any, ...]] = []
        for elem in rows:
            cl = cmap.get(elem["clause_id"])
            if not cl:
                continue
            tj = cl.get("tokenization_json")
            if isinstance(tj, str):
                try:
                    tj = json.loads(tj)
                except json.JSONDecodeError:
                    tj = []
            if not tj:
                continue
            ext = extract_six_w(tj, cl.get("source_text") or "")
            sets: dict[str, Any] = {}
            for f in fields:
                if elem.get(f) is None and ext.get(f):
                    sets[f] = ext[f]
            if not sets:
                continue
            ups.append(
                (
                    sets.get("executor"),
                    sets.get("recipient"),
                    sets.get("what"),
                    sets.get("when_value"),
                    sets.get("where_value"),
                    sets.get("how"),
                    sets.get("condition"),
                    elem["id"],
                )
            )
            filled += 1

        if ups:
            execute_batch(
                cur,
                """
                UPDATE stage_2_elements SET
                  executor = COALESCE(executor, %s),
                  recipient = COALESCE(recipient, %s),
                  what = COALESCE(what, %s),
                  when_value = COALESCE(when_value, %s),
                  where_value = COALESCE(where_value, %s),
                  how = COALESCE(how, %s),
                  condition = COALESCE(condition, %s)
                WHERE id = %s::uuid
                """,
                ups,
                page_size=len(ups),
            )
            conn.commit()

        processed += len(rows)
        logger.info("six_w processed=%s filled_rows=%s", processed, filled)

    cur.close()
    return {"processed_classified": processed, "rows_with_any_fill": filled}


def run_verification_queries(conn) -> dict[str, Any]:
    """§5.7 검증 지표."""
    cur = conn.cursor()
    metrics: dict[str, Any] = {}

    cur.execute(
        """
        SELECT 100.0 * COUNT(*) FILTER (WHERE tokenization_json IS NULL) / COUNT(*) AS tp,
               100.0 * COUNT(*) FILTER (WHERE char_start IS NULL) / COUNT(*) AS cp,
               100.0 * COUNT(*) FILTER (WHERE split_rule_id IS NULL) / COUNT(*) AS sp
        FROM stage_1_clauses
        """
    )
    tp, cp, sp = cur.fetchone()
    metrics["tokenization_null_pct"] = float(tp or 0)
    metrics["char_start_null_pct"] = float(cp or 0)
    metrics["split_rule_null_pct"] = float(sp or 0)

    cur.execute(
        """
        SELECT 100.0 * COUNT(*) FILTER (WHERE sub_type != 'UNCLASSIFIED') / COUNT(*) FROM stage_2_elements
        """
    )
    metrics["classified_pct"] = float(cur.fetchone()[0] or 0)

    cur.execute(
        """
        SELECT 100.0 * COUNT(*) FILTER (WHERE executor IS NOT NULL) / NULLIF(COUNT(*),0),
               100.0 * COUNT(*) FILTER (WHERE recipient IS NOT NULL) / NULLIF(COUNT(*),0),
               100.0 * COUNT(*) FILTER (WHERE what IS NOT NULL) / NULLIF(COUNT(*),0)
        FROM stage_2_elements WHERE sub_type != 'UNCLASSIFIED'
        """
    )
    ex, rc, wh = cur.fetchone()
    metrics["six_w_executor_pct"] = float(ex or 0)
    metrics["six_w_recipient_pct"] = float(rc or 0)
    metrics["six_w_what_pct"] = float(wh or 0)

    cur.execute(
        """
        WITH sample_articles AS (
          SELECT id FROM law_article ORDER BY random() LIMIT 100
        )
        SELECT COUNT(*) AS total_clauses,
               COUNT(*) FILTER (WHERE s2.sub_type != 'UNCLASSIFIED') AS classified
        FROM stage_2_elements s2
        JOIN stage_1_clauses s1 ON s1.id = s2.clause_id
        JOIN law_article_part lap ON lap.id = s1.part_id
        JOIN sample_articles sa ON sa.id = lap.article_id
        """
    )
    tot, cls = cur.fetchone()
    metrics["sample100_total"] = tot
    metrics["sample100_classified"] = cls
    metrics["sample100_pct"] = float(100.0 * cls / tot) if tot else 0.0

    cur.execute("SELECT COUNT(*) FROM stage_1_clauses")
    metrics["row_s1"] = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM stage_2_elements")
    metrics["row_s2"] = cur.fetchone()[0]

    cur.close()
    return metrics


def insert_verification_log(sb, metrics: dict[str, Any]) -> None:
    """§5.8 verification_log."""
    now = datetime.now(timezone.utc).isoformat()
    rows = [
        {
            "stage": 2,
            "check_name": "phase_2_classify_pct",
            "check_type": "AUTO_HOOK",
            "result_status": "PASS" if metrics["classified_pct"] >= 70 else "FAIL",
            "expected_value": ">=70%",
            "actual_value": f"{metrics['classified_pct']:.2f}%",
            "threshold": "70",
            "error_count": 0,
            "error_examples": [],
            "verified_at": now,
            "verified_by": "Cursor_Phase_2_2026-05-10",
            "notes": "UNCLASSIFIED 정밀 분류",
        },
        {
            "stage": 2,
            "check_name": "phase_2_six_w_executor",
            "check_type": "AUTO_HOOK",
            "result_status": "PASS" if metrics["six_w_executor_pct"] >= 50 else "FAIL",
            "expected_value": ">=50%",
            "actual_value": f"{metrics['six_w_executor_pct']:.2f}%",
            "threshold": "50",
            "error_count": 0,
            "error_examples": [],
            "verified_at": now,
            "verified_by": "Cursor_Phase_2",
            "notes": "6하원칙 executor",
        },
        {
            "stage": 2,
            "check_name": "phase_2_six_w_what",
            "check_type": "AUTO_HOOK",
            "result_status": "PASS" if metrics["six_w_what_pct"] >= 50 else "FAIL",
            "expected_value": ">=50%",
            "actual_value": f"{metrics['six_w_what_pct']:.2f}%",
            "threshold": "50",
            "error_count": 0,
            "error_examples": [],
            "verified_at": now,
            "verified_by": "Cursor_Phase_2",
            "notes": "6하원칙 what",
        },
        {
            "stage": 2,
            "check_name": "phase_2_sample_100",
            "check_type": "AUTO_HOOK",
            "result_status": "PASS" if metrics["sample100_pct"] >= 70 else "FAIL",
            "expected_value": ">=70%",
            "actual_value": f"{metrics['sample100_pct']:.2f}%",
            "threshold": "70",
            "error_count": 0,
            "error_examples": [],
            "verified_at": now,
            "verified_by": "Cursor_Phase_2",
            "notes": "100조문 sample",
        },
        {
            "stage": 1,
            "check_name": "phase_2_tokenization_filled",
            "check_type": "AUTO_HOOK",
            "result_status": "PASS" if metrics["tokenization_null_pct"] <= 0.1 else "FAIL",
            "expected_value": "<=0.1% NULL",
            "actual_value": f"{metrics['tokenization_null_pct']:.4f}%",
            "threshold": "99.9",
            "error_count": 0,
            "error_examples": [],
            "verified_at": now,
            "verified_by": "Cursor_Phase_2",
            "notes": "Stage1 tokenization_json",
        },
        {
            "stage": 1,
            "check_name": "phase_2_split_rule_filled",
            "check_type": "AUTO_HOOK",
            "result_status": "INFO",
            "expected_value": "~95% NULL fallback",
            "actual_value": f"{metrics['split_rule_null_pct']:.2f}% NULL",
            "threshold": "95",
            "error_count": 0,
            "error_examples": [],
            "verified_at": now,
            "verified_by": "Cursor_Phase_2",
            "notes": "split_rule_id",
        },
    ]
    sb.table("verification_log").insert(rows).execute()
    logger.info("verification_log inserted 6 rows")


def insert_verification_log_phase21(sb, metrics: dict[str, Any], zero_names: list[str]) -> None:
    """§6.8 Phase 2.1 verification_log."""
    now = datetime.now(timezone.utc).isoformat()
    zm_note = ",".join(zero_names[:12]) if zero_names else ""
    rows = [
        {
            "stage": 2,
            "check_name": "phase_2_1_classify_pct",
            "check_type": "AUTO_HOOK",
            "result_status": "PASS" if metrics["classified_pct"] >= 50 else "FAIL",
            "expected_value": ">=50%",
            "actual_value": f"{metrics['classified_pct']:.2f}%",
            "threshold": "50",
            "error_count": 0,
            "error_examples": [],
            "verified_at": now,
            "verified_by": "Cursor_Phase_2_1_2026-05-10",
            "notes": "Phase 2.1 분류율 (1차 목표)",
        },
        {
            "stage": 2,
            "check_name": "phase_2_1_sample_100",
            "check_type": "AUTO_HOOK",
            "result_status": "PASS" if metrics["sample100_pct"] >= 50 else "FAIL",
            "expected_value": ">=50%",
            "actual_value": f"{metrics['sample100_pct']:.2f}%",
            "threshold": "50",
            "error_count": 0,
            "error_examples": [],
            "verified_at": now,
            "verified_by": "Cursor_Phase_2_1",
            "notes": "100조문 sample",
        },
        {
            "stage": 2,
            "check_name": "phase_2_1_zero_match_rules",
            "check_type": "AUTO_HOOK",
            "result_status": "PASS" if metrics.get("zero_match_count", 0) == 0 else "FAIL",
            "expected_value": "0 rules",
            "actual_value": str(metrics.get("zero_match_count", 0)),
            "threshold": "0",
            "error_count": metrics.get("zero_match_count", 0),
            "error_examples": zero_names[:20],
            "verified_at": now,
            "verified_by": "Cursor_Phase_2_1",
            "notes": "0건 매칭 룰 수",
        },
        {
            "stage": 2,
            "check_name": "phase_2_1_six_w_executor",
            "check_type": "AUTO_HOOK",
            "result_status": "PASS" if metrics["six_w_executor_pct"] >= 50 else "FAIL",
            "expected_value": ">=50%",
            "actual_value": f"{metrics['six_w_executor_pct']:.2f}%",
            "threshold": "50",
            "error_count": 0,
            "error_examples": [],
            "verified_at": now,
            "verified_by": "Cursor_Phase_2_1",
            "notes": "6하 executor",
        },
        {
            "stage": 1,
            "check_name": "phase_2_1_tokenization_filled",
            "check_type": "AUTO_HOOK",
            "result_status": "PASS" if metrics["tokenization_null_pct"] <= 0.1 else "FAIL",
            "expected_value": "<=0.1% NULL",
            "actual_value": f"{metrics['tokenization_null_pct']:.4f}%",
            "threshold": "99.9",
            "error_count": 0,
            "error_examples": [],
            "verified_at": now,
            "verified_by": "Cursor_Phase_2_1",
            "notes": "tokenization_json 보전",
        },
        {
            "stage": 2,
            "check_name": "phase_2_1_phase1_preserved",
            "check_type": "AUTO_HOOK",
            "result_status": "PASS" if metrics.get("phase1_overwrites", 0) == 0 else "FAIL",
            "expected_value": "0",
            "actual_value": str(metrics.get("phase1_overwrites", 0)),
            "threshold": "0",
            "error_count": metrics.get("phase1_overwrites", 0),
            "error_examples": [],
            "verified_at": now,
            "verified_by": "Cursor_Phase_2_1",
            "notes": "Phase1 8209 보전",
        },
    ]
    sb.table("verification_log").insert(rows).execute()
    logger.info("verification_log Phase2.1 inserted 6 rows")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--only",
        choices=(
            "checks",
            "backup",
            "rules",
            "stage1",
            "stage2",
            "sixw",
            "verify",
            "log",
            "all",
            "pipeline",
        ),
        default="all",
    )
    ap.add_argument(
        "--phase21",
        action="store_true",
        help="Phase 2.1 모드 (명세 Cursor_Phase_2_1_Rule_Redesign_Spec.md)",
    )
    ap.add_argument(
        "--phase22",
        action="store_true",
        help="Phase 2.2 v1.2 Pipeline (Cursor_Phase_2_2_Pipeline_Engine_Spec_v1_2.md)",
    )
    ap.add_argument("--limit", type=int, default=None, help="스모크: 각 단계 최대 row")
    ap.add_argument("--batch-stage1", type=int, default=1000)
    ap.add_argument("--batch-stage2", type=int, default=500)
    ap.add_argument("--batch-sixw", type=int, default=400)
    args = ap.parse_args()

    sb = get_supabase()
    conn = pg_conn()

    if args.phase22:
        only = args.only
        if only in ("checks", "all"):
            run_entry_checks_phase22(sb)
        if only in ("backup", "all"):
            run_backup_phase22(conn)
        if only in ("rules", "all"):
            apply_phase_22_schema(conn)
            apply_phase_22_rule_changes(conn)
        if only in ("pipeline", "all"):
            run_phase22_pipeline(sb)
        conn.close()
        return 0

    if args.phase21:
        if args.only == "log":
            m = run_verification_queries(conn)
            zm, zc = count_zero_match_rules(conn)
            m["zero_match_count"] = zc
            m["zero_match_rule_names"] = zm
            m["phase1_overwrites"] = verify_phase1_preserved_phase21(conn)
            insert_verification_log_phase21(sb, m, zm)
            conn.close()
            return 0
        if args.only in ("checks", "all"):
            run_entry_checks_phase21(sb)
        if args.only in ("backup", "all"):
            run_backup_phase21(conn)
        if args.only in ("rules", "all"):
            apply_phase_21_rule_changes(conn)
        rules = (
            load_subtype_rules(sb, phase21=True)
            if args.only in ("stage2", "all")
            else []
        )
        if args.only in ("stage1", "all"):
            run_stage1(sb, conn, batch_size=args.batch_stage1, limit=args.limit)
        if args.only in ("stage2", "all"):
            run_stage2_phase21(
                conn, rules, batch_size=args.batch_stage2, limit=args.limit
            )
        if args.only in ("sixw", "all"):
            run_six_w(sb, conn, batch_size=args.batch_sixw, limit=args.limit)
        m: dict[str, Any] = {}
        if args.only in ("verify", "log", "all"):
            m = run_verification_queries(conn)
            zm, zc = count_zero_match_rules(conn)
            m["zero_match_count"] = zc
            m["zero_match_rule_names"] = zm
            m["phase1_overwrites"] = verify_phase1_preserved_phase21(conn)
            logger.info("metrics: %s", json.dumps({k: v for k, v in m.items() if k != "zero_match_rule_names"}, ensure_ascii=False))
            if zm:
                logger.warning("zero_match rules (%s): %s", zc, zm[:15])

        if args.only in ("log", "all"):
            insert_verification_log_phase21(sb, m, m.get("zero_match_rule_names", []))

        if args.only in ("verify", "all"):
            if m.get("classified_pct", 0) < 50:
                conn.close()
                raise SystemExit(
                    f"Phase2.1 분류율 {m['classified_pct']:.2f}% < 50% — 정지 (명세 §9)"
                )
            if m.get("tokenization_null_pct", 0) > 0.1:
                conn.close()
                raise SystemExit("tokenization_json NULL > 0.1% — 정지")
            if m.get("row_s1") != EXPECTED_TOTAL or m.get("row_s2") != EXPECTED_TOTAL:
                conn.close()
                raise SystemExit("row 수 변동 — 정지")
            if m.get("phase1_overwrites", 0) > 0:
                conn.close()
                raise SystemExit(
                    f"Phase 1 분류 변동 {m['phase1_overwrites']}건 — 정지"
                )
            if m.get("zero_match_count", 0) >= 3:
                conn.close()
                raise SystemExit(
                    f"0건 매칭 룰 {m['zero_match_count']}개 ≥ 3 — 정지 (명세 §9)"
                )
        conn.close()
        return 0

    # --- Phase 2.0 (기본) ---
    if args.only in ("checks", "all"):
        run_entry_checks(sb)

    if args.only in ("backup", "all"):
        run_backup(conn)

    rules = load_subtype_rules(sb) if args.only in ("stage2", "all") else []

    if args.only in ("stage1", "all"):
        run_stage1(sb, conn, batch_size=args.batch_stage1, limit=args.limit)

    if args.only in ("stage2", "all"):
        run_stage2(sb, conn, rules, batch_size=args.batch_stage2, limit=args.limit)

    if args.only in ("sixw", "all"):
        run_six_w(sb, conn, batch_size=args.batch_sixw, limit=args.limit)

    m = {}
    if args.only in ("verify", "log", "all"):
        m = run_verification_queries(conn)
        logger.info("metrics: %s", json.dumps(m, ensure_ascii=False))

    if args.only in ("log", "all"):
        insert_verification_log(sb, m)

    if args.only in ("verify", "all"):
        if m.get("classified_pct", 0) < 60:
            raise SystemExit(f"분류율 {m['classified_pct']:.2f}% < 60% — 정지 (명세 §8)")
        if m.get("tokenization_null_pct", 0) > 0.1:
            raise SystemExit("tokenization_json NULL > 0.1% — 정지")
        if m.get("row_s1") != EXPECTED_TOTAL or m.get("row_s2") != EXPECTED_TOTAL:
            raise SystemExit("row 수 변동 — 정지")
        bad = verify_phase1_preserved(sb)
        if bad > 0:
            raise SystemExit(f"Phase 1 분류 덮어쓰기 {bad}건 — 정지")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
