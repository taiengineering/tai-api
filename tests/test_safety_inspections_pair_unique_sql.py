"""OBJ-01 KNOT-3C2 — safety_inspections schedule-pair UNIQUE INDEX contract tests.

up/down 아티팩트 텍스트 정적 검증(T1-T15 + LOCK). DB 접속 없음. production
Python/Router/Service 변경 0 (이 테스트만 신규).
"""
from __future__ import annotations

import os
import re

HERE = os.path.dirname(__file__)
UP = os.path.abspath(os.path.join(HERE, "..", "docs", "sql",
                                  "20260827_safety_inspections_pair_unique_up.sql"))
DOWN = os.path.abspath(os.path.join(HERE, "..", "docs", "sql",
                                    "20260827_safety_inspections_pair_unique_down.sql"))

INDEX_NAME = "uq_safety_inspections_assignment_factory"


def _up() -> str:
    with open(UP, encoding="utf-8") as f:
        return f.read()


def _down() -> str:
    with open(DOWN, encoding="utf-8") as f:
        return f.read()


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).lower()


# T1 — CREATE UNIQUE INDEX with the exact name
def test_create_unique_index_exact_name():
    n = _norm(_up())
    assert f"create unique index {INDEX_NAME}" in n
    assert "create unique index if not exists" not in n   # (also T10)


# T2 — columns exact = (assignment_id, factory_id)
def test_columns_exact_pair():
    n = _norm(_up())
    assert f"create unique index {INDEX_NAME} on public.safety_inspections (assignment_id, factory_id)" in n


# T3 — order exact = assignment_id then factory_id
def test_column_order_exact():
    n = _norm(_up())
    m = re.search(r"on public\.safety_inspections \(([^)]*)\)", n)
    assert m
    cols = [c.strip() for c in m.group(1).split(",")]
    assert cols == ["assignment_id", "factory_id"]


# T4 — predicate exact semantic = WHERE assignment_id IS NOT NULL
def test_predicate_exact():
    n = _norm(_up())
    assert f"(assignment_id, factory_id) where assignment_id is not null" in n
    # predicate does not add factory_id IS NOT NULL (implied by pair CHECK)
    assert "where assignment_id is not null and factory_id is not null" not in n


# T5 — no standalone UNIQUE(assignment_id) single-column index
def test_no_standalone_assignment_unique():
    n = _norm(_up())
    assert "(assignment_id)" not in n            # only the pair (assignment_id, factory_id) exists
    assert "(assignment_id, factory_id)" in n


# T6 — no assignment_id NOT NULL change
def test_no_assignment_not_null_change():
    n = _norm(_up())
    assert "alter column assignment_id set not null" not in n
    assert "alter column assignment_id drop not null" not in n


# T7 — no factory_id NOT NULL change
def test_no_factory_not_null_change():
    n = _norm(_up())
    assert "alter column factory_id set not null" not in n
    assert "alter column factory_id drop not null" not in n


# T8 — duplicate-pair fail-closed PRECHECK present (group + having + raise)
def test_duplicate_precheck_present():
    n = _norm(_up())
    assert "group by assignment_id, factory_id having count(*) > 1" in n
    assert "precheck p1 failed" in n
    assert "raise exception" in n


# T9 — broken-pair fail-closed PRECHECK present
def test_broken_pair_precheck_present():
    n = _norm(_up())
    assert "(assignment_id is null and factory_id is not null)" in n
    assert "(assignment_id is not null and factory_id is null)" in n
    assert "precheck p2 failed" in n


# T10 — same-name existing index is NOT hidden by IF NOT EXISTS; explicit P3 check
def test_no_if_not_exists_and_p3_present():
    n = _norm(_up())
    assert "create unique index if not exists" not in n
    assert "precheck p3 failed" in n
    assert "c.relname = 'uq_safety_inspections_assignment_factory'" in n


# T11 — no safety_inspections INSERT
def test_no_base_insert():
    n = _norm(_up() + "\n" + _down())
    assert "insert into public.safety_inspections" not in n
    assert "insert into safety_inspections" not in n


# T12 — no safety_inspections UPDATE
def test_no_base_update():
    n = _norm(_up() + "\n" + _down())
    assert "update public.safety_inspections" not in n
    assert "update safety_inspections" not in n


# T13 — no safety_inspections DELETE
def test_no_base_delete():
    n = _norm(_up() + "\n" + _down())
    assert "delete from public.safety_inspections" not in n
    assert "delete from safety_inspections" not in n


# T14 — existing single-column idx_safety_inspections_assignment is NOT dropped
def test_old_assignment_index_not_dropped():
    n = _norm(_up() + "\n" + _down())
    # a mere comment mention is fine; only an actual DROP of that index is forbidden
    assert not re.search(r"drop\s+index[^;]*idx_safety_inspections_assignment", n)


# T15 — DOWN drops ONLY the target unique index (one DROP INDEX, no other DDL)
def test_down_drops_only_target_index():
    n = _norm(_down())
    assert f"drop index if exists public.{INDEX_NAME}" in n
    assert n.count("drop index") == 1
    assert "drop table" not in n
    assert "create " not in n
    assert "alter " not in n


# LOCK — UP takes SHARE MODE lock on safety_inspections during precheck+build
def test_up_locks_table_share_mode():
    n = _norm(_up())
    assert "lock table public.safety_inspections in share mode" in n


if __name__ == "__main__":
    g = dict(globals())
    tests = sorted((k, v) for k, v in g.items() if k.startswith("test_") and callable(v))
    p = f = 0
    for name, fn in tests:
        try:
            fn(); print(f"PASS {name}"); p += 1
        except Exception as e:
            import traceback
            print(f"FAIL {name}: {e}"); traceback.print_exc(); f += 1
    print(f"\n== {p} passed, {f} failed / {p + f} total ==")
    raise SystemExit(1 if f else 0)
