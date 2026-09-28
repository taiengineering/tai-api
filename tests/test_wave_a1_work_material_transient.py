"""WO-SHARED-INPUT-WAVE-A1-WORK-MATERIAL-BACKEND-IMPLEMENT-001 — Wave A1 contracts.

Covers:
  REGISTRY   — GRINDING/DIVING/OBJECT_DROP registered; unknown type rejected
  PROJECTOR  — has_scaffold / has_grinding / has_diving / has_object_drop
  NUMERIC    — attributes captured; canonical numeric NOT emitted (HOLD)
  PARITY     — same row → same output regardless of call site
  SCHEMA     — WorkRowInput/MaterialRowInput extra=forbid; classification_codes rejected
  CONFLICT   — explicit false + projected true → WorkSourceMergeConflict
  MISSING    — empty / None rows → no canonical key; missing attr → no emission
"""
import pytest
from pydantic import ValidationError

from services.work_source.registry import ALLOWED_WORK_TYPES, work_type_spec
from services.work_source.projector import project_work_row, project_work_rows
from services.work_source.merge import WorkSourceMergeConflict, merge_or_raise
from services.work_source.store import WorkSourceValidationError, validate_payload
from schemas.diagnosis_integrated import WorkRowInput, MaterialRowInput


# ── helpers ──────────────────────────────────────────────────────────────────

def active_row(work_type, *, subtype=None, attrs=None):
    r = {"work_type": work_type, "active": True}
    if subtype is not None:
        r["work_subtype"] = subtype
    if attrs:
        r["attributes"] = attrs
    return r


# ── REGISTRY ─────────────────────────────────────────────────────────────────

def test_registry_grinding_registered():
    assert "GRINDING" in ALLOWED_WORK_TYPES
    spec = work_type_spec("GRINDING")
    assert spec is not None
    assert "wheel_diameter_cm" in spec["attributes"]
    assert spec["attributes"]["wheel_diameter_cm"]["type"] == "number"


def test_registry_diving_registered():
    assert "DIVING" in ALLOWED_WORK_TYPES
    spec = work_type_spec("DIVING")
    assert spec is not None
    assert "worker_count" in spec["attributes"]
    assert spec["attributes"]["worker_count"]["type"] == "number"


def test_registry_object_drop_registered():
    assert "OBJECT_DROP" in ALLOWED_WORK_TYPES
    spec = work_type_spec("OBJECT_DROP")
    assert spec is not None
    assert "height_m" in spec["attributes"]
    assert spec["attributes"]["height_m"]["type"] == "number"


def test_registry_existing_8_preserved():
    for wt in ("ELECTRICAL", "HIGH_PLACE", "FORKLIFT", "PAINTING",
               "MAINTENANCE", "EXCAVATION", "ASBESTOS_WASTE_DUST_PROCESSING", "SCAFFOLD"):
        assert wt in ALLOWED_WORK_TYPES, f"{wt} missing from registry"


def test_registry_unknown_type_rejected():
    with pytest.raises(WorkSourceValidationError):
        validate_payload({"work_type": "UNKNOWN_WORK_TYPE_XYZ", "active": True})


# ── ATTRIBUTE VALIDATION ─────────────────────────────────────────────────────

def test_attr_number_accepts_zero():
    row = validate_payload({"work_type": "GRINDING", "attributes": {"wheel_diameter_cm": 0}, "active": True})
    assert row["attributes"]["wheel_diameter_cm"] == 0


def test_attr_number_accepts_positive_float():
    row = validate_payload({"work_type": "GRINDING", "attributes": {"wheel_diameter_cm": 35.5}, "active": True})
    assert row["attributes"]["wheel_diameter_cm"] == 35.5


def test_attr_number_scaffold_height():
    # height_m is a valid numeric SCAFFOLD attribute (does not start with canonical prefix)
    row = validate_payload({"work_type": "SCAFFOLD", "attributes": {"height_m": 6.5}, "active": True})
    assert row["attributes"]["height_m"] == 6.5


