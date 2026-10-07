"""AUTO-SRC-02B: Deterministic projection selector + equipment resolver tests.

F1-F12: selector rule coverage
M1-M8: equipment detail mapping (static map, 40 rows)
A1-A3: asset_id carry — migration SQL static text verification
R1-R4: fn_create_worker_inspection_record regression (SQL static text)
"""
import re
from pathlib import Path

import pytest

from services.document_engine.auto_source_projection_selector import (
    ProjectionDecision,
    select_projections,
)
from services.document_engine.equipment_projection_resolver import (
    _STATIC_MAP,
    resolve_equipment_detail,
)

# ── migration path ─────────────────────────────────────────────────────────────

_MIGRATION = Path("supabase/migrations/20261007182044_doc_auto_src_02b_projection_selector.sql")


@pytest.fixture(scope="module")
def migration_sql() -> str:
    return _MIGRATION.read_text()


# ═══════════════════════════════════════════════════════════════════════════════
# F1-F12: Selector rule tests
# ═══════════════════════════════════════════════════════════════════════════════

def _decide(
    bindings=None,
    asset_id=None,
    equipment_type_code=None,
    is_completed=True,
):
    return select_projections(
        explicit_bindings=bindings or [],
        asset_id=asset_id,
        equipment_type_code=equipment_type_code,
        is_completed=is_completed,
    )


# F1: RULE 1 single explicit binding returned
def test_F1_rule1_single_explicit_binding():
    result = _decide(bindings=[{"projection_type": "CHK", "projection_detail": None}])
    assert len(result) == 1
    assert result[0].projection_type == "CHK"
    assert result[0].rule == "RULE_1_EXPLICIT"


# F2: RULE 1 multiple bindings (CHK + PPE on same inspection_set)
def test_F2_rule1_multi_binding():
    result = _decide(bindings=[
        {"projection_type": "CHK", "projection_detail": None},
        {"projection_type": "PPE", "projection_detail": None},
    ])
    assert len(result) == 2
    types = {r.projection_type for r in result}
    assert types == {"CHK", "PPE"}
    for r in result:
        assert r.rule == "RULE_1_EXPLICIT"


# F3: RULE 1 with detail field
def test_F3_rule1_with_detail():
    result = _decide(bindings=[{"projection_type": "EQUIP", "projection_detail": "CRANE"}])
    assert result[0].projection_detail == "CRANE"


# F4: RULE 1 wins over RULE 2 (explicit binding present, asset also present)
def test_F4_rule1_beats_rule2():
    result = _decide(
        bindings=[{"projection_type": "CHK", "projection_detail": None}],
        asset_id="some-uuid",
        equipment_type_code="021",
    )
    assert len(result) == 1
    assert result[0].rule == "RULE_1_EXPLICIT"


# F5: RULE 2 resolved equipment code → EQUIP projection
def test_F5_rule2_resolved_equip():
    result = _decide(asset_id="some-uuid", equipment_type_code="021")
    assert len(result) == 1
    assert result[0].projection_type == "EQUIP"
    assert result[0].projection_detail == "CRANE"
    assert result[0].rule == "RULE_2_ASSET_EQUIP"


# F6: RULE 2 alias code (CRANE → 021 via canonicalizer)
def test_F6_rule2_alias_crane():
    result = _decide(asset_id="some-uuid", equipment_type_code="CRANE")
    assert len(result) == 1
    assert result[0].projection_detail == "CRANE"
    assert result[0].rule == "RULE_2_ASSET_EQUIP"


# F7: RULE 2 UNRESOLVED code → fail-closed (empty list)
def test_F7_rule2_unresolved_code_fail_closed():
    result = _decide(asset_id="some-uuid", equipment_type_code="040")
    assert result == []


# F8: RULE 2 unknown code → fail-closed
def test_F8_rule2_unknown_code_fail_closed():
    result = _decide(asset_id="some-uuid", equipment_type_code="UNKNOWN_CODE")
    assert result == []


# F9: RULE 2 None equipment_type_code with asset_id → fail-closed
def test_F9_rule2_none_equipment_code_with_asset():
    result = _decide(asset_id="some-uuid", equipment_type_code=None)
    assert result == []


# F10: RULE 3 fallback — no bindings, no asset, completed
def test_F10_rule3_insp_fallback_completed():
    result = _decide()
    assert len(result) == 1
    assert result[0].projection_type == "INSP"
    assert result[0].projection_detail is None
    assert result[0].rule == "RULE_3_INSP_FALLBACK"


