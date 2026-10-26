"""WO-027 C3 — STEP4E_DOWN_FAIL_AUDIT.sql 구조 검증

GPT C3 IV 지시: 실패 Audit SQL의 가드 로직을 격리 테스트로 검증.

T-FA-01: SQL 파일에 INSERT가 DO 블록 내부에만 존재 (블록 외부 실행 불가)
T-FA-02: 플레이스홀더 3개 각각에 대한 독립 가드 조건이 존재
T-FA-03: 가드 조건이 '변수 = 플레이스홀더 리터럴' 형태 (항등 비교가 아님)
T-FA-04: 파일 전체에 DO 블록이 정확히 1개 존재
T-FA-05: DO 블록 외부에 DML 키워드(INSERT/UPDATE/DELETE)가 없음

Production DB write = 0 (SQL 구조만 정적 분석).
"""
from __future__ import annotations

import re
from pathlib import Path

_FAIL_AUDIT_SQL = Path(
    "docs/sql/20261026_WP_PERSISTENCE_02A_STEP4E_DOWN_FAIL_AUDIT.sql"
)

_PLACEHOLDERS = ["ABORT_GATE_HERE", "ERROR_REASON_HERE", "ACTOR_UUID_HERE"]
_VARIABLES = ["v_abort_gate", "v_error_reason", "v_actor"]


def _load_sql() -> str:
    return _FAIL_AUDIT_SQL.read_text(encoding="utf-8")


def _strip_comments(sql: str) -> str:
    """단일행 주석 제거 (-- ...)."""
    return re.sub(r"--[^\n]*", "", sql)


def _extract_do_body(sql: str) -> str:
    """DO $$ ... END $$; 사이 내용 반환."""
    m = re.search(r"DO\s+\$\$(.+?)END\s+\$\$", sql, re.DOTALL | re.IGNORECASE)
    assert m, "DO $$ ... END $$; 블록을 찾을 수 없음"
    return m.group(1)


def _content_outside_do(sql: str) -> str:
    """DO 블록 밖의 내용 반환."""
    return re.sub(r"DO\s+\$\$.*?END\s+\$\$\s*;", "", sql, flags=re.DOTALL | re.IGNORECASE)


# ─── T-FA-01: INSERT가 DO 블록 내부에만 존재 ──────────────────────────

def test_FA01_insert_only_inside_do_block():
    """T-FA-01: INSERT는 DO 블록 내부에만 있어야 한다."""
    sql = _load_sql()
    body = _extract_do_body(sql)
    outside = _strip_comments(_content_outside_do(sql))

    assert "INSERT" in body.upper(), "DO 블록 내부에 INSERT가 없음"
    # 블록 외부에 DML이 없어야 함 (주석 제거 후)
    assert "INSERT" not in outside.upper(), "DO 블록 외부에 INSERT가 존재 — 조건 없이 실행될 수 있음"


# ─── T-FA-02: 플레이스홀더 3개 각각 독립 가드 존재 ─────────────────────

def test_FA02_each_placeholder_has_independent_guard():
    """T-FA-02: 세 플레이스홀더 각각에 대한 독립적인 IF ... RAISE EXCEPTION이 있어야 한다."""
    sql = _load_sql()
    body = _extract_do_body(sql)

    for ph in _PLACEHOLDERS:
        # 각 플레이스홀더가 IF 조건과 RAISE EXCEPTION 안에 함께 등장해야 함
        pattern = rf"IF\b[^;]*{re.escape(ph)}[^;]*THEN"
        assert re.search(pattern, body, re.DOTALL | re.IGNORECASE), (
            f"플레이스홀더 '{ph}'에 대한 IF 가드를 찾을 수 없음"
        )
        # 해당 RAISE EXCEPTION이 이어서 나와야 함
        guard_block = re.search(
            rf"IF\b[^;]*{re.escape(ph)}[^;]*THEN.*?END\s+IF",
            body, re.DOTALL | re.IGNORECASE,
        )
        assert guard_block and "RAISE EXCEPTION" in guard_block.group(0).upper(), (
            f"플레이스홀더 '{ph}'의 가드에 RAISE EXCEPTION이 없음"
        )


# ─── T-FA-03: 가드가 '변수 = 플레이스홀더' 형태 (항등 비교 아님) ─────────

def test_FA03_guard_uses_variable_not_identity_comparison():
    """T-FA-03: 가드 조건이 변수(v_*)와 플레이스홀더 리터럴을 비교해야 한다.
    '플레이스홀더 = 플레이스홀더' (항등비교) 형태이면 치환 후에도 항상 참이 됨.
    """
    sql = _load_sql()
    body = _strip_comments(_extract_do_body(sql))

    for var, ph in zip(_VARIABLES, _PLACEHOLDERS):
        # 각 변수가 해당 플레이스홀더 리터럴과 비교되어야 함
        pattern = rf"{re.escape(var)}\s*=\s*'{re.escape(ph)}'"
        assert re.search(pattern, body, re.IGNORECASE), (
            f"'{var} = {ph!r}' 형태의 가드를 찾을 수 없음 — 항등 비교 여부 확인"
        )

    # 항등 비교 방지: 'PLACEHOLDER' = 'PLACEHOLDER' 형태가 없어야 함
    for ph in _PLACEHOLDERS:
        identity = rf"'{re.escape(ph)}'\s*=\s*'{re.escape(ph)}'"
        assert not re.search(identity, body, re.IGNORECASE), (
            f"항등 비교 '{ph}' = '{ph}' 발견 — 항상 참이므로 실제 치환 여부를 검증하지 못함"
        )


# ─── T-FA-04: DO 블록이 정확히 1개 ────────────────────────────────────

def test_FA04_exactly_one_do_block():
    """T-FA-04: 파일에 DO 블록이 정확히 1개여야 한다."""
    sql = _load_sql()
    matches = re.findall(r"\bDO\s+\$\$", sql, re.IGNORECASE)
    assert len(matches) == 1, f"DO 블록이 {len(matches)}개 발견 (expected 1)"


# ─── T-FA-05: DO 블록 외부에 DML 없음 ────────────────────────────────

def test_FA05_no_dml_outside_do_block():
    """T-FA-05: 주석 제거 후 DO 블록 외부에 DML 키워드가 없어야 한다."""
    sql = _load_sql()
    outside = _strip_comments(_content_outside_do(sql))

    for keyword in ("INSERT", "UPDATE", "DELETE"):
        assert keyword not in outside.upper(), (
            f"DO 블록 외부에 {keyword} 발견 — 무조건 실행될 위험"
        )