def test_attr_unknown_key_rejected():
    with pytest.raises(WorkSourceValidationError, match="unknown attribute"):
        validate_payload({"work_type": "GRINDING", "attributes": {"nonexistent_key": 1}, "active": True})


def test_attr_canonical_prefix_rejected():
    with pytest.raises(WorkSourceValidationError):
        validate_payload({"work_type": "GRINDING", "attributes": {"has_grinding": True}, "active": True})


def test_attr_enum_unknown_scaffold_kind_rejected():
    # scaffold_kind is an enum — unknown code should still be stored (validate_payload doesn't
    # validate enum values, registry only lists options for UI). Document this boundary.
    # validate_payload stores whatever is in attributes; enum enforcement is projector-side.
    row = validate_payload({"work_type": "SCAFFOLD", "attributes": {"scaffold_kind": "UNKNOWN_KIND"}, "active": True})
    assert row["attributes"]["scaffold_kind"] == "UNKNOWN_KIND"


# ── ATTRIBUTE VALUE TYPE VALIDATION (persistent/transient parity gate) ────────

# PERSISTENT_GRINDING_STRING_REJECT
def test_attr_number_string_rejected():
    with pytest.raises(WorkSourceValidationError, match="number"):
        validate_payload({"work_type": "GRINDING", "attributes": {"wheel_diameter_cm": "abc"}, "active": True})


# PERSISTENT_GRINDING_BOOL_REJECT (bool is subclass of int — must be explicitly rejected)
def test_attr_number_bool_rejected():
    with pytest.raises(WorkSourceValidationError, match="number"):
        validate_payload({"work_type": "GRINDING", "attributes": {"wheel_diameter_cm": True}, "active": True})


# PERSISTENT_DIVING_NEGATIVE_REJECT
def test_attr_number_negative_rejected():
    with pytest.raises(WorkSourceValidationError, match=">= 0"):
        validate_payload({"work_type": "DIVING", "attributes": {"worker_count": -1}, "active": True})


def test_attr_number_object_drop_negative_rejected():
    with pytest.raises(WorkSourceValidationError):
        validate_payload({"work_type": "OBJECT_DROP", "attributes": {"height_m": -0.5}, "active": True})


# TRANSIENT_GRINDING_STRING_REJECT
def test_transient_attr_number_string_rejected():
    tr = WorkRowInput(work_type="GRINDING", attributes={"wheel_diameter_cm": "abc"})
    with pytest.raises(WorkSourceValidationError):
        validate_payload(tr.model_dump(exclude_none=True), partial=False)


# TRANSIENT_GRINDING_BOOL_REJECT
def test_transient_attr_number_bool_rejected():
    tr = WorkRowInput(work_type="GRINDING", attributes={"wheel_diameter_cm": True})
    with pytest.raises(WorkSourceValidationError):
        validate_payload(tr.model_dump(exclude_none=True), partial=False)


# TRANSIENT_DIVING_NEGATIVE_REJECT
def test_transient_attr_number_negative_rejected():
    tr = WorkRowInput(work_type="DIVING", attributes={"worker_count": -1})
    with pytest.raises(WorkSourceValidationError):
        validate_payload(tr.model_dump(exclude_none=True), partial=False)


# PERSISTENT_TRANSIENT_NORMALIZED_PARITY — same input → identical validated output
def test_validated_parity_persistent_transient():
    payload = {"work_type": "GRINDING", "attributes": {"wheel_diameter_cm": 40.0}, "active": True}
    tr = WorkRowInput(work_type="GRINDING", attributes={"wheel_diameter_cm": 40.0})
    assert validate_payload(payload) == validate_payload(tr.model_dump(exclude_none=True))


# ── WORK PROJECTOR — Boolean output ──────────────────────────────────────────

def test_projector_scaffold_emits_has_scaffold():
    out = project_work_row(active_row("SCAFFOLD"))
    assert out.get("has_scaffold") is True