# F11: RULE 3 not triggered if not completed
def test_F11_rule3_not_completed_returns_empty():
    result = _decide(is_completed=False)
    assert result == []


# F12: RULE 2 lowercase code rejected (not in canonicalizer aliases; no normalize path)
def test_F12_rule2_lowercase_code_fail_closed():
    result = _decide(asset_id="some-uuid", equipment_type_code="crane")
    assert result == []


# ═══════════════════════════════════════════════════════════════════════════════
# M1-M8: Equipment detail mapping
# ═══════════════════════════════════════════════════════════════════════════════

# M1: static map has exactly 40 entries (codes 001-040)
def test_M1_static_map_40_rows():
    assert len(_STATIC_MAP) == 40


# M2: 35 RESOLVED (non-None) + 5 UNRESOLVED (None)
def test_M2_resolved_unresolved_counts():
    resolved = [v for v in _STATIC_MAP.values() if v is not None]
    unresolved = [v for v in _STATIC_MAP.values() if v is None]
    assert len(resolved) == 35
    assert len(unresolved) == 5


# M3: UNRESOLVED codes are exactly 015/035/036/037/040
def test_M3_unresolved_codes_exact():
    unresolved_keys = {k for k, v in _STATIC_MAP.items() if v is None}
    assert unresolved_keys == {"015", "035", "036", "037", "040"}


# M4: Spot-check ELEC group (001-010 all map to ELEC)
def test_M4_elec_group():
    for code in ("001", "002", "003", "004", "005", "006", "007", "008", "009", "010"):
        assert _STATIC_MAP[code] == "ELEC", f"{code} should be ELEC"


# M5: Spot-check MACHINE group includes 023/024/038
def test_M5_machine_group_press_conveyor_pressure():
    for code in ("023", "024", "038"):
        assert _STATIC_MAP[code] == "MACHINE", f"{code} should be MACHINE"


# M6: resolve_equipment_detail normalizes alias before lookup
def test_M6_resolve_alias_pressure_vessel():
    assert resolve_equipment_detail("PRESSURE_VESSEL") == "MACHINE"


# M7: resolve_equipment_detail returns None for UNRESOLVED code
def test_M7_resolve_unresolved_returns_none():
    assert resolve_equipment_detail("040") is None


# M8: resolve_equipment_detail None input returns None
def test_M8_resolve_none_input():
    assert resolve_equipment_detail(None) is None


# ═══════════════════════════════════════════════════════════════════════════════
# A1-A3: asset_id carry — migration SQL static text
# ═══════════════════════════════════════════════════════════════════════════════

# A1: migration SQL contains asset_id in safety_inspections INSERT column list
def test_A1_migration_insert_has_asset_id_column(migration_sql):
    assert "asset_id" in migration_sql


# A2: migration uses v_sched.asset_id as the value source
def test_A2_migration_uses_vsched_asset_id(migration_sql):
    assert "v_sched.asset_id" in migration_sql


# A3: asset_id appears in the INSERT INTO safety_inspections column list
def test_A3_migration_insert_column_list_contains_asset_id(migration_sql):
    pattern = r"INSERT INTO public\.safety_inspections\s*\([^)]*asset_id[^)]*\)"
    assert re.search(pattern, migration_sql, re.DOTALL), (
        "safety_inspections INSERT must list asset_id in column list"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# R1-R4: fn_create_worker_inspection_record regression (SQL static text)
# ═══════════════════════════════════════════════════════════════════════════════

# R1: function is still SECURITY DEFINER
def test_R1_fn_still_security_definer(migration_sql):
    assert "SECURITY DEFINER" in migration_sql


# R2: function signature unchanged (9 parameters present)
def test_R2_fn_signature_unchanged(migration_sql):
    assert "p_submission_id" in migration_sql
    assert "p_request_hash" in migration_sql
    assert "p_schedule_id" in migration_sql
    assert "p_factory_id" in migration_sql
    assert "p_inspector_id" in migration_sql
    assert "p_submitted_at" in migration_sql
    assert "p_results" in migration_sql
    assert "p_request_payload" in migration_sql


# R3: idempotency replay guard still present (submission_id reuse check)
def test_R3_replay_guard_present(migration_sql):
    assert "SUBMISSION_ID_REUSE_CONFLICT" in migration_sql


# R4: WORK_SCHEDULE_NOT_EXECUTABLE guard still present
def test_R4_executability_guard_present(migration_sql):
    assert "WORK_SCHEDULE_NOT_EXECUTABLE" in migration_sql
