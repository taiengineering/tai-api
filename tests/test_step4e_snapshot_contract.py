"""WO-027-C3-SNAPSHOT-CONTRACT-DELTA-001 R2+P0 — STEP4E 스냅샷 계약 검증

GPT IV R1 FAIL 3건 보정 + GPT Source IV P0(도메인 누락) 보정 후 구조 검증.

T-SNAP-01: STEP4E_UP v_before에 evidence_candidate_decision_ref 키 존재
T-SNAP-02: STEP4E_UP v_after에 evidence_candidate_decision_ref 키 존재
T-SNAP-03: STEP4E_UP S1-5 게이트 존재 (ABORT [S1-5])
T-SNAP-04: S1-5 비교가 ::text 캐스트 없이 UUID = UUID 형태
T-SNAP-05: S1-5 서브쿼리에 COUNT(*) AS cnt 존재
T-SNAP-06: S1-5에 COALESCE(rd.cnt, 0) <> 1 패턴 존재
T-SNAP-07: S1-5에 review_status = 'APPROVED' 조건 존재
T-SNAP-08: S1-5 서브쿼리에 LEFT JOIN 존재 (0건 케이스 커버)
T-SNAP-09: STEP4E_DOWN v_before에 evidence_candidate_decision_ref 키 존재
T-SNAP-10: UP/DOWN 모든 decision_ref 조회에 review_domain='EVIDENCE' 조건 존재

Production DB write = 0 (정적 분석 전용).
"""
from __future__ import annotations

import re
from pathlib import Path

_UP_SQL   = Path("docs/sql/20261026_WP_PERSISTENCE_02A_STEP4E_UP.sql")
_DOWN_SQL = Path("docs/sql/20261026_WP_PERSISTENCE_02A_STEP4E_DOWN.sql")


