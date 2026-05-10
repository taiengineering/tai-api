"""Phase 2.2 — DB CHECK 확장 + 룰 비활성·sub_type 재매핑·신규 INSERT."""

from __future__ import annotations

import logging
from typing import Any

import psycopg2

from engine.phase_22_constants import SUB_TYPES_FOR_CHECK

logger = logging.getLogger(__name__)

# 비활성 (FP): Phase 2.1 보조 AS_본다 3종 + DELEGATION_ETRAH FP
DISABLE_RULE_NAMES: tuple[str, ...] = (
    "AS_본다_WA_GATDA",
    "AS_본다_GWA_GATDA",
    "AS_본다_TTOHAN_GATDA",
    "DELEGATION_ETRAHADA",
)

# rule_name -> 새 sub_type (기존 행 UPDATE)
RULE_SUBTYPE_REMAP: tuple[tuple[str, str], ...] = (
    ("OBLIGATION_DETAIL_GWAN_SAHANG", "ENUMERATION_ITEM"),
    ("WEAK_JUNYONG_HADA", "REFERENCE_INVOCATION"),
)

# (rule_name, sub_type, match_strategy, pattern, pattern_position, priority, description)
PHASE22_RULE_INSERTS: tuple[tuple[str, str, str, str, str, int, str], ...] = (
    (
        "ENUMERATION_LIST_INTRO_DAUM",
        "ENUMERATION_LIST_INTRO",
        "COMPOSITE",
        r"(다음\s*각\s*호(?:와)?\s*같다|다음과\s*같다)",
        "ANY",
        12,
        "Phase2.2: 다음 각 호·다음과 같다",
    ),
    (
        "REFERENCE_TO_ATTACHMENT_BYULPYO",
        "REFERENCE_TO_ATTACHMENT",
        "COMPOSITE",
        r"별표\s*\d",
        "ANY",
        26,
        "Phase2.2: 별표 참조",
    ),
    (
        "REFERENCE_TO_ATTACHMENT_BYULJI",
        "REFERENCE_TO_ATTACHMENT",
        "COMPOSITE",
        r"별지\s*\d",
        "ANY",
        27,
        "Phase2.2: 별지 참조",
    ),
    (
        "OBLIGATION_HEADER_YA_COMPOSITE",
        "OBLIGATION_HEADER",
        "COMPOSITE",
        r"(해야\s*한다|하여야\s*한다)",
        "ANY",
        14,
        "Phase2.2: 해야 한다 / 하여야 한다",
    ),
    (
        "OBLIGATION_HAS_DUTY_COMPOSITE",
        "OBLIGATION_HEADER",
        "COMPOSITE",
        r"(의무가\s*있(?:다|습니다)|의무는\s*있(?:다|습니다))",
        "ANY",
        15,
        "Phase2.2: 의무가/는 있다",
    ),
    (
        "PROHIBITION_HEADER_AN_DOEN_COMP",
        "PROHIBITION_HEADER",
        "COMPOSITE",
        r"안\s*된다",
        "ANY",
        28,
        "Phase2.2: 안 된다",
    ),
    (
        "PROHIBITION_HEADER_MOTHAN_COMP",
        "PROHIBITION_HEADER",
        "COMPOSITE",
        r"못한다",
        "ANY",
        29,
        "Phase2.2: 못한다",
    ),
    (
        "ENUMERATION_ITEM_NOMINAL_LAST",
        "ENUMERATION_ITEM",
        "LAST_MEANINGFUL_TAG_IN",
        "NNG,NNP,NNB,NR",
        "ANY",
        250,
        "Phase2.2: 명사 종결 단편 (저우선)",
    ),
)


def apply_phase_22_schema(conn: psycopg2.extensions.connection) -> None:
    """§4 CHECK 확장 + match_strategy 확장."""
    cur = conn.cursor()
    parts = ", ".join(f"'{x}'::text" for x in SUB_TYPES_FOR_CHECK)
    for tbl, cname in (
        ("stage_2_elements", "stage_2_elements_sub_type_check"),
        ("rule_classify_subtype", "rule_classify_subtype_sub_type_check"),
    ):
        cur.execute(f"ALTER TABLE {tbl} DROP CONSTRAINT IF EXISTS {cname}")
        cur.execute(
            f"""
            ALTER TABLE {tbl} ADD CONSTRAINT {cname}
            CHECK (sub_type = ANY (ARRAY[{parts}]))
            """
        )
        logger.info("applied sub_type CHECK on %s", tbl)

    cur.execute(
        "ALTER TABLE rule_classify_subtype DROP CONSTRAINT IF EXISTS rule_classify_subtype_match_strategy_check"
    )
    cur.execute(
        """
        ALTER TABLE rule_classify_subtype ADD CONSTRAINT rule_classify_subtype_match_strategy_check
        CHECK (match_strategy = ANY (ARRAY[
          'TAIL_POS'::text,'HEAD_TOKEN'::text,'POS_SEQUENCE'::text,'COMPOSITE'::text,
          'LAST_MEANINGFUL_TAG_IN'::text
        ]))
        """
    )
    conn.commit()
    cur.close()
    logger.info("Phase2.2 schema: match_strategy + sub_type CHECK 완료")


def apply_phase_22_rule_changes(conn: psycopg2.extensions.connection) -> dict[str, Any]:
    """§5–§6 룰 비활성·재매핑·INSERT."""
    cur = conn.cursor()
    disabled = 0
    for rn in DISABLE_RULE_NAMES:
        cur.execute(
            """
            UPDATE rule_classify_subtype SET enabled = false, updated_at = NOW()
            WHERE rule_name = %s
            """,
            (rn,),
        )
        disabled += cur.rowcount

    remapped = 0
    for rn, st in RULE_SUBTYPE_REMAP:
        cur.execute(
            """
            UPDATE rule_classify_subtype SET sub_type = %s, updated_at = NOW()
            WHERE rule_name = %s
            """,
            (st, rn),
        )
        remapped += cur.rowcount

    inserted = 0
    for rule_name, sub_type, mstrat, pat, pos, pri, desc in PHASE22_RULE_INSERTS:
        cur.execute(
            "SELECT 1 FROM rule_classify_subtype WHERE rule_name = %s",
            (rule_name,),
        )
        if cur.fetchone():
            continue
        cur.execute(
            """
            INSERT INTO rule_classify_subtype
              (rule_name, sub_type, match_strategy, pattern, pattern_position, priority, enabled, description)
            VALUES (%s, %s, %s, %s, %s, %s, true, %s)
            """,
            (rule_name, sub_type, mstrat, pat, pos, pri, desc),
        )
        inserted += 1

    conn.commit()
    cur.close()
    out = {"disabled_rules": disabled, "remapped_rules": remapped, "inserted_rules": inserted}
    logger.info("Phase2.2 rule changes: %s", out)
    return out