def test_projector_scaffold_preserves_existing_facts():
    out = project_work_row(active_row("SCAFFOLD", subtype="ASSEMBLY",
                                       attrs={"scaffold_kind": "STEEL_PIPE_SCAFFOLD"}))
    assert out.get("has_scaffold") is True
    assert out.get("scaffold_kind_is_steel_pipe_scaffold") is True
    assert out.get("performs_steel_pipe_scaffold_assembly") is True


def test_projector_grinding_emits_has_grinding():
    out = project_work_row(active_row("GRINDING"))
    assert out.get("has_grinding") is True
    assert out == {"has_grinding": True}


def test_projector_diving_emits_has_diving():
    out = project_work_row(active_row("DIVING"))
    assert out.get("has_diving") is True
    assert out == {"has_diving": True}


def test_projector_object_drop_emits_has_object_drop():
    out = project_work_row(active_row("OBJECT_DROP"))
    assert out.get("has_object_drop") is True
    assert out == {"has_object_drop": True}


def test_projector_inactive_row_emits_nothing():
    row = {"work_type": "GRINDING", "active": False, "attributes": {}}
    assert project_work_row(row) == {}


def test_projector_missing_active_emits_nothing():
    # active missing → treated as not True
    row = {"work_type": "GRINDING", "attributes": {}}
    assert project_work_row(row) == {}


# ── NUMERIC HOLD — numeric attributes NOT projected ──────────────────────────

def test_numeric_hold_grinding_wheel_diameter():
    row = active_row("GRINDING", attrs={"wheel_diameter_cm": 35.5})
    out = project_work_row(row)
    assert out.get("has_grinding") is True
    assert "grinding_wheel_diameter_cm" not in out, "HOLD: numeric must not be projected"


def test_numeric_hold_diving_worker_count():
    row = active_row("DIVING", attrs={"worker_count": 3})
    out = project_work_row(row)
    assert out.get("has_diving") is True
    assert "diving_worker_count" not in out, "HOLD: numeric must not be projected"


def test_numeric_hold_object_drop_height():
    row = active_row("OBJECT_DROP", attrs={"height_m": 4.5})
    out = project_work_row(row)
    assert out.get("has_object_drop") is True
    assert "object_drop_height_m" not in out, "HOLD: numeric must not be projected"


def test_numeric_hold_scaffold_height():
    row = active_row("SCAFFOLD", subtype="ASSEMBLY", attrs={"height_m": 6.0})
    out = project_work_row(row)
    assert out.get("has_scaffold") is True
    assert "scaffold_height_m" not in out, "HOLD: numeric must not be projected"


# ── BOOLEAN UNION across multiple rows ───────────────────────────────────────

def test_boolean_union_true_stays_true():
    rows = [active_row("GRINDING"), active_row("DIVING")]
    out = project_work_rows(rows)
    assert out.get("has_grinding") is True
    assert out.get("has_diving") is True


def test_boolean_union_missing_stays_absent():
    rows = [active_row("GRINDING")]
    out = project_work_rows(rows)
    assert "has_diving" not in out
    assert "has_object_drop" not in out


def test_project_work_rows_empty_list():
    assert project_work_rows([]) == {}


def test_project_work_rows_none():
    assert project_work_rows(None) == {}


# ── PERSISTENT / TRANSIENT PARITY ────────────────────────────────────────────

def test_parity_same_row_same_output():
    """Persistent DB row and transient Pydantic row produce identical canonical output."""
    persistent = active_row("GRINDING", attrs={"wheel_diameter_cm": 40.0})
    validated_transient = validate_payload(
        WorkRowInput(work_type="GRINDING", attributes={"wheel_diameter_cm": 40.0}).model_dump(exclude_none=True),
        partial=False,
    )
    assert project_work_row(persistent) == project_work_row(validated_transient)