def _load(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _strip_line_comments(sql: str) -> str:
    return re.sub(r"--[^\n]*", "", sql)


def _extract_before_block(sql: str) -> str:
    m = re.search(
        r"INTO\s+v_before\s*;",
        sql, re.IGNORECASE,
    )
    assert m, "v_before INTO 구문을 찾을 수 없음"
    return sql[: m.end()]


def _extract_after_block(sql: str) -> str:
    m = re.search(
        r"INTO\s+v_after\s*;",
        sql, re.IGNORECASE,
    )
    assert m, "v_after INTO 구문을 찾을 수 없음"
    return sql[: m.end()]


def _extract_s1_5_block(sql: str) -> str:
    m = re.search(
        r"\[S1-5\].+?END\s+IF\s*;",
        sql, re.DOTALL | re.IGNORECASE,
    )
    assert m, "S1-5 게이트 블록을 찾을 수 없음"
    # S1-5 주석부터 END IF; 까지 포함하도록 앞 방향으로 확장
    start = sql.rfind("-- [S1-5]", 0, m.start())
    if start == -1:
        start = sql.rfind("IF EXISTS", 0, m.start())
    return sql[start: m.end()]


# ─── T-SNAP-01 ────────────────────────────────────────────────────────────────

def test_SNAP01_up_v_before_has_decision_ref():
    """T-SNAP-01: STEP4E_UP v_before에 evidence_candidate_decision_ref 존재."""
    sql = _load(_UP_SQL)
    before = _extract_before_block(sql)
    assert "evidence_candidate_decision_ref" in before, (
        "v_before에 evidence_candidate_decision_ref 없음 (C2-FINAL §4-2 미충족)"
    )


# ─── T-SNAP-02 ────────────────────────────────────────────────────────────────

def test_SNAP02_up_v_after_has_decision_ref():
    """T-SNAP-02: STEP4E_UP v_after에 evidence_candidate_decision_ref 존재."""
    sql = _load(_UP_SQL)
    after = _extract_after_block(sql)
    assert "evidence_candidate_decision_ref" in after, (
        "v_after에 evidence_candidate_decision_ref 없음"
    )


# ─── T-SNAP-03 ────────────────────────────────────────────────────────────────

def test_SNAP03_s1_5_gate_exists():
    """T-SNAP-03: STEP4E_UP에 S1-5 게이트 (ABORT [S1-5]) 존재."""
    sql = _load(_UP_SQL)
    assert "ABORT [S1-5]" in sql, "S1-5 게이트가 STEP4E_UP에 없음"


# ─── T-SNAP-04 ────────────────────────────────────────────────────────────────

def test_SNAP04_no_text_cast_in_s1_5():
    """T-SNAP-04: S1-5 비교식에 ::text 캐스트 없음.

    GPT IV R1 P0-A: source_entity_id는 uuid 타입 — ::text 캐스트는
    'operator does not exist: uuid = text' 오류를 유발한다.
    """
    sql = _load(_UP_SQL)
    block = _extract_s1_5_block(sql)
    assert "::text" not in block.lower(), (
        "S1-5 블록에 ::text 캐스트 발견 — UUID 비교에 캐스트 불필요 (P0-A)"
    )


# ─── T-SNAP-05 ────────────────────────────────────────────────────────────────

def test_SNAP05_count_in_s1_5_subquery():
    """T-SNAP-05: S1-5 서브쿼리에 COUNT(*) AS cnt 존재."""
    sql = _load(_UP_SQL)
    block = _extract_s1_5_block(sql)
    assert re.search(r"COUNT\s*\(\s*\*\s*\)\s+AS\s+cnt", block, re.IGNORECASE), (
        "S1-5에 COUNT(*) AS cnt 없음 (P0-B: 카디널리티 검증 필요)"
    )


# ─── T-SNAP-06 ────────────────────────────────────────────────────────────────

def test_SNAP06_coalesce_ne_1_in_s1_5():
    """T-SNAP-06: S1-5에 COALESCE(rd.cnt, 0) <> 1 패턴 존재.

    GPT IV R1 P0-B: IS NULL만으로는 2건+ 중복을 차단하지 못한다.
    """
    sql = _load(_UP_SQL)
    block = _extract_s1_5_block(sql)
    assert re.search(r"COALESCE\s*\(\s*rd\.cnt\s*,\s*0\s*\)\s*<>\s*1", block, re.IGNORECASE), (
        "S1-5에 COALESCE(rd.cnt, 0) <> 1 없음 — IS NULL 단독 사용 시 2건+ 미차단 (P0-B)"
    )


# ─── T-SNAP-07 ────────────────────────────────────────────────────────────────

def test_SNAP07_review_status_approved_in_s1_5():
    """T-SNAP-07: S1-5에 review_status = 'APPROVED' 조건 존재.

    GPT IV R1 P0-C: fn_validate_review_authority() 트리거가
    review_action='APPROVE' 시 review_status='APPROVED'로 설정한다.
    review_action만 체크하면 트리거 미실행 행을 허용할 수 있다.
    """
    sql = _load(_UP_SQL)
    block = _extract_s1_5_block(sql)
    assert re.search(r"review_status\s*=\s*'APPROVED'", block, re.IGNORECASE), (
        "S1-5에 review_status = 'APPROVED' 없음 (P0-C)"
    )


# ─── T-SNAP-08 ────────────────────────────────────────────────────────────────

def test_SNAP08_left_join_in_s1_5():
    """T-SNAP-08: S1-5 서브쿼리가 LEFT JOIN 사용 (0건 케이스 커버).

    INNER JOIN 이면 결정 0건인 efc 행 자체가 제외되어 0건 케이스를 감지하지 못한다.
    """
    sql = _load(_UP_SQL)
    block = _extract_s1_5_block(sql)
    assert re.search(r"\bLEFT\s+JOIN\b", block, re.IGNORECASE), (
        "S1-5에 LEFT JOIN 없음 — INNER JOIN은 결정 0건 케이스를 차단하지 못함"
    )


# ─── T-SNAP-09 ────────────────────────────────────────────────────────────────

def test_SNAP09_down_v_before_has_decision_ref():
    """T-SNAP-09: STEP4E_DOWN v_before에 evidence_candidate_decision_ref 존재 (C2-FINAL §4-4)."""
    sql = _load(_DOWN_SQL)
    before = _extract_before_block(sql)
    assert "evidence_candidate_decision_ref" in before, (
        "STEP4E_DOWN v_before에 evidence_candidate_decision_ref 없음 (C2-FINAL §4-4 미충족)"
    )


# ─── T-SNAP-10 ────────────────────────────────────────────────────────────────

def test_SNAP10_review_domain_evidence_in_all_decision_queries():
    """T-SNAP-10: UP/DOWN 모든 runtime_review_decision 조회에 review_domain='EVIDENCE' 존재.

    GPT Source IV P0: review_domain 없으면 다른 도메인 승인이 Evidence 승인으로 잘못 집계됨.
    UP 3곳(v_before·v_after JOIN, S1-5 WHERE) + DOWN 2곳(v_before·v_after JOIN) = 총 5곳.
    """
    up_sql   = _load(_UP_SQL)
    down_sql = _load(_DOWN_SQL)

    up_count   = up_sql.count("review_domain = 'EVIDENCE'")
    down_count = down_sql.count("review_domain = 'EVIDENCE'")

    assert up_count >= 3, (
        f"STEP4E_UP에 review_domain = 'EVIDENCE' {up_count}곳 — 최소 3곳 필요 "
        "(v_before JOIN, v_after JOIN, S1-5 WHERE)"
    )
    assert down_count >= 2, (
        f"STEP4E_DOWN에 review_domain = 'EVIDENCE' {down_count}곳 — 최소 2곳 필요 "
        "(v_before JOIN, v_after JOIN)"
    )