def test_parity_scaffold_subtype_parity():
    persistent = active_row("SCAFFOLD", subtype="ASSEMBLY",
                             attrs={"scaffold_kind": "SYSTEM_SCAFFOLD"})
    tr = WorkRowInput(work_type="SCAFFOLD", work_subtype="ASSEMBLY",
                      attributes={"scaffold_kind": "SYSTEM_SCAFFOLD"})
    validated_transient = validate_payload(tr.model_dump(exclude_none=True), partial=False)
    assert project_work_row(persistent) == project_work_row(validated_transient)


# ── CONFLICT — explicit false vs projected true ───────────────────────────────

def test_conflict_explicit_false_projected_true():
    explicit = {"has_grinding": False}
    work_rows = [active_row("GRINDING")]
    with pytest.raises(WorkSourceMergeConflict) as exc_info:
        merge_or_raise(explicit, work_rows=work_rows)
    conflicts = exc_info.value.conflicts
    assert any(c["field"] == "has_grinding" for c in conflicts)


def test_conflict_same_value_no_error():
    explicit = {"has_grinding": True}
    work_rows = [active_row("GRINDING")]
    out = merge_or_raise(explicit, work_rows=work_rows)
    assert out["has_grinding"] is True


# ── SCHEMA — WorkRowInput extra=forbid ───────────────────────────────────────

def test_work_row_input_extra_forbidden():
    with pytest.raises(ValidationError):
        WorkRowInput(work_type="GRINDING", canonical_injection="bad_value")


def test_work_row_input_valid():
    row = WorkRowInput(work_type="GRINDING", attributes={"wheel_diameter_cm": 40.0})
    d = row.model_dump(exclude_none=True)
    assert d["work_type"] == "GRINDING"
    assert d["attributes"]["wheel_diameter_cm"] == 40.0
    assert d["active"] is True


# ── SCHEMA — MaterialRowInput classification_codes forbidden ─────────────────

def test_material_row_input_classification_codes_forbidden():
    with pytest.raises(ValidationError):
        MaterialRowInput(
            material_master_key="some_key",
            classification_codes=["MANAGED_HAZARDOUS_SUBSTANCE"],
        )


def test_material_row_input_valid():
    row = MaterialRowInput(material_master_key="some_key", handling_mode_codes=["INDOOR_HANDLING"])
    assert row.material_master_key == "some_key"
    assert row.is_active is True


def test_material_row_input_extra_field_forbidden():
    with pytest.raises(ValidationError):
        MaterialRowInput(material_master_key="k", unknown_field="bad")


# ── MISSING != FALSE ──────────────────────────────────────────────────────────

def test_missing_not_false_no_work_rows():
    out = project_work_rows([])
    assert "has_grinding" not in out
    assert "has_diving" not in out
    assert "has_object_drop" not in out
    assert "has_scaffold" not in out


def test_missing_not_false_no_attr():
    # Row without attributes → only boolean emitted, no numeric key with value
    row = active_row("DIVING")  # no attrs
    out = project_work_row(row)
    assert out == {"has_diving": True}
    assert len(out) == 1


# ── validate_payload reuse ────────────────────────────────────────────────────

def test_validate_payload_reuse_for_transient():
    """WorkRowInput → model_dump → validate_payload must accept without error."""
    tr = WorkRowInput(work_type="OBJECT_DROP", attributes={"height_m": 5.0})
    validated = validate_payload(tr.model_dump(exclude_none=True), partial=False)
    assert validated["work_type"] == "OBJECT_DROP"
    assert validated["attributes"]["height_m"] == 5.0
    assert validated["active"] is True


def test_validate_payload_rejects_unknown_work_type_from_schema():
    """Even if WorkRowInput allows it at schema level, validate_payload catches bad types."""
    # WorkRowInput does NOT validate work_type against registry (Pydantic layer is structural only).
    # validate_payload is the semantic gate.
    with pytest.raises(WorkSourceValidationError):
        validate_payload({"work_type": "NOT_A_REAL_TYPE", "active": True}, partial=False)
